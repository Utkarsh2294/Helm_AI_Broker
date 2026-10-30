import asyncio
import json
from datetime import timedelta
import httpx
import pytest
from sqlalchemy import select
from app import main
from app.agents.quotation import PARTNERS, RFQ, build_rfq, simulate_responses
from app.agents.intake import research_request
from app.clock import DemoClock, LiveClock, get_clock
from app.config import settings
from app.db.models import Approval, Job, utcnow
from app.db.platform import CasePlan, Partner
from app.partners import PartnerGateway
from app.schemas import QuoteRequest, State


def rfq():
    return build_rfq(
        research_request(
            QuoteRequest(
                id="parallel-test",
                name="Fictional Private Name",
                needs={"coverage": {"outpatient": {"level": 2}}},
            )
        ),
        signed_off=True,
    )


def quoted(request):
    body = json.loads(request.content)
    plans, _ = simulate_responses(RFQ.model_validate(body["rfq"]))
    return {
        "partner_id": body["partner_id"],
        "state": "quoted",
        "quotes": [p.model_dump(mode="json") for p in plans if p.insurerId == body["partner_id"]],
    }


@pytest.mark.anyio
async def test_all_five_http_requests_overlap_and_keep_identity_outside_the_payload(monkeypatch):
    monkeypatch.setattr(settings(), "partner_mode", "http_simulator")
    active, maximum, calls = 0, 0, []
    barrier = asyncio.Event()

    async def respond(request):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        calls.append(request)
        if len(calls) == 5:
            barrier.set()
        await barrier.wait()
        await asyncio.sleep(0)
        active -= 1
        return httpx.Response(200, json=quoted(request))

    result = await PartnerGateway(httpx.MockTransport(respond)).collect(rfq(), "happy")
    assert maximum == 5
    assert len(result["quotes"]) == 30
    assert {p["id"] for p in result["partners"]} == {p["id"] for p in PARTNERS}
    assert all("Fictional Private Name" not in r.content.decode() for r in calls)
    assert all(r.headers["Idempotency-Key"].endswith(json.loads(r.content)["partner_id"]) for r in calls)


@pytest.mark.anyio
async def test_partial_results_reject_invalid_quotes_and_keep_timeout_and_referral_metadata(monkeypatch):
    monkeypatch.setattr(settings(), "partner_mode", "http_simulator")

    async def respond(request):
        body = json.loads(request.content)
        result = quoted(request)
        if body["partner_id"] == "northgate":
            result["quotes"][0]["annualPremiumPence"] = -1
        if body["partner_id"] == "cedar":
            result["state"] = "referral"
            result["quotes"] = []
        if body["partner_id"] == "vale":
            await asyncio.sleep(1)
        if body["partner_id"] == "haven":
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=result)

    result = await PartnerGateway(httpx.MockTransport(respond), DemoClock(multiplier=216000)).collect(
        rfq(), "happy"
    )
    assert len(result["quotes"]) == 6
    assert {p["insurerId"] for p in result["quotes"]} == {"alder"}
    states = {p["id"]: p["state"] for p in result["partners"]}
    assert states == {
        "northgate": "invalid",
        "cedar": "referred",
        "vale": "timed_out",
        "haven": "invalid",
        "alder": "quoted",
    }


@pytest.mark.anyio
async def test_transient_failure_retries_once_with_the_same_idempotency_key(monkeypatch):
    monkeypatch.setattr(settings(), "partner_mode", "http_simulator")
    calls = []

    async def respond(request):
        calls.append(request.headers["Idempotency-Key"])
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json=quoted(request))

    request = rfq()
    request.partners = ["northgate"]
    result = await PartnerGateway(httpx.MockTransport(respond)).collect(request, "happy")
    assert len(result["quotes"]) == 6
    assert len(calls) == 2 and calls[0] == calls[1]


def released_case(client, release=True):
    auth = client.post(
        "/api/v1/auth/password", json={"email": "broker@helm.demo", "password": "HelmDemo!2026"}
    ).json()
    headers = {"X-CSRF-Token": auth["csrf"]}
    item = client.post(
        "/api/v1/demo/requests",
        headers=headers,
        json={
            "id": "a2-runtime",
            "name": "Fictional runtime case",
            "needs": {"coverage": {"outpatient": {"level": 2}}},
        },
    ).json()
    url = "/api/v1/cases/" + item["id"]
    assert client.post(url + "/sign-off", headers=headers, json={"dnr_acknowledged": True}).status_code == 200
    if release:
        assert client.post(url + "/release", headers=headers, json={}).status_code == 200
    return item["id"], headers


def test_revoked_partner_blocks_release_without_creating_g1(client):
    case_id, headers = released_case(client, False)
    with main.SessionLocal() as db:
        db.get(Partner, "northgate").toba_status = "expired"
        db.commit()
    result = client.post("/api/v1/cases/" + case_id + "/release", headers=headers, json={})
    assert result.status_code == 200 and result.json()["state"] == State.PAUSED_NEEDS_HUMAN
    with main.SessionLocal() as db:
        assert not db.scalar(select(Approval).where(Approval.case_id == case_id, Approval.gate == "G1"))


