"""Signal engine: run detectors over features, persist with supersede/dedup.

For each configured detector and active market, load the market's features, run
the (pure) detector, attach confidence, and persist:

* no live signal yet → insert one;
* candidate differs from the live signal → insert the new one and point the old
  row's ``superseded_by`` at it (both rows persist — append-only);
* candidate identical to the live signal → no-op.

That last rule makes the engine idempotent (re-running over identical features
changes nothing) while still superseding when evidence actually moves — the
"re-fire supersedes" behavior (E4.1 AC). Exactly one live signal per
(detector, geography, metric) is maintained here and verified by the integrity
check.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..models import Geography, MetricSeries, Signal
from .confidence import confidence
from .config import DETECTOR_CONFIGS
from .detectors import DETECTORS, FeatureValue, SignalCandidate

log = logging.getLogger(__name__)

FEATURE_TRANSFORM_VERSION = "features_v1"
_MAG_PRECISION = 9


@dataclass
class SignalRunResult:
    inserted: int
    superseded: int
    unchanged: int


def _load_features(session: Session, geo_id: int, metric_id: int) -> list[FeatureValue]:
    rows = session.execute(
        text(
            "SELECT id, feature_type, period, value, insufficient_data "
            "FROM feature WHERE geography_id = :g AND metric_id = :m "
            "AND transform_version = :v"
        ),
        {"g": geo_id, "m": metric_id, "v": FEATURE_TRANSFORM_VERSION},
    ).all()
    return [
        FeatureValue(
            feature_id=r.id,
            feature_type=r.feature_type,
            period=r.period,
            value=float(r.value) if r.value is not None else 0.0,
            insufficient_data=r.insufficient_data,
        )
        for r in rows
    ]


def _live_signal(session: Session, detector: str, geo_id: int, metric_ref: int) -> Signal | None:
    return session.scalars(
        select(Signal).where(
            Signal.detector == detector,
            Signal.geography_id == geo_id,
            Signal.metric_ref == metric_ref,
            Signal.superseded_by.is_(None),
        )
    ).one_or_none()


def _same(live: Signal, cand: SignalCandidate, conf: str) -> bool:
    return (
        live.direction == cand.direction
        and live.confidence == conf
        and live.as_of == cand.as_of
        and list(live.feature_refs) == list(cand.feature_refs)
        and round(float(live.magnitude), _MAG_PRECISION)
        == round(cand.magnitude, _MAG_PRECISION)
    )


def run(session: Session, *, as_of: date | None = None) -> SignalRunResult:
    """Run all configured detectors over the active markets. Idempotent."""
    ref_date = as_of or date.today()
    geo_ids = session.execute(
        select(Geography.id).where(
            Geography.is_active.is_(True), Geography.geo_type == "metro"
        )
    ).scalars().all()

    inserted = superseded = unchanged = 0
    for cfg in DETECTOR_CONFIGS:
        detector_fn = DETECTORS[cfg["detector"]]
        metric = session.execute(
            select(MetricSeries).where(MetricSeries.code == cfg["metric_code"])
        ).scalar_one()
        params = {**cfg["params"], "metric_ref": metric.id}

        for geo_id in geo_ids:
            features = _load_features(session, geo_id, metric.id)
            cand = detector_fn(features, params)
            if cand is None:
                continue
            conf = confidence(
                cand.detector,
                as_of=cand.as_of,
                ref_date=ref_date,
                cadence=metric.frequency,
                depth=len(cand.feature_refs),
            )
            live = _live_signal(session, cand.detector, geo_id, metric.id)
            if live is not None and _same(live, cand, conf):
                unchanged += 1
                continue
            new = Signal(
                geography_id=geo_id,
                domain=cand.domain,
                detector=cand.detector,
                detector_version=cand.detector_version,
                metric_ref=cand.metric_ref,
                direction=cand.direction,
                magnitude=cand.magnitude,
                confidence=conf,
                as_of=cand.as_of,
                feature_refs=cand.feature_refs,
            )
            session.add(new)
            session.flush()  # assign new.id
            if live is not None:
                live.superseded_by = new.id  # supersede, never delete
                superseded += 1
            inserted += 1

    session.commit()
    log.info(
        "signal run as_of=%s inserted=%d superseded=%d unchanged=%d",
        ref_date,
        inserted,
        superseded,
        unchanged,
    )
    return SignalRunResult(inserted=inserted, superseded=superseded, unchanged=unchanged)
