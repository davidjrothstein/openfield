"""Idempotent feature recompute orchestrator (E3.1, TDS §8.1, §8.4).

An in-code DAG (no Airflow): for each metric, load each active market's
vintage-correct series via ``observation_as_of`` and compute longitudinal
features, then assemble the cross-section per period. Features are upserted on
their unique key, so:

* running recompute twice over identical observations yields identical features
  (idempotent — E3.1 AC), and
* feature ids stay stable across runs, so downstream signal ``feature_refs`` are
  not invalidated by a nightly recompute.

Because reads go through ``observation_as_of(as_of)``, passing a past ``as_of``
replays history using only then-known vintages — the backtest mechanism (E3.4)
falls out for free.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..models import Feature, Geography, MetricSeries
from .transforms import (
    FeatureRow,
    Point,
    XsObs,
    compute_delta,
    compute_zscore_long,
    compute_zscore_xs,
)

log = logging.getLogger(__name__)

TRANSFORM_VERSION = "features_v1"
DELTA_YOY_LAG = 12
DELTA_QOQ_LAG = 3


@dataclass
class RecomputeResult:
    features: int
    transform_version: str
    as_of: date


def _load_series(session: Session, geo_id: int, metric_id: int, as_of: date) -> list[Point]:
    rows = session.execute(
        text(
            "SELECT id, period, value, vintage "
            "FROM observation_as_of(:g, :m, :a) ORDER BY period"
        ),
        {"g": geo_id, "m": metric_id, "a": as_of},
    ).all()
    return [
        Point(period=r.period, value=float(r.value), obs_id=r.id, vintage=r.vintage)
        for r in rows
    ]


def recompute(session: Session, *, as_of: date | None = None) -> RecomputeResult:
    """Recompute all features for the active markets as of ``as_of`` (default
    today). Idempotent and replayable."""
    as_of = as_of or date.today()
    geo_ids = session.execute(
        select(Geography.id).where(
            Geography.is_active.is_(True), Geography.geo_type == "metro"
        )
    ).scalars().all()
    metric_ids = session.execute(select(MetricSeries.id)).scalars().all()

    rows: list[FeatureRow] = []
    for metric_id in metric_ids:
        series_by_geo: dict[int, list[Point]] = {}
        for geo_id in geo_ids:
            series = _load_series(session, geo_id, metric_id, as_of)
            series_by_geo[geo_id] = series
            rows += compute_delta(
                geo_id, metric_id, series, lag_months=DELTA_YOY_LAG, feature_type="delta_yoy"
            )
            rows += compute_delta(
                geo_id, metric_id, series, lag_months=DELTA_QOQ_LAG, feature_type="delta_qoq"
            )
            rows += compute_zscore_long(geo_id, metric_id, series)

        # Cross-section: per period, standardize across the active markets.
        peers_by_period: dict[date, list[XsObs]] = defaultdict(list)
        for geo_id, series in series_by_geo.items():
            for p in series:
                peers_by_period[p.period].append(
                    XsObs(geography_id=geo_id, value=p.value, obs_id=p.obs_id, vintage=p.vintage)
                )
        for period, peers in peers_by_period.items():
            rows += compute_zscore_xs(metric_id, period, peers)

    written = _upsert(session, rows)
    session.commit()
    log.info(
        "feature recompute as_of=%s version=%s wrote=%d", as_of, TRANSFORM_VERSION, written
    )
    return RecomputeResult(features=written, transform_version=TRANSFORM_VERSION, as_of=as_of)


def _upsert(session: Session, rows: list[FeatureRow]) -> int:
    n = 0
    for r in rows:
        ins = pg_insert(Feature).values(
            geography_id=r.geography_id,
            metric_id=r.metric_id,
            feature_type=r.feature_type,
            period=r.period,
            value=r.value,
            insufficient_data=r.insufficient_data,
            transform_version=TRANSFORM_VERSION,
            input_vintage_hi=r.input_vintage_hi,
            input_observation_ids=r.input_observation_ids,
        )
        stmt = ins.on_conflict_do_update(
            constraint="uq_feature_key",
            set_={
                "value": ins.excluded.value,
                "insufficient_data": ins.excluded.insufficient_data,
                "input_vintage_hi": ins.excluded.input_vintage_hi,
                "input_observation_ids": ins.excluded.input_observation_ids,
                "computed_at": func.now(),
            },
        )
        session.execute(stmt)
        n += 1
    return n
