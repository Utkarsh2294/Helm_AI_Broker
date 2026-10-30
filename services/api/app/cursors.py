"""Authenticated pagination positions, bound to the current user and filter values."""

import base64
import hashlib
import hmac
import json
from app.config import settings
from app.schemas import DomainError


def filter_hash(values):
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def encode_cursor(position, binding):
    data = (
        base64.urlsafe_b64encode(json.dumps({"p": position, "b": binding}, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )
    signature = hmac.new(settings().secret_key.encode(), data.encode(), hashlib.sha256).hexdigest()
    return data + "." + signature


def decode_cursor(cursor, binding):
    try:
        if len(cursor) > 2048:
            raise ValueError()
        data, signature = cursor.split(".")
        expected = hmac.new(settings().secret_key.encode(), data.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        body = json.loads(base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)))
        if body["b"] != binding or len(body["p"]) != 3 or not all(isinstance(v, str) for v in body["p"]):
            raise ValueError()
        return body["p"]
    except (ValueError, KeyError, TypeError):
        raise DomainError("Invalid case cursor; restart the list with the current filters", 422)
