from app.config import settings


def test_security_headers_cover_success_auth_errors_and_early_rejection(client, monkeypatch):
    responses = [
        client.get("/api/v1/cases"),
        client.post("/api/v1/auth/password", json={}, headers={"Origin": "https://untrusted.example"}),
    ]
    for response in responses:
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Cache-Control"] == "no-store"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    monkeypatch.setattr(settings(), "cookie_secure", True)
    response = client.get("/openapi.json")
    assert response.status_code == 200 and "preload" in response.headers["Strict-Transport-Security"]
