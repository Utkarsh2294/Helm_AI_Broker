"""Authenticated multipart parsing and local speech tools, without agent actions."""

import asyncio
import hashlib
from datetime import timedelta
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy import select, delete
from app.auth import identity
from app import service
from app.assistant_files import MAX_BYTES, MAX_COMBINED_TEXT, AUDIO, parse_file
from app.assistant_security import rate_limit
from app.db.async_session import database
from app.db.assistant import AssistantFile
from app.db.copilot import AssistantAudit
from app.db.models import utcnow, uid
from app.schemas import DomainError, Model

router = APIRouter(prefix="/api/v1/assistant")


def file_access(db, request, case_id):
    user, session = identity(db, request)
    if user.role not in {"authorised_broker", "senior_broker", "lead_broker", "compliance_officer"}:
        raise DomainError("An authorised broker or compliance reviewer is required to analyse documents", 403)
    if case_id:
        from app.medical_access import require_medical_access

        require_medical_access(db, service.get_case(db, case_id), user, session)
    return user, session


def cache_key(user, session, case_id, raw, name):
    digest = hashlib.sha256(raw).hexdigest()
    return hashlib.sha256(
        f"v3:{user.id}:{session.id}:{case_id}:{Path(name).suffix.lower()}:{digest}".encode()
    ).hexdigest()


def file_metadata(row, duplicate=False):
    return {
        "id": row.id,
        "name": row.body["name"],
        "sha256": row.body["sha256"],
        "method": row.body["method"],
        "pages": row.body.get("pages"),
        "characters": len(row.body["text"]),
        "preview": row.body["text"][:300],
        "truncated": row.body["truncated"],
        "expires_at": row.expires_at,
        "duplicate": duplicate,
        "notice": "Parsed locally. Temporary for this login session; original file is not retained. Save an answer to evidence to retain its cited extract.",
    }


def find_cached(db, user, session, case_id, raw, name):
    row = db.scalar(
        select(AssistantFile).where(
            AssistantFile.cache_key == cache_key(user, session, case_id, raw, name),
            AssistantFile.expires_at > utcnow().isoformat(),
        )
    )
    return file_metadata(row, True) if row else None


def store_parsed(db, user, session, case_id, raw, name, parsed):
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    db.execute(delete(AssistantFile).where(AssistantFile.expires_at <= utcnow().isoformat()))
    key = cache_key(user, session, case_id, raw, name)
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    statement = insert(AssistantFile).values(
        id=uid(),
        broker_id=user.id,
        session_id=session.id,
        case_id=case_id,
        cache_key=key,
        body={**parsed, "name": name, "sha256": hashlib.sha256(raw).hexdigest(), "protected": bool(case_id)},
        expires_at=min(session.expires_at, (utcnow() + timedelta(hours=1)).isoformat()),
    )
    db.execute(statement.on_conflict_do_nothing(index_elements=["cache_key"]))
    return file_metadata(db.scalar(select(AssistantFile).where(AssistantFile.cache_key == key)))


@router.post("/parse-files")
async def parse_files(
    request: Request,
    files: list[UploadFile] = File(..., max_length=5),
    case_id: str | None = Form(None, max_length=100),
    db=Depends(database, scope="function"),
):
    user, session = await db.run_sync(lambda sync: file_access(sync, request, case_id))
    result = []
    for file in files:
        name = (file.filename or "document")[:180]
        raw = await file.read(MAX_BYTES + 1)
        if not raw or len(raw) > MAX_BYTES:
            raise DomainError("Upload non-empty files of at most 25 MB each", 413)
        cached = await db.run_sync(lambda sync: find_cached(sync, user, session, case_id, raw, name))
        if cached:
            result.append(cached)
            continue
        if Path(name).suffix.lower().lstrip(".") in AUDIO:
            rate_limit(user.id, transcription=True)
        parsed = await asyncio.to_thread(parse_file, raw, name)
        result.append(
            await db.run_sync(lambda sync: store_parsed(sync, user, session, case_id, raw, name, parsed))
        )
    if sum(row["characters"] for row in result) > MAX_COMBINED_TEXT:
        raise DomainError("Combined extracts exceed 150,000 characters. Upload fewer files.", 413)
    return {"files": result, "characters": sum(row["characters"] for row in result)}


