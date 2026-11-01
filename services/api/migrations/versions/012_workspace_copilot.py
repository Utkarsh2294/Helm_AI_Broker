"""Broker notifications, task snoozes, source projections and daily analytics."""

from alembic import op
from sqlalchemy import select, func
from app.db import copilot

revision = "012"
down_revision = "011"
branch_labels = depends_on = None
TABLES = [
    copilot.Notification,
    copilot.PushSubscription,
    copilot.TaskSnooze,
    copilot.NotificationLease,
    copilot.CopilotPreferences,
    copilot.CaseSatisfaction,
    copilot.CaseMetric,
    copilot.ProviderMetric,
    copilot.SatisfactionDrivers,
    copilot.EvidenceVisibility,
    copilot.AssistantAudit,
]


def upgrade():
    connection = op.get_bind()
    for model in TABLES:
        model.__table__.create(connection, checkfirst=True)
    for model in (copilot.CaseSatisfaction, copilot.AssistantAudit):
        name = model.__tablename__
        if connection.dialect.name == "postgresql":
            op.execute(
                f"CREATE TRIGGER {name}_append_only BEFORE UPDATE OR DELETE ON {name} FOR EACH ROW EXECUTE FUNCTION helm_deny_mutation()"
            )
        else:
            for action in ("UPDATE", "DELETE"):
                op.execute(
                    f"CREATE TRIGGER IF NOT EXISTS {name}_no_{action.lower()} BEFORE {action} ON {name} BEGIN SELECT RAISE(ABORT, 'Evidence records are append-only'); END"
                )
    from sqlalchemy.orm import Session
    from app.db.models import Case
    from app.copilot_projection import project_case

    with Session(bind=connection) as db:
        for case in db.scalars(select(Case)):
            project_case(db, case)
        db.flush()
    if connection.dialect.name == "postgresql":
        op.execute(
            "CREATE MATERIALIZED VIEW mv_case_daily_stats AS SELECT date_trunc('day', created_at::timestamptz) AS day, coverage_type, broker_id, insurer_id, count(*) AS new_cases, count(*) FILTER (WHERE state IN ('PUBLISHED','CLOSED')) AS closed_cases, avg(close_days) AS avg_days_to_close FROM case_metrics GROUP BY 1,2,3,4"
        )
        op.execute(
            "CREATE UNIQUE INDEX ix_mv_case_daily_stats ON mv_case_daily_stats(day, coverage_type, broker_id, insurer_id)"
        )
    else:
        op.execute(
            "CREATE VIEW mv_case_daily_stats AS SELECT substr(created_at,1,10) AS day, coverage_type, broker_id, insurer_id, count(*) AS new_cases, sum(CASE WHEN state IN ('PUBLISHED','CLOSED') THEN 1 ELSE 0 END) AS closed_cases, avg(close_days) AS avg_days_to_close FROM case_metrics GROUP BY 1,2,3,4"
        )


def downgrade():
    connection = op.get_bind()
    for model in (copilot.Notification, copilot.CaseSatisfaction, copilot.AssistantAudit):
        if connection.scalar(select(func.count()).select_from(model)):
            raise RuntimeError("Cannot downgrade saved workspace evidence; restore a tested backup instead")
    kind = "MATERIALIZED VIEW" if connection.dialect.name == "postgresql" else "VIEW"
    op.execute(f"DROP {kind} IF EXISTS mv_case_daily_stats")
    for model in reversed(TABLES):
        model.__table__.drop(connection, checkfirst=True)
