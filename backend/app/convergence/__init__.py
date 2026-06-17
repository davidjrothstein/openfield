"""Convergence engine (TDS §10, E5): per-domain stance + breadth + coherence,
honest 'no read' for empty domains, and NO scalar anywhere.

Importing this package registers the convergence lineage resolver and integrity
check with ``app.lineage``.
"""

from . import lineage as _lineage  # noqa: F401  (registers resolver + integrity check)
