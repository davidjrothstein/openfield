"""Register the convergence layer with the lineage walker (E1.2 / E8.1).

An assessment decomposes to its contributing signals (across all domains), which
the walker recurses to features → observations → source. The explainability
requirement is enforced by storing the contributing ids at every level: an
assessment that cannot name its contributing signals is a bug (TDS §10.5).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .. import lineage


def _contributing_ids(per_domain: dict) -> list[int]:
    ids: list[int] = []
    for stance in per_domain.values():
        ids.extend(stance.get("contributing_signal_ids", []))
    return ids


def _resolve_convergence(conn: Connection, node_id: int):
    row = conn.execute(
        text(
            "SELECT geography_id, as_of, per_domain_stance, breadth, coherence, "
            "weakest_data_flag FROM convergence_assessment WHERE id = :i"
        ),
        {"i": node_id},
    ).mappings().first()
    if row is None:
        return None
    attrs = {
        "as_of": row["as_of"].isoformat(),
        "per_domain_stance": row["per_domain_stance"],
        "breadth": row["breadth"],
        "coherence": row["coherence"],
        "weakest_data_flag": row["weakest_data_flag"],
    }
    inputs = [("signal", sid) for sid in _contributing_ids(row["per_domain_stance"])]
    inputs.append(("geography", row["geography_id"]))
    return attrs, inputs


def _check_convergence(conn: Connection) -> list[lineage.IntegrityViolation]:
    violations: list[lineage.IntegrityViolation] = []
    rows = conn.execute(
        text("SELECT id, per_domain_stance FROM convergence_assessment")
    ).mappings().all()
    for r in rows:
        for sid in _contributing_ids(r["per_domain_stance"]):
            exists = conn.execute(
                text("SELECT 1 FROM signal WHERE id = :i"), {"i": sid}
            ).first()
            if exists is None:
                violations.append(
                    lineage.IntegrityViolation(
                        "convergence_assessment", r["id"], f"contributing signal {sid} missing"
                    )
                )
    return violations


lineage.register_node_type("convergence_assessment", _resolve_convergence)
lineage.register_integrity_check(_check_convergence)
