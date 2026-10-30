"""Read-only case file, explainable agent work and a source-grounded local assistant."""

from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import select, func
from app import service
from app.auth import identity
from app.agents.runtime import AGENTS
from app.case_access import visible_cases
from app.compliance.medical_firewall import safe_case
from app.db.models import Activity, Case, Snapshot
from app.db.store import verify_chain
from app.demo_documents import database
from app.schemas import Model

router = APIRouter(prefix="/api/v1")

WHY = {
    1: "Extract the client's stated requirements and source facts before requesting quotations. Missing information or unclear medical wording stops the normal journey.",
    2: "Send a minimised request to eligible partners and check returned premiums and documents. Names and raw medical statements are excluded from the default RFQ.",
    3: "Compare policy fit and balance against the saved budget, coverage and priorities. Commission does not contribute to ranking scores.",
    4: "Build the recommendation from the broker's chosen policies and order, and make gaps, terms and disclosures visible before the broker signs.",
    5: "Evaluate recorded broker choices as preference evidence. Insufficient evidence is reported; model changes are proposals and are never activated automatically.",
}


def next_action(case):
    automatic = case.profile.get("workflow") == "fictional-two-decisions-v1"
    return {
        "BROKER_REVIEW": "Choose three policies and put them in your preferred order.",
        "AWAIT_APPROVAL": "Review the recommendation and give your authenticated final sign-off.",
        "PUBLISHED": "Recommendation delivered. No further broker decision is required for this demo.",
        "CLOSED": "Case closed. The saved file and audit evidence remain available.",
        "PAUSED_NEEDS_HUMAN": "Automation is on hold. Review the recorded exception before continuing.",
        "UW_REFERRAL": "An underwriter referral requires an explicit recorded resolution.",
        "COMPLAINT_FLAGGED": "The complaint is on hold with its assigned compliance owner.",
        "NEEDS_INFO": "The fact-find is incomplete. Review the missing information.",
        "FACTFIND_REVIEW": "The demo coordinator is checking the fictional facts automatically."
        if automatic
        else "Review and sign off the fact-find.",
        "AWAIT_BROKER_RELEASE": "Review the partner panel and release the quotation request.",
    }.get(
        case.state, "Agents are preparing the case automatically. This screen updates as their work is saved."
    )


