"""Narration of recorded numeric inputs; no model changes scores or clinical meaning."""


def explain(plan, needs, overall):
    met = sum(plan.coverage.get(key, 0) >= need.level for key, need in needs.coverage.items())
    coverage = "; ".join(
        f"{key}: recorded level {plan.coverage.get(key, 0)}, requested {need.level}"
        for key, need in sorted(needs.coverage.items())
    )
    stats = plan.insurerStats
    shrunk = (stats.n * stats.upheldRate + 30 * 0.25) / (stats.n + 30)
    return {
        "affordability": f"Annual premium £{plan.annualPremiumPence / 100:.2f}; annual budget headroom £{(needs.budget_annual_pence - plan.annualPremiumPence) / 100:.2f}. Affordability uses the fixed £{needs.reference_low_pence / 100:.2f}–£{needs.reference_high_pence / 100:.2f} reference band and expected excess cost.",
        "coverage": f"Meets {met} of {len(needs.coverage)} requested benefit levels. {coverage}.",
        "network": f"Recorded preferred-hospital share {plan.preferredHospitalShare:.0%}; hospital list level {plan.hospitalListLevel} against requested level {needs.hospital_level}.",
        "underwriting": f"{plan.underwritingType}; "
        + ("matches" if plan.underwritingType == needs.preferred_underwriting else "differs from")
        + f" the stated preference {needs.preferred_underwriting}. No medical interpretation is made.",
        "insurer_quality": f"Fixture uphold rate after shrinkage {shrunk:.1%} (n={stats.n}, prior count 30). Recorded financial-strength score {stats.finStrength:.0%} and service score {stats.slaScore:.0%}.",
        "process_ease": f"{plan.docsRequired} documents required; {plan.docsUnavailable} unavailable. Recorded turnaround {plan.turnaroundDays:g} days.",
        "terms_clarity": f"IPID completeness {plan.ipidCompleteness:.0%}; plain-language score {plan.plainLanguage:.0%}; {plan.exclusionsCount} recorded exclusions.",
        "overall": overall,
    }
