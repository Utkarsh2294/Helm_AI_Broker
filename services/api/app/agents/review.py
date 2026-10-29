"""A4: selection validation and draft pack assembly. This agent cannot approve."""
import hashlib
import json
from app.schemas import DNR, DomainError, Survey


def canonical_hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def assemble_pack(dnr: DNR, ranking: dict, selected: list[str], survey: Survey,
                  acknowledgements: list[str], suitability: str | None = None) -> dict:
    available = {r["plan"]["id"]: r for r in ranking["top"]}
    if len(selected) != 3 or len(set(selected)) != 3 or set(selected) - set(available):
        raise DomainError("Select three distinct plans from this ranking's top five", 422)
    if set(survey.thumbs) != set(selected):
        raise DomainError("Give thumbs up or down for each selected plan", 422)
    if ranking["top"][0]["plan"]["id"] not in selected and not survey.omitted_first_reason.strip():
        raise DomainError("Explain why the engine's first plan was omitted", 422)
    for plan_id in selected:
        row = available[plan_id]
        if row["blockers"] and plan_id not in acknowledgements:
            raise DomainError("Acknowledge the outstanding blockers for each selected plan", 422)
        if not row["plan"]["ipidUrl"].startswith("https://") or not row["plan"]["ipidVersion"]:
            raise DomainError("A versioned HTTPS IPID is required for every plan", 422)
    chosen = [available[p] for p in selected]
    unmet = [{"plan_id": r["plan"]["id"], "need": k}
             for r in chosen for k, v in dnr.needs.coverage.items() if r["plan"]["coverage"].get(k, 0) < v.level]
    draft = ("Draft for broker review. The customer prioritised " + ", ".join(dnr.needs.priorities) +
             f" with an annual budget of £{dnr.needs.budget_annual_pence / 100:,.2f}. " +
             "The selected plans balance these priorities using the recorded score breakdown. " +
             ("Unmet needs are listed in the pack. " if unmet else "The recorded coverage levels meet the stated targets. ") +
             "Medical cover remains subject to the insurer's underwriting and policy terms.")
    baseline = sum(r["plan"]["commissionPct"] for r in ranking["top"][:3]) / 3
    selected_commission = sum(r["plan"]["commissionPct"] for r in chosen) / 3
    body = {
        "ranking_id": ranking["id"], "inputs_hash": ranking["inputs_hash"],
        "dnr_version": dnr.version, "selected": selected, "plans": chosen,
        "survey": survey.model_dump(), "acknowledgements": acknowledgements,
        "suitability_draft": draft, "suitability_final": suitability.strip() if suitability else draft,
        "unmet_needs": unmet, "search_basis": "Fictional panel of five insurers (demo)",
        "rule_pack_version": "demo-pending-compliance-v1",
        "cancellation_notice": "Cancellation wording must be verified before live publication.",
        "remuneration": "Commission is disclosed separately and is excluded from ranking inputs.",
        "commission_deviation": selected_commission - baseline > 3,
        "medical_notice": "No conclusion about cover for any medical condition has been made.",
        "demo": True,
    }
    return {**body, "pack_hash": canonical_hash(body)}
