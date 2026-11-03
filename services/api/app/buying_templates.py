"""Source-bound local demo templates; no medical answers or banking inputs."""

from app.clock import get_clock

WATERMARK = "DEMO — NOT A REAL POLICY DOCUMENT"
IPID_HEADINGS = (
    "Insurer and product",
    "What is this type of insurance?",
    "What is insured?",
    "What is not insured?",
    "Are there any restrictions on cover?",
    "Where am I covered?",
    "What are my obligations?",
    "When and how do I pay?",
    "When does the cover start and end?",
    "How do I cancel the contract?",
)


def section(heading, text):
    return {"heading": heading, "text": text}


def illustrative_start():
    return get_clock().now().date().isoformat()


def ipid(buying):
    plan = buying.body["plan"]
    premium, excess = plan["annualPremiumPence"] / 100, plan.get("excessPence", 0) / 100
    limits = "; ".join(
        f"{key.replace('_', ' ').capitalize()}: fictional benefit level {value}/3"
        for key, value in sorted(plan.get("coverage", {}).items())
    )
    exclusion = (
        "Moratorium underwriting applies. The fictional five-year/two-year declaration explains the pre-existing-condition exclusion."
        if buying.underwriting_basis == "moratorium"
        else "Full Medical Underwriting (FMU) applies. Fresh answers are required; only the insurer can decide personal exclusions. No medical eligibility is inferred."
    )
    start = buying.body.get("illustrative_start", illustrative_start())
    texts = [
        f"Fictional insurer: {plan['insurerId']}. Product: {plan['name']}. Quote: {plan['id']}. This is a demo summary, not an insurer-issued IPID.",
        "Private medical insurance is intended to help pay for eligible private treatment, subject to insurer terms, benefit limits and underwriting.",
        f"{limits}. Monetary limits are not supplied in this quote; check the insurer's policy wording.",
        f"{exclusion} No cover for any condition is promised by this demo; actual policy wording determines exclusions.",
        f"Recorded excess GBP {excess:,.2f}. Hospital list level {plan.get('hospitalListLevel', 'not supplied')}. Network, referral and waiting-period rules need the insurer's wording; missing rules are not assumed.",
        "Illustrative demo geography: UK private treatment only. No overseas benefit is promised by this fixture.",
        "Take reasonable care to answer insurer questions accurately, disclose relevant changes when requested, follow authorisation requirements and pay premiums. Ask the broker about unclear terms.",
        f"Illustrative annual premium GBP {premium:,.2f}, including IPT. Annual payment directly to the fictional insurer; Helm does not hold client money. Banking consent is separately simulated.",
        f"Illustrative start: {start}. Illustrative term: one year, subject to insurer acceptance. No cover starts in this demo and no real waiting period is waived.",
        "Demo wording: a 14-day cancellation right may apply to general insurance. Timing depends on contract conclusion and receipt of required information; exceptions and charges depend on actual terms. Contact the insurer or broker. This fixture does not exercise a real cancellation right.",
    ]
    return {
        "title": "Insurance Product Information Document",
        "demo": True,
        "watermark": WATERMARK,
        "sections": [section(heading, text) for heading, text in zip(IPID_HEADINGS, texts)],
        "source": "Published quote and original fact-find; demo wording, not regulatory approval",
    }
