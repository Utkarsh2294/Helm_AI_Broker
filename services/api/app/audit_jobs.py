import logging
from sqlalchemy import select
from app.db.models import Case, Activity, utcnow
from app.db.platform import AuditAnchor
from app.db.store import SessionLocal, verify_chain
from app.agents.review import canonical_hash


def verify_all():
    with SessionLocal() as db:
        day = utcnow().date().isoformat()
        existing = db.scalar(select(AuditAnchor).where(AuditAnchor.day == day))
        roots, failures = {}, []
        for case in db.scalars(select(Case)):
            events = db.scalars(
                select(Activity).where(Activity.case_id == case.id).order_by(Activity.seq)
            ).all()
            if not verify_chain(events):
                failures.append(case.id)
            roots[case.id] = events[-1].hash if events else None
        body = {"day": day, "last_hashes": roots, "failures": failures, "checked": len(roots)}
        body["root_hash"] = canonical_hash(body)
        if not existing:
            db.add(AuditAnchor(day=day, body=body))
            db.commit()
        if failures:
            logging.getLogger("helm.audit").critical(
                "P1_AUDIT_CHAIN_FAILURE", extra={"failed_case_ids": failures}
            )
        return body


async def nightly_verify(ctx):
    import asyncio

    return await asyncio.to_thread(verify_all)
