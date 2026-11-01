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
from sqlalchemy import select, func
from app import service
from app.auth import identity
from app.case_access import visible_cases
from app.compliance.medical_firewall import safe_case
from app.db.assistant import AssistantLog, AssistantFile, AssistantShare
from app.db.copilot import AssistantAudit
from app.db.models import Case, Activity, Snapshot, utcnow, uid, SecretJSON
from app.db.store import save_snapshot, audit
from app.demo_documents import database
from app.schemas import Model, DomainError
from app.assistant_files import MAX_BYTES, MAX_COMBINED_TEXT

router = APIRouter(prefix="/api/v1/workspace/assistant")
VERSION = "helm-local-evidence-v3"
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


def own_response(db, response_id, request, receipt=None):
    """Unseal a browser-held reply, or read an explicitly retained audit report."""
    if db.get(AssistantLog, response_id):
        return own_log(db, response_id, request)
    user, session = identity(db, request)
    try:
        payload = SecretJSON().process_result_value(receipt, None)
        if (
            payload.get("type") != "helm-assistant-reply-v1"
            or payload["id"] != response_id
            or payload["broker_id"] != user.id
            or payload["session_id"] != session.id
            or payload["expires_at"] <= utcnow().isoformat()
        ):
            raise ValueError()
        row = SimpleNamespace(**{k: v for k, v in payload.items() if k not in {"type", "expires_at"}})
    except Exception:
        raise DomainError(
            "This unsaved reply is unavailable or expired. Ask again to save or export it.", 404
        )
    scoped_case(db, row.case_id)
    require_protected(db, row, user, session)
    return row, user, session


def retain_response(db, row):
    if not isinstance(row, AssistantLog):
        row = AssistantLog(
            **{
                key: getattr(row, key)
                for key in (
                    "id",
                    "broker_id",
                    "session_id",
                    "case_id",
                    "body",
                    "model_version",
                    "confidence_level",
                    "created_at",
                )
            }
        )
        db.add(row)
        db.flush()
    return row


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
    elif any(
        word in query for word in ("attention", "urgent", "priority", "triage", "compliance", "overdue")
    ):
        from app.copilot_api import task_cards

        tasks = task_cards(db, user)
        if "overdue" in query:
            tasks = [task for task in tasks if task["overdue"]]
        if "compliance" not in query:
            by_id = {case.id: case for case in cases}
            answer = "Your next saved broker tasks, using the configured demo priority score:\n" + (
                "\n".join(
                    case_line(
                        by_id[task["case_id"]],
                        f"{task['title']}; priority {task['priority_score']:.1f}; {task['elapsed_days']} days since the last broker action",
                    )
                    for task in tasks[:3]
                )
                or "No matching outstanding broker tasks."
            )
            return {"answer": answer, "sources": sources, "confidence": "HIGH"}
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
                "case_count": len(cases),
                "scope_hash": hashlib.sha256(
                    "|".join(f"{c.id}:{c.version}:{c.state}" for c in cases).encode()
                ).hexdigest(),
                "case_versions": [
                    {
                        "id": c.id,
                        "version": c.version,
                        "state": c.state,
                        "last_activity": last_actions.get(c.id, c.created_at),
                    }
                    for c in cases[:100]
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
    from app.assistant_security import rate_limit

    rate_limit(user.id)
    case = scoped_case(db, body.case_id)
    previous_question = getattr(body, "previous_question", "")
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
            previous_question
            and re.search(r"\b(it|that|those|they|more|and|why)\b", query)
            and not any(
                w in query
                for w in ("rank", "agent", "prefer", "next", "file", "workspace", "blocked", "pipeline")
            )
        ):
            context_question = previous_question.split(" — ", 1)[0]
            resolved = context_question + " — " + question
        if not case and getattr(body, "page", "") == "insights":
            from app.broker_insights import build_context, assistant_answer
            from datetime import date

            filters = getattr(body, "context_filters", {})
            try:
                start = date.fromisoformat(filters["from"]) if filters.get("from") else None
                end = date.fromisoformat(filters["to"]) if filters.get("to") else None
            except ValueError:
                raise DomainError("Choose valid dates for the Insights period", 422)
            coverage = filters.get("coverage_type") or None
            if coverage and coverage not in {"individual", "couple", "family"}:
                raise DomainError("Unknown coverage type", 422)
            ctx = build_context(
                db,
                user,
                start,
                end,
                coverage,
                filters.get("broker_id") or None,
                filters.get("insurer_id") or None,
            )
            result = assistant_answer(ctx, resolved.casefold())
        else:
            result = (
                saved_answer(SimpleNamespace(question=resolved, case_id=body.case_id), request, db)
                if case
                else workspace_answer(db, user, resolved.casefold())
            )
        result["resolved_question"] = resolved
        if case:
            context = workspace_data(db, case, user)
            if "what just happened" in query:
                last = context["events"][-1] if context["events"] else None
                result["answer"] = (
                    f"The latest saved event is {last['type'].replace('_', ' ')} at {last['created_at']} by {last['actor']}. The current case state is {case.state.replace('_', ' ').lower()}."
                    if last
                    else "No event is recorded for this case yet."
                )
            records = context["client_file"]["records"]
            for index, source in enumerate(result["sources"], 1):
                source["record"] = f"case:{case.id}:v{case.version}"
                source["snapshots"] = records
                source["number"] = index
                source.setdefault("case_id", case.id)
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
        combined_characters = 0
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
            combined_characters += len(file.body["text"])
            if combined_characters > MAX_COMBINED_TEXT:
                raise DomainError(
                    "Attached extracts exceed 150,000 characters. Remove a file and try again.", 413
                )
            source = {
                "label": file.body["name"],
                "record": f"assistant-file:{file.id}",
                "sha256": file.body["sha256"],
                "method": file.body["method"],
                "excerpt": file.body["text"][:2000],
                "pages": file.body.get("pages"),
            }
            result["sources"].append(source)
            excerpts.append(
                f"Received and parsed {file.body['name']}. Extracted document text (unverified):\n"
                + re.sub(r"\[(\d+)\]", r"［\1］", file.body["text"][:2000])
                + f" [{len(result['sources'])}]"
            )
        result["answer"] = (
            "\n\n".join(excerpts)
            + "\n\n"
            + result["answer"]
            + "\nUploaded statements are unverified source data. Check these extracts against the cited saved client facts for conflicts and gaps. No preference or case field has been updated. Use the fact-find review to confirm any change."
        )
        result["confidence"] = "LOW"
        protected = True  # Uploaded prose may contain health details absent from the fact-find.
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
    if len(result["answer"].split()) > 200 and not any(
        word in query for word in ("detail", "full", "complete", "more")
    ):
        result["answer"] = (
            " ".join(result["answer"].split()[:190]) + "… See the cited records for the full detail."
        )
    return record_answer(db, user, session, body, result, rate_checked=True)


