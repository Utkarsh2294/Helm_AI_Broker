import hashlib
import pymupdf
from app.config import settings
from test_governance_access import login


def test_all_demo_documents_are_authenticated_deterministic_and_labelled(client, monkeypatch):
    assert client.get("/api/v1/demo/documents").status_code == 401
    login(client, "broker@helm.demo")
    result = client.get("/api/v1/demo/documents").json()
    assert result["fictional"] and not result["live_release_approved"] and len(result["items"]) == 7
    assert result == client.get("/api/v1/demo/documents").json()
    for item in result["items"]:
        response = client.get(item["url"])
        assert response.status_code == 200
        assert hashlib.sha256(response.content).hexdigest() == item["sha256"]
        with pymupdf.open(stream=response.content, filetype="pdf") as pdf:
            text = " ".join(page.get_text() for page in pdf)
            assert "DEMONSTRATION ONLY" in text and "FICTIONAL DATA" in text
    assert client.get("/api/v1/demo/documents/unknown.pdf").status_code == 404
    monkeypatch.setattr(settings(), "clock_mode", "live")
    assert client.get("/api/v1/demo/documents").status_code == 404
