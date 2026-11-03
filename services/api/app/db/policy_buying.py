"""Demo buying records; customer-bearing bodies use existing AES-256-GCM storage."""

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.models import Base, SecretJSON, uid, stamp


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
