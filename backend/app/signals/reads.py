"""Read-time access to live signals, with salience decay applied here — not
stored (TDS §9.2). The convergence engine (E5) and the change feed consume this.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .confidence import salience


@dataclass(frozen=True)
class LiveSignal:
    id: int
    geography_id: int
    domain: str
    detector: str
    direction: str
    magnitude: float | None
    confidence: str
    as_of: date
    feature_refs: list[int]
    salience: float  # recency weight, computed at read time


def live_signals(
    conn: Connection,
    geography_id: int,
    *,
    ref_date: date | None = None,
    half_life_days: int = 90,
) -> list[LiveSignal]:
    """Non-superseded signals for a market, each with a read-time salience weight
    (recency decay). Old signals are not deleted — they fade in weight."""
    ref = ref_date or date.today()
    rows = conn.execute(
        text(
            "SELECT id, geography_id, domain, detector, direction, magnitude, "
            "confidence, as_of, feature_refs "
            "FROM signal WHERE geography_id = :g AND superseded_by IS NULL "
            "ORDER BY as_of DESC"
        ),
        {"g": geography_id},
    ).mappings().all()
    return [
        LiveSignal(
            id=r["id"],
            geography_id=r["geography_id"],
            domain=r["domain"],
            detector=r["detector"],
            direction=r["direction"],
            magnitude=None if r["magnitude"] is None else float(r["magnitude"]),
            confidence=r["confidence"],
            as_of=r["as_of"],
            feature_refs=list(r["feature_refs"]),
            salience=salience(r["as_of"], ref, half_life_days=half_life_days),
        )
        for r in rows
    ]
