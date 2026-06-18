"""Signal engine (TDS §9, E4): deterministic threshold + trend-break detectors
over features, emitting append-only, superseding signals with lineage.

Importing this package registers the signal lineage resolver and integrity check
with ``app.lineage``.
"""

from . import lineage as _lineage  # noqa: F401  (registers resolver + integrity check)