@router.post("/transcribe")
async def transcribe(
    request: Request,
    file: UploadFile = File(...),
    case_id: str | None = Form(None, max_length=100),
    db=Depends(database, scope="function"),
):
    def authorise(sync):
        user, _ = identity(sync, request)
        if case_id:
            service.get_case(sync, case_id)
        rate_limit(user.id, transcription=True)
        return user.id

    broker_id = await db.run_sync(authorise)
    if Path(file.filename or "").suffix.lower().lstrip(".") not in AUDIO:
        raise DomainError("Record or upload MP3, WAV, M4A or WebM audio", 422)
    raw = await file.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise DomainError("Audio exceeds the 25 MB limit or is empty", 413)
    from app.speech import transcribe as local_transcribe

    result = await asyncio.to_thread(local_transcribe, raw)
    db.add(
        AssistantAudit(
            broker_id=broker_id,
            case_id=case_id,
            query_hash=hashlib.sha256(raw).hexdigest(),
            response_hash=hashlib.sha256(result["text"].encode()).hexdigest(),
        )
    )
    return result


@router.get("/capabilities")
async def capabilities(request: Request, db=Depends(database, scope="function")):
    from app.speech import available

    def read(sync):
        _, session = identity(sync, request)
        return {
            "reply_mode": "local_demo",
            "speech_available": available(),
            "history_session": hashlib.sha256(session.id.encode()).hexdigest(),
            "max_file_bytes": MAX_BYTES,
            "max_files": 5,
            "max_combined_characters": MAX_COMBINED_TEXT,
        }

    return await db.run_sync(read)


@router.get("/context")
async def context(request: Request, case_id: str | None = None, db=Depends(database, scope="function")):
    def read(sync):
        user, session = identity(sync, request)
        case = service.get_case(sync, case_id) if case_id else None
        expires = None
        if case:
            from app.medical_access import require_medical_access
            from app.db.platform import MedicalAccess

            try:
                require_medical_access(sync, case, user, session)
                expires = sync.get(MedicalAccess, (session.id, case.id)).expires_at
            except DomainError:
                pass
        return {
            "case_id": case_id,
            "client": case.profile.get("name", "Saved client") if case else None,
            "state": case.state if case else None,
            "medical_access_expires": expires,
        }

    return await db.run_sync(read)


class CaseEvidence(Model):
    log_id: str
    case_id: str
    query_hash: str
    receipt: str | None = None


@router.post("/case-evidence")
async def case_evidence(body: CaseEvidence, request: Request, db=Depends(database, scope="function")):
    from app.assistant import save_evidence, EvidenceInput

    return await db.run_sync(
        lambda sync: save_evidence(
            body.log_id,
            request,
            EvidenceInput(case_id=body.case_id, query_hash=body.query_hash, receipt=body.receipt),
            sync,
        )
    )


@router.get("/suitability/{case_id}.pdf")
async def suitability_pdf(case_id: str, request: Request, db=Depends(database, scope="function")):
    from fastapi.responses import Response
    from app.db.store import latest
    from app.documents import record_pdf
    from app.medical_access import require_medical_access

    def read(sync):
        user, session = identity(sync, request)
        case = service.get_case(sync, case_id)
        saved = latest(sync, case.id, "pack")
        if not saved:
            raise DomainError("A recommendation draft is not available yet", 409)
        from app.compliance.medical_firewall import safe_case

        dnr = latest(sync, case.id, "dnr")
        pack = saved.body
        research = pack.get("supporting_research", [])
        if any(row.get("protected") for row in research):
            require_medical_access(sync, case, user, session)
        else:
            pack = safe_case({"dnr": dnr.body if dnr else {}, "pack": pack}, user)["pack"]
        paragraphs = [
            "Fictional prototype recommendation. A draft is not approved advice.",
            f"Case: {case.id}",
            f"Saved pack version: {saved.version}",
            f"Pack SHA-256: {pack['pack_hash']}",
            pack.get("suitability_final", ""),
        ]
        if research:
            paragraphs.append(
                "Appendix: supporting research — saved-record assistant answers. Broker review required."
            )
        for row in research:
            paragraphs += [
                row["question"],
                row["answer"],
                f"{row['timestamp']} · {row['model_version']} · {row['confidence']}",
                f"Evidence snapshot SHA-256: {row['snapshot_hash']}",
            ]
            paragraphs += [
                f"[{i + 1}] {source['label']} — {source.get('record', source.get('sha256', ''))}"
                for i, source in enumerate(row["sources"])
            ]
        return paragraphs

    paragraphs = await db.run_sync(read)
    content = await asyncio.to_thread(record_pdf, "Helm — recommendation and supporting research", paragraphs)
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="helm-suitability-{case_id}.pdf"'},
    )
