from sqlalchemy import select
from app.db.platform import EngineModel, ShadowEvaluation
from app.schemas import DNR, Plan
from app.agents.ranking import rank_quotes
from app.governance import champion
from decimal import Decimal


def rank_with_models(db, payload):
    current = champion(db)
    dnr, plans = DNR.model_validate(payload["dnr"]), [Plan.model_validate(p) for p in payload["quotes"]]
    result = rank_quotes(
        dnr,
        plans,
        payload["id"],
        learned=current.weights if current.version != "user-v1" else None,
        tax_rate=Decimal(payload["tax_rate"]),
    )
    result["weights_version"] = current.version
    challenger = db.scalar(select(EngineModel).where(EngineModel.status == "challenger"))
    if challenger and not db.scalar(
        select(ShadowEvaluation).where(
            ShadowEvaluation.model_id == challenger.id, ShadowEvaluation.case_id == payload["case_id"]
        )
    ):
        hidden = rank_quotes(
            dnr,
            plans,
            payload["id"] + "-shadow",
            learned=challenger.weights,
            tax_rate=Decimal(payload["tax_rate"]),
        )
        db.add(
            ShadowEvaluation(
                model_id=challenger.id,
                case_id=payload["case_id"],
                body={
                    "ranking_id": result["id"],
                    "champion": [r["plan"]["id"] for r in result["top"]],
                    "challenger": [r["plan"]["id"] for r in hidden["top"]],
                },
            )
        )
    return result
