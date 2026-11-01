"""Broker-scoped operational projections, notifications and survey evidence."""

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, JSON, event
from sqlalchemy.orm import Mapped, mapped_column
from app.db.models import Base, SecretJSON, uid, stamp, immutable


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("broker_id", "event_key"),
        Index("ix_notifications_broker_unread", "broker_id", "read_at", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    broker_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id"), index=True)
    event_key: Mapped[str] = mapped_column(String(150))
    event_type: Mapped[str] = mapped_column(String(50))
    body: Mapped[dict] = mapped_column(SecretJSON)
    actionable: Mapped[bool] = mapped_column(default=True)
    read_at: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[str] = mapped_column(String(40), default=stamp)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    __table_args__ = (UniqueConstraint("broker_id", "endpoint_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    broker_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    endpoint_hash: Mapped[str] = mapped_column(String(64))
    body: Mapped[dict] = mapped_column(SecretJSON)
    created_at: Mapped[str] = mapped_column(String(40), default=stamp)


class TaskSnooze(Base):
    __tablename__ = "task_card_snoozes"
    broker_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), primary_key=True)
    task_key: Mapped[str] = mapped_column(String(60), primary_key=True)
    snoozed_until: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(50), default="later")


class NotificationLease(Base):
    __tablename__ = "notification_stream_leases"
    broker_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    token: Mapped[str] = mapped_column(String(36))
    expires_at: Mapped[str] = mapped_column(String(40))


class CopilotPreferences(Base):
    __tablename__ = "copilot_preferences"
    broker_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    timezone: Mapped[str] = mapped_column(String(80), default="Europe/London")
    voice_banner: Mapped[bool] = mapped_column(default=False)
    digest_day: Mapped[str | None] = mapped_column(String(10))
    last_login: Mapped[str | None] = mapped_column(String(40))
    previous_login: Mapped[str | None] = mapped_column(String(40))


class CaseSatisfaction(Base):
    __tablename__ = "case_satisfaction"
    __table_args__ = (CheckConstraint("score BETWEEN 1 AND 5"),)
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    score: Mapped[int]
    body: Mapped[dict] = mapped_column(SecretJSON)
    submitted_at: Mapped[str] = mapped_column(String(40), default=stamp)


class CaseMetric(Base):
    __tablename__ = "case_metrics"
    __table_args__ = (
        Index("ix_case_metrics_scope_date", "broker_id", "created_at", "coverage_type", "insurer_id"),
        Index("ix_case_metrics_scope_state", "broker_id", "state", "last_action_at"),
    )
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), primary_key=True)
    broker_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    coverage_type: Mapped[str] = mapped_column(String(30))
    state: Mapped[str] = mapped_column(String(50))
    insurer_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    closed_at: Mapped[str | None] = mapped_column(String(40))
    last_action_at: Mapped[str] = mapped_column(String(40))
    close_days: Mapped[float | None]
    budget_pence: Mapped[int | None]
    csat: Mapped[float | None]
    body: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[str] = mapped_column(String(40), default=stamp)


class ProviderMetric(Base):
    __tablename__ = "case_provider_metrics"
    __table_args__ = (
        Index("ix_provider_metrics_scope", "broker_id", "created_at", "coverage_type", "insurer_id"),
    )
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), primary_key=True)
    insurer_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    broker_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    coverage_type: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[str] = mapped_column(String(40))
    shown: Mapped[int] = mapped_column(default=0)
    top_three: Mapped[int] = mapped_column(default=0)
    selected: Mapped[int] = mapped_column(default=0)
    accepted: Mapped[int] = mapped_column(default=0)
    rated_highly: Mapped[int] = mapped_column(default=0)
    quoted_turnaround: Mapped[float | None]
    upheld_rate: Mapped[float | None]


class SatisfactionDrivers(Base):
    __tablename__ = "satisfaction_drivers"
    broker_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    body: Mapped[dict] = mapped_column(JSON)
    computed_at: Mapped[str] = mapped_column(String(40), default=stamp)


class EvidenceVisibility(Base):
    __tablename__ = "assistant_evidence_visibility"
    evidence_id: Mapped[str] = mapped_column(ForeignKey("snapshots.id"), primary_key=True)
    broker_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    hidden_at: Mapped[str | None] = mapped_column(String(40))


class AssistantAudit(Base):
    __tablename__ = "assistant_audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    broker_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id"), index=True)
    response_id: Mapped[str | None] = mapped_column(ForeignKey("assistant_logs.id"))
    query_hash: Mapped[str] = mapped_column(String(64))
    response_hash: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[str] = mapped_column(String(40), default=stamp)


for table in (CaseSatisfaction, AssistantAudit):
    event.listen(table, "before_update", immutable)
    event.listen(table, "before_delete", immutable)
