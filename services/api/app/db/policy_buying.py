"""Demo buying records; customer-bearing bodies use existing AES-256-GCM storage."""

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column
from app.db.models import Base, SecretJSON, uid, stamp, immutable


class BuyingCase(Base):
    __tablename__ = "policy_buying_cases"
    __table_args__ = (
        CheckConstraint("underwriting_basis IN ('moratorium','fmu')"),
        CheckConstraint(
            "stage IN ('QUOTE_SELECTED','IPID_DRAFTING','AWAITING_IPID_CONFIRMATION',"
            "'UNDERWRITING_IN_PROGRESS','AWAITING_BANKING_DETAILS','SUBMISSION_PACKAGE_READY',"
            "'SUBMITTED_TO_INSURER','POLICY_ISSUED')"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), unique=True)
    selected_plan_id: Mapped[str] = mapped_column(String(200))
    underwriting_basis: Mapped[str] = mapped_column(String(20))
    stage: Mapped[str] = mapped_column(String(40), default="QUOTE_SELECTED", index=True)
    body: Mapped[dict] = mapped_column(SecretJSON, default=dict)
    pending_response: Mapped[bool] = mapped_column(default=False)
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[str] = mapped_column(String(40), default=stamp)
    updated_at: Mapped[str] = mapped_column(String(40), default=stamp)
    closed_at: Mapped[str | None] = mapped_column(String(40))
    policy_number: Mapped[str | None] = mapped_column(String(80), unique=True)
    __mapper_args__ = {"version_id_col": version}


class BuyingDocument(Base):
    __tablename__ = "pb_documents"
    __table_args__ = (UniqueConstraint("pb_case_id", "doc_type", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    pb_case_id: Mapped[str] = mapped_column(ForeignKey("policy_buying_cases.id"), index=True)
    doc_type: Mapped[str] = mapped_column(String(40))
    version: Mapped[int] = mapped_column()
    content: Mapped[dict] = mapped_column(SecretJSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    edited_by_broker: Mapped[bool] = mapped_column(default=False)
    actor: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[str] = mapped_column(String(40), default=stamp)


event.listen(BuyingDocument, "before_update", immutable)
event.listen(BuyingDocument, "before_delete", immutable)


class BuyingUpdate(Base):
    __tablename__ = "pb_update_feed"
    __table_args__ = (UniqueConstraint("pb_case_id", "seq"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    pb_case_id: Mapped[str] = mapped_column(ForeignKey("policy_buying_cases.id"), index=True)
    seq: Mapped[int] = mapped_column()
    update_type: Mapped[str] = mapped_column(String(70))
    body: Mapped[dict] = mapped_column(SecretJSON)
    created_at: Mapped[str] = mapped_column(String(40), default=stamp)


class BuyingRead(Base):
    __tablename__ = "pb_read_positions"
    pb_case_id: Mapped[str] = mapped_column(ForeignKey("policy_buying_cases.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    seq: Mapped[int] = mapped_column(default=0)


event.listen(BuyingUpdate, "before_update", immutable)
event.listen(BuyingUpdate, "before_delete", immutable)


class BuyingAgreement(Base):
    __tablename__ = "pb_standing_agreements"
    __table_args__ = (UniqueConstraint("consumer_key", "document_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    consumer_key: Mapped[str] = mapped_column(String(64), index=True)
    document_hash: Mapped[str] = mapped_column(String(64))
    document_id: Mapped[str] = mapped_column(ForeignKey("pb_documents.id"))
    accepted_at: Mapped[str] = mapped_column(String(40), default=stamp)


event.listen(BuyingAgreement, "before_update", immutable)
event.listen(BuyingAgreement, "before_delete", immutable)
