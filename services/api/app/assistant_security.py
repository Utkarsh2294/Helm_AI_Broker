"""Per-broker limits shared by chat, explanations and transcription."""

import secrets
import time
from app.auth import rate_limiter
from app.schemas import DomainError


def rate_limit(broker_id, transcription=False):
    limit, scope = (5, "transcription") if transcription else (30, "assistant")
    now = time.time()
    script = """redis.call('ZREMRANGEBYSCORE',KEYS[1],'-inf',ARGV[1]); if redis.call('ZCARD',KEYS[1])>=tonumber(ARGV[2]) then return 0 end; redis.call('ZADD',KEYS[1],ARGV[3],ARGV[4]); redis.call('EXPIRE',KEYS[1],60); return 1"""
    try:
        with rate_limiter.redis_client() as redis:
            allowed = redis.eval(
                script, 1, f"helm:{scope}:broker:{broker_id}", now - 60, limit, now, secrets.token_hex(8)
            )
    except Exception:
        raise DomainError("Assistant rate limiter unavailable; retry shortly", 503)
    if not allowed:
        raise DomainError("Assistant request limit reached. Retry in one minute.", 429, retry_after=60)
