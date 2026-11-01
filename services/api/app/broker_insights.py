"""Filtered analytics over indexed non-clinical projections, never customer snapshots."""

import csv
import io
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import Literal
from fastapi import Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import select, func, case as sql_case, table, column, String, cast, and_, true
from app.auth import identity
from app.copilot_api import metric_scope, senior
from app.db.models import User, utcnow
from app.db.copilot import CaseMetric, ProviderMetric, SatisfactionDrivers
from app.demo_documents import database
from app.schemas import DomainError, Model
from app.insights_cache import cached
from app.db.async_session import OperationalRouter, asynchronous

router = OperationalRouter(prefix="/api/v1/insights")
daily = table(
    "mv_case_daily_stats",
    *[
        column(name)
        for name in (
            "day",
            "coverage_type",
            "broker_id",
            "insurer_id",
            "new_cases",
            "closed_cases",
            "avg_days_to_close",
        )
    ],
)


@asynchronous
def context(
    request: Request,
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    coverage_type: Literal["individual", "couple", "family"] | None = None,
    broker_id: str | None = None,
    insurer_id: str | None = Query(None, max_length=100),
    db=Depends(database, scope="function"),
):
    user, _ = identity(db, request)
    return build_context(db, user, from_date, to_date, coverage_type, broker_id, insurer_id)


def build_context(
    db, user, from_date=None, to_date=None, coverage_type=None, broker_id=None, insurer_id=None
):
    start, end = from_date or utcnow().date() - timedelta(days=29), to_date or utcnow().date()
    if start > end or (end - start).days > 3660:
        raise DomainError("Choose an ordered date range of at most ten years", 422)
    metric_scope(user, broker_id)

    def filters(model=CaseMetric):
        rows = [
            metric_scope(user, broker_id, model),
            model.created_at >= start.isoformat(),
            model.created_at < (end + timedelta(days=1)).isoformat(),
        ]
        if coverage_type:
            rows.append(model.coverage_type == coverage_type)
        if insurer_id:
            rows.append(model.insurer_id == insurer_id)
        return rows

    return SimpleNamespace(
        db=db,
        user=user,
        start=start,
        end=end,
        coverage=coverage_type,
        broker=broker_id,
        insurer=insurer_id,
        filters=filters,
    )


def median_close(ctx):
    query = select(CaseMetric.close_days).where(*ctx.filters(), CaseMetric.close_days.is_not(None))
    if ctx.db.bind.dialect.name == "postgresql":
        return ctx.db.scalar(
            select(func.percentile_cont(0.5).within_group(CaseMetric.close_days)).where(*ctx.filters())
        )
    values = ctx.db.scalars(query).all()
    return statistics.median(values) if values else None


@router.get("/volume")
@cached
def volume(granularity: Literal["day", "week", "month", "year"] = "day", ctx=Depends(context)):
    filters = [
        metric_scope(ctx.user, ctx.broker, daily.c),
        cast(daily.c.day, String) >= ctx.start.isoformat(),
        cast(daily.c.day, String) < (ctx.end + timedelta(days=1)).isoformat(),
    ]
    if ctx.coverage:
        filters.append(daily.c.coverage_type == ctx.coverage)
    if ctx.insurer:
        filters.append(daily.c.insurer_id == ctx.insurer)
    if ctx.db.bind.dialect.name == "postgresql":
        bucket = func.date_trunc(granularity, daily.c.day)
    else:
        bucket = func.strftime(
            {"day": "%Y-%m-%d", "week": "%Y-%W", "month": "%Y-%m", "year": "%Y"}[granularity], daily.c.day
        )
    rows = (
        ctx.db.execute(
            select(
                bucket.label("bucket"),
                func.sum(daily.c.new_cases).label("new"),
                func.sum(daily.c.closed_cases).label("closed"),
            )
            .where(*filters)
            .group_by(bucket)
            .order_by(bucket)
        )
        .mappings()
        .all()
    )
    return {
        "rows": [dict(row) for row in rows],
        "granularity": granularity,
        "source": "mv_case_daily_stats",
        "basis": "Intake cohorts: delivered/closed status within each intake-date group. UTC dates. PostgreSQL projection refreshes every 15 minutes.",
    }