def record_answer(db, user, session, body, result, rate_checked=False):
    if not rate_checked:
        from app.assistant_security import rate_limit

        rate_limit(user.id)
    result.setdefault("question", body.question)
    result["query_hash"] = hashlib.sha256(body.question.encode()).hexdigest()
    result["response_hash"] = hashlib.sha256(result["answer"].encode()).hexdigest()
    row = SimpleNamespace(
        id=uid(),
        created_at=utcnow().isoformat(),
        broker_id=user.id,
        session_id=session.id,
        case_id=body.case_id,
        body=result,
        model_version=VERSION,
        confidence_level=result["confidence"],
    )
    db.add(
        AssistantAudit(
            id=row.id,
            broker_id=user.id,
            case_id=body.case_id,
            query_hash=result["query_hash"],
            response_hash=result["response_hash"],
        )
    )
    receipt = SecretJSON().process_bind_param(
        {"type": "helm-assistant-reply-v1", "expires_at": session.expires_at, **vars(row)}, None
    )
    return {
        **public_log(row),
        "receipt": receipt,
        "history_storage": "browser_session",
        "reply_mode": "local_demo",
    }


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
    content_base64: str = Field(min_length=1, max_length=35_000_000)


@router.post("/files")
def upload(body: FileInput, request: Request, db=Depends(database, scope="function")):
    from app.assistant_tools import file_access, find_cached, store_parsed
    from app.assistant_files import parse_file

    user, session = file_access(db, request, body.case_id)
    try:
        raw = base64.b64decode(body.content_base64, validate=True)
    except ValueError:
        raise DomainError("Invalid file encoding", 422)
    if len(raw) > MAX_BYTES:
        raise DomainError("File exceeds 25 MB", 413)
    cached = find_cached(db, user, session, body.case_id, raw, body.name)
    if cached:
        return cached
    parsed = parse_file(raw, body.name)
    return store_parsed(db, user, session, body.case_id, raw, body.name, parsed)


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


class EvidenceInput(Model):
    case_id: str | None = Field(default=None, max_length=100)
    query_hash: str | None = Field(default=None, max_length=64)
    receipt: str | None = Field(default=None, max_length=2_000_000)


