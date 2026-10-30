from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy import select, func
from app.auth import identity
from app.db.models import Case
from app.main import database
from app.schemas import DomainError

router = APIRouter(prefix="/api/v1")


@router.get("/cases")
def cases(
    request: Request,
    q: str = "",
    state: str = "",
    assignee: str = "",
    priority: str = "",
    sort: str = "newest",
    limit: int = Query(0, ge=0, le=200),
    offset: int = Query(0, ge=0),
    db=Depends(database, scope="function"),
):
    user, _ = identity(db, request)
    query = select(Case)
    if state:
        query = query.where(Case.state == state)
    if assignee == "me":
        query = query.where(Case.assigned_to == user.id)
    elif assignee == "unassigned":
        query = query.where(Case.assigned_to.is_(None))
    elif assignee:
        raise DomainError("Unknown assignee filter", 422)
    if priority:
        query = query.where(Case.priority == priority)
    if sort not in ("newest", "oldest", "name"):
        raise DomainError("Unknown case sort", 422)
    query = query.order_by(Case.created_at.asc() if sort == "oldest" else Case.created_at.desc(), Case.id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    # Profile fields are encrypted. Search/name sort decrypt only inside the authorised API.
    if q or sort == "name":
        rows = db.scalars(query).all()
        rows = [
            r
            for r in rows
            if not q
            or q.lower() in f"{r.profile['name']} {r.core_request_id} {r.profile.get('postcode', '')}".lower()
        ]
        if sort == "name":
            rows.sort(key=lambda r: (r.profile["name"].casefold(), r.id))
        total = len(rows)
        rows = rows[offset : offset + limit] if limit else rows
    else:
        rows = db.scalars(query.offset(offset).limit(limit) if limit else query).all()
    items = [
        {
            "id": r.id,
            **r.profile,
            "state": r.state,
            "assigned_to": r.assigned_to,
            "priority": r.priority,
            "created_at": r.created_at,
            "version": r.version,
        }
        for r in rows
    ]
    if not limit:
        return items
    summary = dict(db.execute(select(Case.state, func.count()).group_by(Case.state)).all())
    return {
        "items": items,
        "total": total,
        "summary": summary,
        "next_offset": offset + len(items) if offset + len(items) < total else None,
    }