@router.get("/aging")
@cached
def aging(ctx=Depends(context)):
    now = utcnow()
    boundaries = [
        ("0–2 days", now - timedelta(days=2), None),
        ("3–5 days", now - timedelta(days=5), now - timedelta(days=2)),
        ("6–10 days", now - timedelta(days=10), now - timedelta(days=5)),
        ("10+ days", None, now - timedelta(days=10)),
    ]
    expressions = []
    for label, lower, upper in boundaries:
        condition = []
        if lower:
            condition.append(CaseMetric.created_at >= lower.isoformat())
        if upper:
            condition.append(CaseMetric.created_at < upper.isoformat())
        from sqlalchemy import and_

        expressions.append(func.sum(sql_case((and_(*condition), 1), else_=0)).label(label))
    row = (
        ctx.db.execute(
            select(*expressions).where(*ctx.filters(), CaseMetric.state.notin_(["PUBLISHED", "CLOSED"]))
        )
        .mappings()
        .one()
    )
    oldest = (
        ctx.db.execute(
            select(CaseMetric.case_id, CaseMetric.state, CaseMetric.created_at)
            .where(*ctx.filters(), CaseMetric.state.notin_(["PUBLISHED", "CLOSED"]))
            .order_by(CaseMetric.created_at)
            .limit(10)
        )
        .mappings()
        .all()
    )
    return {
        "buckets": [
            {"label": name, "count": row[name] or 0, "key": key}
            for name, key in zip(row.keys(), ["0-2", "3-5", "6-10", "10+"])
        ],
        "oldest": [dict(r) for r in oldest],
        "basis": "Calendar age since intake, among open cases in the selected intake-date range.",
    }


@router.get("/time-to-close")
@cached
def time_to_close(by: Literal["state", "coverage_type"] = "coverage_type", ctx=Depends(context)):
    column = CaseMetric.coverage_type if by == "coverage_type" else CaseMetric.state
    rows = (
        ctx.db.execute(
            select(
                column.label("group"),
                func.count(CaseMetric.close_days).label("samples"),
                func.avg(CaseMetric.close_days).label("average_days"),
            )
            .where(*ctx.filters())
            .group_by(column)
        )
        .mappings()
        .all()
    )
    phase = defaultdict(list)
    if ctx.db.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import JSONB
        from sqlalchemy import Float

        entries = (
            func.jsonb_each_text(cast(CaseMetric.body["state_durations"], JSONB))
            .table_valued("key", "value")
            .lateral()
        )
        state_rows = (
            ctx.db.execute(
                select(
                    entries.c.key.label("state"),
                    func.avg(cast(entries.c.value, Float)).label("average_days"),
                    func.percentile_cont(0.5).within_group(cast(entries.c.value, Float)).label("median_days"),
                    func.count().label("samples"),
                )
                .select_from(CaseMetric)
                .join(entries, true())
                .where(*ctx.filters(), CaseMetric.closed_at.is_not(None))
                .group_by(entries.c.key)
            )
            .mappings()
            .all()
        )
    else:
        for body in ctx.db.scalars(
            select(CaseMetric.body).where(*ctx.filters(), CaseMetric.closed_at.is_not(None))
        ):
            for state, days in body.get("state_durations", {}).items():
                phase[state].append(days)
        state_rows = [
            {
                "state": state,
                "average_days": statistics.mean(values),
                "median_days": statistics.median(values),
                "samples": len(values),
            }
            for state, values in phase.items()
        ]
    return {
        "rows": [dict(r) for r in rows],
        "median_days": median_close(ctx),
        "state_durations": [dict(row) for row in state_rows],
        "basis": "First recorded delivery or closure. State timings use saved audit transitions; no missing broker timing is inferred.",
    }


