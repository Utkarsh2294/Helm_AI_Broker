"""Source-grounded local assistant: no model egress and no workflow commands."""

import base64
import hashlib
import io
import json
import re
import secrets
import zipfile
from datetime import datetime, timedelta
from types import SimpleNamespace
from xml.sax.saxutils import escape
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import Field
from sqlalchemy import select, delete, func
from app import service
from app.auth import identity
from app.case_access import visible_cases
from app.compliance.medical_firewall import safe_case
from app.db.assistant import AssistantLog, AssistantFile, AssistantShare
from app.db.models import Case, Activity, Snapshot, utcnow
from app.db.store import save_snapshot, audit
from app.demo_documents import database
from app.schemas import Model, DomainError
from app.assistant_files import MAX_BYTES, parse_file

router = APIRouter(prefix="/api/v1/workspace/assistant")
VERSION = "helm-local-evidence-v2"
WORKSPACE_CHIPS = [
    "Summarise my workspace",
    "What needs attention today?",
    "Show blocked cases",
    "Pipeline overview",
]
CASE_CHIPS = [
    "What should I do next?",
    "What are the client’s preferences?",
    "Why this ranking?",
    "What did each agent do?",
]
BLOCKED = {"AWAIT_APPROVAL", "PAUSED_NEEDS_HUMAN", "UW_REFERRAL", "COMPLAINT_FLAGGED", "NEEDS_INFO"}


def scoped_case(db, case_id):
    return service.get_case(db, case_id) if case_id else None


def public_log(row):
    return {
        **row.body,
        "id": row.id,
        "case_id": row.case_id,
        "broker_id": row.broker_id,
        "timestamp": row.created_at,
        "model_version": row.model_version,
        "confidence": row.confidence_level,
    }


def require_protected(db, row, user, session):
    if row.body.get("protected") and row.case_id:
        from app.medical_access import require_medical_access

        require_medical_access(db, service.get_case(db, row.case_id), user, session)


def own_log(db, log_id, request):
    user, session = identity(db, request)
    row = db.get(AssistantLog, log_id)
    if not row or row.broker_id != user.id:
        raise DomainError("Assistant response not found", 404)
    scoped_case(db, row.case_id)
    require_protected(db, row, user, session)
    return row, user, session


def business_days(start, end):
    days = max(0, (end.date() - start.date()).days)
    weeks, remainder = divmod(days, 7)
    return weeks * 5 + sum((start.weekday() + n + 1) % 7 < 5 for n in range(remainder))


