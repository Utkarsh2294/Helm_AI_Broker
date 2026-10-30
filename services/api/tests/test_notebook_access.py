from sqlalchemy import select
from app import main
from app.db.models import Case, User
from app.db.platform import EdgeCase
from app.db.store import save_snapshot
from test_governance_access import login


def test_notebook_respects_case_ownership_and_redacts_known_medical_text(client):
    login(client, "broker@helm.demo")
    with main.SessionLocal() as db:
        other = db.scalar(select(User).where(User.email == "lead@helm.demo"))
        case = db.scalar(select(Case))
        case.assigned_to = other.id
        save_snapshot(db, case.id, "dnr", {"medical_items": ["PHI_NOTEBOOK_CANARY"]})
        db.add(
            EdgeCase(
                case_id=case.id,
                selection_id="fixture-selection",
                body={
                    "summary": "Review requested",
                    "survey": {"note": "PHI_NOTEBOOK_CANARY copied in feedback"},
                },
            )
        )
        db.commit()
    assert client.get("/api/v1/edge-cases").json() == []
    login(client, "compliance@helm.demo")
    visible = client.get("/api/v1/edge-cases")
    assert visible.status_code == 200 and len(visible.json()) == 1
    assert "PHI_NOTEBOOK_CANARY" not in visible.text
