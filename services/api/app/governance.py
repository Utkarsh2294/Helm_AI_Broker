"""G5: independent approvals, invisible shadow scores and explicit promotion/rollback."""

import math
from sqlalchemy import select
from app.config import settings
from app.db.models import ModelProposal
from app.db.platform import EngineModel, ModelApproval, ShadowEvaluation, GovernanceEvent
from app.db.store import latest
from app.engine.ranking import user_weights
from app.schemas import DomainError


def governance_role(user):
    if user.role == "compliance_officer":
        return "compliance_officer"
    if user.role == "authorised_broker" and user.is_lead_broker:
        return "lead_broker"
    raise DomainError("G5 requires compliance or a designated lead broker", 403)


def champion(db):
    model = db.scalar(select(EngineModel).where(EngineModel.status == "champion").with_for_update())
    if model:
        return model
    model = EngineModel(version="user-v1", weights=user_weights([]), status="champion")
    db.add(model)
    db.flush()
    return model


def event(db, user, action, body):
    db.add(GovernanceEvent(actor=user.id, action=action, body=body))


def approval(db, proposal_id, stage, user):
    role = governance_role(user)
    proposal = db.scalar(select(ModelProposal).where(ModelProposal.id == proposal_id).with_for_update())
    if not proposal:
        raise DomainError("Model change request not found", 404)
    if proposal.body.get("proposed_by") == user.id:
        raise DomainError("The proposer cannot approve their own model change", 403)
    if proposal.status != ("proposed" if stage == "shadow" else "shadow_mode"):
        raise DomainError("This proposal is not awaiting this approval stage", 409)
    if not proposal.body.get("eligible_for_shadow"):
        raise DomainError("Held-out results must improve before G5 approval")
    old, new = proposal.body.get("champion_metrics", {}), proposal.body.get("challenger_metrics", {})
    if (
        not old.get("cases")
        or not new.get("cases")
        or new.get("ndcg3", 0) - old.get("ndcg3", 0) + 1e-12 < 0.02
        or new.get("top3_agreement", 0) < old.get("top3_agreement", 0)
    ):
        raise DomainError("Verified held-out NDCG@3 improvement of at least 0.02 is required")
    if proposal.body.get("champion_version", champion(db).version) != champion(db).version:
        raise DomainError("Champion changed; rerun evaluation before G5 approval")
    rows = db.scalars(
        select(ModelApproval).where(ModelApproval.proposal_id == proposal_id, ModelApproval.stage == stage)
    ).all()
    if any(r.user_id == user.id or r.role == role for r in rows):
        raise DomainError("This role already approved; a second independent person is required", 403)
    if role == "lead_broker" and not any(r.role == "compliance_officer" for r in rows):
        raise DomainError("Compliance must approve before the lead broker")
    db.add(ModelApproval(proposal_id=proposal_id, stage=stage, user_id=user.id, role=role))
    event(db, user, f"G5_{stage}", {"proposal_id": proposal_id, "role": role})
    return proposal, {r.role for r in rows} | {role}


def approve_shadow(db, proposal_id, user):
    proposal, roles = approval(db, proposal_id, "shadow", user)
    if len(roles) == 2:
        champion(db)
        if db.scalar(select(EngineModel).where(EngineModel.status == "challenger")):
            raise DomainError("Finish the existing shadow evaluation before starting another")
        db.add(
            EngineModel(
                version=f"mcr-{proposal.id}",
                weights=proposal.body["weights"],
                status="challenger",
                proposal_id=proposal.id,
            )
        )
        proposal.status = "shadow_mode"
    return {"status": proposal.status, "roles": sorted(roles)}


def ndcg(order, selected):
    relevance = {pid: 3 - i for i, pid in enumerate(selected)}
    ideal = sum((2**r - 1) / math.log2(i + 2) for i, r in enumerate((3, 2, 1)))
    return sum((2 ** relevance.get(pid, 0) - 1) / math.log2(i + 2) for i, pid in enumerate(order[:3])) / ideal


