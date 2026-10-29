import os
import subprocess
import sys
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session
from app.config import ROOT
from app.db.models import Case
from app.db.store import audit, make_engine


def test_migration_enforces_immutability_against_raw_sql(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT,
                            env={**os.environ, "HELM_DATABASE_URL": url}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    engine = make_engine(url)
    with Session(engine) as db:
        case = Case(core_request_id="migrated", profile={"name": "Demo"})
        db.add(case)
        db.flush()
        audit(db, case.id, "created", "system")
        db.commit()
        with pytest.raises(DatabaseError, match="append-only"):
            db.execute(text("UPDATE activity_events SET type='tampered'"))
        db.rollback()
        with pytest.raises(DatabaseError, match="append-only"):
            db.execute(text("DELETE FROM activity_events"))
        db.rollback()
    engine.dispose()
