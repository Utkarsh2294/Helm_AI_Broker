"""Supporting research is versioned with the draft; signed packs never change."""

from sqlalchemy import select
from app.db.models import Snapshot
from app.db.copilot import EvidenceVisibility
from app.db.store import latest, save_snapshot, audit


def research_rows(db, case_id):
    hidden = select(EvidenceVisibility.evidence_id).where(EvidenceVisibility.hidden_at.is_not(None))
    return db.scalars(
        select(Snapshot)
        .where(Snapshot.case_id == case_id, Snapshot.kind == "assistant_evidence", Snapshot.id.not_in(hidden))
        .order_by(Snapshot.version.desc())
    ).all()


def pack_research(db, case_id):
    return [
        {
            "evidence_id": row.id,
            "snapshot_hash": row.body_hash,
            "question": row.body["question"],
            "answer": row.body["answer"],
            "sources": row.body.get("sources", []),
            "timestamp": row.body["timestamp"],
            "broker_id": row.body["broker_id"],
            "model_version": row.body["model_version"],
            "confidence": row.body["confidence"],
            "protected": bool(row.body.get("protected")),
        }
        for row in research_rows(db, case_id)
    ]


def refresh_draft(db, case, user):
    if case.state != "AWAIT_APPROVAL":
        return
    saved = latest(db, case.id, "pack")
    if not saved:
        return
    from app.agents.review import canonical_hash

    body = {key: value for key, value in saved.body.items() if key != "pack_hash"}
    research = pack_research(db, case.id)
    if body.get("supporting_research", []) == research:
        return
    body["supporting_research"] = research
    body.update(
        overall_suitability_confirmed=False,
        suitability_confirmed_plans=[],
        dnr_sections_confirmed=[],
        unmet_needs_addressed=[],
    )
    # Confirmation records/challenges are hash-bound and must be reviewed again.
    body["pack_hash"] = canonical_hash(body)
    save_snapshot(db, case.id, "pack", body)
    case.version += 1
    audit(
        db,
        case.id,
        "supporting_research_updated",
        f"broker:{user.id}",
        {
            "previous_pack_hash": saved.body["pack_hash"],
            "pack_hash": body["pack_hash"],
            "evidence_ids": [row["evidence_id"] for row in research],
        },
    )
