"""Source-bound local demo templates; no medical answers or banking inputs."""

from app.clock import get_clock

WATERMARK = "DEMO — NOT A REAL POLICY DOCUMENT"
MORATORIUM_STATEMENT = "I understand that any medical condition present, symptomatic, or treated in the last 5 years will be excluded from cover until I have been completely free of treatment, medication, and advice for that condition for a continuous period of 2 full years after the policy starts."
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


def moratorium(buying, name):
    return {
        "title": "Moratorium Declaration",
        "demo": True,
        "watermark": WATERMARK,
        "sections": [
            section(
                "Consumer and policy reference",
                f"Fictional consumer: {name}. Quote: {buying.selected_plan_id}. Demo only; no policy is in force.",
            ),
            section("Underwriting declaration", MORATORIUM_STATEMENT),
            section(
                "What this means",
                "In this fictional illustration, a related claim may fall outside cover during the exclusion window. Only insurer terms and underwriting determine actual cover. Review the underwriting baseline and ask the broker if unclear.",
            ),
            section(
                "Signature",
                "A fresh explicit demo acceptance is required for this document version. No real electronic signature or insurance contract is created. The broker must review and sign off afterwards.",
            ),
        ],
    }


def toba():
    return {
        "title": "Terms of Business Agreement",
        "demo": True,
        "watermark": WATERMARK,
        "sections": [
            section(
                "Who we are",
                "Helm Demonstration Brokerage is a fictional firm. FCA reference: DEMO-NOT-REGISTERED. This fixture does not claim FCA authorisation or permission to conduct real insurance distribution.",
            ),
            section(
                "Our service",
                "This fictional advised service compares a panel of five demo insurers against the consumer's stated requirements. It is not a whole-market search. A human broker selects recommendations and signs off advice.",
            ),
            section(
                "How we are paid",
                "In the illustrative model, remuneration may include commission paid by an insurer. Its nature is disclosed separately. Commission does not influence policy ranking. No real fee or payment is collected in this demonstration.",
            ),
            section(
                "Client money",
                "Helm does not hold client money. Any real premium would be paid directly to the insurer under separately approved arrangements. The banking steps here use fictional fixtures only.",
            ),
            section(
                "Complaints",
                "For this demo, contact complaints@helm.example to see the fictional route; no email is sent. In a real eligible insurance complaint, a firm generally has eight weeks to respond. A consumer can refer an unhappy final response, or a complaint without a response after the applicable deadline, to the Financial Ombudsman Service. Normally refer within six months of the final response. Official contact and eligibility details: https://www.financial-ombudsman.org.uk/consumers/how-to-complain . No real complaint is submitted by this fixture.",
            ),
            section(
                "Cancellation and duration",
                "This illustrative standing agreement continues for the policy relationship until replaced. You may end the broker relationship by contacting the broker. Separate insurer policy cancellation terms apply. This demo creates no binding agreement.",
            ),
            section(
                "Data protection",
                "The prototype uses fictional records. Real processing would require an approved UK GDPR privacy notice, lawful basis, special-category safeguards and retention rules. See the demonstration DPIA in Pilot showcase; it is not a production privacy notice.",
            ),
        ],
    }


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
