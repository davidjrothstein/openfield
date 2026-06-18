"""Centralized data-freshness scan (TDS §6.4, E10.1).

For each active market × metric, compare the latest observed period against the
metric's expected cadence and classify fresh / aging / stale. Computed centrally
so every aggregate can display the freshness of its weakest input. Idempotent:
upserts one row per (geography, metric).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..models import DataFreshness, Geography, MetricSeries

log = logging.getLogger(__name__)

_CADENCE_DAYS = {"monthly": 31, "quarterly": 92, "annual": 366}
# A series is fresh within ~2 cadence periods of its latest period (public data
# is released with a lag), aging within ~4, stale beyond.
_FRESH_MULT = 2
_AGING_MULT = 4

_RANK = {"fresh": 0, "aging": 1, "stale": 2, "no_data": 3}


@dataclass
class FreshnessResult:
    rows: int


def _classify(age_days: int | None, cadence: str) -> str:
    if age_days is None:
        return "no_data"
    cadence_days = _CADENCE_DAYS.get(cadence, 31)
    if age_days <= _FRESH_MULT * cadence_days:
        return "fresh"
    if age_days <= _AGING_MULT * cadence_days:
        return "aging"
    return "stale"


def scan(session: Session, *, as_of: date | None = None) -> FreshnessResult:
    ref = as_of or date.today()
    geo_ids = session.execute(
        select(Geography.id).where(
            Geography.is_active.is_(True), Geography.geo_type == "metro"
        )
    ).scalars().all()
    metrics = session.execute(select(MetricSeries.id, MetricSeries.frequency)).all()

    n = 0
    for geo_id in geo_ids:
        for metric_id, cadence in metrics:
            row = session.execute(
                text(
                    "SELECT max(period) AS latest_period FROM observation "
                    "WHERE geography_id = :g AND metric_id = :m"
                ),
                {"g": geo_id, "m": metric_id},
            ).first()
            latest_period = row.latest_period if row else None
            latest_vintage = None
            age_days = None
            if latest_period is not None:
                latest_vintage = session.execute(
                    text(
                        "SELECT max(vintage) FROM observation WHERE geography_id=:g "
                        "AND metric_id=:m AND period=:p"
                    ),
                    {"g": geo_id, "m": metric_id, "p": latest_period},
                ).scalar()
                age_days = (ref - latest_period).days
            state = _classify(age_days, cadence)

            ins = pg_insert(DataFreshness).values(
                geography_id=geo_id,
                metric_id=metric_id,
                latest_period=latest_period,
                latest_vintage=latest_vintage,
                state=state,
                age_days=age_days,
            )
            stmt = ins.on_conflict_do_update(
                constraint="uq_freshness_geo_metric",
                set_={
                    "latest_period": ins.excluded.latest_period,
                    "latest_vintage": ins.excluded.latest_vintage,
                    "state": ins.excluded.state,
                    "age_days": ins.excluded.age_days,
                    "computed_at": func.now(),
                },
            )
            session.execute(stmt)
            n += 1

    session.commit()
    log.info("freshness scan as_of=%s rows=%d", ref, n)
    return FreshnessResult(rows=n)


def weakest_freshness(session: Session, geography_id: int) -> str | None:
    """The worst freshness state among a market's metrics that have data — the
    'weakest input' freshness an aggregate should display."""
    states = session.execute(
        select(DataFreshness.state).where(
            DataFreshness.geography_id == geography_id,
            DataFreshness.state != "no_data",
        )
    ).scalars().all()
    if not states:
        return None
    return max(states, key=lambda s: _RANK[s])
