"""Feature computation engine (TDS §8, E3).

Turns vintage-correct observations into detector-ready features — deltas and
z-scores in V1 — recomputable, versioned, and honest about insufficient data.
Seasonal adjustment (STL) is deferred to 90-day (E3.3); 60-day uses simple YoY
deltas, which are naturally robust to seasonality.

Importing this package registers the feature lineage resolver and integrity
check with ``app.lineage``.
"""

from . import lineage as _lineage  # noqa: F401  (registers resolver + integrity check)
