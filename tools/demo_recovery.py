"""Encrypted SQLite recovery rehearsal. Restores only into a new directory.

This local demo does not provide production KMS, PostgreSQL PITR or off-site storage.
"""

import argparse
from contextlib import closing
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import zipfile
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"HELM-DEMO-BACKUP-1\0"


def digest(body):
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def verify(database, key):
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Restored database failed integrity check")
        roots, sequences = {}, {}
        events = db.execute("SELECT * FROM activity_events ORDER BY case_id, seq").fetchall()
        for row in events:
            previous = roots.get(row["case_id"], "0" * 64)
            body = {field: row[field] for field in ("case_id", "seq", "actor", "type", "created_at")}
            body["payload"] = json.loads(row["payload"])
            if (
                row["seq"] != sequences.get(row["case_id"], 0) + 1
                or row["prev_hash"] != previous
                or row["hash"] != digest({"prev_hash": previous, **body})
            ):
                raise ValueError("Restored audit chain verification failed")
            roots[row["case_id"]], sequences[row["case_id"]] = row["hash"], row["seq"]
        snapshots = db.execute("SELECT body, body_hash FROM snapshots").fetchall()
        for row in snapshots:
            raw = base64.urlsafe_b64decode(row["body"])
            body = json.loads(AESGCM(key).decrypt(raw[:12], raw[12:], b"helm-snapshot-v1"))
            if digest(body) != row["body_hash"]:
                raise ValueError("Restored snapshot hash verification failed")
        return {
            "cases": db.execute("SELECT count(*) FROM cases").fetchone()[0],
            "events_verified": len(events),
            "snapshots_decrypted_and_verified": len(snapshots),
            "database_integrity": "ok",
            "live_recovery_approved": False,
        }


def derive(passphrase, salt):
    if len(passphrase) < 20:
        raise ValueError("Use a separate backup passphrase of at least 20 characters")
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode())


def backup(database, key, target, passphrase):
    if len(key) != 32:
        raise ValueError("Expected the existing 256-bit database key")
    with tempfile.TemporaryDirectory(prefix="helm-backup-") as temporary:
        snapshot = Path(temporary) / "broker.db"
        with (
            closing(sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)) as source,
            closing(sqlite3.connect(snapshot)) as destination,
        ):
            source.backup(destination)
        checked = verify(snapshot, key)
        content = snapshot.read_bytes()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("broker.db", content)
            archive.writestr("demo.key", key)
            archive.writestr(
                "manifest.json",
                json.dumps({"database_sha256": hashlib.sha256(content).hexdigest(), **checked}),
            )
        salt, nonce = os.urandom(16), os.urandom(12)
        encrypted = AESGCM(derive(passphrase, salt)).encrypt(nonce, buffer.getvalue(), MAGIC)
        with Path(target).open("xb") as output:
            output.write(MAGIC + salt + nonce + encrypted)
        return checked


def restore(bundle, directory, passphrase):
    directory = Path(directory)
    if directory.exists():
        raise ValueError("Restore requires a new directory; existing data is never replaced")
    raw = Path(bundle).read_bytes()
    if not raw.startswith(MAGIC):
        raise ValueError("Unsupported backup format")
    offset = len(MAGIC)
    decrypted = AESGCM(derive(passphrase, raw[offset : offset + 16])).decrypt(
        raw[offset + 16 : offset + 28], raw[offset + 28 :], MAGIC
    )
    with zipfile.ZipFile(io.BytesIO(decrypted)) as archive:
        if set(archive.namelist()) != {"broker.db", "demo.key", "manifest.json"}:
            raise ValueError("Unexpected backup entries")
        database, key = archive.read("broker.db"), archive.read("demo.key")
        manifest = json.loads(archive.read("manifest.json"))
    if hashlib.sha256(database).hexdigest() != manifest["database_sha256"]:
        raise ValueError("Backup database digest mismatch")
    with tempfile.TemporaryDirectory(prefix="helm-restore-") as temporary:
        candidate = Path(temporary) / "broker.db"
        candidate.write_bytes(database)
        checked = verify(candidate, key)
    directory.mkdir(parents=True, exist_ok=False)
    for name, content in (("broker.db", database), ("demo.key", key)):
        with os.fdopen(
            os.open(directory / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "wb"
        ) as output:
            output.write(content)
    return checked


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["backup", "restore"])
    parser.add_argument("--database", type=Path)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args()
    passphrase = os.environ.get("HELM_BACKUP_PASSPHRASE", "")
    if args.operation == "backup":
        if not args.database or not args.key_file:
            parser.error("backup requires --database and --key-file")
        result = backup(args.database, args.key_file.read_bytes(), args.bundle, passphrase)
    else:
        if not args.directory:
            parser.error("restore requires --directory")
        result = restore(args.bundle, args.directory, passphrase)
    print(json.dumps(result, indent=2))