@router.get("/satisfaction")
@cached
def satisfaction(by: Literal["broker", "insurer", "coverage_type"] = "coverage_type", ctx=Depends(context)):
    if by == "broker" and not senior(ctx.user):
        raise DomainError("Senior broker or administrator access is required for broker comparisons", 403)
    group = {
        "broker": CaseMetric.broker_id,
        "insurer": CaseMetric.insurer_id,
        "coverage_type": CaseMetric.coverage_type,
    }[by]
    rows = (
        ctx.db.execute(
            select(
                group.label("group"),
                func.count(CaseMetric.csat).label("samples"),
                func.avg(CaseMetric.csat).label("score"),
            )
            .where(*ctx.filters())
            .group_by(group)
        )
        .mappings()
        .all()
    )
    trend = (
        ctx.db.execute(
            select(
                func.substr(CaseMetric.created_at, 1, 7).label("month"),
                func.avg(CaseMetric.csat).label("score"),
                func.count(CaseMetric.csat).label("samples"),
            )
            .where(*ctx.filters(), CaseMetric.csat.is_not(None))
            .group_by("month")
            .order_by("month")
        )
        .mappings()
        .all()
    )
    return {
        "rows": [dict(r) for r in rows],
        "trend": [dict(r) for r in trend],
        "samples": sum(row["samples"] for row in rows),
        "average": sum((row["score"] or 0) * row["samples"] for row in rows)
        / sum(row["samples"] for row in rows)
        if sum(row["samples"] for row in rows)
        else None,
        "benchmark": None,
        "notice": "Only explicitly recorded consumer satisfaction, 1–5. Broker plan ratings are not CSAT. No verified sector benchmark has been supplied.",
    }


@router.get("/insurer-performance")
@cached
def insurer_performance(ctx=Depends(context)):
    rows = (
        ctx.db.execute(
            select(
                ProviderMetric.insurer_id,
                func.sum(ProviderMetric.shown).label("shown"),
                func.sum(ProviderMetric.top_three).label("top_three"),
                func.sum(ProviderMetric.selected).label("selected"),
                func.sum(ProviderMetric.accepted).label("accepted"),
                func.sum(ProviderMetric.rated_highly).label("rated_highly"),
                func.avg(ProviderMetric.quoted_turnaround).label("quoted_turnaround_days"),
                func.avg(ProviderMetric.upheld_rate).label("saved_upheld_rate"),
            )
            .where(*ctx.filters(ProviderMetric))
            .group_by(ProviderMetric.insurer_id)
        )
        .mappings()
        .all()
    )
    result = []
    for row in rows:
        data = dict(row)
        data["top_three_share"] = data["top_three"] / data["shown"] if data["shown"] else None
        data["selection_share"] = data["selected"] / data["shown"] if data["shown"] else None
        data["actual_underwriting_days"] = None
        result.append(data)
    return {
        "rows": result,
        "notice": "Counts use saved quote, ranking, broker choice and consumer response projections. Quoted turnaround and insurer-reported upheld rates are not measured live underwriting/complaint outcomes.",
    }


@router.get("/plan-patterns")
@cached
def plan_patterns(ctx=Depends(context)):
    if ctx.db.bind.dialect.name == "postgresql":
        return postgres_patterns(ctx)
    coverage, must_have, underwriting = Counter(), Counter(), Counter()
    budgets = {"open": [], "closed": []}
    for body, budget, state in ctx.db.execute(
        select(CaseMetric.body, CaseMetric.budget_pence, CaseMetric.state).where(*ctx.filters())
    ):
        coverage.update(f"{key}: level {value}" for key, value in body.get("coverage", {}).items())
        must_have.update(body.get("must_have", []))
        if body.get("underwriting"):
            underwriting.update([body["underwriting"]])
        if budget is not None:
            budgets["closed" if state in {"PUBLISHED", "CLOSED"} else "open"].append(budget)
    return {
        "coverage": [{"label": k, "count": v} for k, v in coverage.items()],
        "must_have": [{"label": k, "count": v} for k, v in must_have.items()],
        "underwriting": [{"label": k, "count": v} for k, v in underwriting.items()],
        "budget": {
            k: {
                "samples": len(v),
                "median_pence": statistics.median(v) if v else None,
                "minimum_pence": min(v) if v else None,
                "maximum_pence": max(v) if v else None,
            }
            for k, v in budgets.items()
        },
        "notice": "Coverage tiers and must-haves are saved client requests, not proof of insurer coverage or a consumer purchase.",
    }


