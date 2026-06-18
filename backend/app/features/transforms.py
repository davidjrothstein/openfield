"""Pure feature transforms (TDS §8.3).

Each function is a pure function of its input series — no DB, no wall clock — so
the engine's arithmetic is unit-testable in isolation and deterministic. Every
function returns ``FeatureRow``s carrying lineage (the observation ids used) and
the max input vintage. A window with too little history yields
``insufficient_data=True`` with a ``None`` value — never a fabricated number
(CLAUDE.md; E3.1 AC).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date

# Detector-tunable minimums (kept here as reviewed constants, not scattered).
MIN_HISTORY_LONG = 12  # min prior points for a longitudinal z-score
LONG_WINDOW = 36  # trailing window (months) for the longitudinal distribution
MIN_MARKETS_XS = 3  # min peers for a cross-sectional z-score


@dataclass(frozen=True)
class Point:
    """One vintage-correct observation in a (geo, metric) series."""

    period: date
    value: float
    obs_id: int
    vintage: date


@dataclass(frozen=True)
class XsObs:
    """One market's vintage-correct value for a metric in a single period."""

    geography_id: int
    value: float
    obs_id: int
    vintage: date


@dataclass(frozen=True)
class FeatureRow:
    geography_id: int
    metric_id: int
    feature_type: str
    period: date
    value: float | None
    insufficient_data: bool
    input_observation_ids: list[int]
    input_vintage_hi: date


def month_add(d: date, months: int) -> date:
    """Shift a first-of-month date by ``months`` (negative = back)."""
    m = d.month - 1 + months
    return date(d.year + m // 12, m % 12 + 1, 1)


def _insufficient(geo, metric, ftype, p: Point, extra_ids=(), extra_vintages=()):
    ids = [p.obs_id, *extra_ids]
    vintage_hi = max([p.vintage, *extra_vintages])
    return FeatureRow(geo, metric, ftype, p.period, None, True, ids, vintage_hi)


def compute_delta(
    geography_id: int,
    metric_id: int,
    series: list[Point],
    *,
    lag_months: int,
    feature_type: str,
) -> list[FeatureRow]:
    """A point delta: value(t) − value(t − lag). YoY (lag=12) is the 60-day
    default — robust to seasonality. QoQ (lag=3) is the 3-month change on a
    monthly series. Periods without the lagged observation are insufficient."""
    by_period = {p.period: p for p in series}
    out: list[FeatureRow] = []
    for p in series:
        prev = by_period.get(month_add(p.period, -lag_months))
        if prev is None:
            out.append(_insufficient(geography_id, metric_id, feature_type, p))
        else:
            out.append(
                FeatureRow(
                    geography_id,
                    metric_id,
                    feature_type,
                    p.period,
                    p.value - prev.value,
                    False,
                    [p.obs_id, prev.obs_id],
                    max(p.vintage, prev.vintage),
                )
            )
    return out


def compute_zscore_long(
    geography_id: int,
    metric_id: int,
    series: list[Point],
    *,
    min_history: int = MIN_HISTORY_LONG,
    window: int = LONG_WINDOW,
    feature_type: str = "zscore_long",
) -> list[FeatureRow]:
    """Standardize each point against its own trailing distribution — "this
    market vs its own history" (TDS §8.3). Needs ``min_history`` prior points and
    non-zero spread, else insufficient."""
    series = sorted(series, key=lambda p: p.period)
    out: list[FeatureRow] = []
    for i, p in enumerate(series):
        history = series[max(0, i - window) : i]  # strictly prior, bounded window
        if len(history) < min_history:
            out.append(_insufficient(geography_id, metric_id, feature_type, p))
            continue
        vals = [h.value for h in history]
        hist_ids = [h.obs_id for h in history]
        hist_vintages = [h.vintage for h in history]
        sd = statistics.stdev(vals)
        if sd == 0:
            out.append(
                _insufficient(
                    geography_id, metric_id, feature_type, p, hist_ids, hist_vintages
                )
            )
            continue
        z = (p.value - statistics.mean(vals)) / sd
        out.append(
            FeatureRow(
                geography_id,
                metric_id,
                feature_type,
                p.period,
                z,
                False,
                [p.obs_id, *hist_ids],
                max([p.vintage, *hist_vintages]),
            )
        )
    return out


def compute_zscore_xs(
    metric_id: int,
    period: date,
    peers: list[XsObs],
    *,
    min_markets: int = MIN_MARKETS_XS,
    feature_type: str = "zscore_xs",
) -> list[FeatureRow]:
    """Standardize each market against its peers for one period — "this market
    vs its peers right now" (TDS §8.3). The peer set is the lineage of every
    market's value, so each row references all peer observations. Too few
    markets, or zero spread, → insufficient for every market in the set."""
    if not peers:
        return []
    all_ids = [x.obs_id for x in peers]
    vintage_hi = max(x.vintage for x in peers)
    vals = [x.value for x in peers]

    def insufficient(x: XsObs) -> FeatureRow:
        return FeatureRow(
            x.geography_id, metric_id, feature_type, period, None, True, [x.obs_id], x.vintage
        )

    if len(peers) < min_markets:
        return [insufficient(x) for x in peers]
    sd = statistics.stdev(vals)
    if sd == 0:
        # Degenerate cross-section: reference the full peer set in the lineage.
        return [
            FeatureRow(
                x.geography_id, metric_id, feature_type, period, None, True, all_ids, vintage_hi
            )
            for x in peers
        ]
    mean = statistics.mean(vals)
    return [
        FeatureRow(
            x.geography_id,
            metric_id,
            feature_type,
            period,
            (x.value - mean) / sd,
            False,
            all_ids,
            vintage_hi,
        )
        for x in peers
    ]