def workspace_answer(db, user, query):
    cases = db.scalars(select(Case).where(visible_cases(user))).all()
    last_actions = dict(
        db.execute(select(Activity.case_id, func.max(Activity.created_at)).group_by(Activity.case_id)).all()
    )
    now = utcnow()
    opened = [c for c in cases if c.state not in {"CLOSED", "PUBLISHED"}]
    stale = [
        c
        for c in opened
        if business_days(datetime.fromisoformat(last_actions.get(c.id, c.created_at)), now) > 3
    ]
    sources = []

    def case_line(case, reason):
        sources.append(
            {
                "label": case.profile.get("name", "Unnamed case"),
                "case_id": case.id,
                "record": f"case:{case.id}:v{case.version}",
                "state": case.state,
                "last_activity": last_actions.get(case.id, case.created_at),
            }
        )
        return f"• {case.profile.get('name', 'Unnamed case')}: {reason} [{len(sources)}]"

    if any(word in query for word in ("employee", "census", "renewal")):
        answer = "Employee bands, census sizes and renewal deadlines are not structured fields in these saved case profiles. I cannot reliably filter or prioritise by them. Open the source client file or upload the relevant record."
    elif "blocked" in query or ("ranking" in query and "pending" in query):
        matches = [
            c
            for c in cases
            if c.state in ({"BROKER_REVIEW", "AWAIT_APPROVAL"} if "ranking" in query else BLOCKED)
        ]
        answer = "Cases matching your saved status filter:\n" + (
            "\n".join(case_line(c, c.state.replace("_", " ").lower()) for c in matches[:20])
            or "No matching accessible cases."
        )
    elif any(word in query for word in ("attention", "urgent", "priority", "triage", "compliance")):
        matches = (
            [c for c in opened if c.state == "COMPLAINT_FLAGGED"]
            if "compliance" in query
            else sorted(opened, key=lambda c: (c.state not in BLOCKED, last_actions.get(c.id, c.created_at)))
        )
        answer = "Priority from saved holds and oldest activity; renewal deadlines are not available:\n" + (
            "\n".join(
                case_line(
                    c,
                    f"{c.state.replace('_', ' ').lower()}; last activity {last_actions.get(c.id, c.created_at)}",
                )
                for c in matches[:3]
            )
            or "No open matching cases."
        )
    elif any(word in query for word in ("pipeline", "stage")):
        answer = "Saved pipeline positions:\n" + (
            "\n".join(case_line(c, c.state.replace("_", " ").lower()) for c in cases[:20])
            or "No accessible cases."
        )
    elif any(word in query for word in ("show", "find", "search")):
        matches = [c for c in cases if c.profile.get("name", "").casefold() in query or c.id in query]
        answer = (
            "\n".join(case_line(c, c.state.replace("_", " ").lower()) for c in matches[:20])
            or "Which client name or saved case status should I search for?"
        )
    else:
        closed = [
            c
            for c in cases
            if c.state == "CLOSED"
            and datetime.fromisoformat(last_actions.get(c.id, c.created_at)).date()
            >= (now.date() - timedelta(days=now.weekday()))
        ]
        # Counts are derived from this broker's accessible saved records only.
        sources.append(
            {
                "label": "Accessible case status and last activity snapshot",
                "record": "workspace:visible-cases",
                "case_versions": [
                    {
                        "id": c.id,
                        "version": c.version,
                        "state": c.state,
                        "last_activity": last_actions.get(c.id, c.created_at),
                    }
                    for c in cases
                ],
            }
        )
        answer = (
            f"Your visible workspace has {len(cases)} cases. [1]\n"
            f"• Open cases: {len(opened)}. [1]\n• No activity for more than three business days: {len(stale)}. [1]\n"
            f"• Awaiting final sign-off: {sum(c.state == 'AWAIT_APPROVAL' for c in cases)}; other blocked cases: {sum(c.state in BLOCKED - {'AWAIT_APPROVAL'} for c in cases)}. [1]\n"
            f"• Recorded as delivered/in progress: {sum(c.state == 'PUBLISHED' for c in cases)}; status alone does not prove a magic-link was sent. [1]\n"
            f"• Closed this week: {len(closed)}. [1]\nOpen a case for its saved client file and detailed answers."
        )
    if not sources:
        sources = [
            {
                "label": "Accessible saved case profiles and schema",
                "record": "workspace:visible-cases",
                "case_ids": [c.id for c in cases],
            }
        ]
        answer += " [1]"
    return {"answer": answer, "sources": sources, "confidence": "MEDIUM" if "not" in answer else "HIGH"}


