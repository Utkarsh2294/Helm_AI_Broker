import hashlib
import json
import time
import inspect
from app.config import settings
from app.db.platform import LLMCall
from app.schemas import DomainError
from app.llm.redaction import RedactionService


class LLMGateway:
    def __init__(self, redis, db, completion=None):
        self.redis, self.db, self.completion = redis, db, completion

    async def call(
        self, messages, case_id, step_name, model=None, identifiers=(), medical_texts=(), max_tokens=1000
    ):
        config = settings()
        model = model or config.llm_model
        if model.split("/")[0] not in config.llm_allowed_providers:
            raise DomainError("Model provider is not allowed", 403)
        if not self.completion and (not config.llm_enabled or config.llm_region not in ("uk", "eu")):
            raise DomainError("Live model calls require an enabled, region-approved gateway", 503)
        redactor = RedactionService(self.redis)
        from app.db.store import latest
        from app.db.models import Case

        dnr = latest(self.db, case_id, "dnr")
        if dnr:
            medical_texts = tuple(medical_texts) + tuple(dnr.body.get("medical_items", []))
        case = self.db.get(Case, case_id)
        if case:
            identifiers = tuple(identifiers) + (case.profile.get("name", ""),)
        # Redact every message, including templates; caller-provided medical canaries never leave.
        clean = []
        for message in messages:
            text, _ = redactor.redact(str(message["content"]), case_id, identifiers, medical_texts)
            clean.append({"role": message["role"], "content": text})
        encoded = json.dumps(clean, sort_keys=True)
        reserve = len(encoded) // 4 + max_tokens
        key = f"helm:tokens:{case_id}"
        allowed = self.redis.eval(
            "local n=redis.call('INCRBY',KEYS[1],ARGV[1]); redis.call('EXPIRE',KEYS[1],86400); if n>tonumber(ARGV[2]) then redis.call('DECRBY',KEYS[1],ARGV[1]); return 0 end; return 1",
            1,
            key,
            reserve,
            config.llm_token_budget,
        )
        if not allowed:
            raise DomainError("H9: case model-token budget exceeded", 429)
        started, status = time.monotonic(), "failed"
        try:
            completion = self.completion
            if not completion:
                from litellm import acompletion

                completion = acompletion
            response = completion(
                model=model, messages=clean, max_tokens=max_tokens, api_key=config.llm_api_key
            )
            if inspect.isawaitable(response):
                response = await response
            text = response["choices"][0]["message"]["content"]
            if any(secret and secret in text for secret in medical_texts):
                raise DomainError("H10: forbidden medical output", 422)
            status = "ok"
            return text
        finally:
            self.db.add(
                LLMCall(
                    case_id=case_id,
                    prompt_hash=hashlib.sha256(encoded.encode()).hexdigest(),
                    model=model,
                    tokens=reserve,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    status=status,
                )
            )
