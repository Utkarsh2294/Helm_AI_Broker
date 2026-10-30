import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy.orm import Session
from app.db.models import Base, Case, encryption_key
from app.db.store import make_engine, audit, save_snapshot
from tools.demo_recovery import backup, restore


def test_encrypted_backup_restores_and_checks_all_chains_without_overwriting(tmp_path):
    source = tmp_path / "source.db"
    engine = make_engine(f"sqlite:///{source}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        case = Case(core_request_id="restore-fixture", profile={"name": "Fictional recovery"})
        db.add(case)
        db.flush()
        audit(db, case.id, "received", "system", {"sample": True})
        save_snapshot(db, case.id, "request", {"name": "Fictional recovery", "medical_items": []})
        db.commit()
    engine.dispose()
    before = source.read_bytes()
    bundle = tmp_path / "backup.helm"
    passphrase = "separate-demo-backup-passphrase-only"
    checked = backup(source, encryption_key(), bundle, passphrase)
    assert checked["cases"] == 1 and checked["events_verified"] == 1
    assert b"Fictional recovery" not in bundle.read_bytes() and encryption_key() not in bundle.read_bytes()
    with pytest.raises(InvalidTag):
        restore(bundle, tmp_path / "wrong-passphrase", "a different long passphrase")
    assert not (tmp_path / "wrong-passphrase").exists()
    restored = restore(bundle, tmp_path / "recovered", passphrase)
    assert restored == checked and restored["snapshots_decrypted_and_verified"] == 1
    with pytest.raises(ValueError, match="new directory"):
        restore(bundle, tmp_path / "recovered", passphrase)
    assert source.read_bytes() == before
