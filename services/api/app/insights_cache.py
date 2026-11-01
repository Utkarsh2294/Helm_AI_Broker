"""Five-minute, scope-bound aggregate cache, invalidated after source commits."""

import hashlib
import json
from functools import wraps
from fastapi.encoders import jsonable_encoder
from app.db.store import event_client


def cached(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        ctx = kwargs.get("ctx") or next((value for value in args if hasattr(value, "filters")), None)
        if ctx is None:
            return function(*args, **kwargs)
        redis = None
        try:
            redis = event_client()
            epoch = redis.get("helm:insights:epoch") or b"0"
            binding = [
                ctx.db.get_bind().url.render_as_string(hide_password=False),
                ctx.user.id,
                ctx.user.role,
                ctx.user.is_lead_broker,
                ctx.start.isoformat(),
                ctx.end.isoformat(),
                ctx.coverage,
                ctx.broker,
                ctx.insurer,
                function.__name__,
                {k: v for k, v in kwargs.items() if k != "ctx"},
                str(epoch),
            ]
            key = (
                "helm:insights:query:"
                + hashlib.sha256(json.dumps(binding, sort_keys=True, default=str).encode()).hexdigest()
            )
            saved = redis.get(key)
            if saved:
                return json.loads(saved)
        except Exception:
            redis = None
        result = function(*args, **kwargs)
        if redis:
            try:
                redis.setex(key, 300, json.dumps(jsonable_encoder(result)))
            except Exception:
                pass
        return result

    return wrapped
