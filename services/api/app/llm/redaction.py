import json
import re
import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.db.models import encryption_key

PATTERNS = {
    "EMAIL": r"\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b",
    "NHS": r"\b\d{3}[ -]\d{3}[ -]\d{4}\b",
    "DOB": r"\b(?:\d{4}-\d{2}-\d{2}|\d{2}[/-]\d{2}[/-]\d{4})\b",
    "PHONE": r"(?<!\w)(?:\+44\s?\d[\d\s-]{8,}|0\d[\d\s-]{8,})(?!\w)",
    "POSTCODE": r"\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b",
    "ADDRESS": r"\b\d{1,5}\s+[\w\s]{1,50}\s(?:Street|Road|Lane|Avenue|Close|Drive)\b",
    "PERSON": r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b",
}


class RedactionService:
    def __init__(self, redis):
        self.redis = redis

    def redact(self, text, case_id, identifiers=(), medical_texts=()):
        mapping = {}
        for medical in sorted(medical_texts, key=len, reverse=True):
            if medical:
                text = text.replace(medical, "[MEDICAL_REDACTED]")

        def substitute(kind, value):
            for placeholder, original in mapping.items():
                if original == value:
                    return placeholder
            token = f"[{kind}_{len(mapping) + 1}]"
            mapping[token] = value
            return token

        for identifier in sorted(identifiers, key=len, reverse=True):
            if identifier:
                text = text.replace(identifier, substitute("IDENTIFIER", identifier))
        for kind, pattern in PATTERNS.items():
            text = re.sub(
                pattern,
                lambda match: substitute(kind, match.group()),
                text,
                flags=re.IGNORECASE if kind in ("POSTCODE", "ADDRESS") else 0,
            )
        nonce = os.urandom(12)
        encrypted = nonce + AESGCM(encryption_key()).encrypt(
            nonce, json.dumps(mapping).encode(), case_id.encode()
        )
        self.redis.setex(f"helm:redaction:{case_id}", 3600, base64.urlsafe_b64encode(encrypted))
        return text, mapping

    def restore(self, text, mapping):
        for token, original in mapping.items():
            text = text.replace(token, original)
        return text
