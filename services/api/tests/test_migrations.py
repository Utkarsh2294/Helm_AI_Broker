import os
import subprocess
import sys
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session
from app.config import ROOT
from app.db.models import Case, User
from app.db.assistant import AssistantLog
from app.db.store import audit, make_engine


def test_migration_enforces_immutability_against_raw_sql(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env={**os.environ, "HELM_DATABASE_URL": url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    engine = make_engine(url)
    with Session(engine) as db:
        case = Case(core_request_id="migrated", profile={"name": "Demo"})
        db.add(case)
        user = User(email="migration@helm.demo", name="Migration fixture", password_hash="unused")
        db.add(user)
        db.flush()
        audit(db, case.id, "created", "system")
        db.add(
            AssistantLog(
                broker_id=user.id,
                session_id="migration-fixture",
                case_id=case.id,
                body={"question": "Saved fixture", "answer": "Read-only fixture"},
                model_version="test",
                confidence_level="LOW",
            )
        )
        db.commit()
        with pytest.raises(DatabaseError, match="append-only"):
            db.execute(text("UPDATE activity_events SET type='tampered'"))
        db.rollback()
        with pytest.raises(DatabaseError, match="append-only"):
            db.execute(text("UPDATE assistant_logs SET confidence_level='HIGH'"))
        db.rollback()
        with pytest.raises(DatabaseError, match="append-only"):
            db.execute(text("DELETE FROM activity_events"))
        db.rollback()
    engine.dispose()


def test_empty_database_round_trip_and_populated_downgrade_guard(tmp_path):
    url = f"sqlite:///{tmp_path / 'round-trip.db'}"
    environment = {**os.environ, "HELM_DATABASE_URL": url}
    for command in (("upgrade", "head"), ("downgrade", "base"), ("upgrade", "head")):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *command],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
    engine = make_engine(url)
    with Session(engine) as db:
        db.add(Case(core_request_id="preserved", profile={"name": "Fictional"}))
        db.commit()
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0 and "contains user or evidence records" in result.stderr
    engine.dispose()
