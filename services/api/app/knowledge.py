from sqlalchemy import or_, select
from app.db.platform import KnowledgeEntry

TOPICS = {
    "hospitals": "Ask which hospitals are included and record the source for each preferred hospital.",
    "excess": "Confirm the excess amount, when it applies and any per-person or per-year limits with the insurer.",
    "underwriting": "Ask the insurer to explain its underwriting basis. Refer medical interpretation to a human underwriter.",
    "cancer": "Confirm the stated cancer-cover level against the current policy document. Do not infer coverage for a condition.",
    "outpatient": "Confirm outpatient limits and the customer's desired level. List any unmet needs in the broker statement.",
    "mental health": "Confirm the stated mental-health benefit and restrictions from the insurer's documentation.",
    "children": "For family requests, ask about dependent eligibility and required benefits without guessing needs.",
    "existing cover": "Compare the renewal document with the customer's stated existing cover and highlight discrepancies.",
    "budget": "Record the customer's annual budget and whether it is a hard cap before comparing quotations.",
    "documents": "Confirm which documents are required and which the customer can provide before selecting a plan.",
}


def seed_knowledge(db):
    for topic, answer in TOPICS.items():
        for i, template in enumerate(["What should we confirm about {}?", "Which evidence is needed for {}?", "How should a broker review {}?", "What should a family ask about {}?", "What should be recorded when comparing {}?"]):
            key = f"pmi:{topic.replace(' ', '-')}:v1:{i}"
            if not db.get(KnowledgeEntry, key):
                db.add(KnowledgeEntry(id=key, category=topic, question=template.format(topic), answer=answer))


def search_knowledge(db, query, limit=5):
    words = [word for word in query.split() if len(word) > 3][:8]
    statement = select(KnowledgeEntry)
    if words:
        statement = statement.where(or_(*[KnowledgeEntry.question.ilike(f"%{word}%") for word in words]))
    return [{"id": row.id, "question": row.question, "answer": row.answer, "category": row.category}
            for row in db.scalars(statement.order_by(KnowledgeEntry.id).limit(limit))]
