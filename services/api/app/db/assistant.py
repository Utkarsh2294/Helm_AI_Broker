"""Private encrypted assistant sessions and immutable response evidence."""

from sqlalchemy import ForeignKey, String, event
from sqlalchemy.orm import Mapped, mapped_column
from app.db.models import Base, SecretJSON, uid, stamp, immutable


class AssistantLog(Base):
    __tablename__ = "assistant_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    broker_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id"), index=True)
    body: Mapped[dict] = mapped_column(SecretJSON)
    model_version: Mapped[str] = mapped_column(String(60))
    confidence_level: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[str] = mapped_column(String(40), default=stamp)


class AssistantFile(Base):
    __tablename__ = "assistant_files"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    broker_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id"), index=True)
    body: Mapped[dict] = mapped_column(SecretJSON)
    expires_at: Mapped[str] = mapped_column(String(40))


class AssistantShare(Base):
    __tablename__ = "assistant_shares"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    log_id: Mapped[str] = mapped_column(ForeignKey("assistant_logs.id"))
    expires_at: Mapped[str] = mapped_column(String(40))


event.listen(AssistantLog, "before_update", immutable)
event.listen(AssistantLog, "before_delete", immutable)
