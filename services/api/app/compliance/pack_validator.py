from app.schemas import DomainError


def validate_pack(pack):
    missing = []
    manifest = pack.get("manifest", {})
    plans = manifest.get("plans", [])
    if len(plans) != 3:
        missing.append("three_selected_plans")
    for plan in plans:
        if not plan.get("ipid_reference", {}).get("url") or not plan["ipid_reference"].get("version"):
            missing.append("C5:ipid")
        premium = plan.get("premium_breakdown", {})
        if not all(k in premium for k in ("base_pence", "ipt_pence", "annual_pence")) or abs(premium.get("annual_pence", 0) - premium.get("base_pence", 0) - premium.get("ipt_pence", 0)) > 1:
            missing.append("C7:premium_breakdown")
        if plan.get("toba_reference", {}).get("status") != "active":
            missing.append("C9:toba")
    if not manifest.get("cancellation_notice", {}).get("basis"):
        missing.append("C6:cancellation")
    if not manifest.get("remuneration_panel", {}).get("fair_value_statement"):
        missing.append("C8:remuneration")
    if not manifest.get("search_basis_statement", {}).get("partner_count"):
        missing.append("C10:search_basis")
    if missing:
        raise DomainError("Pack validation failed: " + ", ".join(missing), 422)
    return True
