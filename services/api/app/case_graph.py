"""Explicit workflow events. Guard names are enforced by the transactional service."""

GRAPH = {
    "RECEIVED": {"intake_started": ("INTAKE_RUNNING", None)},
    "INTAKE_RUNNING": {"intake_completed": ("FACTFIND_REVIEW", None), "missing_info": ("NEEDS_INFO", None)},
    "NEEDS_INFO": {"info_received": ("INTAKE_RUNNING", "broker")},
    "FACTFIND_REVIEW": {"dnr_signed_off": ("RFQ_DRAFTING", "G0")},
    "RFQ_DRAFTING": {"rfq_drafted": ("RFQ_RELEASE_CHECK", None)},
    "RFQ_RELEASE_CHECK": {"release_check_completed": ("AWAIT_BROKER_RELEASE", None)},
    "AWAIT_BROKER_RELEASE": {"rfq_released": ("QUOTES_PENDING", "G1")},
    "QUOTES_PENDING": {
        "quotes_collected": ("QUOTES_COLLECTED", None),
        "partner_referred": ("UW_REFERRAL", None),
    },
    "QUOTES_COLLECTED": {"ranking_started": ("RANKING", None)},
    "RANKING": {"ranking_completed": ("BROKER_REVIEW", None)},
    "BROKER_REVIEW": {"review_started": ("SUITABILITY_DRAFT", "broker")},
    "SUITABILITY_DRAFT": {"pack_drafted": ("AWAIT_APPROVAL", None)},
    "AWAIT_APPROVAL": {"published": ("PUBLISHED", "G2"), "changes_requested": ("BROKER_REVIEW", "broker")},
    "PUBLISHED": {"closed": ("CLOSED", "broker")},
    "UW_REFERRAL": {"referral_resolved": ("QUOTES_PENDING", "G3")},
    "PAUSED_NEEDS_HUMAN": {},
    "COMPLAINT_FLAGGED": {},
    "CLOSED": {},
}


def permits(source, target, event):
    if event == "consumer_requirements_updated":
        return source not in {"PUBLISHED", "CLOSED", "COMPLAINT_FLAGGED"} and target == "INTAKE_RUNNING"
    if event == "core_request_withdrawn":
        return source not in {"CLOSED", "COMPLAINT_FLAGGED"} and target == "CLOSED"
    if target in {item[0] for item in GRAPH.get(source, {}).values()}:
        return True
    if event == "broker_paused":
        return target == "PAUSED_NEEDS_HUMAN" and source not in {"PUBLISHED", "CLOSED", "COMPLAINT_FLAGGED"}
    if event == "partner_panel_unavailable":
        return source in {"AWAIT_BROKER_RELEASE", "QUOTES_PENDING"} and target == "PAUSED_NEEDS_HUMAN"
    if event == "complaint_flagged":
        return target == "COMPLAINT_FLAGGED" and source not in {"CLOSED", "COMPLAINT_FLAGGED"}
    if event == "broker_resumed":
        return source == "PAUSED_NEEDS_HUMAN" and target not in {"PUBLISHED", "CLOSED", "COMPLAINT_FLAGGED"}
    if event == "complaint_resolved":
        return source == "COMPLAINT_FLAGGED" and target != "COMPLAINT_FLAGGED"
    if event in {"consumer_declined", "POLICY_BOUND"}:
        return source == "PUBLISHED" and target == "CLOSED"
    if event == "no_suitable_plans":
        return source == "BROKER_REVIEW" and target == "CLOSED"
    if event == "broker_referral_requested":
        return source == "BROKER_REVIEW" and target == "UW_REFERRAL"
    if event == "broker_referral_resolved":
        return source == "UW_REFERRAL" and target == "BROKER_REVIEW"
    if event == "medical_review_recorded":
        return source in {"PAUSED_NEEDS_HUMAN", "NEEDS_INFO", "FACTFIND_REVIEW"} and target in {
            "FACTFIND_REVIEW",
            "NEEDS_INFO",
        }
    if event == "dnr_revised":
        return source in {"NEEDS_INFO", "FACTFIND_REVIEW", "AWAIT_BROKER_RELEASE"} and target in {
            "NEEDS_INFO",
            "FACTFIND_REVIEW",
        }
    return (source, target) in {
        ("INTAKE_RUNNING", "NEEDS_INFO"),
        ("INTAKE_RUNNING", "PAUSED_NEEDS_HUMAN"),
        ("QUOTES_PENDING", "UW_REFERRAL"),
        ("QUOTES_PENDING", "PAUSED_NEEDS_HUMAN"),
        ("RANKING", "PAUSED_NEEDS_HUMAN"),
        ("AWAIT_APPROVAL", "PAUSED_NEEDS_HUMAN"),
        ("PAUSED_NEEDS_HUMAN", "QUOTES_PENDING"),
        ("BROKER_REVIEW", "RANKING"),
    }


HALTS = {
    "H1": "Invalid structured output",
    "H2": "Low confidence in a required field",
    "H3": "Premium arithmetic mismatch",
    "H4": "Contradictory partner revisions",
    "H5": "Ambiguous medical wording",
    "H6": "Missing or expired consent",
    "H7": "Unknown or unauthorised partner",
    "H8": "API retries exhausted",
    "H9": "Token or cost budget exceeded",
    "H10": "Output policy violation",
}
