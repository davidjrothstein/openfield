"""Generic lineage walker (E1.2 / E8.1, TDS §5.5).

Lineage is a first-class, queryable chain. Given any ``(node_type, id)`` the
walker returns the node and its *inputs*, recursively, all the way to source —
satisfying the PRD's two-click traceability on the server side.

Design: a registry of per-node-type resolvers. Each resolver loads one node and
names the edges to its inputs. Derived layers added in E3–E5 (feature, signal,
convergence_assessment) register here as they are built — the walker itself
never changes, which is what "build lineage with the first layer, never
retrofit" means in practice.

Current registered chain (post-E2):

    observation → ingestion_run → source
                ↘ geography, metric_series (registry context)

The integrity check (also here) asserts that every row with non-FK-enforced
input references (the ``*_refs`` arrays arriving with E3+) points at existing
rows. For FK-enforced edges Postgres is the guarantee; the check still walks a
sample to prove the resolvers themselves are sound.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy import text
from sqlalchemy.engine import Connection


class UnknownNodeType(KeyError):
    pass


class NodeNotFound(LookupError):
    pass


@dataclass(frozen=True)
class LineageNode:
    """One node in a lineage chain, plus the typed edges to its inputs."""

    node_type: str
    node_id: int
    # Human-meaningful attributes for the UI panel (as-of dates, codes, names).
    attrs: dict
    # Edges to the rows this node was derived from / depends on.
    inputs: list["LineageNode"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "node_type": self.node_type,
            "node_id": self.node_id,
            "attrs": self.attrs,
            "inputs": [n.to_dict() for n in self.inputs],
        }


# A resolver returns (attrs, [(input_node_type, input_id), ...]) for one row,
# or None when the row does not exist.
Resolver = Callable[[Connection, int], "tuple[dict, list[tuple[str, int]]] | None"]

_RESOLVERS: dict[str, Resolver] = {}


def register_node_type(node_type: str, resolver: Resolver) -> None:
    """Derived layers (E3+: feature, signal, ...) call this to join the chain."""
    _RESOLVERS[node_type] = resolver


def registered_node_types() -> list[str]:
    return sorted(_RESOLVERS)


def walk(conn: Connection, node_type: str, node_id: int, *, max_depth: int = 12) -> LineageNode:
    """Resolve ``(node_type, id)`` and recursively expand its inputs to source.

    ``max_depth`` is a guard against future resolver cycles, not a expected
    limit — the real chain is depth ≤ 6 (assessment→signal→feature→observation→
    run→source)."""
    if node_type not in _RESOLVERS:
        raise UnknownNodeType(node_type)
    if max_depth <= 0:
        raise RecursionError(f"lineage walk exceeded max depth at {node_type}/{node_id}")
    resolved = _RESOLVERS[node_type](conn, node_id)
    if resolved is None:
        raise NodeNotFound(f"{node_type}/{node_id}")
    attrs, input_refs = resolved
    return LineageNode(
        node_type=node_type,
        node_id=node_id,
        attrs=attrs,
        inputs=[walk(conn, t, i, max_depth=max_depth - 1) for t, i in input_refs],
    )


# --------------------------------------------------------------------------- #
# Resolvers for the current layers (observation store + ingestion provenance)
# --------------------------------------------------------------------------- #
def _resolve_source(conn: Connection, node_id: int):
    row = conn.execute(
        text(
            "SELECT code, name, publisher, retrieval_method, license_terms, url "
            "FROM source WHERE id = :i"
        ),
        {"i": node_id},
    ).mappings().first()
    if row is None:
        return None
    return dict(row), []  # source is the chain terminus


def _resolve_ingestion_run(conn: Connection, node_id: int):
    row = conn.execute(
        text(
            "SELECT source_id, status, started_at, finished_at, raw_payload_key, error "
            "FROM ingestion_run WHERE id = :i"
        ),
        {"i": node_id},
    ).mappings().first()
    if row is None:
        return None
    attrs = {
        "status": row["status"],
        "started_at": _iso(row["started_at"]),
        "finished_at": _iso(row["finished_at"]),
        # The stored fetch/file record — the "who/when/whence" of provenance.
        "raw_payload_key": row["raw_payload_key"],
        "error": row["error"],
    }
    return attrs, [("source", row["source_id"])]


def _resolve_geography(conn: Connection, node_id: int):
    row = conn.execute(
        text("SELECT geo_type, cbsa_code, name, state FROM geography WHERE id = :i"),
        {"i": node_id},
    ).mappings().first()
    if row is None:
        return None
    return dict(row), []


def _resolve_metric_series(conn: Connection, node_id: int):
    row = conn.execute(
        text("SELECT code, name, domain, unit, frequency FROM metric_series WHERE id = :i"),
        {"i": node_id},
    ).mappings().first()
    if row is None:
        return None
    return dict(row), []


def _resolve_observation(conn: Connection, node_id: int):
    row = conn.execute(
        text(
            "SELECT geography_id, metric_id, period, value, vintage, release_date, "
            "source_id, ingest_run_id FROM observation WHERE id = :i"
        ),
        {"i": node_id},
    ).mappings().first()
    if row is None:
        return None
    attrs = {
        "period": _iso(row["period"]),
        "value": str(row["value"]),
        "vintage": _iso(row["vintage"]),  # the as-of date for vintage-correct reads
        "release_date": _iso(row["release_date"]),
    }
    inputs = [
        ("ingestion_run", row["ingest_run_id"]),
        ("source", row["source_id"]),
        ("geography", row["geography_id"]),
        ("metric_series", row["metric_id"]),
    ]
    return attrs, inputs


def _iso(v):
    return v.isoformat() if v is not None else None


register_node_type("source", _resolve_source)
register_node_type("ingestion_run", _resolve_ingestion_run)
register_node_type("geography", _resolve_geography)
register_node_type("metric_series", _resolve_metric_series)
register_node_type("observation", _resolve_observation)


# --------------------------------------------------------------------------- #
# Integrity check (E1.2: "assert every derived row references existing inputs")
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class IntegrityViolation:
    node_type: str
    node_id: int
    problem: str


# Derived layers with array-based (non-FK) input refs register a checker here
# as they land (E3+: feature.input refs, signal.feature_refs, ...). FK-enforced
# edges need no checker — Postgres guarantees them.
ArrayRefCheck = Callable[[Connection], list[IntegrityViolation]]
_ARRAY_REF_CHECKS: list[ArrayRefCheck] = []


def register_integrity_check(check: ArrayRefCheck) -> None:
    _ARRAY_REF_CHECKS.append(check)


def run_integrity_check(conn: Connection, *, sample_walk: int = 25) -> list[IntegrityViolation]:
    """Run all registered array-ref checks, then sanity-walk a sample of recent
    observations to prove the resolver chain itself resolves to source."""
    violations: list[IntegrityViolation] = []
    for check in _ARRAY_REF_CHECKS:
        violations.extend(check(conn))

    sample = conn.execute(
        text("SELECT id FROM observation ORDER BY id DESC LIMIT :n"),
        {"n": sample_walk},
    ).scalars().all()
    for obs_id in sample:
        try:
            node = walk(conn, "observation", obs_id)
        except (NodeNotFound, UnknownNodeType, RecursionError) as e:
            violations.append(IntegrityViolation("observation", obs_id, f"walk failed: {e}"))
            continue
        if not any(n.node_type == "source" for n in _flatten(node)):
            violations.append(
                IntegrityViolation("observation", obs_id, "chain does not reach a source")
            )
    return violations


def _flatten(node: LineageNode):
    yield node
    for child in node.inputs:
        yield from _flatten(child)
