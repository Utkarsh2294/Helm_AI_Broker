"""Append new document versions; accepted/sent state is tracked independently."""

from sqlalchemy import select
from app.agents.review import canonical_hash
from app.db.policy_buying import BuyingDocument


def document_versions(db, buying_id):
    return db.scalars(
        select(BuyingDocument)
        .where(BuyingDocument.pb_case_id == buying_id)
        .order_by(BuyingDocument.version.desc(), BuyingDocument.doc_type)
    ).all()


def current_documents(db, buying_id):
    documents = {}
    for document in document_versions(db, buying_id):
        documents.setdefault(document.doc_type, document)
    return documents


def add_document(db, buying, kind, content, actor="demo-agent", edited=False):
    previous = current_documents(db, buying.id).get(kind)
    row = BuyingDocument(
        pb_case_id=buying.id,
        doc_type=kind,
        version=previous.version + 1 if previous else 1,
        content=content,
        content_hash=canonical_hash(content),
        actor=actor,
        edited_by_broker=edited,
    )
    db.add(row)
    db.flush()
    return row
