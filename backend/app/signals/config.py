"""Reviewed, versioned detector configuration (E4.2 AC).

Detector params live here as reviewed config, not scattered through the code. A
change to a threshold or window is a reviewed edit to this file with a bumped
``CONFIG_VERSION`` — the same discipline as a migration.

Direction semantics for the supply domain: more permitted supply is a
*deteriorating* fundamental (future oversupply), less is *improving*. That
mapping is made explicit per config rather than baked into the detectors, which
stay generic.
"""

from __future__ import annotations

CONFIG_VERSION = "supply_detectors_v1"

# Each entry binds a detector implementation to a metric with its params. The
# engine resolves ``metric_code`` → metric_ref and injects it before calling.
DETECTOR_CONFIGS: list[dict] = [
    {
        # Cross-sectional outlier: permits far above peers → future oversupply.
        "detector": "threshold",
        "metric_code": "permits_5plus_units",
        "params": {
            "feature_type": "zscore_xs",
            "high": 1.0,
            "low": -1.0,
            "high_direction": "deteriorating",
            "low_direction": "improving",
            "domain": "supply",
        },
    },
    {
        # Sustained YoY move in multifamily permits over N consecutive periods.
        "detector": "trend_break",
        "metric_code": "permits_5plus_units",
        "params": {
            "feature_type": "delta_yoy",
            "n": 3,
            "up_direction": "deteriorating",  # accelerating supply
            "down_direction": "improving",  # decelerating supply
            "domain": "supply",
        },
    },
]
