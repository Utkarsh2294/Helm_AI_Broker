"""Explicit workflow events. Guard names are enforced by the transactional service."""
GRAPH = {
    "RECEIVED": {"intake_started": ("INTAKE_RUNNING", None)},
    "INTAKE_RUNNING": {"intake_completed": ("FACTFIND_REVIEW", None), "missing_info": ("NEEDS_INFO", None)},
    "NEEDS_INFO": {"info_received": ("INTAKE_RUNNING", "broker")},
    "FACTFIND_REVIEW": {"dnr_signed_off": ("RFQ_DRAFTING", "G0")},
    "RFQ_DRAFTING": {"rfq_drafted": ("RFQ_RELEASE_CHECK", None)},
    "RFQ_RELEASE_CHECK": {"release_check_completed": ("AWAIT_BROKER_RELEASE", None)},
    "AWAIT_BROKER_RELEASE": {"rfq_released": ("QUOTES_PENDING", "G1")},
    "QUOTES_PENDING": {"quotes_collected": ("QUOTES_COLLECTED", None), "partner_referred": ("UW_REFERRAL", None)},
    "QUOTES_COLLECTED": {"ranking_started": ("RANKING", None)},
    "RANKING": {"ranking_completed": ("BROKER_REVIEW", None)},
    "BROKER_REVIEW": {"review_started": ("SUITABILITY_DRAFT", "broker")},
    "SUITABILITY_DRAFT": {"pack_drafted": ("AWAIT_APPROVAL", None)},
    "AWAIT_APPROVAL": {"published": ("PUBLISHED", "G2"), "changes_requested": ("BROKER_REVIEW", "broker")},
    "PUBLISHED": {"closed": ("CLOSED", "broker")},
    "UW_REFERRAL": {"referral_resolved": ("QUOTES_PENDING", "G3")},
    "PAUSED_NEEDS_HUMAN": {}, "COMPLAINT_FLAGGED": {}, "CLOSED": {},
}
HALTS = {"H1": "Invalid structured output", "H2": "Low confidence in a required field", "H3": "Premium arithmetic mismatch",
         "H4": "Contradictory partner revisions", "H5": "Ambiguous medical wording", "H6": "Missing or expired consent",
         "H7": "Unknown or unauthorised partner", "H8": "API retries exhausted", "H9": "Token or cost budget exceeded",
         "H10": "Output policy violation"}
