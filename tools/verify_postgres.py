"""Exercise clean migrations and SQL evidence guards in a disposable local database."""

import os
import re
import subprocess
import sys
from uuid import uuid4
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import DatabaseError
from app.db.models import Case
from app.db.store import audit


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
            db.commit()
            try:
                db.execute(text("UPDATE activity_events SET type='tampered'"))
            except DatabaseError:
                db.rollback()
            else:
                raise AssertionError("PostgreSQL permitted evidence mutation")
        print("PASS: PostgreSQL upgrade -> empty downgrade -> upgrade; direct SQL evidence update denied")
    finally:
        target.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


if __name__ == "__main__":
    main()
