"""Validated boundaries shared by agents, the API and persisted snapshots."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Pence = Annotated[int, Field(ge=0, strict=True)]
Unit = Annotated[float, Field(ge=0, le=1)]
CRITERIA = (
    "affordability",
    "coverage",
    "network",
    "underwriting",
    "insurer_quality",
    "process_ease",
    "terms_clarity",
)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class State(StrEnum):
    RECEIVED = "RECEIVED"
    INTAKE_RUNNING = "INTAKE_RUNNING"
    RFQ_DRAFTING = "RFQ_DRAFTING"
    RFQ_RELEASE_CHECK = "RFQ_RELEASE_CHECK"
    QUOTES_COLLECTED = "QUOTES_COLLECTED"
    RANKING = "RANKING"
    SUITABILITY_DRAFT = "SUITABILITY_DRAFT"
    UW_REFERRAL = "UW_REFERRAL"
    NEEDS_INFO = "NEEDS_INFO"
    FACTFIND_REVIEW = "FACTFIND_REVIEW"
    AWAIT_BROKER_RELEASE = "AWAIT_BROKER_RELEASE"
    QUOTES_PENDING = "QUOTES_PENDING"
    BROKER_REVIEW = "BROKER_REVIEW"
    AWAIT_APPROVAL = "AWAIT_APPROVAL"
    PUBLISHED = "PUBLISHED"
    PAUSED_NEEDS_HUMAN = "PAUSED_NEEDS_HUMAN"
    COMPLAINT_FLAGGED = "COMPLAINT_FLAGGED"
    CLOSED = "CLOSED"


class CoverageNeed(Model):
    level: int = Field(ge=0, le=3)
    importance: float = Field(default=1, ge=0, le=1)
    must_have: bool = False


class Needs(Model):
    budget_annual_pence: Pence = 180000
    hard_budget_cap: Pence | None = None
    priorities: list[str] = Field(default_factory=lambda: ["affordability", "coverage", "network"])
    coverage: dict[str, CoverageNeed] = Field(default_factory=dict)
    hospital_level: int = Field(default=2, ge=1, le=3)
    preferred_underwriting: str = "moratorium"
    allowed_underwriting: list[str] = Field(default_factory=lambda: ["moratorium", "FMU"])
    # Fixed external benchmark: never recomputed from the candidate quote batch.
    reference_low_pence: Pence = 60000
    reference_high_pence: Pence = 400000

    @model_validator(mode="after")
    def valid_priorities(self):
        if len(set(self.priorities)) != len(self.priorities) or set(self.priorities) - set(CRITERIA):
            raise ValueError("Priorities must be unique known criteria")
        if self.reference_high_pence <= self.reference_low_pence or self.budget_annual_pence <= 0:
            raise ValueError("Budget and reference band must be positive")
        return self


class QuoteRequest(Model):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    cover_type: Literal["individual", "couple", "family"] = "individual"
    postcode_district: str = Field(default="M20", max_length=10)
    needs: Needs = Field(default_factory=Needs)
    consent_to_share: bool = True
    medical_items: list[str] = Field(default_factory=list, max_length=30)
    vulnerability_flags: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)


class Fact(Model):
    value: object
    confidence: Unit = 1
    source: str
    verified_by: str | None = None


class DNR(Model):
    request_id: str
    version: int = 1
    needs: Needs
    facts: dict[str, Fact]
    medical_items: list[str]
    vulnerability_flags: list[str]
    missing: list[str]
    hypotheses: list[str]
    consent_to_share: bool


class InsurerStats(Model):
    n: int = Field(default=200, ge=0)
    upheldRate: Unit = 0.2
    finStrength: Unit = 0.8
    slaScore: Unit = 0.8


class Plan(Model):
    id: str
    insurerId: str
    name: str
    revision: int = Field(default=1, ge=1)
    status: Literal["quoted", "declined", "referred"] = "quoted"
    basePremiumPence: Pence
    annualPremiumPence: Pence
    excessPence: Pence = 25000
    coverage: dict[str, Annotated[int, Field(ge=0, le=3)]]
    hospitalListLevel: int = Field(default=2, ge=1, le=3)
    preferredHospitalShare: Unit = 0.8
    exclusionSeverities: list[Annotated[float, Field(ge=0)]] = Field(default_factory=list)
    underwritingType: Literal["moratorium", "FMU"] = "moratorium"
    insurerStats: InsurerStats = Field(default_factory=InsurerStats)
    docsRequired: int = Field(default=3, ge=0)
    docsUnavailable: int = Field(default=0, ge=0)
    turnaroundDays: float = Field(default=3, ge=0)
    ipidCompleteness: Unit = 1
    plainLanguage: Unit = 0.85
    exclusionsCount: int = Field(default=4, ge=0)
    commissionPct: float = Field(default=12, ge=0, le=100)
    ipidUrl: str = "https://example.test/ipid"
    ipidVersion: str = "demo-2026"
    medicalFlagsAmbiguous: bool = False
    fcaStatus: str = "authorised"
    provenance: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_documents(self):
        if self.docsUnavailable > self.docsRequired:
            raise ValueError("Unavailable documents exceed required documents")
        return self


class Survey(Model):
    thumbs: dict[str, Literal["up", "down"]]
    reasons: list[str] = Field(default_factory=list)
    omitted_first_reason: str = Field(default="", max_length=140)
    clarity: int | None = Field(default=None, ge=1, le=5)
    note: str = Field(default="", max_length=140)


class DomainError(Exception):
    def __init__(self, message: str, status: int = 409, **flags):
        super().__init__(message)
        self.status = status
        self.flags = flags
