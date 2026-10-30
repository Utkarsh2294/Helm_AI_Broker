from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import select, func
from app.auth import identity
from app.db.platform import EngineModel, EdgeCase, Playbook, GovernanceEvent
from app.db.models import Case
from app.case_access import visible_cases
from app.main import database
from app.schemas import DomainError, Model
from app import governance

router = APIRouter(prefix="/api/v1")


@router.get("/governance")
def dashboard(request: Request, db=Depends(database, scope="function")):
    identity(db, request)
    return {
        "models": [
            {
                "id": m.id,
                "version": m.version,
                "status": m.status,
                "proposal_id": m.proposal_id,
                "metrics": governance.shadow_metrics(db, m),
            }
            for m in db.scalars(select(EngineModel))
        ],
        "events": [
            {"action": e.action, "created_at": e.created_at, **e.body}
            for e in db.scalars(
                select(GovernanceEvent).order_by(GovernanceEvent.created_at.desc()).limit(100)
            )
        ],
    }


@router.post("/mcr/{proposal_id}/{action}")
def decide(proposal_id: str, action: str, request: Request, db=Depends(database, scope="function")):
    from app.auth.router import credential_access

    user, proof = credential_access(db, request)
    governance.governance_role(user)
    proof.consumed = True
    if action == "approve":
        return governance.approve_shadow(db, proposal_id, user)
    if action == "promote":
        return governance.promote(db, proposal_id, user)
    raise DomainError("Unknown governance action", 404)


@router.post("/engine-models/{model_id}/rollback")
def rollback(model_id: str, request: Request, db=Depends(database, scope="function")):
    from app.auth.router import credential_access

    user, proof = credential_access(db, request)
    proof.consumed = True
    return governance.rollback(db, model_id, user)


@router.get("/edge-cases")
def notebook(request: Request, db=Depends(database, scope="function")):
    from app.compliance.medical_firewall import safe_case
    from app.db.store import latest

    user, _ = identity(db, request)
    result = []
    for row in db.scalars(
        select(EdgeCase)
        .join(Case, EdgeCase.case_id == Case.id)
        .where(visible_cases(user))
        .order_by(EdgeCase.created_at.desc())
        .limit(200)
    ):
        dnr = latest(db, row.case_id, "dnr")
        safe = safe_case(
            {
                "dnr": dnr.body if dnr else {},
                "entry": {
                    "id": row.id,
                    "case_id": row.case_id,
                    "status": row.status,
                    "created_at": row.created_at,
                    **row.body,
                },
            },
            user,
        )
        result.append(safe["entry"])
    return result


class NotebookReview(Model):
    finding: str = Field(min_length=10, max_length=2000)


@router.patch("/edge-cases/{edge_id}")
def review_edge(edge_id: str, body: NotebookReview, request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    governance.governance_role(user)
    row = db.get(EdgeCase, edge_id)
    if not row:
        raise DomainError("Notebook entry not found", 404)
    from app.service import get_case

    get_case(db, row.case_id)
    if len(body.finding.strip()) < 10:
        raise DomainError("Record the review in at least 10 characters", 422)
    row.body, row.status = {**row.body, "finding": body.finding, "reviewer": user.id}, "reviewed"
    governance.event(db, user, "edge_case_reviewed", {"edge_id": row.id})
    return {"status": row.status}


class PlaybookDraft(Model):
    scope: str = Field(min_length=3, max_length=100)
    guidance: str = Field(min_length=20, max_length=3000)


@router.get("/playbooks")
def playbooks(request: Request, db=Depends(database, scope="function")):
    identity(db, request)
    return [
        {"id": p.id, "scope": p.scope, "version": p.version, "approved_by": p.approved_by, **p.body}
        for p in db.scalars(select(Playbook).order_by(Playbook.scope, Playbook.version.desc()))
    ]


@router.post("/playbooks")
def create_playbook(body: PlaybookDraft, request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    if user.role not in ("authorised_broker", "compliance_officer"):
        raise DomainError("Only advisers and compliance may draft guidance", 403)
    version = (db.scalar(select(func.max(Playbook.version)).where(Playbook.scope == body.scope)) or 0) + 1
    row = Playbook(scope=body.scope, version=version, body={"guidance": body.guidance}, created_by=user.id)
    db.add(row)
    db.flush()
    governance.event(db, user, "playbook_drafted", {"id": row.id, "version": version})
    return {"id": row.id, "version": version}


@router.post("/playbooks/{playbook_id}/approve")
def approve_playbook(playbook_id: str, request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    row = db.get(Playbook, playbook_id)
    if not row:
        raise DomainError("Playbook not found", 404)
    if user.role != "compliance_officer" or user.id == row.created_by:
        raise DomainError("A separate compliance reviewer must approve guidance", 403)
    row.approved_by = user.id
    governance.event(db, user, "playbook_approved", {"id": row.id})
    return {"approved": True}