@router.post("/{log_id}/evidence")
def save_evidence(
    log_id: str, request: Request, body: EvidenceInput | None = None, db=Depends(database, scope="function")
):
    body = body or EvidenceInput()
    row, user, session = own_response(db, log_id, request, body.receipt)
    target = body.case_id or row.case_id
    if not target:
        raise DomainError("Choose a case for this saved research", 422)
    if row.case_id and target != row.case_id:
        raise DomainError("A case answer must remain with its original case", 409)
    if body.query_hash and body.query_hash != row.body.get("query_hash"):
        raise DomainError("The response does not match the original query", 409)
    source_ids = set()
    for source in row.body.get("sources", []):
        if source.get("case_id"):
            source_ids.add(source["case_id"])
        source_ids.update(version["id"] for version in source.get("case_versions", []))
        if source.get("case_count", 0) > 1:
            raise DomainError(
                "This answer summarises multiple cases. Ask about the chosen case before saving its research.",
                409,
            )
    if source_ids - {target}:
        raise DomainError("This answer cites another case. Ask the question in the chosen case instead.", 409)
    if user.role not in {"authorised_broker", "senior_broker", "lead_broker", "compliance_officer"}:
        raise DomainError("An authorised broker or reviewer must save evidence", 403)
    case = service.get_case(db, target)
    if row.body.get("protected"):
        from app.medical_access import require_medical_access

        require_medical_access(db, case, user, session)
    original_case_id = row.case_id
    if row.case_id is None and not isinstance(row, AssistantLog):
        row.case_id = target
    row = retain_response(db, row)
    for saved in db.scalars(
        select(Snapshot).where(Snapshot.case_id == target, Snapshot.kind == "assistant_evidence")
    ):
        if saved.body.get("id") == row.id:
            from app.db.copilot import EvidenceVisibility
            from app.research import refresh_draft

            hidden = db.scalars(
                select(EvidenceVisibility).where(
                    EvidenceVisibility.evidence_id == saved.id, EvidenceVisibility.hidden_at.is_not(None)
                )
            ).all()
            if hidden:
                for visibility in hidden:
                    visibility.hidden_at = None
                audit(
                    db, target, "assistant_evidence_restored", f"broker:{user.id}", {"evidence_id": saved.id}
                )
                refresh_draft(db, case, user)
            return {"id": saved.id, "hash": saved.body_hash, "duplicate": True}
    snapshot = save_snapshot(
        db,
        target,
        "assistant_evidence",
        {**public_log(row), "case_id": target, "original_response_case_id": original_case_id},
    )
    audit(
        db,
        target,
        "assistant_evidence_saved",
        f"broker:{user.id}",
        {"log_id": row.id, "snapshot_hash": snapshot.body_hash},
    )
    from app.research import refresh_draft

    refresh_draft(db, case, user)
    return {
        "id": snapshot.id,
        "hash": snapshot.body_hash,
        "notice": "Saved as supporting research. Published recommendations remain bound to their signed version.",
    }


@router.get("/evidence")
def evidence(request: Request, case_id: str, db=Depends(database, scope="function")):
    user, session = identity(db, request)
    scoped_case(db, case_id)
    from app.research import research_rows

    rows = research_rows(db, case_id)
    result = []
    for row in rows:
        if row.body.get("protected"):
            from app.medical_access import require_medical_access

            require_medical_access(db, service.get_case(db, case_id), user, session)
        result.append(
            {
                **row.body,
                "response_id": row.body["id"],
                "id": row.id,
                "hash": row.body_hash,
                "version": row.version,
            }
        )
    return result


class VisibilityInput(Model):
    hidden: bool = True


@router.put("/evidence/{evidence_id}/visibility")
def evidence_visibility(
    evidence_id: str, body: VisibilityInput, request: Request, db=Depends(database, scope="function")
):
    from app.db.copilot import EvidenceVisibility
    from app.research import refresh_draft

    user, session = identity(db, request)
    if user.role not in {"authorised_broker", "senior_broker", "lead_broker", "compliance_officer"}:
        raise DomainError("An authorised broker or reviewer must update research", 403)
    row = db.get(Snapshot, evidence_id)
    if not row or row.kind != "assistant_evidence":
        raise DomainError("Saved research not found", 404)
    case = service.get_case(db, row.case_id)
    require_protected(db, row, user, session)
    visibility = db.get(EvidenceVisibility, (row.id, user.id))
    if not visibility:
        visibility = EvidenceVisibility(evidence_id=row.id, broker_id=user.id)
        db.add(visibility)
    visibility.hidden_at = utcnow().isoformat() if body.hidden else None
    if not body.hidden:
        for previous in db.scalars(
            select(EvidenceVisibility).where(EvidenceVisibility.evidence_id == row.id)
        ):
            previous.hidden_at = None
    audit(
        db,
        case.id,
        "assistant_evidence_hidden" if body.hidden else "assistant_evidence_restored",
        f"broker:{user.id}",
        {"evidence_id": row.id, "immutable_snapshot_hash": row.body_hash},
    )
    refresh_draft(db, case, user)
    return {
        "id": row.id,
        "hidden": body.hidden,
        "notice": "Research visibility updated. The audit and original snapshot are retained.",
    }


class ExportInput(Model):
    log_ids: list[str] = Field(min_length=1, max_length=20)
    format: str = Field(pattern="^(pdf|docx)$")
    receipts: dict[str, str] = Field(default_factory=dict, max_length=20)


@router.post("/export")
def export(body: ExportInput, request: Request, db=Depends(database, scope="function")):
    rows = [
        public_log(own_response(db, log_id, request, body.receipts.get(log_id))[0]) for log_id in body.log_ids
    ]
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
def share(
    log_id: str, request: Request, body: EvidenceInput | None = None, db=Depends(database, scope="function")
):
    row, user, _ = own_response(db, log_id, request, body.receipt if body else None)
    if not row.case_id:
        raise DomainError("Only case responses can be shared for compliance review", 422)
    row = retain_response(db, row)
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
