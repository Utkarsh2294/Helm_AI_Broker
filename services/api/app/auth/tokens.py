"""RS256 tokens backed by revocable SQL sessions and one-use step-up records."""

import hashlib
import os
import secrets
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from filelock import FileLock
from app.clock import wall_now
from app.config import settings
from app.schemas import DomainError


@lru_cache(maxsize=4)
def load_signer(pem, filename):
    if pem:
        data = pem.encode()
    else:
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(path) + ".lock", timeout=10):
            if not path.exists():
                key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
                data = key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
                with os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "wb") as stream:
                    stream.write(data)
            data = path.read_bytes()
    key = serialization.load_pem_private_key(data, password=None)
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
        raise RuntimeError("Authentication signing requires an RSA key of at least 2048 bits")
    return key


def signer():
    config = settings()
    return load_signer(
        config.jwt_private_key.get_secret_value() if config.jwt_private_key else "",
        config.jwt_signing_key_file,
    )


def key_id(key):
    public = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return hashlib.sha256(public).hexdigest()[:16]


def mint_token(user_id, kind="access", role=None, session_id=None):
    now = wall_now()
    key = signer()
    claims = {
        "iss": "helm-broker",
        "aud": f"helm-broker-{kind}",
        "sub": str(user_id),
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=15 if kind == "access" else 5),
        "jti": secrets.token_urlsafe(24),
        "kind": kind,
    }
    if role:
        claims.update(role=role, scopes=["staff"])
    if kind == "step-up":
        claims.update(su=True, session_id=session_id)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": key_id(key)})


def verify_token(token, kind="access"):
    try:
        if len(token) > 4096:
            raise jwt.InvalidTokenError()
        key = signer()
        if jwt.get_unverified_header(token).get("kid") != key_id(key):
            raise jwt.InvalidTokenError()
        claims = jwt.decode(
            token,
            key.public_key(),
            algorithms=["RS256"],
            issuer="helm-broker",
            audience=f"helm-broker-{kind}",
            options={"require": ["exp", "iat", "nbf", "sub", "jti"]},
        )
        if claims.get("kind") != kind or (kind == "step-up" and not claims.get("su")):
            raise jwt.InvalidTokenError()
        return claims
    except jwt.PyJWTError:
        if kind == "step-up":
            raise DomainError("Re-authenticate before approval", 403, requires_step_up=True)
        raise DomainError("Sign in to continue", 401)
