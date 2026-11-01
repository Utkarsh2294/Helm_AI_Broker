"""Explicitly enrolled device reminders. No client names or health data in push payloads."""

import base64
import hashlib
import json
import os
from functools import lru_cache
from urllib.parse import urlsplit
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from fastapi import Depends, Request
from pydantic import Field
from sqlalchemy import select
from app.auth import identity
from app.config import ROOT, settings
from app.db.copilot import PushSubscription, Notification
from app.db.models import utcnow
from app.demo_documents import database
from app.schemas import Model, DomainError
from app.copilot_api import router


@lru_cache(maxsize=1)
def vapid_key():
    path = ROOT / ".runtime/push-vapid.pem"
    path.parent.mkdir(exist_ok=True)
    if not path.exists():
        key = ec.generate_private_key(ec.SECP256R1())
        raw = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        try:
            handle = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(handle, "wb") as output:
                output.write(raw)
        except FileExistsError:
            pass
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return str(path), base64.urlsafe_b64encode(public).decode().rstrip("=")


@router.get("/notifications/push/config")
def capability(request: Request, db=Depends(database, scope="function")):
    identity(db, request)
    return {
        "available": settings().push_enabled,
        "public_key": vapid_key()[1] if settings().push_enabled else None,
        "notice": "Browser push is disabled by the portal operator."
        if not settings().push_enabled
        else "Optional device reminders; no client details are sent.",
    }


class SubscriptionInput(Model):
    endpoint: str = Field(min_length=1, max_length=2048)
    expirationTime: float | None = None
    keys: dict[str, str]


@router.post("/notifications/push/subscribe")
def subscribe(body: SubscriptionInput, request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    if not settings().push_enabled:
        raise DomainError("Browser push is disabled", 503)
    target = urlsplit(body.endpoint)
    allowed = target.hostname in {
        "fcm.googleapis.com",
        "web.push.apple.com",
        "updates.push.services.mozilla.com",
    } or bool(target.hostname and target.hostname.endswith(".push.services.mozilla.com"))
    if (
        target.scheme != "https"
        or not allowed
        or target.port not in (None, 443)
        or target.username
        or target.password
    ):
        raise DomainError("Unsupported browser push provider", 422)
    try:
        values = {
            name: base64.urlsafe_b64decode(body.keys[name] + "=" * (-len(body.keys[name]) % 4))
            for name in ("p256dh", "auth")
        }
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), values["p256dh"])
        if len(values["auth"]) != 16:
            raise ValueError()
    except (KeyError, ValueError):
        raise DomainError("Invalid push encryption keys", 422)
    digest = hashlib.sha256(body.endpoint.encode()).hexdigest()
    row = db.scalar(
        select(PushSubscription).where(
            PushSubscription.broker_id == user.id, PushSubscription.endpoint_hash == digest
        )
    )
    if not row:
        row = PushSubscription(broker_id=user.id, endpoint_hash=digest)
        db.add(row)
    row.body = {"endpoint": body.endpoint, "keys": body.keys}
    db.flush()
    return {"id": row.id, "subscribed": True}


def deliver_pending(db):
    if not settings().push_enabled:
        return
    from pywebpush import webpush, WebPushException
    from app.db.models import User, Case

    rows = db.scalars(
        select(Notification)
        .where(
            Notification.actionable.is_(True),
            Notification.read_at.is_(None),
            Notification.push_sent_at.is_(None),
        )
        .order_by(Notification.created_at.desc())
        .limit(10)
        .with_for_update(skip_locked=True)
    ).all()
    for notification in rows:
        failed = False
        user = db.get(User, notification.broker_id)
        case = db.get(Case, notification.case_id) if notification.case_id else None
        if not user or not user.is_active or (case and case.assigned_to not in (None, user.id)):
            notification.push_sent_at = utcnow().isoformat()
            continue
        subscriptions = db.scalars(
            select(PushSubscription).where(PushSubscription.broker_id == user.id)
        ).all()
        for subscription in subscriptions:
            try:
                webpush(
                    subscription_info=subscription.body,
                    data=json.dumps(
                        {
                            "title": "Helm workspace update",
                            "body": "Sign in to review your saved workspace notifications.",
                            "url": "/notifications",
                        }
                    ),
                    vapid_private_key=vapid_key()[0],
                    vapid_claims={"sub": settings().push_subject},
                    timeout=3,
                )
            except WebPushException as error:
                if error.response is not None and error.response.status_code in {404, 410}:
                    db.delete(subscription)
                else:
                    failed = True
        # Transient delivery failures remain in the durable inbox for retry.
        if not failed:
            notification.push_sent_at = utcnow().isoformat()
