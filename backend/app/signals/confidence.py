"""Single-signal confidence and read-time salience decay (TDS §9.2, §9.3).

Confidence is categorical (high/moderate/low), derived from explicit inputs:
detector type (threshold > trend-break), data freshness (as_of age vs the
metric's cadence), and depth (how many features backed it). Corroboration is
deliberately *excluded* — that is a convergence-level concept, kept out so a
leading-domain signal is never down-weighted for lacking corroboration (TDS
§9.3, the "dangerous missed signal").

Salience decay is applied at *read time*, never stored: an old signal fades in
weight but its row is preserved and auditable.
"""

from __future__ import annotations

from datetime import date

_LEVELS = ["low", "moderate", "high"]
_BASE = {"threshold": "high", "trend_break": "moderate"}

# Cadence → expected days between releases (for the freshness judgement).
_CADENCE_DAYS = {"monthly": 31, "quarterly": 92, "annual": 366}


def _downgrade(level: str, steps: int = 1) -> str:
    return _LEVELS[max(0, _LEVELS.index(level) - steps)]


def confidence(
    detector: str,
    *,
    as_of: date,
    ref_date: date,
    cadence: str,
    depth: int,
    min_depth: int = 1,
) -> str:
    """Categorical confidence for one signal. Starts from the detector's base
    trust, then downgrades for staleness (older than ~2 cadence periods) and for
    thin support. Never folds in corroboration."""
    level = _BASE.get(detector, "moderate")
    age_days = (ref_date - as_of).days
    cadence_days = _CADENCE_DAYS.get(cadence, 31)
    if age_days > 2 * cadence_days:
        level = _downgrade(level)
    if depth < min_depth:
        level = _downgrade(level)
    return level


def salience(as_of: date, ref_date: date, *, half_life_days: int = 90) -> float:
    """Recency weight in (0, 1], halving every ``half_life_days``. Applied at
    read time by the convergence engine (E5) and read APIs — not persisted."""
    age_days = max(0, (ref_date - as_of).days)
    return 0.5 ** (age_days / half_life_days)
