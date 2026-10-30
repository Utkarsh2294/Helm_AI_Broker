from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy import select, func, or_, and_
from app.auth import identity
from app.db.models import Case
from app.main import database
from app.schemas import DomainError
from app.case_access import visible_cases
from app.cursors import encode_cursor, decode_cursor, filter_hash

router = APIRouter(prefix="/api/v1")


@router.get("/cases")
def cases(
    request: Request,
    q: str = Query("", max_length=200),
    state: str = "",
    assignee: str = "",
    priority: str = "",
    sort: str = "newest",
    limit: int = Query(0, ge=0, le=200),
    offset: int = Query(0, ge=0),
    cursor: str = Query("", max_length=2048),
    db=Depends(database, scope="function"),
):
    user, _ = identity(db, request)
    scope = visible_cases(user)
    query = select(Case).where(scope)
    binding = filter_hash([user.id, q, state, assignee, priority, sort])
    position = decode_cursor(cursor, binding) if cursor else None
    if cursor and offset:
        raise DomainError("Use a cursor or an offset, not both", 422)
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
    more = False
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
        if position:
            if sort == "name":
                rows = [r for r in rows if (r.profile["name"].casefold(), r.id) > (position[2], position[1])]
            elif sort == "oldest":
                rows = [r for r in rows if (r.created_at, r.id) > (position[0], position[1])]
            else:
                rows = [
                    r
                    for r in rows
                    if r.created_at < position[0] or (r.created_at == position[0] and r.id > position[1])
                ]
        more = bool(limit and len(rows) > offset + limit)
        rows = rows[offset : offset + limit] if limit else rows
    else:
        if position:
            comparison = Case.created_at > position[0] if sort == "oldest" else Case.created_at < position[0]
            query = query.where(or_(comparison, and_(Case.created_at == position[0], Case.id > position[1])))
        rows = db.scalars(query.offset(offset).limit(limit + 1) if limit else query).all()
        more = bool(limit and len(rows) > limit)
        rows = rows[:limit] if limit else rows
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
    summary = dict(db.execute(select(Case.state, func.count()).where(scope).group_by(Case.state)).all())
    return {
        "items": items,
        "total": total,
        "summary": summary,
        "next_offset": offset + len(items) if more else None,
        "next_cursor": encode_cursor(
            [rows[-1].created_at, rows[-1].id, rows[-1].profile["name"].casefold()], binding
        )
        if more and rows
        else None,
    }