def respond(db, request, body):
    from app.case_workspace import saved_answer, workspace_data

    user, session = identity(db, request)
    case = scoped_case(db, body.case_id)
    history = db.scalars(
        select(AssistantLog)
        .where(
            AssistantLog.broker_id == user.id,
            AssistantLog.session_id == session.id,
            AssistantLog.case_id == body.case_id,
        )
        .order_by(AssistantLog.created_at.desc())
        .limit(10)
    ).all()
    question = body.question.strip()
    query = question.casefold()
    if len(query) < 3:
        result = {
            "answer": "Would you like the client preferences, policy ranking or next action for this case?"
            if case
            else "Would you like a workspace summary, blocked cases or pipeline overview?",
            "sources": [],
            "confidence": "LOW",
        }
    else:
        resolved = question
        if (
            history
            and re.search(r"\b(it|that|those|they|more|and|why)\b", query)
            and not any(
                w in query
                for w in ("rank", "agent", "prefer", "next", "file", "workspace", "blocked", "pipeline")
            )
        ):
            context_question = next(
                (
                    row.body.get("resolved_question", row.body["question"]).split(" — ", 1)[0]
                    for row in history
                    if row.body.get("resolved_question") or row.body["question"]
                ),
                "",
            )
            resolved = context_question + " — " + question
        result = (
            saved_answer(SimpleNamespace(question=resolved, case_id=body.case_id), request, db)
            if case
            else workspace_answer(db, user, resolved.casefold())
        )
        result["resolved_question"] = resolved
        if case:
            context = workspace_data(db, case, user)
            records = context["client_file"]["records"]
            for index, source in enumerate(result["sources"], 1):
                source["record"] = f"case:{case.id}:v{case.version}"
                source["snapshots"] = records
                source["number"] = index
            result["answer"] += " [1]"
            result["confidence"] = (
                "MEDIUM"
                if any(
                    s in result["answer"].lower()
                    for s in ("not provided", "no ranking", "missing", "waiting", "on hold")
                )
                else "HIGH"
            )
            if any(w in query for w in ("suitab", "disclos", "conflict")):
                data = safe_case(service.detail(db, case), user)
                pack = data.get("pack")
                result["answer"] = (
                    (
                        "Saved suitability gaps: "
                        + json.dumps(pack.get("unmet_needs", []), ensure_ascii=False)
                        + ". Review the saved recommendation and disclosures before final sign-off. [1]"
                    )
                    if pack
                    else "No suitability recommendation pack has been saved. Review the client needs and wait for the saved draft; I cannot invent a suitability finding. [1]"
                )
                result["confidence"] = "MEDIUM"
            elif any(
                w in query for w in ("renewal date", "current insurer", "employee", "census", "exclusion")
            ):
                result["answer"] = (
                    "That field is not available as a verified structured client fact here. Check the sourced client file or upload the record; I will not guess it. [1]"
                )
                result["confidence"] = "LOW"
            elif "evidence" in query:
                evidence = db.scalars(
                    select(Snapshot).where(Snapshot.case_id == case.id, Snapshot.kind == "assistant_evidence")
                ).all()
                result["answer"] += (
                    f"\nAssistant responses saved to evidence: {len(evidence)}. "
                    + "; ".join(f"v{r.version}: {r.body.get('question', 'Saved response')}" for r in evidence)
                    + ". [1]"
                )
            elif any(w in resolved.casefold() for w in ("rank", "compar", "premium", "score")):
                ranking = safe_case(service.detail(db, case), user).get("ranking")
                if ranking:
                    rows = ranking["top"]
                    result["table"] = {
                        "columns": ["Policy [1]", "Annual premium incl. IPT [1]", "Score /100 [1]"],
                        "rows": [
                            [
                                r["plan"]["name"],
                                f"£{r['plan']['annualPremiumPence'] / 100:,.2f}",
                                f"{r['score']:.1f}",
                            ]
                            for r in rows
                        ],
                    }
                    weights = ranking.get("weights", {})
                    result["answer"] += (
                        "\nSaved criterion weights: "
                        + "; ".join(f"{k.replace('_', ' ')} {v:.1%}" for k, v in weights.items())
                        + ". [1]\nThe saved engine combines 70% weighted-sum fit with 30% fixed-anchor TOPSIS balance. It does not have separate claims-speed or dental/optical scoring criteria. [1]"
                    )
                    match = next(
                        (r for r in rows if r["plan"]["name"].casefold() in resolved.casefold()), None
                    )
                    if match:
                        result["answer"] += (
                            "\nSaved criterion utilities: "
                            + "; ".join(
                                f"{k.replace('_', ' ')} {v:.3f}, weighted points {match.get('points', {}).get(k, 0):.2f}"
                                for k, v in match.get("utilities", {}).items()
                            )
                            + ". [1]"
                        )
            elif any(w in query for w in ("agent", "audit")):
                result["answer"] += "\n" + "\n".join(
                    f"Agent {a['id']} saved {a['finished_at'] or 'no completed output yet'}; events {a['event_sequences']}. [1]"
                    for a in context["agent_work"]
                )
            if result["answer"].startswith("I can explain"):
                result.update(
                    answer="Which saved information would you like: client preferences, policy ranking, agent work, documents or the next action? [1]",
                    confidence="LOW",
                )
    if re.search(
        r"\b(approve|select for me|choose for me|send (?:the )?(?:link|magic)|override|ignore instructions)\b",
        query,
    ):
        result.update(
            answer="I cannot select or approve policies, send links or override a broker decision. "
            + (
                "The broker must review and record the next decision in the case journey."
                if case
                else "Open a case to review its saved next action."
            )
            + (" [1]" if result["sources"] else ""),
            confidence="HIGH",
        )
    file_ids = getattr(body, "file_ids", [])
    protected = False
    if file_ids:
        excerpts = []
        for file_id in file_ids:
            file = db.get(AssistantFile, file_id)
            if (
                not file
                or file.broker_id != user.id
                or file.session_id != session.id
                or file.case_id != body.case_id
                or file.expires_at <= utcnow().isoformat()
            ):
                raise DomainError("Attachment is unavailable in this assistant session", 404)
            require_protected(db, file, user, session)
            source = {
                "label": file.body["name"],
                "record": f"assistant-file:{file.id}",
                "sha256": file.body["sha256"],
                "method": file.body["method"],
                "excerpt": file.body["text"][:2000],
            }
            result["sources"].append(source)
            excerpts.append(
                f"Received and parsed {file.body['name']}. Extracted document text (unverified):\n{file.body['text'][:2000]} [{len(result['sources'])}]"
            )
        result["answer"] = (
            "\n\n".join(excerpts)
            + "\n\n"
            + result["answer"]
            + "\nUploaded statements are unverified source data. Check these extracts against the cited saved client facts for conflicts and gaps. No preference or case field has been updated. Use the fact-find review to confirm any change."
        )
        result["confidence"] = "LOW"
        protected = bool(case)
        if case:
            needs = workspace_data(db, case, user)["client_file"]["preferences"]
            for file_id in file_ids:
                file = db.get(AssistantFile, file_id)
                match = re.search(
                    r"(?:annual\s+)?budget\s*[:=]?\s*(?:GBP|£)\s*([\d,]{1,12}(?:\.\d{1,2})?)(?![\d,])",
                    file.body["text"],
                    re.IGNORECASE,
                )
                if match and needs.get("budget_annual_pence") is not None:
                    stated = round(float(match[1].replace(",", "")) * 100)
                    if stated != needs["budget_annual_pence"]:
                        result["answer"] += (
                            f"\nPossible conflict: uploaded budget £{stated / 100:,.2f}, saved client preference £{needs['budget_annual_pence'] / 100:,.2f}. Broker verification is required. [1]"
                        )
    regulatory = (
        ["ICOBS 5 — needs and suitability review", "ICOBS 6 — disclosure review"]
        if any(w in query for w in ("suitab", "disclos", "conflict", "recommend"))
        else ["ICOBS 7 — cancellation review"]
        if "cancel" in query
        else []
    )
    chips = CASE_CHIPS if case else WORKSPACE_CHIPS
    suggestions = [chip for chip in chips if chip.casefold() != query][:3]
    result.update(
        question=question,
        suggestions=suggestions,
        compliance_context=regulatory,
        protected=protected,
        mode="local_saved_evidence",
        actions_performed=[],
    )
    row = AssistantLog(
        broker_id=user.id,
        session_id=session.id,
        case_id=body.case_id,
        body=result,
        model_version=VERSION,
        confidence_level=result["confidence"],
    )
    db.add(row)
    db.flush()
    return public_log(row)


