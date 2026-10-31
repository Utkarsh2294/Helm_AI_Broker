"""Request headers and metadata-only records for denied human gates."""

from app.auth import digest
from app.db.models import Case, LoginSession
from app.db.store import audit

CSP = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"


def secure_headers(response):
    from app.config import settings

    response.headers.update(
        {
            "Content-Security-Policy": CSP,
            "X-Frame-Options": "DENY",
            "Permissions-Policy": "geolocation=(), microphone=(self), camera=()",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
        }
    )
    if settings().cookie_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    return response


def denied_gate(session_factory, request, status):
    case_id = request.path_params.get("case_id")
    if not case_id or request.method == "GET":
        return
    with session_factory() as db:
        if not db.get(Case, case_id):
            return
        session = db.get(LoginSession, digest(request.cookies.get("helm_session", "")))
        audit(
            db,
            case_id,
            "GATE_VIOLATION",
            f"broker:{session.user_id}" if session else "anonymous",
            {"action": request.url.path.rsplit("/", 1)[-1], "status": status},
        )
        db.commit()
