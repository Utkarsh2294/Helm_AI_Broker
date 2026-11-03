"""Compile accepted versions; medical answers travel as sealed references, never prose."""

from sqlalchemy import select
from app.agents.review import canonical_hash
from app.buying_documents import current_documents, add_document
from app.buying_review import set_document_state, current_document
from app.buying_templates import WATERMARK, section
from app.buying_updates import record_update
from app.db.policy_buying import BuyingMedicalResponse
from app.schemas import DomainError


def manifest(db, case, buying):
    kind = "moratorium_declaration" if buying.underwriting_basis == "moratorium" else "fmu_questionnaire"
    documents, statuses = current_documents(db, buying.id), buying.body.get("documents", {})
    required = ["ipid", "toba", kind, "banking_summary"]
    if (
        not buying.body.get("baseline_acknowledged")
        or not buying.body.get("declaration_approved")
        or not buying.body.get("banking_verified")
    ):
        raise DomainError("Underwriting and banking approvals must be current")
    accepted = {}
    for name in required:
        row = documents.get(name)
        if not row or statuses.get(name) != {"id": row.id, "status": "confirmed"}:
            raise DomainError("Every required document needs confirmation of its current version")
        accepted[name] = {"id": row.id, "hash": row.content_hash, "version": row.version}
    if (buying.body.get("declaration_response") or {}).get("document_id") != documents[kind].id:
        raise DomainError("The current declaration needs a fresh consumer signature")
    medical_id = None
    if buying.underwriting_basis == "fmu":
        medical = db.scalar(
            select(BuyingMedicalResponse).where(BuyingMedicalResponse.document_id == documents[kind].id)
        )
        if not medical:
            raise DomainError("A completed sealed FMU questionnaire is required")
        medical_id = medical.id
    return {
        "documents": accepted,
        "plan_id": buying.selected_plan_id,
        "insurer": buying.body["plan"]["insurerId"],
        "consumer": {
            key: case.profile.get(key) for key in ("name", "date_of_birth", "email", "phone", "postcode")
        },
        "sealed_medical_response_id": medical_id,
        "standing_toba_acceptance": buying.body.get("standing_toba_acceptance"),
        "demo": True,
    }


def prepare_package(db, case, buying):
    package = manifest(db, case, buying)
    content = {
        "title": "Final Submission Package",
        "demo": True,
        "watermark": WATERMARK,
        "sections": [
            section(
                "Insurer cover note",
                f"Fictional application for {buying.body['plan']['name']} with {buying.body['plan']['insurerId']}. The broker confirmed the required document versions and fictional payment setup. No coverage or medical conclusion is made.",
            ),
            section(
                "Accepted document manifest",
                "; ".join(
                    f"{name.replace('_', ' ')} v{row['version']}"
                    for name, row in package["documents"].items()
                ),
            ),
            section(
                "Sensitive attachments",
                "Completed FMU answers, where required, remain sealed and are passed by immutable reference to the mock adapter. Banking summaries contain masked details only. No real insurer receives this package.",
            ),
        ],
        "manifest": package,
    }
    document = add_document(db, buying, "submission_package", content)
    set_document_state(buying, "submission_package", document, "draft")
    buying.body = {**buying.body, "package_hash": canonical_hash(package), "submission_reviewed": None}
    record_update(
        db,
        buying,
        "submission_ready",
        "Local demo agent prepared the full submission package for broker review",
    )


def review_package(db, case, buying, document_id, actor):
    document = current_document(db, buying, "submission_package", document_id)
    package = manifest(db, case, buying)
    if (
        buying.stage != "SUBMISSION_PACKAGE_READY"
        or document.content.get("manifest") != package
        or buying.body.get("package_hash") != canonical_hash(package)
    ):
        raise DomainError("The package is stale; prepare and review the current accepted versions")
    buying.body = {**buying.body, "submission_reviewed": buying.body["package_hash"]}
    record_update(
        db, buying, "submission_reviewed", "Broker opened the read-only final submission preview", actor
    )