def workspace_data(db, case, user):
    data = safe_case(service.detail(db, case), user)
    rows = db.scalars(select(Snapshot).where(Snapshot.case_id == case.id).order_by(Snapshot.version)).all()
    last = {row.kind: row for row in rows}
    dnr = data.get("dnr") or {}
    needs = dnr.get("needs") or (last["request"].body.get("needs", {}) if "request" in last else {})
    events = data["events"]
    agent_work = []
    outputs = {1: "dnr", 2: "quotes", 3: "ranking", 4: "pack", 5: "demo_learning"}
    starts = {
        1: "intake_started",
        2: "demo_quotation_started",
        3: "ranking_started",
        4: "review_started",
        5: "G2_APPROVED",
    }
    for agent in AGENTS:
        number = agent["id"]
        evidence = last.get(outputs[number])
        related = [e for e in events if e["actor"] == f"agent:{number}"]
        started = next(
            (
                e
                for e in reversed(events)
                if e["type"] == starts[number] or (number == 2 and e["type"] == "rfq_released")
            ),
            None,
        )
        failed = any(
            e["type"]
            in {
                "ranking_requires_human",
                "partner_requires_human",
                "insufficient_quotes",
                "partner_gateway_halted",
            }
            for e in related
        )
        held = case.state in {"PAUSED_NEEDS_HUMAN", "COMPLAINT_FLAGGED", "UW_REFERRAL"}
        status = (
            "needs_attention"
            if failed
            else "complete"
            if evidence
            else "on_hold"
            if held
            else "running"
            if started
            else "waiting"
        )
        summary = "Waiting for the preceding step."
        if number == 1 and evidence:
            summary = f"Saved {len(dnr.get('facts', {}))} sourced facts; {len(dnr.get('missing', []))} missing fields."
        elif number == 2 and evidence:
            summary = (
                f"Saved {len(data['quotes']['quotes'])} structured quotations and the partner response board."
            )
        elif number == 3 and evidence:
            summary = f"Compared quotations and saved {len(data['ranking']['top'])} ranked policies with score explanations."
        elif number == 4 and evidence:
            summary = f"Prepared the three-policy recommendation; {len(data['pack']['unmet_needs'])} recorded unmet needs. Final approval belongs to the broker."
        elif number == 5 and evidence:
            result = evidence.body
            summary = f"Evaluation: {result['status'].replace('_', ' ')}; {result['comparison_count']} comparisons. No model change was applied."
        elif status == "running":
            summary = "Work is queued or running; the saved output will appear here when it completes."
        agent_work.append(
            {
                **agent,
                "status": status,
                "why": WHY[number],
                "summary": summary,
                "started_at": started["created_at"] if started else None,
                "finished_at": evidence.created_at if evidence else None,
                "evidence": {"kind": evidence.kind, "version": evidence.version, "hash": evidence.body_hash}
                if evidence
                else None,
                "event_sequences": [e["seq"] for e in related],
            }
        )
    source = last.get("request")
    result = {
        "case_id": case.id,
        "state": case.state,
        "next_action": next_action(case),
        "agent_work": agent_work,
        "chain_valid": verify_chain(
            db.scalars(select(Activity).where(Activity.case_id == case.id).order_by(Activity.seq)).all()
        ),
        "events": events,
        "client_file": {
            "identity": {
                "name": data["name"],
                "cover_type": data["cover_type"],
                "postcode": data["postcode"],
                "date_of_birth": None,
                "contact_details": None,
                "request_reference": case.core_request_id,
            },
            "preferences": needs,
            "facts": dnr.get("facts", {}),
            "consent_to_share": dnr.get("consent_to_share"),
            "missing": dnr.get("missing", []),
            "medical_declaration_count": len(dnr.get("medical_items", [])),
            "medical_notice": "Medical statements and sensitive documents require verified case access. No clinical history or coverage conclusion is inferred.",
            "record": dnr.get("record"),
            "source": {"kind": "request", "version": source.version, "hash": source.body_hash}
            if source
            else None,
            "documents": [
                {
                    "id": row.id,
                    "category": row.body["category"],
                    "mime": row.body["mime"],
                    "pages": row.body["pages"],
                    "sha256": row.body["sha256"],
                    "created_at": row.created_at,
                }
                for row in rows
                if row.kind == "case_document"
            ],
            "records": [
                {
                    "kind": row.kind,
                    "version": row.version,
                    "hash": row.body_hash,
                    "created_at": row.created_at,
                }
                for row in rows
                if row.kind
                in {
                    "request",
                    "dnr",
                    "rfq",
                    "quotes",
                    "ranking",
                    "selection",
                    "pack",
                    "publication",
                    "consumer_response",
                    "policy_bound",
                }
            ],
            "selected_policies": [
                {
                    "id": row["plan"]["id"],
                    "name": row["plan"]["name"],
                    "annual_pence": row["plan"]["annualPremiumPence"],
                }
                for row in (data.get("pack") or {}).get("plans", [])
            ],
            "publication": data.get("publication"),
            "consumer_response": data.get("consumer_response"),
        },
    }
    # All free-form facts are redacted together against the original medical statements.
    return safe_case(
        {**result, "medical_items": (last["dnr"].body.get("medical_items", []) if "dnr" in last else [])},
        user,
    )