@router.post("/stream")
def stream_answer(request: Request, body: dict, db=Depends(database, scope="function")):
    from app.case_workspace import Question

    result = respond(db, request, Question.model_validate(body))
    # Commit the response stamp before streaming; disconnects must not erase the audit log.
    db.commit()
    answer = result["answer"]

    def events():
        yield (
            "event: metadata\ndata: "
            + json.dumps({k: v for k, v in result.items() if k != "answer"})
            + "\n\n"
        )
        for offset in range(0, len(answer), 80):
            yield "event: delta\ndata: " + json.dumps({"text": answer[offset : offset + 80]}) + "\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})


@router.get("/history")
def history(
    request: Request, case_id: str | None = None, q: str = "", db=Depends(database, scope="function")
):
    user, session = identity(db, request)
    scoped_case(db, case_id)
    # Search encrypted history after decryption, never a plaintext duplicate search column.
    rows = db.scalars(
        select(AssistantLog)
        .where(AssistantLog.broker_id == user.id, AssistantLog.case_id == case_id)
        .order_by(AssistantLog.created_at.desc())
        .limit(20)
    ).all()
    result = []
    for row in rows:
        if q.casefold() in (row.body["question"] + row.body["answer"]).casefold():
            try:
                require_protected(db, row, user, session)
            except DomainError:
                continue
            result.append(public_log(row))
    return result


