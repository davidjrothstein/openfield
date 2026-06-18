"""Register the feature layer with the lineage walker (E1.2 / E8.1).

This is the pattern every derived layer follows: a resolver that names a
feature's input observations, plus an integrity checker for the array-based refs
(which Postgres does not FK-enforce). Importing ``app.features`` wires these in;
the walker and integrity job never change.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .. import lineage


def _resolve_feature(conn: Connection, node_id: int):
    row = conn.execute(
        text(
            "SELECT geography_id, metric_id, feature_type, period, value, "
            "insufficient_data, transform_version, input_vintage_hi, "
            "input_observation_ids "
            "FROM feature WHERE id = :i"
        ),
        {"i": node_id},
    ).mappings().first()
    if row is None:
        return None
    attrs = {
        "feature_type": row["feature_type"],
        "period": row["period"].isoformat(),
        "value": None if row["value"] is None else str(row["value"]),
        "insufficient_data": row["insufficient_data"],
        "transform_version": row["transform_version"],
        "input_vintage_hi": row["input_vintage_hi"].isoformat(),
    }
    inputs = [("observation", oid) for oid in (row["input_observation_ids"] or [])]
    # Registry context (also reachable through the observations, but handy here).
    inputs.append(("geography", row["geography_id"]))
    inputs.append(("metric_series", row["metric_id"]))
    return attrs, inputs


def _check_feature_refs(conn: Connection) -> list[lineage.IntegrityViolation]:
    """Flag any feature whose input_observation_ids point at a missing
    observation, or any value-bearing feature with no inputs at all."""
    violations: list[lineage.IntegrityViolation] = []

    dangling = conn.execute(
        text(
            """
            SELECT f.id
            FROM feature f
            WHERE EXISTS (
                SELECT 1 FROM unnest(f.input_observation_ids) AS u(oid)
                WHERE NOT EXISTS (SELECT 1 FROM observation o WHERE o.id = u.oid)
            )
            """
        )
    ).scalars().all()
    for fid in dangling:
        violations.append(
            lineage.IntegrityViolation("feature", fid, "input_observation_ids dangling")
        )

    orphan = conn.execute(
        text(
            "SELECT id FROM feature "
            "WHERE insufficient_data = false "
            "AND coalesce(array_length(input_observation_ids, 1), 0) = 0"
        )
    ).scalars().all()
    for fid in orphan:
        violations.append(
            lineage.IntegrityViolation("feature", fid, "value-bearing feature has no inputs")
        )
    return violations


lineage.register_node_type("feature", _resolve_feature)
lineage.register_integrity_check(_check_feature_refs)
