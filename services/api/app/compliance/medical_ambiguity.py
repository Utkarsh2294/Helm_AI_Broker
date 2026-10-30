"""Conservative wording triage. This never diagnoses, scores or excludes a condition."""

import json
import re
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def rules():
    path = Path(__file__).with_name("medical_ambiguity_patterns.json")
    return [(item["id"], re.compile(item["pattern"], re.IGNORECASE)) for item in json.loads(path.read_text())]


def check_medical_ambiguity(consumer_answers):
    texts = consumer_answers.get("medical_items", [])
    matched = sorted({key for text in texts for key, pattern in rules() if pattern.search(text)})
    return (
        {
            "code": "H5",
            "phase_alias": "H4",
            "rule_ids": matched,
            "message": "Medical wording needs a broker review; no coverage decision has been made.",
        }
        if matched
        else None
    )


def pending_review(db, case_id):
    from app.db.store import latest

    triage, review = latest(db, case_id, "medical_triage"), latest(db, case_id, "medical_review")
    return bool(triage and not (review and review.body.get("resolved")))