def postgres_patterns(ctx):
    from sqlalchemy.dialects.postgresql import JSONB

    coverage = (
        func.jsonb_each_text(cast(CaseMetric.body["coverage"], JSONB)).table_valued("key", "value").lateral()
    )
    must = (
        func.jsonb_array_elements_text(cast(CaseMetric.body["must_have"], JSONB))
        .table_valued("value")
        .render_derived()
        .lateral()
    )
    cover_rows = ctx.db.execute(
        select(coverage.c.key, coverage.c.value, func.count())
        .select_from(CaseMetric)
        .join(coverage, true())
        .where(*ctx.filters())
        .group_by(coverage.c.key, coverage.c.value)
    ).all()
    must_rows = ctx.db.execute(
        select(must.c.value, func.count())
        .select_from(CaseMetric)
        .join(must, true())
        .where(*ctx.filters())
        .group_by(must.c.value)
    ).all()
    uw = CaseMetric.body["underwriting"].as_string()
    uw_rows = ctx.db.execute(
        select(uw, func.count()).where(*ctx.filters(), uw.is_not(None)).group_by(uw)
    ).all()
    status = sql_case((CaseMetric.state.in_(["PUBLISHED", "CLOSED"]), "closed"), else_="open").label("status")
    budget_rows = (
        ctx.db.execute(
            select(
                status,
                func.count(CaseMetric.budget_pence).label("samples"),
                func.percentile_cont(0.5).within_group(CaseMetric.budget_pence).label("median_pence"),
                func.min(CaseMetric.budget_pence).label("minimum_pence"),
                func.max(CaseMetric.budget_pence).label("maximum_pence"),
            )
            .where(*ctx.filters(), CaseMetric.budget_pence.is_not(None))
            .group_by("status")
        )
        .mappings()
        .all()
    )
    budgets = {
        key: {"samples": 0, "median_pence": None, "minimum_pence": None, "maximum_pence": None}
        for key in ["open", "closed"]
    }
    for row in budget_rows:
        budgets[row["status"]] = {key: value for key, value in row.items() if key != "status"}
    return {
        "coverage": [{"label": f"{key}: level {value}", "count": count} for key, value, count in cover_rows],
        "must_have": [{"label": key, "count": count} for key, count in must_rows],
        "underwriting": [{"label": key, "count": count} for key, count in uw_rows],
        "budget": budgets,
        "notice": "Coverage tiers and must-haves are saved client requests, not proof of insurer coverage or a consumer purchase.",
    }


@router.get("/broker-productivity")
@cached
def productivity(ctx=Depends(context)):
    if not senior(ctx.user):
        raise DomainError("Senior broker or administrator access is required", 403)
    rows = (
        ctx.db.execute(
            select(
                CaseMetric.broker_id,
                func.count().label("cases"),
                func.avg(CaseMetric.close_days).label("average_days_to_close"),
            )
            .where(*ctx.filters())
            .group_by(CaseMetric.broker_id)
        )
        .mappings()
        .all()
    )
    data = [dict(r) for r in rows]
    med = (
        statistics.median(
            [r["average_days_to_close"] for r in data if r["average_days_to_close"] is not None]
        )
        if any(r["average_days_to_close"] is not None for r in data)
        else None
    )
    return {
        "rows": data,
        "anonymous_team_median_days": med,
        "rating_time_minutes": None,
        "notice": "Operational context only. Rating timestamps do not measure active work duration; no time estimate or punitive score is invented.",
    }


