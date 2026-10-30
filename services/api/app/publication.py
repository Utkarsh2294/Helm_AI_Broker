"""Process committed G2 approvals. External delivery cannot precede durable approval."""

import asyncio
from datetime import datetime, timedelta
from app.core_client.client import CoreAPIClient
from app.db.models import Approval, Publication, utcnow
from app.db.store import audit, latest, save_snapshot
from app.schemas import State


def process_publication(db, case, job):
    from app.service import transition

    approval = db.get(Approval, job.body["approval_id"])
    pack = latest(db, case.id, "pack").body
    if case.state != State.AWAIT_APPROVAL or pack["pack_hash"] != job.body["pack_hash"]:
        job.status = "cancelled"
        return
    if utcnow() - datetime.fromisoformat(approval.step_up_at) > timedelta(minutes=5):
        job.status = "cancelled"
        case.previous_state = State.AWAIT_APPROVAL
        transition(
            db,
            case,
            [case.state],
            State.PAUSED_NEEDS_HUMAN,
            "publication_approval_expired",
            "system",
            {"reason": "H8"},
        )
        return
    try:
        delivered = asyncio.run(CoreAPIClient().publish(case.id, approval.id, pack))
    except Exception:
        attempts = job.body.get("attempts", 0) + 1
        job.body = {**job.body, "attempts": attempts}
        job.due_at = (utcnow() + timedelta(seconds=2**attempts)).isoformat()
        audit(db, case.id, "publication_retry", "system", {"attempt": attempts})
        if attempts >= 3:
            case.previous_state = State.AWAIT_APPROVAL
            transition(
                db,
                case,
                [case.state],
                State.PAUSED_NEEDS_HUMAN,
                "publication_failed",
                "system",
                {"reason": "H8"},
            )
        return
    save_snapshot(db, case.id, "publication", delivered)
    db.add(
        Publication(
            case_id=case.id, approval_id=approval.id, pack_hash=pack["pack_hash"], status=delivered["status"]
        )
    )
    transition(
        db,
        case,
        [State.AWAIT_APPROVAL],
        State.PUBLISHED,
        "recommendation_delivered",
        f"broker:{approval.user_id}",
    )
    job.status = "completed"


def process_revocation(db, case, job):
    try:
        asyncio.run(
            CoreAPIClient().request(
                "POST",
                f"/v1/recommendations/{job.body['recommendation_id']}/revoke",
                {},
                key=f"revoke:{case.id}:{job.id}",
            )
        )
    except Exception:
        attempts = job.body.get("attempts", 0) + 1
        job.body = {**job.body, "attempts": attempts}
        job.due_at = (utcnow() + timedelta(seconds=2**attempts)).isoformat()
        job.status = "needs_human" if attempts >= 3 else "pending"
        audit(
            db,
            case.id,
            "recommendation_revocation_failed",
            "system",
            {"attempt": attempts, "requires_human": attempts >= 3},
        )
        return
    save_snapshot(
        db,
        case.id,
        "revocation",
        {"recommendation_id": job.body["recommendation_id"], "at": utcnow().isoformat()},
    )
    audit(db, case.id, "recommendation_revoked", "system")
    job.status = "completed"
