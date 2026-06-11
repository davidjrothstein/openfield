"""Runnable lineage integrity check (E1.2).

Asserts every derived row references existing inputs and that the resolver
chain reaches a source. A violation is a P1 — it means the UI could show an
underivable number (TDS §19). Scheduled nightly alongside the recompute DAG
(E10); runnable any time as:

    python -m app.integrity_job
"""

from __future__ import annotations

import logging
import sys

from .db import engine
from .lineage import run_integrity_check

log = logging.getLogger(__name__)


def main() -> int:
    with engine.connect() as conn:
        violations = run_integrity_check(conn)
    if not violations:
        print("lineage integrity OK: no violations")
        return 0
    for v in violations:
        print(f"VIOLATION {v.node_type}/{v.node_id}: {v.problem}", file=sys.stderr)
    print(f"lineage integrity FAILED: {len(violations)} violation(s)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