def test_valid_quotes_are_persisted_as_immutable_revisions_and_late_timeout_is_a_noop(client):
    case_id, _ = released_case(client)
    with main.SessionLocal() as db:
        collect = db.scalar(select(Job).where(Job.case_id == case_id, Job.kind == "collect_quotes"))
        collect.due_at = (utcnow() - timedelta(seconds=1)).isoformat()
        db.commit()
    result = client.get("/api/v1/cases/" + case_id).json()
    assert result["state"] == State.BROKER_REVIEW
    with main.SessionLocal() as db:
        plans = db.scalars(select(CasePlan).where(CasePlan.case_id == case_id)).all()
        assert len(plans) == 30
        plans[0].body = {}
        with pytest.raises(ValueError, match="append-only"):
            db.flush()
        db.rollback()
        timeout = db.scalar(select(Job).where(Job.case_id == case_id, Job.kind == "rfq_timeout"))
        timeout.due_at = (utcnow() - timedelta(seconds=1)).isoformat()
        db.commit()
    assert client.get("/api/v1/cases/" + case_id).json()["state"] == State.BROKER_REVIEW


def test_demo_and_live_deadlines_use_the_shared_clock_without_scaling_security_time(monkeypatch):
    monkeypatch.setattr(settings(), "demo_clock_multiplier", 3600)
    monkeypatch.setattr(settings(), "clock_mode", "demo")
    assert get_clock().wall_delay(timedelta(hours=6)) == timedelta(seconds=6)
    assert rfq().clock_multiplier == 3600
    monkeypatch.setattr(settings(), "clock_mode", "live")
    assert isinstance(get_clock(), LiveClock)
    assert get_clock().wall_delay(timedelta(hours=6)) == timedelta(hours=6)
    assert rfq().clock_multiplier == 1


def test_fewer_than_three_valid_quotes_pause_before_ranking(client, monkeypatch):
    case_id, _ = released_case(client)

    async def empty(self, request, scenario, partners=None):
        return {
            "quotes": [],
            "raw_quotes": [],
            "partners": [{"id": p["id"], "state": "timed_out"} for p in PARTNERS],
        }

    monkeypatch.setattr(PartnerGateway, "collect", empty)
    with main.SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.case_id == case_id, Job.kind == "collect_quotes"))
        job.due_at = (utcnow() - timedelta(seconds=1)).isoformat()
        db.commit()
    result = client.get("/api/v1/cases/" + case_id).json()
    assert result["state"] == State.PAUSED_NEEDS_HUMAN
    assert result["ranking"] is None
    assert result["events"][-1]["payload"]["reason"] == "insufficient_quotes"


def test_g1_pause_records_a_reason_and_sends_nothing_until_explicit_release(client):
    case_id, headers = released_case(client, False)
    url = "/api/v1/cases/" + case_id
    assert client.post(url + "/pause", headers=headers, json={}).status_code == 422
    paused = client.post(
        url + "/pause",
        headers=headers,
        json={"reason": "Verify the requested hospital network before release."},
    )
    assert paused.status_code == 200 and paused.json()["state"] == State.PAUSED_NEEDS_HUMAN
    with main.SessionLocal() as db:
        assert not db.scalar(select(Job).where(Job.case_id == case_id, Job.kind == "collect_quotes"))
        assert not db.scalar(select(Approval).where(Approval.case_id == case_id, Approval.gate == "G1"))
    resumed = client.post(url + "/resume", headers=headers, json={})
    assert resumed.status_code == 200 and resumed.json()["state"] == State.AWAIT_BROKER_RELEASE
    assert client.post(url + "/release", headers=headers, json={}).status_code == 200


@pytest.mark.parametrize("failure,code", [("conflict", "H4"), ("transport", "H8")])
def test_partner_failures_become_durable_metadata_only_halts(client, monkeypatch, failure, code):
    from app.schemas import DomainError

    case_id, _ = released_case(client)

    async def failed(self, request, scenario, partners=None):
        if failure == "conflict":
            raise DomainError("Contradictory partner revisions: PRIVATE_CANARY")
        raise httpx.ConnectError("PRIVATE_CANARY")

    monkeypatch.setattr(PartnerGateway, "collect", failed)
    with main.SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.case_id == case_id, Job.kind == "collect_quotes"))
        job.due_at = (utcnow() - timedelta(seconds=1)).isoformat()
        db.commit()
    response = client.get("/api/v1/cases/" + case_id)
    assert response.status_code == 200
    assert response.json()["state"] == State.PAUSED_NEEDS_HUMAN
    assert response.json()["events"][-1]["payload"]["code"] == code
    assert "PRIVATE_CANARY" not in response.text
