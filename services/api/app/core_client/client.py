import hashlib
import hmac
import json
import time
import httpx
from app.config import settings
from app.schemas import DomainError


def sign(body: bytes, timestamp: str, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def verify_signature(body: bytes, timestamp: str, signature: str):
    try:
        fresh = abs(time.time() - int(timestamp)) <= 300
    except ValueError:
        fresh = False
    if not fresh or not hmac.compare_digest(sign(body, timestamp, settings().core_webhook_secret), signature):
        raise DomainError("Invalid webhook signature or expired timestamp", 401)


class CoreAPIClient:
    def __init__(self, transport=None):
        self.transport = transport

    async def request(self, method, path, body=None, key=None):
        config = settings()
        async with httpx.AsyncClient(
            base_url=config.core_api_url, timeout=15, transport=self.transport
        ) as client:
            response = await client.post(
                "/oauth/token",
                json={
                    "client_id": config.core_client_id,
                    "client_secret": config.core_client_secret,
                    "grant_type": "client_credentials",
                },
            )
            response.raise_for_status()
            headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
            if key:
                headers["Idempotency-Key"] = key
            result = await client.request(method, path, json=body, headers=headers)
            result.raise_for_status()
            return result.json()

    async def get_quote_request(self, request_id):
        return await self.request("GET", f"/v1/quote-requests/{request_id}")

    async def publish(self, case_id, approval_id, pack):
        return await self.request(
            "POST",
            "/v1/recommendations",
            {"case_id": case_id, "approval_id": approval_id, "pack": pack},
            key=f"publish:{case_id}:{pack['pack_hash']}",
        )


def encode_event(event):
    return json.dumps(event, sort_keys=True, separators=(",", ":")).encode()