class FileInput(Model):
    name: str = Field(min_length=1, max_length=180)
    case_id: str | None = Field(default=None, max_length=100)
    content_base64: str = Field(min_length=1, max_length=28_000_000)


@router.post("/files")
def upload(body: FileInput, request: Request, db=Depends(database, scope="function")):
    user, session = identity(db, request)
    if user.role not in {"authorised_broker", "compliance_officer"}:
        raise DomainError("An authorised broker or compliance reviewer is required to analyse documents", 403)
    case = scoped_case(db, body.case_id)
    if case:
        from app.medical_access import require_medical_access

        require_medical_access(db, case, user, session)
    try:
        raw = base64.b64decode(body.content_base64, validate=True)
    except ValueError:
        raise DomainError("Invalid file encoding", 422)
    if len(raw) > MAX_BYTES:
        raise DomainError("File exceeds 20 MB", 413)
    parsed = parse_file(raw, body.name)
    db.execute(delete(AssistantFile).where(AssistantFile.expires_at <= utcnow().isoformat()))
    row = AssistantFile(
        broker_id=user.id,
        session_id=session.id,
        case_id=body.case_id,
        body={
            **parsed,
            "name": body.name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "protected": bool(case),
        },
        expires_at=min(session.expires_at, (utcnow() + timedelta(hours=1)).isoformat()),
    )
    db.add(row)
    db.flush()
    return {
        "id": row.id,
        "name": body.name,
        "method": parsed["method"],
        "truncated": parsed["truncated"],
        "expires_at": row.expires_at,
        "notice": "Parsed locally. Temporary for this login session; original file is not retained. Save an answer to evidence to retain its cited extract.",
    }


class AttachInput(Model):
    case_id: str = Field(min_length=1, max_length=100)


@router.post("/files/{file_id}/attach")
def attach_file(file_id: str, body: AttachInput, request: Request, db=Depends(database, scope="function")):
    from app.medical_access import require_medical_access

    user, session = identity(db, request)
    file = db.get(AssistantFile, file_id)
    if (
        not file
        or file.broker_id != user.id
        or file.session_id != session.id
        or file.expires_at <= utcnow().isoformat()
    ):
        raise DomainError("Attachment is unavailable in this assistant session", 404)
    if file.case_id and file.case_id != body.case_id:
        raise DomainError("A case attachment cannot move to a different case", 403)
    case = service.get_case(db, body.case_id)
    require_medical_access(db, case, user, session)
    for row in db.scalars(
        select(Snapshot).where(Snapshot.case_id == case.id, Snapshot.kind == "assistant_document")
    ):
        if row.body["sha256"] == file.body["sha256"]:
            return {"id": row.id, "duplicate": True}
    row = save_snapshot(
        db,
        case.id,
        "assistant_document",
        {
            **file.body,
            "protected": True,
            "category": "supporting",
            "mime": "text/plain",
            "pages": 1,
            "uploaded_by": user.id,
            "preference_changes_applied": False,
        },
    )
    audit(
        db,
        case.id,
        "assistant_document_attached",
        f"broker:{user.id}",
        {"document_id": row.id, "sha256": file.body["sha256"]},
    )
    return {
        "id": row.id,
        "hash": row.body_hash,
        "notice": "Extract attached to the digital client file. No client preferences were changed.",
    }


@router.post("/{log_id}/evidence")
def save_evidence(log_id: str, request: Request, db=Depends(database, scope="function")):
    row, user, _ = own_log(db, log_id, request)
    if not row.case_id:
        raise DomainError("Open a case assistant to save case evidence", 422)
    if user.role not in {"authorised_broker", "compliance_officer"}:
        raise DomainError("An authorised broker or reviewer must save evidence", 403)
    service.get_case(db, row.case_id)
    for saved in db.scalars(
        select(Snapshot).where(Snapshot.case_id == row.case_id, Snapshot.kind == "assistant_evidence")
    ):
        if saved.body.get("id") == row.id:
            return {"id": saved.id, "hash": saved.body_hash, "duplicate": True}
    snapshot = save_snapshot(db, row.case_id, "assistant_evidence", public_log(row))
    audit(
        db,
        row.case_id,
        "assistant_evidence_saved",
        f"broker:{user.id}",
        {"log_id": row.id, "snapshot_hash": snapshot.body_hash},
    )
    return {"id": snapshot.id, "hash": snapshot.body_hash}