def shadow_metrics(db, model):
    rows = db.scalars(select(ShadowEvaluation).where(ShadowEvaluation.model_id == model.id)).all()
    values = []
    for row in rows:
        choice = latest(db, row.case_id, "selection")
        disputed = choice and "down" in choice.body.get("survey", {}).get("thumbs", {}).values()
        if choice and not disputed and choice.body["ranking_id"] == row.body["ranking_id"]:
            selected = choice.body["selected"]
            values.append((ndcg(row.body["champion"], selected), ndcg(row.body["challenger"], selected)))
    return {
        "distinct_cases": len(rows),
        "labelled_cases": len(values),
        "champion_ndcg3": sum(v[0] for v in values) / len(values) if values else None,
        "challenger_ndcg3": sum(v[1] for v in values) / len(values) if values else None,
    }


def promote(db, proposal_id, user):
    model = db.scalar(
        select(EngineModel)
        .where(EngineModel.proposal_id == proposal_id, EngineModel.status == "challenger")
        .with_for_update()
    )
    if not model:
        raise DomainError("No challenger is in shadow mode")
    metrics = shadow_metrics(db, model)
    if metrics["labelled_cases"] < settings().shadow_case_minimum:
        raise DomainError(f"At least {settings().shadow_case_minimum} new labelled shadow cases are required")
    improvement = metrics["challenger_ndcg3"] - metrics["champion_ndcg3"]
    if improvement + 1e-12 < settings().shadow_minimum_improvement:
        raise DomainError("Shadow NDCG@3 must improve by at least 0.02 before promotion")
    proposal, roles = approval(db, proposal_id, "promote", user)
    if len(roles) == 2:
        previous = champion(db)
        previous.status = "retired"
        db.flush()
        model.previous_champion_id, model.status = previous.id, "champion"
        proposal.status = "promoted"
        event(db, user, "model_promoted", {"model_id": model.id, **metrics})
    return {"status": proposal.status, "roles": sorted(roles), "metrics": metrics}


def rollback(db, model_id, user, reason=""):
    if user.role != "compliance_officer":
        raise DomainError("Compliance must authorize rollback", 403)
    model = champion(db)
    if model.id != model_id or not model.previous_champion_id:
        raise DomainError("This model has no active promotion to roll back")
    if len(reason.strip()) < 20:
        raise DomainError("Record a rollback reason of at least 20 characters", 422)
    previous = db.get(EngineModel, model.previous_champion_id)
    model.status = "retired"
    db.flush()
    previous.status = "champion"
    from app.agents.review import canonical_hash

    proposal = db.get(ModelProposal, model.proposal_id)
    if proposal:
        proposal.status = "rolled_back"
        proposal.body = {**proposal.body, "rollback": {"reason": reason.strip(), "by": user.id}}
    event(
        db,
        user,
        "model_rolled_back",
        {"from": model.id, "to": previous.id, "reason_hash": canonical_hash(reason.strip())},
    )
    return {"champion": previous.version}


def reject(db, proposal_id, user, reason):
    governance_role(user)
    proposal = db.scalar(select(ModelProposal).where(ModelProposal.id == proposal_id).with_for_update())
    if not proposal:
        raise DomainError("Model change request not found", 404)
    if proposal.status not in {"proposed", "shadow_mode"}:
        raise DomainError("This proposal cannot be rejected at its current stage", 409)
    if len(reason.strip()) < 20:
        raise DomainError("Record a rejection reason of at least 20 characters", 422)
    model = db.scalar(
        select(EngineModel).where(EngineModel.proposal_id == proposal_id, EngineModel.status == "challenger")
    )
    if model:
        model.status = "retired"
    proposal.status = "rejected"
    proposal.body = {**proposal.body, "rejection": {"reason": reason.strip(), "by": user.id}}
    from app.agents.review import canonical_hash

    event(
        db,
        user,
        "model_rejected",
        {"proposal_id": proposal.id, "reason_hash": canonical_hash(reason.strip())},
    )
    return {"status": "rejected"}
