import hashlib
import io
import wave
from types import SimpleNamespace
from sqlalchemy import select
from app import main
from app.db.models import Snapshot
from app.db.assistant import AssistantLog
from app.db.copilot import AssistantAudit
from app.compliance.medical_firewall import safe_case
from test_agentic_demo import packed, login
from test_assistant import ask


def test_sealed_replies_hash_audit_research_undo_and_versioned_pdf(client):
    headers, case = packed(client)
    reply = ask(client, headers, "Why this ranking?", case["id"])
    with main.SessionLocal() as db:
        assert db.get(AssistantLog, reply["id"]) is None
        stamp = db.get(AssistantAudit, reply["id"])
        assert stamp.query_hash == hashlib.sha256(b"Why this ranking?").hexdigest()
        assert stamp.response_hash == hashlib.sha256(reply["answer"].encode()).hexdigest()
    body = {
        "log_id": reply["id"],
        "case_id": case["id"],
        "query_hash": reply["query_hash"],
        "receipt": reply["receipt"],
    }
    assert (
        client.post(
            "/api/v1/assistant/case-evidence",
            headers=headers,
            json={**body, "receipt": reply["receipt"][:-4] + "AAAA"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/assistant/case-evidence", headers=headers, json={**body, "query_hash": "0" * 64}
        ).status_code
        == 409
    )
    saved = client.post("/api/v1/assistant/case-evidence", headers=headers, json=body)
    assert saved.status_code == 200, saved.text
    evidence = saved.json()
    current = client.get("/api/v1/cases/" + case["id"]).json()
    assert current["state"] == case["state"] and current["pack"]["pack_hash"] != case["pack"]["pack_hash"]
    assert current["pack"]["supporting_research"][0]["evidence_id"] == evidence["id"]
    pdf = client.get("/api/v1/assistant/suitability/" + case["id"] + ".pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    import pymupdf

    with pymupdf.open(stream=pdf.content, filetype="pdf") as doc:
        text = "\n".join(page.get_text() for page in doc)
        assert "supporting research" in text and "TOPSIS" in text
    endpoint = f"/api/v1/workspace/assistant/evidence/{evidence['id']}/visibility"
    assert client.put(endpoint, headers=headers, json={"hidden": True}).status_code == 200
    assert not client.get("/api/v1/workspace/assistant/evidence?case_id=" + case["id"]).json()
    with main.SessionLocal() as db:
        assert db.get(Snapshot, evidence["id"]).body_hash == evidence["hash"]
    assert client.put(endpoint, headers=headers, json={"hidden": False}).status_code == 200
    assert len(client.get("/api/v1/workspace/assistant/evidence?case_id=" + case["id"]).json()) == 1
    workspace = ask(client, headers, "Summarise my workspace")
    assert (
        client.post(
            "/api/v1/assistant/case-evidence",
            headers=headers,
            json={
                "log_id": workspace["id"],
                "case_id": case["id"],
                "query_hash": workspace["query_hash"],
                "receipt": workspace["receipt"],
            },
        ).status_code
        == 409
    )
    unsaved = ask(client, headers, "What should I do next?", case["id"])
    headers = login(client)
    assert (
        client.post(
            "/api/v1/workspace/assistant/" + unsaved["id"] + "/evidence",
            headers=headers,
            json={"receipt": unsaved["receipt"]},
        ).status_code
        == 404
    )


def test_multipart_cache_parser_limits_and_broker_session_isolation(client):
    headers = login(client)
    data = b"# Meeting notes\nBudget: GBP 1,800.00\nNo preference changes are authorised."

    def upload():
        return client.post(
            "/api/v1/assistant/parse-files",
            headers=headers,
            files=[("files", ("meeting.md", data, "text/markdown"))],
        )

    first = upload()
    assert first.status_code == 200, first.text
    result = first.json()["files"][0]
    assert result["characters"] == len(data) and "Budget" in result["preview"]
    duplicate = upload().json()["files"][0]
    assert duplicate["id"] == result["id"] and duplicate["duplicate"]
    big = client.post(
        "/api/v1/assistant/parse-files",
        headers=headers,
        files=[("files", ("large.txt", b"x" * 60000, "text/plain"))],
    )
    parsed = big.json()["files"][0]
    assert parsed["characters"] == 50000 and parsed["truncated"]
    assert (
        client.post(
            "/api/v1/assistant/parse-files",
            headers=headers,
            files=[("files", (f"{i}.txt", b"hello", "text/plain")) for i in range(6)],
        ).status_code
        == 422
    )
    login(client, "pilot@helm.demo")
    response = client.post(
        "/api/v1/workspace/assistant",
        headers={"X-CSRF-Token": client.cookies.get("helm_csrf")},
        json={"question": "Read this file", "file_ids": [result["id"]]},
    )
    assert response.status_code == 404


def test_local_audio_transcription_audit_duration_and_protected_redaction(client, monkeypatch):
    from app import speech

    headers = login(client)
    monkeypatch.setattr(speech, "available", lambda: True)
    monkeypatch.setattr(
        speech,
        "model",
        lambda: SimpleNamespace(
            transcribe=lambda *args, **kwargs: ([SimpleNamespace(text="Summarise my workspace")], None)
        ),
    )

    def recording(seconds):
        stream = io.BytesIO()
        with wave.open(stream, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(b"\0\0" * int(seconds * 16000))
        return stream.getvalue()

    audio = recording(0.25)
    response = client.post(
        "/api/v1/assistant/transcribe", headers=headers, files={"file": ("voice.wav", audio, "audio/wav")}
    )
    assert response.status_code == 200, response.text
    assert (
        response.json()["text"] == "Summarise my workspace" and response.json()["method"] == "local_whisper"
    )
    with main.SessionLocal() as db:
        assert db.scalar(
            select(AssistantAudit).where(AssistantAudit.query_hash == hashlib.sha256(audio).hexdigest())
        )
        assert not db.scalars(select(AssistantLog)).all()
    assert (
        client.post(
            "/api/v1/assistant/transcribe",
            headers=headers,
            files={"file": ("long.wav", recording(61), "audio/wav")},
        ).status_code
        == 422
    )
    value = {
        "pack": {
            "supporting_research": [
                {
                    "protected": True,
                    "question": "PRIVATE_NEW_MEDICAL",
                    "answer": "PRIVATE_NEW_MEDICAL",
                    "sources": [{"excerpt": "PRIVATE_NEW_MEDICAL"}],
                }
            ]
        }
    }
    assert "PRIVATE_NEW_MEDICAL" not in str(safe_case(value, SimpleNamespace(role="authorised_broker")))
