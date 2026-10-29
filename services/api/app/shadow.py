from sqlalchemy import select
from app.db.platform import EngineModel, ShadowEvaluation
from app.agents.runtime import run_agent
from app.config import settings
from app.governance import champion


def rank_with_models(db, payload):
    current = champion(db)
    result = run_agent("ranking", {**payload, "learned": current.weights if current.version != "user-v1" else None}, settings().agent_runtime)
    result["weights_version"] = current.version
    challenger = db.scalar(select(EngineModel).where(EngineModel.status == "challenger"))
    if challenger and not db.scalar(
        select(ShadowEvaluation).where(
            ShadowEvaluation.model_id == challenger.id, ShadowEvaluation.case_id == payload["case_id"]
        )
    ):
        hidden = run_agent("ranking", {**payload, "id": payload["id"] + "-shadow", "learned": challenger.weights}, settings().agent_runtime)
        db.add(
            ShadowEvaluation(
                model_id=challenger.id,
                case_id=payload["case_id"],
                body={
                    "ranking_id": result["id"],
                    "champion_version": current.version,
                    "champion": [r["plan"]["id"] for r in result["top"]],
                    "challenger": [r["plan"]["id"] for r in hidden["top"]],
                },
            )
        )
    return result
