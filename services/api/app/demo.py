from sqlalchemy import select
from app.auth import hasher
from app.db.models import User
from app.schemas import CoverageNeed, Needs, QuoteRequest
from app.service import import_request

DEMO_PASSWORD = "HelmDemo!2026"


def seed_demo(db):
    for email, name, role, approve in [
        ("broker@helm.demo", "Garv Gupta", "authorised_broker", True),
        ("assistant@helm.demo", "Alex Morgan", "broker_assistant", False),
        ("compliance@helm.demo", "Sam Taylor", "compliance_officer", False),
    ]:
        if not db.scalar(select(User).where(User.email == email)):
            db.add(User(email=email, name=name, role=role, can_approve=approve,
                        password_hash=hasher.hash(DEMO_PASSWORD)))
    for i, (name, cover, postcode, budget) in enumerate([
        ("Asha Patel", "family", "M20", 240000),
        ("Oliver Bennett", "individual", "SW11", 150000),
        ("Sophie & James", "couple", "BS8", 190000),
    ]):
        import_request(db, QuoteRequest(id=f"demo-request-{i + 1}", name=name, cover_type=cover,
            postcode_district=postcode, needs=Needs(budget_annual_pence=budget, coverage={
                "cancer": CoverageNeed(level=3, must_have=True),
                "mental": CoverageNeed(level=2, importance=0.6),
                "outpatient": CoverageNeed(level=3, importance=0.8)})))
    db.commit()
