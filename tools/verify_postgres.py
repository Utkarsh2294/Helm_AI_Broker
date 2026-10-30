"""Exercise clean migrations and SQL evidence guards in a disposable local database."""

import os
import re
import subprocess
import sys
from pathlib import Path

from uuid import uuid4
from sqlalchemy import create_engine, text, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import DatabaseError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/api"))
from app.db.models import Case, User  # noqa: E402
from app.db.store import audit, save_snapshot  # noqa: E402
from app.db.platform import Partner, CasePlan, BrokerRating  # noqa: E402
from app.schemas import Plan  # noqa: E402
from app.agents.review import canonical_hash  # noqa: E402


def main():
    admin = create_engine(
        "postgresql+psycopg://helm:helm_local_demo_only@127.0.0.1:55439/postgres",
        isolation_level="AUTOCOMMIT",
    )
    name = "helm_migration_qa_" + uuid4().hex[:12]
    assert re.fullmatch(r"helm_migration_qa_[a-f0-9]{12}", name)
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    target = create_engine(f"postgresql+psycopg://helm:helm_local_demo_only@127.0.0.1:55439/{name}")
    try:
        environment = {
            **os.environ,
            "HELM_DATABASE_URL": str(target.url.render_as_string(hide_password=False)),
        }
        for command in (("upgrade", "head"), ("downgrade", "base"), ("upgrade", "head")):
            result = subprocess.run(
                [sys.executable, "-m", "alembic", *command], env=environment, capture_output=True, text=True
            )
            if result.returncode:
                raise RuntimeError(result.stderr)
        with Session(target) as db:
            case = Case(core_request_id="migration-qa", profile={"name": "Fictional"})
            db.add(case)
            db.flush()
            audit(db, case.id, "qa_created", "test")
            db.add(Partner(id="migration-partner", name="Fictional migration partner"))
            db.flush()
            plan = Plan(
                id="migration-quote",
                insurerId="migration-partner",
                name="Fictional migration quote",
                basePremiumPence=100000,
                annualPremiumPence=112000,
                coverage={},
            ).model_dump(mode="json")
            snapshot = save_snapshot(db, case.id, "quotes", {"quotes": [plan]})
            db.add(
                CasePlan(
                    case_id=case.id,
                    partner_id="migration-partner",
                    snapshot_id=snapshot.id,
                    plan_id=plan["id"],
                    revision=1,
                    body=plan,
                    body_hash=canonical_hash(plan),
                )
            )
            db.commit()
            quote = db.scalar(select(CasePlan).where(CasePlan.case_id == case.id))
            broker = User(
                email="migration-reviewer@example.test",
                name="Fictional migration reviewer",
                password_hash="not-a-login-credential",
            )
            db.add(broker)
            db.flush()
            ranking = save_snapshot(db, case.id, "ranking", {"id": "migration-ranking"})
            db.add(
                BrokerRating(
                    case_id=case.id,
                    ranking_id="migration-ranking",
                    ranking_snapshot_id=ranking.id,
                    plan_id=quote.plan_id,
                    plan_record_id=quote.id,
                    broker_id=broker.id,
                    stars=4,
                    decision="YES",
                    body={"reason_text": "Fictional migration guard assessment."},
                    is_edited=True,
                    chars_changed=40,
                    version=1,
                    body_hash="0" * 64,
                )
            )
            db.commit()
            for statement in (
                "UPDATE activity_events SET type='tampered'",
                "UPDATE plans SET revision=999",
                "DELETE FROM plans",
                "UPDATE broker_ratings SET stars=1",
                "DELETE FROM broker_ratings",
            ):
                try:
                    db.execute(text(statement))
                except DatabaseError:
                    db.rollback()
                else:
                    raise AssertionError("PostgreSQL permitted evidence mutation")
        print(
            "PASS: PostgreSQL upgrade -> empty downgrade -> upgrade; direct SQL audit/quote update and quote deletion denied"
        )
    finally:
        target.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


if __name__ == "__main__":
    main()