@router.get("/cases/{case_id}/workspace")
def case_workspace(case_id: str, request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    return workspace_data(db, service.get_case(db, case_id), user)


class Question(Model):
    question: str = Field(min_length=1, max_length=1500)
    case_id: str | None = Field(default=None, max_length=100)


@router.post("/workspace/assistant")
def assistant(body: Question, request: Request, db=Depends(database, scope="function")):
    user, _ = identity(db, request)
    query = body.question.casefold()
    if not body.case_id:
        scope = visible_cases(user)
        counts = dict(db.execute(select(Case.state, func.count()).where(scope).group_by(Case.state)).all())
        cases = db.scalars(select(Case).where(scope).order_by(Case.created_at.desc()).limit(10)).all()
        return {
            "answer": f"Your visible workspace has {sum(counts.values())} cases. "
            + "; ".join(f"{key.replace('_', ' ').lower()}: {value}" for key, value in sorted(counts.items()))
            + ". Open a case to ask about its client, policies, agent work or next step.",
            "sources": [
                {
                    "label": f"{case.profile['name']} · {case.state.replace('_', ' ').lower()}",
                    "case_id": case.id,
                }
                for case in cases
            ],
            "mode": "local_saved_evidence",
            "actions_performed": [],
        }
    case = service.get_case(db, body.case_id)
    context = workspace_data(db, case, user)
    data = safe_case(service.detail(db, case), user)
    file = context["client_file"]
    sources = []
    answer = context["next_action"]
    if any(word in query for word in ("medical", "diagnos", "condition", "disease", "patient history")):
        answer = (
            file["medical_notice"]
            + f" There are {file['medical_declaration_count']} recorded medical statements."
        )
        sources = [{"label": "Digital client file · protected medical declaration", "view": "file"}]
    elif any(word in query for word in ("budget", "prefer", "need", "client", "patient", "profile")):
        needs = file["preferences"]
        answer = f"{file['identity']['name']} requested {file['identity']['cover_type']} cover in {file['identity']['postcode']}. Annual budget: £{needs.get('budget_annual_pence', 0) / 100:,.2f}. Priorities in order: {', '.join(needs.get('priorities', []))}. Hospital list level: {needs.get('hospital_level', 'not provided')}. "
        answer += (
            "Requested benefits: "
            + "; ".join(
                f"{key}: level {value['level']}" + (" (must have)" if value.get("must_have") else "")
                for key, value in needs.get("coverage", {}).items()
            )
            + "."
        )
        sources = [{"label": "Saved demands and needs · client preferences", "view": "file"}]
    elif any(
        word in query
        for word in ("quote", "plan", "polic", "rank", "score", "best", "recommend", "trade", "gap")
    ):
        ranking = data.get("ranking")
        if ranking:
            rows = ranking["top"]
            match = next(
                (
                    row
                    for row in rows
                    if row["plan"]["name"].casefold() in query or row["plan"]["id"] in query
                ),
                None,
            )
            if match:
                answer = f"{match['plan']['name']}: {match['explanation']['overall']} Annual premium £{match['plan']['annualPremiumPence'] / 100:,.2f} including IPT. "
                answer += (
                    "Recorded blockers: " + (", ".join(map(str, match.get("blockers", []))) or "none") + "."
                )
            else:
                answer = (
                    "The current engine order is: "
                    + "; ".join(
                        f"{i + 1}. {row['plan']['name']} — £{row['plan']['annualPremiumPence'] / 100:,.2f} per year, {row['score']:.1f}/100"
                        for i, row in enumerate(rows)
                    )
                    + ". Scores follow the saved client priorities. Commission is excluded. Ask about a policy by name for its saved explanation."
                )
            if data.get("pack"):
                answer += (
                    " Broker's chosen order: "
                    + ", ".join(row["plan"]["name"] for row in data["pack"]["plans"])
                    + "."
                )
            sources = [{"label": "Current ranking · " + ranking["id"], "view": "journey"}]
        else:
            answer = "No ranking has been saved yet. " + context["next_action"]
    elif any(word in query for word in ("agent", "why", "audit", "work", "stop", "progress")):
        answer = "\n\n".join(
            f"Agent {agent['id']} — {agent['name']} ({agent['status'].replace('_', ' ')}). {agent['summary']} Why: {agent['why']}"
            for agent in context["agent_work"]
        )
        sources = [{"label": "Agent work and verified event trail", "view": "audit"}]
    elif any(word in query for word in ("document", "file", "evidence", "record")):
        answer = f"The digital file has {len(file['documents'])} uploaded source documents and {len(file['records'])} versioned workflow records. It includes available identity facts, preferences, consent, policy choices and delivery history. Missing birth date, contact details and clinical history are not invented."
        sources = [{"label": "Digital client file · documents and record versions", "view": "file"}]
    elif not any(
        word in query for word in ("next", "status", "approve", "select", "help", "do", "continue", "stage")
    ):
        answer = (
            "I can explain this case's saved client preferences, current policy ranking, each agent's work, documents and next action. "
            + context["next_action"]
        )
    if not sources:
        sources = [
            {"label": "Current case status · " + case.state.replace("_", " ").lower(), "view": "journey"}
        ]
    # Questions are not commands. This endpoint never invokes an agent, changes a case,
    # sends messages, approves a plan or forwards health information to an external model.
    return {
        "answer": answer,
        "sources": sources,
        "mode": "local_saved_evidence",
        "actions_performed": [],
        "case_id": case.id,
    }
