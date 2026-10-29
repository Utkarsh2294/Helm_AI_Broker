import copy

MEDICAL_ROLES = {"authorised_broker", "compliance_officer"}


def safe_case(data, user, include_medical=False):
    result = copy.deepcopy(data)
    if not (include_medical and user.role in MEDICAL_ROLES):
        def redact(value):
            if isinstance(value, dict):
                return {key: (["[REDACTED]"] * len(item) if key == "medical_items" and isinstance(item, list)
                              else redact(item)) for key, item in value.items()}
            if isinstance(value, list):
                return [redact(item) for item in value]
            return value
        result = redact(result)
    return result


def llm_profile(request):
    """An allow-list, not a deny-list. Free-text/medical fields never enter model context."""
    return {"cover_type": request.cover_type, "needs": request.needs.model_dump(),
            "requires_clinical_underwriting": bool(request.medical_items)}


VULNERABILITY = {
    "health": ["terminal", "disability", "carer", "bereavement"],
    "life_events": ["divorce", "redundancy", "recently bereaved", "new diagnosis"],
    "resilience": ["struggling financially", "on benefits", "low income"],
    "capability": ["hard to read", "dyslexia", "english not first language", "someone helping me"],
}


def screen_vulnerability(text):
    return [category for category, words in VULNERABILITY.items() if any(word in text.lower() for word in words)]


def possible_complaint(text):
    return any(word in text.lower() for word in ("complaint", "unhappy", "dissatisfied", "let down", "not satisfied", "unfair", "disappointed"))
