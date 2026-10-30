"""Case-scoped, measured outcomes; small demographic groups are suppressed."""

from collections import Counter, defaultdict
from datetime import timedelta, timezone
import re
from sqlalchemy import select
from app.case_access import visible_cases
from app.clock import get_clock
from app.db.models import Case, Snapshot, Activity, utcnow
from app.db.platform import Complaint, BrokerRating
from app.governance import ndcg


def measured_outcomes(db, user):
    scope = visible_cases(user)
    since = (utcnow() - timedelta(days=30)).isoformat()
    cases = {case.id: case for case in db.scalars(select(Case).where(scope))}
    rows = db.scalars(
        select(Snapshot)
        .join(Case, Snapshot.case_id == Case.id)
        .where(
            scope,
            Snapshot.kind.in_(["selection", "ranking", "dnr", "policy_bound"]),
            Snapshot.created_at >= since,
        )
        .order_by(Snapshot.created_at, Snapshot.version)
        .limit(4000)
    ).all()
    current = {}
    rankings = {}
    for row in rows:
        current[row.case_id, row.kind] = row
        if row.kind == "ranking":
            rankings[row.case_id, row.body["id"]] = row.body
    daily = defaultdict(list)
    cohorts = defaultdict(list)
    thumbs = Counter()
    durations = []
    for (case_id, kind), row in current.items():
        if kind != "selection":
            continue
        body = row.body
        ranking = rankings.get((case_id, body.get("ranking_id")))
        if not ranking:
            continue
        value = ndcg([r["plan"]["id"] for r in ranking["top"]], body["selected"])
        daily[row.created_at[:10]].append(value)
        thumbs.update(body.get("survey", {}).get("thumbs", {}).values())
        case = cases[case_id]
        dnr = current.get((case_id, "dnr"))
        area = re.match(r"[A-Za-z]+", case.profile.get("postcode_district", ""))
        segments = {
            "cover_type": case.profile.get("cover_type", "not supplied"),
            "postcode_area": area.group().upper() if area else "not supplied",
            "age_band": "not supplied",
            "vulnerability": "flagged" if dnr and dnr.body.get("vulnerability_flags") else "not flagged",
        }
        for axis, segment in segments.items():
            cohorts[axis, segment].append(value)
    ratings = {}
    for row in db.scalars(
        select(BrokerRating)
        .join(Case, BrokerRating.case_id == Case.id)
        .where(scope, BrokerRating.created_at >= since)
        .order_by(BrokerRating.version)
    ):
        ratings[row.case_id, row.ranking_id, row.plan_id, row.broker_id] = row
    distribution = Counter(row.stars for row in ratings.values())
    decisions = Counter(row.decision for row in ratings.values())
    rank_times = {}
    for row in db.scalars(
        select(Activity)
        .join(Case, Activity.case_id == Case.id)
        .where(
            scope,
            Activity.created_at >= since,
            Activity.type.in_(["ranking_completed", "reranking_completed", "selection_submitted"]),
        )
        .order_by(Activity.created_at)
    ):
        from datetime import datetime

        if row.type != "selection_submitted":
            rank_times[row.case_id] = row.created_at
        elif row.case_id in rank_times:
            durations.append(
                max(
                    0,
                    (
                        datetime.fromisoformat(row.created_at)
                        - datetime.fromisoformat(rank_times[row.case_id])
                    ).total_seconds(),
                )
            )
    complaints = []
    for row in db.scalars(
        select(Complaint).join(Case, Complaint.case_id == Case.id).where(scope, Complaint.status == "open")
    ):
        due = row.due_at if row.due_at.tzinfo else row.due_at.replace(tzinfo=timezone.utc)
        days = (due - utcnow()).total_seconds() * getattr(get_clock(), "multiplier", 1) / 86400
        complaints.append(
            {
                "id": row.id,
                "case_id": row.case_id,
                "due_at": due.isoformat(),
                "business_days_remaining": round(days, 1),
                "severity": "overdue"
                if days < 0
                else "red"
                if days < 14
                else "amber"
                if days <= 28
                else "green",
            }
        )
    bound = [row.body["final_premium"] for (case_id, kind), row in current.items() if kind == "policy_bound"]
    return {
        "period_days": 30,
        "source_snapshot_limit": 4000,
        "sample_limited": len(rows) == 4000,
        "ndcg_series": [
            {"day": day, "cases": len(values), "ndcg3": sum(values) / len(values)}
            for day, values in sorted(daily.items())
        ],
        "ratings": {
            "stars": {str(i): distribution[i] for i in range(1, 6)},
            "decisions": dict(decisions),
            "edited": sum(row.is_edited for row in ratings.values()),
            "total": len(ratings),
        },
        "survey": dict(thumbs),
        "mean_review_seconds": sum(durations) / len(durations) if durations else None,
        "complaints": complaints,
        "bound_ipt_pence": sum(row["ipt_pence"] for row in bound),
        "bound_cases": len(bound),
        "ipt_basis": "Recorded IPT already included in confirmed fictional bound premiums; not an estimate of tax liability.",
        "cohorts": [
            {
                "axis": axis,
                "segment": segment,
                "cases": len(values),
                "ndcg3": sum(values) / len(values) if len(values) >= 5 else None,
                "suppressed": len(values) < 5,
            }
            for (axis, segment), values in sorted(cohorts.items())
        ],
        "fairness_note": "Descriptive outcomes only. Groups under five cases are suppressed; missing age is not inferred and no protected characteristic enters scoring.",
    }
