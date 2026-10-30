import copy
import re

MEDICAL_ROLES = {"authorised_broker", "compliance_officer"}


def safe_case(data, user, include_medical=False):
    result = copy.deepcopy(data)
    if user.role not in MEDICAL_ROLES:

        def hide_links(value):
            if isinstance(value, dict):
                return {k: "[REDACTED]" if k == "magic_link" else hide_links(v) for k, v in value.items()}
            if isinstance(value, list):
                return [hide_links(v) for v in value]
            return value

        result = hide_links(result)
    if not (include_medical and user.role in MEDICAL_ROLES):
        texts = set()

        def gather(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "medical_items" and isinstance(item, list):
                        for medical in item:
                            text = medical.get("text") if isinstance(medical, dict) else medical
                            if isinstance(text, str) and text and text != "[REDACTED]":
                                texts.add(text)
                    gather(item)
            elif isinstance(value, list):
                for item in value:
                    gather(item)

        gather(result)
        pattern = (
            re.compile("|".join(re.escape(t) for t in sorted(texts, key=len, reverse=True)), re.IGNORECASE)
            if texts
            else None
        )

        def redact(value):
            if isinstance(value, dict):
                if value.get("kind") in {
                    "medical_review",
                    "broker_pause",
                    "broker_referral",
                    "referral_resolution",
                } and isinstance(value.get("body"), dict):
                    value = {**value, "body": {**value["body"], "reason": "[REDACTED]"}}
                return {
                    key: (
                        ["[REDACTED]"] * len(item)
                        if key == "medical_items" and isinstance(item, list)
                        else {**redact(item), "reason": "[REDACTED]"}
                        if key in {"medical_review", "broker_referral", "referral_resolution"}
                        and isinstance(item, dict)
                        else redact(item)
                    )
                    for key, item in value.items()
                }
            if isinstance(value, list):
                return [redact(item) for item in value]
            if isinstance(value, str) and pattern:
                return pattern.sub("[REDACTED]", value)
            return value

        result = redact(result)
    return result


def llm_profile(request):
    """An allow-list, not a deny-list. Free-text/medical fields never enter model context."""
    return {
        "cover_type": request.cover_type,
        "needs": request.needs.model_dump(),
        "requires_clinical_underwriting": bool(request.medical_items),
    }


VULNERABILITY = {
    "health": ["terminal", "disability", "carer", "bereavement"],
    "life_events": ["divorce", "redundancy", "recently bereaved", "new diagnosis"],
    "resilience": ["struggling financially", "on benefits", "low income"],
    "capability": ["hard to read", "dyslexia", "english not first language", "someone helping me"],
}


def screen_vulnerability(text):
    return [
        category for category, words in VULNERABILITY.items() if any(word in text.lower() for word in words)
    ]


def possible_complaint(text):
    return any(
        word in text.lower()
        for word in (
            "complaint",
            "unhappy",
            "dissatisfied",
            "let down",
            "not satisfied",
            "unfair",
            "disappointed",
        )
    )