@router.get("/overview")
@cached
def overview(ctx=Depends(context)):
    row = (
        ctx.db.execute(
            select(
                func.count().label("cases"),
                func.sum(sql_case((CaseMetric.state.notin_(["PUBLISHED", "CLOSED"]), 1), else_=0)).label(
                    "open"
                ),
                func.avg(CaseMetric.close_days).label("average_days_to_close"),
                func.avg(CaseMetric.csat).label("csat"),
                func.count(CaseMetric.csat).label("csat_samples"),
                func.sum(
                    sql_case(
                        (
                            and_(
                                CaseMetric.state.notin_(["PUBLISHED", "CLOSED"]),
                                CaseMetric.last_action_at < (utcnow() - timedelta(days=5)).isoformat(),
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("past_action_sla"),
            ).where(*ctx.filters())
        )
        .mappings()
        .one()
    )
    response = {
        k: v or 0 if k in {"cases", "open", "csat_samples", "past_action_sla"} else v for k, v in row.items()
    }
    response["median_days_to_close"] = median_close(ctx)
    response["from"], response["to"] = ctx.start.isoformat(), ctx.end.isoformat()
    response["source"] = "Indexed case_metrics projections; no clinical fields"
    return response


@router.get("/cohorts")
@cached
def cohorts(ctx=Depends(context)):
    known = ctx.db.scalars(
        select(CaseMetric.body).where(
            *ctx.filters(),
            CaseMetric.closed_at.is_not(None),
            CaseMetric.body["consumer_key"].as_string().is_not(None),
        )
    ).all()
    identifiers = Counter(row.get("consumer_key") for row in known if row.get("consumer_key"))
    year_start = (ctx.start - timedelta(days=365)).isoformat()
    year_end = (ctx.end - timedelta(days=364)).isoformat()
    candidates = ctx.db.scalars(
        select(CaseMetric).where(
            metric_scope(ctx.user, ctx.broker),
            CaseMetric.closed_at >= year_start,
            CaseMetric.closed_at < year_end,
            CaseMetric.body["consumer_key"].as_string().is_not(None),
        )
    ).all()
    candidates = [
        row
        for row in candidates
        if row.body.get("consumer_key")
        and row.body.get("bound")
        and (not ctx.coverage or row.coverage_type == ctx.coverage)
        and (not ctx.insurer or row.insurer_id == ctx.insurer)
    ]
    source_ids = {row.case_id: row for row in candidates}
    renewed = set()
    if source_ids:
        for row in ctx.db.scalars(
            select(CaseMetric).where(
                metric_scope(ctx.user, ctx.broker),
                CaseMetric.created_at >= year_start,
                CaseMetric.body["renewal_of"].as_string().is_not(None),
            )
        ):
            source = source_ids.get(row.body.get("renewal_of"))
            if (
                source
                and row.body.get("bound")
                and row.body.get("consumer_key") == source.body.get("consumer_key")
            ):
                days = (
                    datetime.fromisoformat(row.created_at) - datetime.fromisoformat(source.closed_at)
                ).days
                if 0 < days <= 365:
                    renewed.add(source.case_id)
    return {
        "identified_consumers": len(identifiers),
        "repeat_intakes": sum(count > 1 for count in identifiers.values()),
        "eligible_renewal_cases": len(candidates),
        "confirmed_renewals": len(renewed),
        "renewal_rate": len(renewed) / len(candidates) if candidates else None,
        "notice": "Renewal cohorts use matching hashed consumer references, explicit source-case links and confirmed binding within 365 days. Missing identifiers/outcomes are not guessed; repeated intakes alone are not retention.",
    }


@router.get("/anomalies")
@cached
def anomalies(ctx=Depends(context)):
    return anomaly_report(ctx)


def anomaly_report(ctx, limit=50):
    if ctx.db.bind.dialect.name == "postgresql":
        return postgres_anomalies(ctx, limit)
    history = defaultdict(list)
    for body in ctx.db.scalars(
        select(CaseMetric.body).where(*ctx.filters(), CaseMetric.closed_at.is_not(None))
    ):
        for state, days in body.get("state_durations", {}).items():
            history[state].append(days)
    result = []
    benchmarks = {
        state: (statistics.median(values), statistics.pstdev(values), len(values))
        for state, values in history.items()
        if len(values) >= 5
    }
    for case_id, state, body in ctx.db.execute(
        select(CaseMetric.case_id, CaseMetric.state, CaseMetric.body).where(
            *ctx.filters(), CaseMetric.state.notin_(["PUBLISHED", "CLOSED"])
        )
    ):
        if state not in benchmarks or not body.get("state_entered_at"):
            continue
        age = max(0, (utcnow() - datetime.fromisoformat(body["state_entered_at"])).total_seconds()) / 86400
        median, spread, samples = benchmarks[state]
        if age > median + 2 * spread and age > 0:
            result.append(
                {
                    "case_id": case_id,
                    "state": state,
                    "days_in_state": age,
                    "median_days": median,
                    "samples": samples,
                    "state_entered_at": body["state_entered_at"],
                    "priority_boost": 25,
                    "href": f"/case/{case_id}?view=audit",
                }
            )
    return {
        "items": sorted(result, key=lambda row: -row["days_in_state"])[:limit] if limit else result,
        "total": len(result),
        "notice": "Aging signal from at least five completed saved state timings; not a causal or clinical finding.",
    }


def postgres_anomalies(ctx, limit):
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy import Float, DateTime

    entries = (
        func.jsonb_each_text(cast(CaseMetric.body["state_durations"], JSONB))
        .table_valued("key", "value")
        .lateral()
    )
    duration = cast(entries.c.value, Float)
    baseline = (
        select(
            entries.c.key.label("state"),
            func.percentile_cont(0.5).within_group(duration).label("median_days"),
            func.stddev_pop(duration).label("spread"),
            func.count().label("samples"),
        )
        .select_from(CaseMetric)
        .join(entries, true())
        .where(*ctx.filters(), CaseMetric.closed_at.is_not(None))
        .group_by(entries.c.key)
        .cte("state_baseline")
    )
    entered = CaseMetric.body["state_entered_at"].as_string()
    age = func.extract("epoch", utcnow() - cast(entered, DateTime(timezone=True))) / 86400.0
    query = (
        select(
            CaseMetric.case_id,
            CaseMetric.state,
            entered.label("state_entered_at"),
            age.label("days_in_state"),
            baseline.c.median_days,
            baseline.c.samples,
            func.count().over().label("total"),
        )
        .join(baseline, baseline.c.state == CaseMetric.state)
        .where(
            *ctx.filters(),
            CaseMetric.state.not_in(["PUBLISHED", "CLOSED"]),
            entered.is_not(None),
            baseline.c.samples >= 5,
            age > baseline.c.median_days + 2 * baseline.c.spread,
            age > 0,
        )
        .order_by(age.desc())
    )
    if limit:
        query = query.limit(limit)
    rows = ctx.db.execute(query).mappings().all()
    return {
        "items": [
            {
                **{
                    key: float(value) if key in {"days_in_state", "median_days"} else value
                    for key, value in row.items()
                    if key != "total"
                },
                "priority_boost": 25,
                "href": f"/case/{row['case_id']}?view=audit",
            }
            for row in rows
        ],
        "total": rows[0]["total"] if rows else 0,
        "notice": "Aging signal from at least five completed saved state timings; not a causal or clinical finding.",
    }


@router.get("/drivers")
@cached
def drivers(ctx=Depends(context)):
    broker = ctx.broker or ctx.user.id
    if broker == "all":
        raise DomainError("Choose a specific broker for the driver report", 422)
    rows = ctx.db.execute(driver_query().where(*ctx.filters())).all()
    report = fit_drivers(rows)
    nightly = ctx.db.get(SatisfactionDrivers, broker)
    return {
        **report,
        "computed_at": utcnow().isoformat(),
        "nightly_baseline_at": nightly.computed_at if nightly else None,
        "basis": "Current global filters; numeric operational fields only.",
    }


def driver_query():
    return select(
        CaseMetric.close_days,
        CaseMetric.csat,
        CaseMetric.body["plans"].as_integer().label("plans"),
        CaseMetric.body["selected_count"].as_integer().label("selected_count"),
    ).where(CaseMetric.csat.is_not(None), CaseMetric.close_days.is_not(None))


def fit_drivers(rows):
    base = {
        "samples": len(rows),
        "notice": "Descriptive association within this recorded sample; not a causal, predictive or punitive score.",
    }
    if len(rows) < 20:
        return {
            **base,
            "status": "not_enough_observations",
            "minimum": 20,
            "notice": "At least 20 verified scored cases with completion timings are required. Correlation does not establish causation.",
        }
    if len({row.csat for row in rows}) < 2:
        return {
            **base,
            "status": "not_enough_variation",
            "notice": "Recorded scores do not vary enough to estimate satisfaction associations.",
        }
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import StandardScaler

    x = [[row.close_days, row.plans or 0, row.selected_count or 0] for row in rows]
    coefficients = LinearRegression().fit(StandardScaler().fit_transform(x), [row.csat for row in rows]).coef_
    return {
        **base,
        "status": "descriptive_fit",
        "drivers": sorted(
            [
                {"feature": name, "standardised_coefficient": float(value)}
                for name, value in zip(
                    ["Time to delivery/closure", "Plans shown", "Number selected"], coefficients
                )
            ],
            key=lambda item: -abs(item["standardised_coefficient"]),
        ),
    }


@router.get("/scorecard")
def scorecard(format: Literal["csv", "pdf"] = "csv", ctx=Depends(context)):
    summary = overview(ctx)
    values = [(key, str(value) if value is not None else "Not recorded") for key, value in summary.items()]
    if format == "pdf":
        from app.documents import record_pdf

        raw = record_pdf(
            "Helm broker period scorecard",
            [f"{key}: {value}" for key, value in values]
            + ["Saved prototype observations. Operational context only; not a compliance certification."],
        )
        mime = "application/pdf"
    else:
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["Metric", "Value"])
        writer.writerows(values)
        raw = out.getvalue().encode()
        mime = "text/csv"
    return Response(
        raw,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="helm-scorecard.{format}"'},
    )


class SummaryInput(Model):
    from_date: date | None = None
    to_date: date | None = None
    coverage_type: Literal["individual", "couple", "family"] | None = None
    broker_id: str | None = None
    insurer_id: str | None = None


def assistant_answer(ctx, query=""):
    stats = overview(ctx=ctx)
    if "provider" in query or "insurer" in query:
        rows = sorted(insurer_performance(ctx=ctx)["rows"], key=lambda row: -row["selected"])[:3]
        answer = (
            "Recorded provider selections in this period: "
            + (
                "; ".join(
                    f"{row['insurer_id']}: {row['selected']} selections from {row['shown']} plans shown"
                    for row in rows
                )
                or "none recorded"
            )
            + ". [1] These counts describe saved broker choices; they do not establish a provider's quality or suitability."
        )
    elif "longer" in query or "time" in query:
        timings = time_to_close(ctx=ctx)["state_durations"]
        longest = max(timings, key=lambda row: row["median_days"]) if timings else None
        answer = (
            f"The longest recorded median state duration is {longest['state'].replace('_', ' ').lower()}: {longest['median_days']:.2f} days from {longest['samples']} observations. [1] This describes elapsed saved timings, including waiting; it does not establish the cause of a delay."
            if longest
            else "No completed state timings are recorded for this filtered cohort. [1] I cannot identify a bottleneck without saved timing evidence."
        )
    else:
        answer = f"From {ctx.start} to {ctx.end}, the filtered intake cohort contains {stats['cases']} cases, with {stats['open']} still open. [1] "
        answer += (
            f"Average time to recorded delivery or closure is {stats['average_days_to_close']:.2f} days. [1] "
            if stats["average_days_to_close"] is not None
            else "No delivery or closure duration is recorded for this cohort. [1] "
        )
        answer += (
            f"Verified consumer satisfaction averages {stats['csat']:.2f}/5 from {stats['csat_samples']} scored cases. [1]"
            if stats["csat_samples"]
            else "No verified consumer satisfaction scores are recorded for this cohort. [1]"
        )
    return {
        "answer": answer,
        "sources": [
            {
                "label": "Filtered operational projection snapshot",
                "record": "case_metrics",
                "snapshot": stats,
                "filters": {
                    "from": ctx.start.isoformat(),
                    "to": ctx.end.isoformat(),
                    "coverage_type": ctx.coverage,
                    "broker_id": ctx.broker or ctx.user.id,
                    "insurer_id": ctx.insurer,
                },
                "case_count": stats["cases"],
            }
        ],
        "confidence": "HIGH",
        "protected": False,
        "mode": "local_saved_evidence",
        "actions_performed": [],
        "compliance_context": [],
        "suggestions": [
            "Summarise this period",
            "Why are cases taking longer?",
            "Which providers are selected most?",
        ],
    }


@router.post("/summary")
def summary(body: SummaryInput, request: Request, db=Depends(database, scope="function")):
    from app.assistant import record_answer
    from app.case_workspace import Question

    user, session = identity(db, request)
    ctx = build_context(
        db, user, body.from_date, body.to_date, body.coverage_type, body.broker_id, body.insurer_id
    )
    stats = overview(ctx)
    answer = f"From {ctx.start} to {ctx.end}, this filtered intake cohort contains {stats['cases']} cases, of which {stats['open']} remain open. [1] "
    answer += (
        f"Average time to recorded delivery/closure is {stats['average_days_to_close']:.2f} days. [1] "
        if stats["average_days_to_close"] is not None
        else "No delivery/closure duration is recorded for this cohort. [1] "
    )
    answer += (
        f"Consumer satisfaction averages {stats['csat']:.2f}/5 from {stats['csat_samples']} scored cases. [1]"
        if stats["csat_samples"]
        else "No verified consumer satisfaction scores are recorded for this cohort. [1]"
    )
    result = {
        "answer": answer,
        "sources": [
            {
                "label": "Filtered operational projection snapshot",
                "record": "case_metrics",
                "snapshot": stats,
                "filters": {
                    "from": ctx.start.isoformat(),
                    "to": ctx.end.isoformat(),
                    "coverage_type": ctx.coverage,
                    "broker_id": ctx.broker or user.id,
                    "insurer_id": ctx.insurer,
                },
                "case_count": stats["cases"],
            }
        ],
        "confidence": "HIGH",
        "suggestions": ["What needs attention today?", "Pipeline overview", "Summarise my workspace"],
        "protected": False,
        "mode": "local_saved_evidence",
        "actions_performed": [],
        "compliance_context": [],
    }
    return record_answer(
        db,
        user,
        session,
        Question(question="Summarise my period: " + ctx.start.isoformat() + " to " + ctx.end.isoformat()),
        result,
    )


def compute_drivers(db):
    for user in db.scalars(select(User).where(User.is_active.is_(True))):
        rows = db.execute(driver_query().where(CaseMetric.broker_id == user.id)).all()
        row = db.get(SatisfactionDrivers, user.id)
        if not row:
            row = SatisfactionDrivers(broker_id=user.id)
            db.add(row)
        row.body = fit_drivers(rows)
        row.computed_at = utcnow().isoformat()
    db.info["metrics_cache_invalidate"] = True


@router.get("/brokers")
def brokers(ctx=Depends(context)):
    if not senior(ctx.user):
        raise DomainError("Senior broker or administrator access is required", 403)
    return [
        {"id": u.id, "name": u.name}
        for u in ctx.db.scalars(
            select(User).where(
                User.is_active.is_(True), User.role.in_(["authorised_broker", "senior_broker", "admin"])
            )
        )
    ]


@router.get("/dashboard")
@cached
def dashboard(granularity: Literal["day", "week", "month", "year"] = "day", ctx=Depends(context)):
    previous_end = ctx.start - timedelta(days=1)
    previous = build_context(
        ctx.db,
        ctx.user,
        previous_end - (ctx.end - ctx.start),
        previous_end,
        ctx.coverage,
        ctx.broker,
        ctx.insurer,
    )
    day = func.substr(CaseMetric.created_at, 1, 10)
    trend = (
        ctx.db.execute(
            select(
                day.label("day"),
                func.sum(sql_case((CaseMetric.state.notin_(["PUBLISHED", "CLOSED"]), 1), else_=0)).label(
                    "open"
                ),
                func.avg(CaseMetric.close_days).label("average_days"),
                func.avg(CaseMetric.csat).label("csat"),
                func.sum(
                    sql_case(
                        (
                            and_(
                                CaseMetric.state.notin_(["PUBLISHED", "CLOSED"]),
                                CaseMetric.last_action_at < (utcnow() - timedelta(days=5)).isoformat(),
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("overdue"),
            )
            .where(*ctx.filters())
            .group_by(day)
            .order_by(day)
        )
        .mappings()
        .all()
    )
    return {
        "overview": overview(ctx=ctx),
        "previous": overview(ctx=previous),
        "trend": [dict(row) for row in trend],
        "volume": volume(granularity=granularity, ctx=ctx),
        "aging": aging(ctx=ctx),
        "timing": time_to_close(ctx=ctx),
        "satisfaction": satisfaction(ctx=ctx),
        "insurers": insurer_performance(ctx=ctx),
        "patterns": plan_patterns(ctx=ctx),
        "cohorts": cohorts(ctx=ctx),
        "anomalies": anomalies(ctx=ctx),
        "drivers": drivers(ctx=ctx)
        if ctx.broker != "all"
        else {"status": "Choose a specific broker for driver analysis"},
        "productivity": productivity(ctx=ctx) if senior(ctx.user) else None,
        "generated_at": utcnow().isoformat(),
    }
