import fitz
from sqlalchemy import select
from app import main
from app.config import settings
from app.core_client.client import encode_event, sign
from app.db.models import Case, User, Approval, Job, utcnow
from app.db.store import save_snapshot, latest
from app.schemas import State, QuoteRequest
from app.agents.intake import research_request
from app.agents.review import canonical_hash


def published_fixture():
    with main.SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "broker@helm.demo"))
        case = Case(
            core_request_id="consumer-" + str(utcnow().timestamp()),
            profile={"name": "Fictional consumer"},
            state=State.PUBLISHED,
        )
        db.add(case)
        db.flush()
        dnr = research_request(
            QuoteRequest(
                id=case.core_request_id,
                name="Fictional",
                medical_items=["PRIVATE_MEDICAL_CANARY"],
                needs={"coverage": {"outpatient": {"level": 2}}},
            )
        ).model_dump(mode="json")
        save_snapshot(db, case.id, "dnr", dnr)
        pack = {
            "selected": ["p1", "p2", "p3"],
            "plans": [
                {"plan": {"id": key, "annualPremiumPence": 112000, "basePremiumPence": 100000}}
                for key in ("p1", "p2", "p3")
            ],
            "suitability_final": "Fictional broker explanation recorded against the stated needs.",
            "broker_ratings": [
                {"plan_id": "p1", "stars": 4, "decision": "YES", "reason_text": "PRIVATE_RATING_CANARY"}
            ],
        }
        pack["pack_hash"] = canonical_hash(pack)
        save_snapshot(db, case.id, "pack", pack)
        db.add(
            Approval(
                case_id=case.id,
                gate="G2",
                user_id=user.id,
                payload_hash=pack["pack_hash"],
                step_up_at=utcnow().isoformat(),
            )
        )
        db.commit()
        return case.id, pack["pack_hash"]


def send(client, case_id, pack_hash, event_id, kind, **fields):
    raw = encode_event({"id": event_id, "type": kind, "case_id": case_id, "pack_hash": pack_hash, **fields})
    timestamp = str(int(utcnow().timestamp()))
    return client.post(
        "/api/v1/webhooks/core",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Helm-Timestamp": timestamp,
            "X-Helm-Signature": sign(raw, timestamp, settings().core_webhook_secret),
        },
    )


def test_signed_acceptance_then_binding_closes_and_persists_a_redacted_closure_pdf(client):
    case_id, hash = published_fixture()
    assert (
        send(
            client,
            case_id,
            hash,
            "wrong-plan",
            "consumer.responded",
            decision="ACCEPTED",
            selected_plan_id="outside-pack",
        ).status_code
        == 422
    )
    assert (
        send(
            client,
            case_id,
            "0" * 64,
            "old-pack",
            "consumer.responded",
            decision="ACCEPTED",
            selected_plan_id="p1",
        ).status_code
        == 409
    )
    assert (
        send(
            client,
            case_id,
            hash,
            "accepted",
            "consumer.responded",
            decision="ACCEPTED",
            selected_plan_id="p1",
        ).status_code
        == 200
    )
    assert send(
        client, case_id, hash, "accepted", "consumer.responded", decision="ACCEPTED", selected_plan_id="p1"
    ).json()["duplicate"]
    assert (
        send(client, case_id, hash, "accepted", "consumer.responded", decision="DECLINED").status_code == 409
    )
    assert (
        send(
            client,
            case_id,
            hash,
            "bound",
            "consumer.bound",
            plan_id="p1",
            policy_number="FICTIONAL-BOUND-001",
            effective_date="2026-11-01",
        ).status_code
        == 200
    )
    with main.SessionLocal() as db:
        assert db.get(Case, case_id).state == State.CLOSED
        assert latest(db, case_id, "policy_bound").body["final_premium"]["ipt_pence"] == 12000
        assert db.scalar(select(Job).where(Job.case_id == case_id, Job.kind == "retention_review")).body[
            "requires_policy_approval"
        ]
    login = client.post(
        "/api/v1/auth/password", json={"email": "broker@helm.demo", "password": "HelmDemo!2026"}
    )
    assert login.status_code == 200
    pdf = client.get("/api/v1/cases/" + case_id + "/closure.pdf")
    assert pdf.status_code == 200
    doc = fitz.open(stream=pdf.content, filetype="pdf")
    text = "".join(page.get_text() for page in doc)
    assert "PRIVATE_MEDICAL_CANARY" not in text and "PRIVATE_RATING_CANARY" not in text
    assert (
        "FICTIONAL" not in str(client.get("/api/v1/cases/" + case_id + "/events").json()).upper()
        or b"policy_number" not in client.get("/api/v1/cases/" + case_id + "/events").content
    )
    assert "proposed six-year" in text
    doc.close()


def test_decline_closes_but_partial_and_expiry_keep_case_available_for_broker_review(client):
    case_id, hash = published_fixture()
    assert (
        send(
            client, case_id, hash, "opened", "consumer.magic_link_opened", opened_at=utcnow().isoformat()
        ).status_code
        == 200
    )
    assert send(client, case_id, hash, "expired", "consumer.magic_link_expired").status_code == 200
    assert (
        send(
            client,
            case_id,
            hash,
            "partial",
            "consumer.responded",
            decision="PARTIALLY",
            partial_details="Please clarify the preferred hospital choice.",
        ).status_code
        == 200
    )
    with main.SessionLocal() as db:
        assert db.get(Case, case_id).state == State.PUBLISHED
    assert (
        send(
            client,
            case_id,
            hash,
            "premature-bound",
            "consumer.bound",
            plan_id="p1",
            policy_number="FICTIONAL",
            effective_date="2026-11-01",
        ).status_code
        == 422
    )
    assert (
        send(
            client,
            case_id,
            hash,
            "declined",
            "consumer.responded",
            decision="DECLINED",
            decline_reason="Fictional consumer chose not to proceed.",
        ).status_code
        == 200
    )
    with main.SessionLocal() as db:
        assert db.get(Case, case_id).state == State.CLOSED
        assert latest(db, case_id, "closure_pdf")
