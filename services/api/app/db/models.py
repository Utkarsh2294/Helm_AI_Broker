"""Relational workflow records; all customer snapshots are encrypted at rest."""

import base64
import json
import os
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.config import ROOT, settings
from app.clock import wall_now


def uid():
    return str(uuid4())


def utcnow():
    return wall_now()


def stamp():
    return utcnow().isoformat()


@lru_cache(maxsize=1)
def encryption_key():
    # Configuration is process-scoped; rotation requires coordinated worker restart.
    key = settings().encryption_key
    if key:
        return base64.urlsafe_b64decode(key)
    # shortcut: local demo key file; live deployment needs an external KMS and key rotation.
    path = Path(ROOT / ".runtime/demo.key")
    path.parent.mkdir(exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(AESGCM.generate_key(bit_length=256))
    except FileExistsError:
        pass
    return path.read_bytes()


class SecretJSON(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        nonce = os.urandom(12)
        encrypted = AESGCM(encryption_key()).encrypt(nonce, json.dumps(value).encode(), b"helm-snapshot-v1")
        return base64.urlsafe_b64encode(nonce + encrypted).decode()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        raw = base64.urlsafe_b64decode(value)
        return json.loads(AESGCM(encryption_key()).decrypt(raw[:12], raw[12:], b"helm-snapshot-v1"))


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(40), default="authorised_broker")
    can_approve: Mapped[bool] = mapped_column(default=False)
    fca_irn: Mapped[str | None] = mapped_column(String(100))
    is_lead_broker: Mapped[bool] = mapped_column(default=False)


class LoginSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    csrf: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[str] = mapped_column(String(40))
    step_up_at: Mapped[str | None] = mapped_column(String(40))


class Case(Base):
    __tablename__ = "cases"
    priority: Mapped[str] = mapped_column(String(20), default="normal", server_default="normal")
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    core_request_id: Mapped[str] = mapped_column(String(100), unique=True)
    profile: Mapped[dict] = mapped_column(SecretJSON)
    state: Mapped[str] = mapped_column(String(50), default="RECEIVED")
    previous_state: Mapped[str | None] = mapped_column(String(50))
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[str] = mapped_column(String(40), default=stamp)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": version}


class Snapshot(Base):
    __tablename__ = "snapshots"
    __table_args__ = (UniqueConstraint("case_id", "kind", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    kind: Mapped[str] = mapped_column(String(30))
    version: Mapped[int] = mapped_column(Integer)
    body: Mapped[dict] = mapped_column(SecretJSON)
    body_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40), default=stamp)


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (UniqueConstraint("case_id", "gate", "payload_hash", "user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    gate: Mapped[str] = mapped_column(String(10))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    payload_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40), default=stamp)
    step_up_at: Mapped[str | None] = mapped_column(String(40))


class Activity(Base):
    __tablename__ = "activity_events"
    __table_args__ = (UniqueConstraint("case_id", "seq"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    seq: Mapped[int] = mapped_column(Integer)
    actor: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=stamp)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id"))
    kind: Mapped[str] = mapped_column(String(30))
    due_at: Mapped[str] = mapped_column(String(40))
    body: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending")


class ModelProposal(Base):
    __tablename__ = "model_change_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    body: Mapped[dict] = mapped_column(SecretJSON)
    status: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[str] = mapped_column(String(40), default=stamp)


class Publication(Base):
    __tablename__ = "publications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), unique=True)
    approval_id: Mapped[str] = mapped_column(ForeignKey("approvals.id"))
    pack_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="demo_delivered")
    created_at: Mapped[str] = mapped_column(String(40), default=stamp)


def immutable(mapper, connection, target):
    raise ValueError("Evidence records are append-only")


for table in (Snapshot, Approval, Activity, Publication):
    event.listen(table, "before_update", immutable)
    event.listen(table, "before_delete", immutable)

# Register the concrete tables used by auth, integration and governance.
from app.db import platform as platform_models  # noqa: E402,F401