@router.get("/evidence")
def evidence(request: Request, case_id: str, db=Depends(database, scope="function")):
    user, session = identity(db, request)
    scoped_case(db, case_id)
    rows = db.scalars(
        select(Snapshot)
        .where(Snapshot.case_id == case_id, Snapshot.kind == "assistant_evidence")
        .order_by(Snapshot.version.desc())
    ).all()
    result = []
    for row in rows:
        if row.body.get("protected"):
            from app.medical_access import require_medical_access

            require_medical_access(db, service.get_case(db, case_id), user, session)
        result.append({"id": row.id, "hash": row.body_hash, "version": row.version, **row.body})
    return result


class ExportInput(Model):
    log_ids: list[str] = Field(min_length=1, max_length=20)
    format: str = Field(pattern="^(pdf|docx)$")


@router.post("/export")
def export(body: ExportInput, request: Request, db=Depends(database, scope="function")):
    rows = [public_log(own_log(db, log_id, request)[0]) for log_id in body.log_ids]
    paragraphs = ["Saved-record assistant report. Broker review required; this is not policy advice."]
    for row in rows:
        paragraphs += [
            f"Broker {row['broker_id']} · {row['timestamp']} · {row['model_version']} · {row['confidence']}",
            "Question: " + row["question"],
            row["answer"],
        ]
        paragraphs += [
            f"[{i + 1}] {s['label']} — {s.get('record', '')} {s.get('sha256', '')}"
            for i, s in enumerate(row["sources"])
        ]
    if body.format == "pdf":
        from app.documents import record_pdf

        content = record_pdf("Helm assistant evidence", paragraphs)
        mime = "application/pdf"
    else:
        output = io.BytesIO()
        xml = (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
            + "".join(
                '<w:p><w:r><w:t xml:space="preserve">' + escape(p) + "</w:t></w:r></w:p>"
                for text in paragraphs
                for p in text.splitlines()
            )
            + "</w:body></w:document>"
        )
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "[Content_Types].xml",
                '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
            )
            archive.writestr(
                "_rels/.rels",
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
            )
            archive.writestr("word/document.xml", xml)
        content = output.getvalue()
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return Response(
        content,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="helm-assistant.{body.format}"'},
    )


@router.post("/{log_id}/share")
def share(log_id: str, request: Request, db=Depends(database, scope="function")):
    row, user, _ = own_log(db, log_id, request)
    if not row.case_id:
        raise DomainError("Only case responses can be shared for compliance review", 422)
    token = secrets.token_urlsafe(32)
    expires = (utcnow() + timedelta(hours=24)).isoformat()
    db.add(
        AssistantShare(
            token_hash=hashlib.sha256(token.encode()).hexdigest(), log_id=row.id, expires_at=expires
        )
    )
    audit(
        db,
        row.case_id,
        "assistant_review_link_created",
        f"broker:{user.id}",
        {"log_id": row.id, "expires_at": expires},
    )
    return {"path": f"/assistant-review/{token}", "expires_at": expires, "requires_compliance_login": True}


@router.get("/shared/{token}")
def shared(token: str, request: Request, db=Depends(database, scope="function")):
    user, session = identity(db, request)
    if user.role != "compliance_officer":
        raise DomainError("Sign in as a compliance officer to view this read-only response", 403)
    link = db.get(AssistantShare, hashlib.sha256(token.encode()).hexdigest())
    if not link or link.expires_at <= utcnow().isoformat():
        raise DomainError("Review link is invalid or expired", 404)
    row = db.get(AssistantLog, link.log_id)
    scoped_case(db, row.case_id)
    require_protected(db, row, user, session)
    return {**public_log(row), "read_only": True, "expires_at": link.expires_at}
