"""Versioned human assessments, bound to the exact ranking and quote evidence."""

from fastapi import APIRouter, Depends, Request
from pydantic import Field
from typing import Literal
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.auth import identity
from app import service
from app.db.platform import BrokerRating, CasePlan, Partner
from app.db.store import audit, latest
from app.schemas import DomainError, Model, State
from app.agents.review import canonical_hash
from app.compliance.medical_firewall import safe_case

router = APIRouter(prefix="/api/v1/cases")


def database():
    # Domain validation is also imported by workers and isolated service tests.
    from app.main import database as application_database

    yield from application_database()


class RatingInput(Model):
    stars: int = Field(ge=1, le=5, strict=True)
    decision: Literal["YES", "NO", "REFER"]
    reason_text: str = Field(min_length=20, max_length=2000)
    ai_draft_text: str = Field(default="", max_length=3000)
    ranking_id: str = Field(min_length=1, max_length=100)


def edit_distance(a, b):
    if len(a) > len(b):
        a, b = b, a
    row = list(range(len(a) + 1))
    for index, right in enumerate(b, 1):
        next_row = [index]
        for column, left in enumerate(a, 1):
            next_row.append(min(next_row[-1] + 1, row[column] + 1, row[column - 1] + (left != right)))
        row = next_row
    return row[-1]


def draft_text(row):
    explanation = row.get("explanation", {})
    return row.get("ai_draft_text") or (
        explanation if isinstance(explanation, str) else explanation.get("overall", "")
    )


def current_ratings(db, case_id, ranking_id, broker_id):
    rows = db.scalars(
        select(BrokerRating)
        .where(
            BrokerRating.case_id == case_id,
            BrokerRating.ranking_id == ranking_id,
            BrokerRating.broker_id == broker_id,
        )
        .order_by(BrokerRating.version, BrokerRating.id)
    ).all()
    return {row.plan_id: row for row in rows}


def public(row):
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "case_id",
            "ranking_id",
            "plan_id",
            "broker_id",
            "stars",
            "decision",
            "is_edited",
            "chars_changed",
            "version",
            "created_at",
            "body_hash",
        )
    } | row.body


def redact_ratings(db, case, user, rows, include_medical=False):
    dnr = latest(db, case.id, "dnr")
    return safe_case(
        {"dnr": dnr.body if dnr else {}, "ratings": [public(row) for row in rows]}, user, include_medical
    )["ratings"]


def validate_reviews(db, case_id, ranking, user, selected=None):
    reviews = current_ratings(db, case_id, ranking["id"], user.id)
    ids = {row["plan"]["id"] for row in ranking["top"]}
    missing = sorted(ids - set(reviews))
    if missing:
        raise DomainError(
            "Rate every shortlisted plan before continuing",
            422,
            error="UNRATED_PLANS",
            unrated_plan_ids=missing,
        )
    if selected is not None and any(
        reviews.get(plan_id) is None or reviews[plan_id].decision != "YES" for plan_id in selected
    ):
        raise DomainError(
            "Selected plans must have a Recommend decision", 422, error="PLAN_DECISION_CONFLICT"
        )
    return [reviews[plan_id] for plan_id in sorted(ids)]


def reviews_hash(rows):
    return canonical_hash(
        [
            {"id": row.id, "hash": row.body_hash, "plan_id": row.plan_id}
            for row in sorted(rows, key=lambda item: item.plan_id)
        ]
    )


@router.get("/{case_id}/ratings")
def ratings(
    case_id: str, request: Request, include_medical: bool = False, db=Depends(database, scope="function")
):
    user, session = identity(db, request)
    case = service.get_case(db, case_id)
    ranking = latest(db, case_id, "ranking")
    if not ranking:
        return {"ranking_id": None, "ratings": [], "total": 0}
    if include_medical:
        from app.medical_access import require_medical_access

        require_medical_access(db, case, user, session)
    rows = current_ratings(db, case_id, ranking.body["id"], user.id)
    return {
        "ranking_id": ranking.body["id"],
        "ratings": redact_ratings(db, case, user, rows.values(), include_medical),
        "total": len(ranking.body["top"]),
    }


@router.post("/{case_id}/plans/{plan_id}/rating")
def rate(
    case_id: str, plan_id: str, body: RatingInput, request: Request, db=Depends(database, scope="function")
):
    user, _ = identity(db, request)
    service.require_broker(user)
    case = service.get_case(db, case_id)
    if case.state != State.BROKER_REVIEW:
        raise DomainError("Return the case to comparison before changing an assessment", 409)
    ranking = latest(db, case_id, "ranking")
    if not ranking or ranking.body["id"] != body.ranking_id:
        raise DomainError("Ranking changed. Review the current comparison.", 409)
    row = next((row for row in ranking.body["top"] if row["plan"]["id"] == plan_id), None)
    if not row:
        raise DomainError("Plan is outside the current shortlist", 404)
    reason = body.reason_text.strip()
    if len(reason) < 20:
        raise DomainError("Give your assessment in at least 20 characters", 422)
    draft = draft_text(row)
    distance = edit_distance(reason, draft.strip())
    quote_snapshot = latest(db, case_id, "quotes")
    if not quote_snapshot:
        raise DomainError("Quotation evidence needs review before rating", 409)
    plan_record = db.scalar(
        select(CasePlan).where(
            CasePlan.snapshot_id == quote_snapshot.id,
            CasePlan.plan_id == plan_id,
            CasePlan.revision == row["plan"]["revision"],
        )
    )
    if not plan_record:
        # Older prototype snapshots predate relational plans. Add a derived record;
        # the original quote snapshot remains unchanged and is still the source.
        if not db.get(Partner, row["plan"]["insurerId"]):
            raise DomainError("Partner evidence needs review before rating", 409)
        plan_record = CasePlan(
            case_id=case_id,
            partner_id=row["plan"]["insurerId"],
            snapshot_id=quote_snapshot.id,
            plan_id=plan_id,
            revision=row["plan"]["revision"],
            body=row["plan"],
            body_hash=canonical_hash(row["plan"]),
        )
        db.add(plan_record)
        db.flush()
    previous = current_ratings(db, case_id, body.ranking_id, user.id).get(plan_id)
    data = {"reason_text": reason, "ai_draft_text": draft}
    row = BrokerRating(
        case_id=case_id,
        ranking_id=body.ranking_id,
        ranking_snapshot_id=ranking.id,
        plan_id=plan_id,
        plan_record_id=plan_record.id,
        broker_id=user.id,
        stars=body.stars,
        decision=body.decision,
        body=data,
        is_edited=distance > 10,
        chars_changed=distance,
        version=previous.version + 1 if previous else 1,
        body_hash=canonical_hash(
            {
                "ranking_id": body.ranking_id,
                "plan_id": plan_id,
                "stars": body.stars,
                "decision": body.decision,
                **data,
            }
        ),
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise DomainError("Another assessment was saved. Reload before resubmitting.", 409)
    audit(
        db,
        case_id,
        "PLAN_RATED",
        f"broker:{user.id}",
        {
            "rating_id": row.id,
            "plan_id": plan_id,
            "stars": body.stars,
            "decision": body.decision,
            "is_edited": row.is_edited,
            "version": row.version,
        },
    )
    return redact_ratings(db, case, user, [row])[0]
