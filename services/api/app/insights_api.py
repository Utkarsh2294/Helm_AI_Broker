from datetime import datetime
from fastapi import APIRouter, Request, Depends, Query
from sqlalchemy import select, func
from app.auth import identity
from app.db.models import Activity, Case, Snapshot
from app.main import database
from app import service
from app.evidence import replay
from app.case_access import visible_cases

router = APIRouter(prefix="/api/v1")


@router.get("/insights/outcomes")
def outcomes(request: Request, db=Depends(database, scope="function")):
    from app.outcome_metrics import measured_outcomes

    user, _ = identity(db, request)
    return measured_outcomes(db, user)


@router.get("/cases/{case_id}/replay")
def historical(case_id: str, request: Request, at: datetime, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    return replay(db, service.get_case(db, case_id), at, user)


@router.get("/audit/search")
def search(
    request: Request,
    case_id: str = "",
    actor: str = "",
    event_type: str = "",
    after: str = "",
    before: str = "",
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db=Depends(database, scope="function"),
):
    user, _ = identity(db, request)
    query = select(Activity).join(Case, Activity.case_id == Case.id).where(visible_cases(user))
    for column, value in ((Activity.case_id, case_id), (Activity.actor, actor), (Activity.type, event_type)):
        if value:
            query = query.where(column == value)
    if after:
        query = query.where(Activity.created_at >= after)
    if before:
        query = query.where(Activity.created_at <= before)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(Activity.created_at.desc(), Activity.seq.desc()).offset(offset).limit(limit)
    )
    return {
        "total": total,
        "offset": offset,
        "items": [
            {k: getattr(r, k) for k in ("case_id", "seq", "actor", "type", "created_at", "payload", "hash")}
            for r in rows
        ],
    }


@router.get("/insights")
def insights(request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    scope = visible_cases(user)
    states = dict(db.execute(select(Case.state, func.count()).where(scope).group_by(Case.state)).all())
    halts = dict(
        db.execute(
            select(Activity.type, func.count())
            .join(Case, Activity.case_id == Case.id)
            .where(scope)
            .where(Activity.type.in_(["partner_requires_human", "ranking_requires_human"]))
            .group_by(Activity.type)
        ).all()
    )
    surveys = db.scalars(
        select(Snapshot)
        .join(Case, Snapshot.case_id == Case.id)
        .where(Snapshot.kind == "selection", scope)
        .order_by(Snapshot.version)
    ).all()
    latest = {s.case_id: s.body["survey"] for s in surveys}
    thumbs = [v for s in latest.values() for v in s["thumbs"].values()]
    return {
        "cases": sum(states.values()),
        "states": states,
        "halts": halts,
        "labelled_cases": len(latest),
        "satisfaction": sum(v == "up" for v in thumbs) / len(thumbs) if thumbs else None,
    }
