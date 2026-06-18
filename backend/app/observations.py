"""Point-in-time (vintage-correct) reads of the observation store.

The append-only store keeps every vintage of every period. A point-in-time read
answers *"what did we know as of date X"* by selecting, per period, the row with
the greatest ``vintage`` ≤ the as-of date (TDS §5.1). This is the mechanism
behind backtesting and "what did we know when" analysis.

The authoritative implementation is the SQL function ``observation_as_of``,
created in the initial migration, so the same logic is available to raw SQL,
the ORM, and any future reporting tool. The Python helpers here are thin
wrappers over it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection


@dataclass(frozen=True)
class ObservationRow:
    id: int
    geography_id: int
    metric_id: int
    period: date
    value: Decimal
    vintage: date
    release_date: date
    source_id: int
    ingest_run_id: int


_AS_OF_SQL = text(
    """
    SELECT id, geography_id, metric_id, period, value,
           vintage, release_date, source_id, ingest_run_id
    FROM observation_as_of(:geography_id, :metric_id, :as_of)
    ORDER BY period
    """
).bindparams(
    bindparam("geography_id"),
    bindparam("metric_id"),
    bindparam("as_of"),
)


def read_as_of(
    conn: Connection,
    geography_id: int,
    metric_id: int,
    as_of: date,
) -> list[ObservationRow]:
    """Return the vintage-correct series for one (geography, metric) as known on
    ``as_of``: for each period, the value from the latest vintage published on or
    before ``as_of``. Periods first known after ``as_of`` are excluded — exactly
    what the system would have shown that day."""
    rows = conn.execute(
        _AS_OF_SQL,
        {"geography_id": geography_id, "metric_id": metric_id, "as_of": as_of},
    ).all()
    return [ObservationRow(*row) for row in rows]


def value_as_of(
    conn: Connection,
    geography_id: int,
    metric_id: int,
    period: date,
    as_of: date,
) -> Decimal | None:
    """Single point-in-time value for one period: the greatest-vintage value
    ≤ ``as_of``, or ``None`` if nothing was known by then."""
    for r in read_as_of(conn, geography_id, metric_id, as_of):
        if r.period == period:
            return r.value
    return None
