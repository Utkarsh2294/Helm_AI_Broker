"""Authentication, integration and governance records used by the complete prototype."""

from datetime import datetime
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.models import Base, SecretJSON, stamp, uid

Json = JSON().with_variant(JSONB, "postgresql")


class AuthChallenge(Base):
    __tablename__ = "auth_challenges"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    purpose: Mapped[str] = mapped_column(String(30))
    body: Mapped[dict] = mapped_column(SecretJSON)  # ENCRYPTED at application level
    expires_at: Mapped[str] = mapped_column(String(40))
    consumed: Mapped[bool] = mapped_column(default=False)


class Passkey(Base):
    __tablename__ = "credentials_passkey"
    id: Mapped[str] = mapped_column(String(1000), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    public_key: Mapped[str] = mapped_column(Text)
    sign_count: Mapped[int] = mapped_column(default=0)
    device_name: Mapped[str] = mapped_column(String(100), default="Passkey")
    created_at: Mapped[str] = mapped_column(String(40), default=stamp)


class TOTPSecret(Base):
    __tablename__ = "totp_secrets"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    body: Mapped[dict] = mapped_column(SecretJSON)  # ENCRYPTED at application level
    enabled: Mapped[bool] = mapped_column(default=False)
    last_counter: Mapped[int] = mapped_column(default=-1)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    session_id: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    password_hash: Mapped[str] = mapped_column(Text)
    revoked: Mapped[bool] = mapped_column(default=False)
    expires_at: Mapped[str] = mapped_column(String(40))


class SessionDevice(Base):
    __tablename__ = "session_devices"
    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    ip: Mapped[str] = mapped_column(String(100))
    user_agent: Mapped[str] = mapped_column(String(300))
    last_seen_at: Mapped[str] = mapped_column(String(40), default=stamp)


class InboxEvent(Base):
    __tablename__ = "inbox_events"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100))
    body: Mapped[dict] = mapped_column(SecretJSON)  # ENCRYPTED at application level
    received_at: Mapped[str] = mapped_column(String(40), default=stamp)


class KnowledgeEntry(Base):
    __tablename__ = "knowledge_entries"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50))


class EngineModel(Base):
    __tablename__ = "engine_models"
    __table_args__ = (CheckConstraint("status IN ('champion','challenger','retired')"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    version: Mapped[str] = mapped_column(String(100), unique=True)
    weights: Mapped[dict] = mapped_column(Json)
    status: Mapped[str] = mapped_column(String(20))
    proposal_id: Mapped[str | None] = mapped_column(ForeignKey("model_change_requests.id"))
    previous_champion_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[str] = mapped_column(String(40), default=stamp)


class ModelApproval(Base):
    __tablename__ = "model_approvals"
    __table_args__ = (UniqueConstraint("proposal_id", "stage", "user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("model_change_requests.id"))
    stage: Mapped[str] = mapped_column(String(20))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(30))
    at: Mapped[str] = mapped_column(String(40), default=stamp)


Index(
    "engine_one_champion",
    EngineModel.status,
    unique=True,
    postgresql_where=EngineModel.status == "champion",
    sqlite_where=EngineModel.status == "champion",
)


class GovernanceEvent(Base):
    __tablename__ = "governance_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(60))
    body: Mapped[dict] = mapped_column(Json)
    created_at: Mapped[str] = mapped_column(String(40), default=stamp)


class ShadowEvaluation(Base):
    __tablename__ = "shadow_evaluations"
    __table_args__ = (UniqueConstraint("model_id", "case_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    model_id: Mapped[str] = mapped_column(ForeignKey("engine_models.id"))
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    body: Mapped[dict] = mapped_column(SecretJSON)  # ENCRYPTED at application level


class EdgeCase(Base):
    __tablename__ = "edge_cases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    selection_id: Mapped[str] = mapped_column(String(36), unique=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    body: Mapped[dict] = mapped_column(SecretJSON)  # ENCRYPTED at application level
    status: Mapped[str] = mapped_column(String(50), default="pending_review")
    created_at: Mapped[str] = mapped_column(String(40), default=stamp)


class Playbook(Base):
    __tablename__ = "playbooks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    scope: Mapped[str] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(default=1)
    body: Mapped[dict] = mapped_column(Json)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class Complaint(Base):
    __tablename__ = "complaints"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), unique=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="open")
    resolution: Mapped[dict | None] = mapped_column(SecretJSON)  # ENCRYPTED at application level


class LLMCall(Base):
    __tablename__ = "llm_calls"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(String(100), index=True)
    prompt_hash: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(100))
    tokens: Mapped[int] = mapped_column(default=0)
    latency_ms: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(30))


class AuditAnchor(Base):
    __tablename__ = "audit_anchors"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uid)
    day: Mapped[str] = mapped_column(String(10), unique=True)
    body: Mapped[dict] = mapped_column(Json)
