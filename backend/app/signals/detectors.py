"""Deterministic detectors (TDS §9.1, §9.5).

A detector is a *pure* function of ``(features, params, version)`` — no DB, no
wall clock, no randomness — so the same inputs always emit the same candidate
(E4.2 AC). V1 ships two editorial detectors; statistical change-point detection
is deferred behind the backtest gate (E4.3) but plugs into this same shape.

Detectors emit a ``SignalCandidate`` with direction, magnitude, as_of, and the
feature ids it used (lineage). They do *not* set confidence: confidence depends
on freshness/depth relative to a reference date, which is the engine's concern
(``confidence.py``). Crucially, corroboration is never an input here (TDS §9.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class FeatureValue:
    """One feature row the detectors read (a non-insufficient point unless the
    detector explicitly inspects the flag)."""

    feature_id: int
    feature_type: str
    period: date
    value: float
    insufficient_data: bool


@dataclass(frozen=True)
class SignalCandidate:
    domain: str
    detector: str
    detector_version: str
    metric_ref: int
    direction: str  # improving | deteriorating | neutral
    magnitude: float
    as_of: date
    feature_refs: list[int]


def _usable(features: list[FeatureValue], feature_type: str) -> list[FeatureValue]:
    rows = [f for f in features if f.feature_type == feature_type and not f.insufficient_data]
    rows.sort(key=lambda f: f.period)
    return rows


# --------------------------------------------------------------------------- #
# Threshold-crossing (fully trusted, no statistics)
# --------------------------------------------------------------------------- #
THRESHOLD_VERSION = "threshold_v1"


def threshold(features: list[FeatureValue], params: dict) -> SignalCandidate | None:
    """Fire when the latest value of ``feature_type`` crosses a registered band.

    params: feature_type, high, low, high_direction, low_direction, domain,
    metric_ref. Above ``high`` → ``high_direction``; below ``low`` →
    ``low_direction``; within the band → no signal (a crossing is required)."""
    rows = _usable(features, params["feature_type"])
    if not rows:
        return None
    latest = rows[-1]
    if latest.value >= params["high"]:
        direction = params["high_direction"]
    elif latest.value <= params["low"]:
        direction = params["low_direction"]
    else:
        return None
    return SignalCandidate(
        domain=params["domain"],
        detector="threshold",
        detector_version=THRESHOLD_VERSION,
        metric_ref=params["metric_ref"],
        direction=direction,
        magnitude=latest.value,
        as_of=latest.period,
        feature_refs=[latest.feature_id],
    )


# --------------------------------------------------------------------------- #
# Trend-break (N consecutive same-sign periods)
# --------------------------------------------------------------------------- #
TREND_BREAK_VERSION = "trend_break_v1"


def trend_break(features: list[FeatureValue], params: dict) -> SignalCandidate | None:
    """Fire when the last ``n`` values of ``feature_type`` are all the same sign
    — a sustained directional move (TDS §9.1).

    params: feature_type, n, up_direction, down_direction, domain, metric_ref.
    Positive run → ``up_direction``; negative run → ``down_direction``."""
    rows = _usable(features, params["feature_type"])
    n = params["n"]
    if len(rows) < n:
        return None
    window = rows[-n:]
    if all(f.value > 0 for f in window):
        direction = params["up_direction"]
    elif all(f.value < 0 for f in window):
        direction = params["down_direction"]
    else:
        return None
    magnitude = sum(f.value for f in window) / n
    return SignalCandidate(
        domain=params["domain"],
        detector="trend_break",
        detector_version=TREND_BREAK_VERSION,
        metric_ref=params["metric_ref"],
        direction=direction,
        magnitude=magnitude,
        as_of=window[-1].period,
        feature_refs=[f.feature_id for f in window],
    )


# Registry of detector implementations by name.
DETECTORS = {"threshold": threshold, "trend_break": trend_break}
