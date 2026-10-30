from sqlalchemy import select, event
from app import main
from app.db.models import Case
from app.db.store import save_snapshot
from test_governance_access import login


def test_case_detail_uses_latest_versions_without_a_query_per_snapshot_kind(client):
    login(client, "broker@helm.demo")
    with main.SessionLocal() as db:
        case = db.scalar(select(Case))
        case_id = case.id
        for number in range(8):
            save_snapshot(db, case_id, "consumer_link", {"type": "fixture", "version": number})
        db.commit()
    engine = main.SessionLocal.kw["bind"]
    queries = []

    def record(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        result = client.get("/api/v1/cases/" + case_id)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert result.status_code == 200
    assert result.json()["consumer_link"]["version"] == 7
    assert result.json()["dnr"] and len(queries) <= 9
