import secrets
import time
from redis import Redis
from app.config import settings
from app.schemas import DomainError


def redis_client():
    return Redis.from_url(settings().redis_url, socket_connect_timeout=1, socket_timeout=1)


def check_limit(request, scope="auth", limit=None, window=900):
    ip = request.client.host if request.client else "unknown"
    maximum = limit or settings().auth_rate_limit
    now = time.time()
    script = """redis.call('ZREMRANGEBYSCORE',KEYS[1],'-inf',ARGV[1]);
    if redis.call('ZCARD',KEYS[1]) >= tonumber(ARGV[2]) then return 0 end;
    redis.call('ZADD',KEYS[1],ARGV[3],ARGV[4]); redis.call('EXPIRE',KEYS[1],ARGV[5]); return 1"""
    try:
        with redis_client() as redis:
            allowed = redis.eval(
                script, 1, f"helm:{scope}:{ip}", now - window, maximum, now, secrets.token_hex(8), window
            )
    except Exception:
        raise DomainError("Authentication rate limiter unavailable; retry shortly", 503)
    if not allowed:
        raise DomainError("Too many attempts; retry after 15 minutes", 429)
