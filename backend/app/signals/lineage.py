"""Register the signal layer with the lineage walker (E1.2 / E8.1).

A signal resolves to the features it consumed (``feature_refs``), which the
walker recurses on to observations and source. The integrity check validates the
non-FK array refs and asserts the "one live signal per (detector, geo, metric)"
invariant the engine maintains.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .. import lineage


def _resolve_signal(conn: Connection, node_id: int):
    row = conn.execute(
        text(
            "SELECT geography_id, domain, detector, detector_version, metric_ref, "
            "direction, magnitude, confidence, as_of, feature_refs, superseded_by "
            "FROM signal WHERE id = :i"
        ),
        {"i": node_id},
    ).mappings().first()
    if row is None:
        return None
    attrs = {
        "domain": row["domain"],
        "detector": row["detector"],
        "detector_version": row["detector_version"],
        "direction": row["direction"],
        "magnitude": None if row["magnitude"] is None else str(row["magnitude"]),
        "confidence": row["confidence"],
        "as_of": row["as_of"].isoformat(),
        "superseded_by": row["superseded_by"],
    }
    inputs = [("feature", fid) for fid in (row["feature_refs"] or [])]
    if row["metric_ref"] is not None:
        inputs.append(("metric_series", row["metric_ref"]))
    inputs.append(("geography", row["geography_id"]))
    return attrs, inputs


def _check_signal(conn: Connection) -> list[lineage.IntegrityViolation]:
    violations: list[lineage.IntegrityViolation] = []

    # Dangling feature_refs.
    dangling = conn.execute(
        text(
            """
            SELECT s.id FROM signal s
            WHERE EXISTS (
                SELECT 1 FROM unnest(s.feature_refs) AS u(fid)
                WHERE NOT EXISTS (SELECT 1 FROM feature f WHERE f.id = u.fid)
            )
            """
        )
    ).scalars().all()
    for sid in dangling:
        violations.append(
            lineage.IntegrityViolation("signal", sid, "feature_refs dangling")
        )

    # Empty refs on a live signal (a signal must name its evidence).
    no_refs = conn.execute(
        text(
            "SELECT id FROM signal "
            "WHERE coalesce(array_length(feature_refs, 1), 0) = 0"
        )
    ).scalars().all()
    for sid in no_refs:
        violations.append(lineage.IntegrityViolation("signal", sid, "signal has no feature_refs"))

    # One live signal per (detector, geography, metric_ref).
    dupes = conn.execute(
        text(
            "SELECT detector, geography_id, metric_ref, count(*) AS n "
            "FROM signal WHERE superseded_by IS NULL "
            "GROUP BY detector, geography_id, metric_ref HAVING count(*) > 1"
        )
    ).all()
    for d in dupes:
        violations.append(
            lineage.IntegrityViolation(
                "signal",
                -1,
                f"{d.n} live signals for ({d.detector}, geo {d.geography_id}, metric {d.metric_ref})",
            )
        )
    return violations


lineage.register_node_type("signal", _resolve_signal)
lineage.register_integrity_check(_check_signal)
