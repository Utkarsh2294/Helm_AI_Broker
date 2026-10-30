"""Typed broker boundary around the supplied, separately tested pure engine."""

from helm_engine import engine as E


def context(needs, tax_rate=0.12):
    return {
        "budgetAnnualPence": needs.budget_annual_pence,
        "hardBudgetCapPence": needs.hard_budget_cap,
        "bench": {"p10": needs.reference_low_pence, "p90": needs.reference_high_pence},
        "desiredCoverage": {
            key: {"level": value.level, "importance": value.importance, "mustHave": value.must_have}
            for key, value in needs.coverage.items()
        },
        "desiredHospitalLevel": needs.hospital_level,
        "preferredUnderwriting": needs.preferred_underwriting,
        "allowedUnderwriting": needs.allowed_underwriting,
        "iptRate": float(tax_rate),
        "maxSeverity": 10,
    }


def weights(priorities):
    # The reference assigns only 15% mass to an empty list. Preserve the broker
    # boundary's neutral, normalised policy when no order has been supplied.
    return E.user_weights(priorities) if priorities else dict.fromkeys(E.CRITERIA, 1 / len(E.CRITERIA))


def utilities(plan, needs):
    result = E.utilities(plan.model_dump(), context(needs))
    if not sum(need.importance for need in needs.coverage.values()):
        result["coverage"] = 0.5
    return {criterion: result[criterion] for criterion in E.CRITERIA}


def aggregate(utilities, weights):
    result = E.aggregate(utilities, weights)
    return result["score"], result["fit"], result["balance"]
