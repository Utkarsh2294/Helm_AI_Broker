import logging
import json
import os
from datetime import date
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.config import settings
from app.db.models import Case, Activity, utcnow
from app.db.platform import AuditAnchor
from app.db.store import SessionLocal, verify_chain
from app.agents.review import canonical_hash


def verify_all():
    with SessionLocal() as db:
        day = utcnow().date().isoformat()
        existing = db.scalar(select(AuditAnchor).where(AuditAnchor.day == day))
        roots, failures, hashes = {}, [], {}
        for case in db.scalars(select(Case)):
            events = db.scalars(
                select(Activity).where(Activity.case_id == case.id).order_by(Activity.seq)
            ).all()
            if not verify_chain(events):
                failures.append(case.id)
            roots[case.id] = events[-1].hash if events else None
            hashes[case.id] = {event.hash for event in events}
        body = {"day": day, "last_hashes": roots, "failures": failures, "checked": len(roots)}
        body["root_hash"] = canonical_hash(body)
        if not existing:
            db.add(AuditAnchor(day=day, body=body))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
            existing = db.scalar(select(AuditAnchor).where(AuditAnchor.day == day))
        directory = Path(settings().audit_anchor_directory).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        anchor_failures = []
        for anchor in db.scalars(select(AuditAnchor)):
            try:
                if date.fromisoformat(anchor.day).isoformat() != anchor.day:
                    raise ValueError("Non-canonical date")
            except ValueError:
                anchor_failures.append({"code": "invalid_anchor_day"})
                continue
            if any(
                value and value not in hashes.get(case_id, set())
                for case_id, value in anchor.body["last_hashes"].items()
            ):
                anchor_failures.append({"day": anchor.day, "code": "anchored_history_missing"})
            target = directory / (anchor.day + ".json")
            encoded = json.dumps(anchor.body, sort_keys=True, separators=(",", ":")).encode()
            try:
                # Local demo of object-lock behaviour; an external WORM store is a live deployment gate.
                with os.fdopen(os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "wb") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
            except FileExistsError:
                if target.read_bytes() != encoded:
                    anchor_failures.append({"day": anchor.day, "code": "anchor_copy_mismatch"})
        if failures or anchor_failures:
            alert = {
                "severity": "P1",
                "type": "AUDIT_INTEGRITY_FAILURE",
                "created_at": utcnow().isoformat(),
                "failed_case_ids": failures,
                "anchor_failures": anchor_failures,
                "customer_text_included": False,
            }
            alert_path = directory / ("alert-" + uuid4().hex + ".json")
            with alert_path.open("xb") as stream:
                stream.write(json.dumps(alert, sort_keys=True).encode())
        if failures or anchor_failures:
            logging.getLogger("helm.audit").critical(
                "P1_AUDIT_CHAIN_FAILURE", extra={"failed_case_ids": failures}
            )
        return {
            **body,
            "anchor_failures": anchor_failures,
            "alert_raised": bool(failures or anchor_failures),
            "anchored_root_hash": existing.body["root_hash"],
            "storage": "local_demo_write_once",
            "external_object_lock_verified": False,
        }


async def nightly_verify(ctx):
    import asyncio

    return await asyncio.to_thread(verify_all)
