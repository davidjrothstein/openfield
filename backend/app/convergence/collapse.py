"""Within-domain redundancy collapse + cross-domain breadth/coherence (TDS §10).

Pure, unit-testable core of the convergence engine. The central discipline
(PRD §6.1): the signals in a domain do not each get a vote — they collapse to
ONE stance. Conflict yields ``mixed`` (surfaced, never averaged into a false
neutral). A domain with no fresh signals yields ``no_read`` — explicitly distinct
from ``neutral``; absence of data is never treated as evidence of stability.

There is no scalar anywhere: stances are categorical, breadth is a count, and
coherence is an enum.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import date

DOMAINS = ("economy", "supply", "operator", "capital")

# Stance vocabulary. 'no_read' (no fresh signals) is distinct from 'neutral'.
NO_READ = "no_read"

_CONF_WEIGHT = {"high": 1.0, "moderate": 0.6, "low": 0.3}
_SIGN = {"improving": 1, "deteriorating": -1, "neutral": 0}
_CONF_RANK = ["low", "moderate", "high"]

# Causal template (PRD §6.2): economy/supply lead → operator → capital.
_TEMPLATE_ORDER = {"economy": 0, "supply": 0, "operator": 1, "capital": 2}


@dataclass(frozen=True)
class DomainSignal:
    signal_id: int
    direction: str
    confidence: str
    salience: float
    as_of: date


@dataclass(frozen=True)
class DomainStance:
    stance: str
    confidence: str
    contributing_signal_ids: list[int] = field(default_factory=list)
    as_of: date | None = None  # max as_of among contributors (for coherence)


def _best_confidence(signals: list[DomainSignal]) -> str:
    best = max(_CONF_RANK.index(s.confidence) for s in signals)
    if max(s.salience for s in signals) < 0.5:  # stale → one notch down
        best = max(0, best - 1)
    return _CONF_RANK[best]


def collapse_domain(
    signals: list[DomainSignal],
    *,
    fresh_floor: float = 0.25,
    conflict_ratio: float = 0.5,
) -> DomainStance:
    """Collapse a domain's live signals into one stance. ``fresh_floor`` filters
    out decayed signals; if nothing fresh remains the domain is ``no_read``."""
    fresh = [s for s in signals if s.salience >= fresh_floor]
    if not fresh:
        return DomainStance(NO_READ, "none", [])

    pos = [s for s in fresh if _SIGN[s.direction] > 0]
    neg = [s for s in fresh if _SIGN[s.direction] < 0]
    pos_w = sum(s.salience * _CONF_WEIGHT[s.confidence] for s in pos)
    neg_w = sum(s.salience * _CONF_WEIGHT[s.confidence] for s in neg)

    if pos_w == 0 and neg_w == 0:
        return DomainStance("neutral", "low", [s.signal_id for s in fresh], _max_as_of(fresh))

    # Substantial two-sided weight → mixed, conflict surfaced (never averaged).
    if pos_w > 0 and neg_w > 0 and min(pos_w, neg_w) / max(pos_w, neg_w) >= conflict_ratio:
        return DomainStance("mixed", "low", [s.signal_id for s in fresh], _max_as_of(fresh))

    dominant, stance = (pos, "improving") if pos_w >= neg_w else (neg, "deteriorating")
    return DomainStance(
        stance,
        _best_confidence(dominant),
        [s.signal_id for s in dominant],
        _max_as_of(dominant),
    )


def breadth(per_domain: dict[str, DomainStance]) -> int:
    """Count of domains agreeing in the same direction (0–4). Directional only —
    'mixed', 'neutral', and 'no_read' do not count (TDS §10.2)."""
    improving = sum(1 for d in per_domain.values() if d.stance == "improving")
    deteriorating = sum(1 for d in per_domain.values() if d.stance == "deteriorating")
    return max(improving, deteriorating)


def coherence(per_domain: dict[str, DomainStance]) -> str:
    """Lead-lag check vs the causal template. With fewer than two directional
    domains there is no multi-domain transition to confirm → 'no'. Simultaneity
    across leaders/followers is treated as not-coherent (PRD §6.2)."""
    directional = {
        dom: st.as_of
        for dom, st in per_domain.items()
        if st.stance in ("improving", "deteriorating") and st.as_of is not None
    }
    if len(directional) < 2:
        return "no"
    ok = total = 0
    for (da, ta), (db, tb) in itertools.combinations(directional.items(), 2):
        if _TEMPLATE_ORDER[da] == _TEMPLATE_ORDER[db]:
            continue
        total += 1
        (lt, ft) = (ta, tb) if _TEMPLATE_ORDER[da] < _TEMPLATE_ORDER[db] else (tb, ta)
        if lt <= ft:  # leader's evidence precedes (or matches) the follower's
            ok += 1
    if total == 0:
        return "no"
    if ok == total:
        return "yes"
    return "partial" if ok > 0 else "no"


def _max_as_of(signals: list[DomainSignal]) -> date | None:
    return max((s.as_of for s in signals), default=None)
