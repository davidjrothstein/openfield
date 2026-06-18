"""Per-assumption invalidation state machine (TDS §12.3, E6.3).

Invalidation is per-assumption, never wholesale. The decision core
(``decide_state``) is pure and unit-testable; ``evaluate_thesis`` does the DB
work (resolve the binding, gather live matching signals, compute the contradiction
run length along the supersede chain) and applies transitions, emitting events.

State semantics:
* intact     — a supporting signal is holding (or no contradicting evidence yet).
* watch      — a supporting signal has gone stale (freshness alone), or a weak
               contradiction appeared.
* challenged — a contradicting signal appeared at sufficient confidence; the
               owner is alerted and must respond.
* broken     — the contradiction has persisted for the pre-set number of
               consecutive periods; the thesis enters under_review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Assumption, MetricSeries, Signal, Thesis, ThesisEvent

_CONF_RANK = {"low": 0, "moderate": 1, "high": 2}


@dataclass(frozen=True)
class SignalView:
    """The facts the decision core needs about one live matching signal."""

    signal_id: int
    direction: str
    confidence: str
    as_of: date
    contradiction_run: int  # trailing consecutive periods in the contradiction dir


@dataclass(frozen=True)
class Decision:
    state: str
    reason: str
    supporting_ids: list[int] = field(default_factory=list)
    contradicting_ids: list[int] = field(default_factory=list)


def _conf_ge(conf: str, minimum: str) -> bool:
    return _CONF_RANK.get(conf, 0) >= _CONF_RANK.get(minimum, 0)


def decide_state(
    binding: dict,
    threshold: dict,
    signals: list[SignalView],
    *,
    ref_date: date,
) -> Decision:
    """Pure state decision for one assumption given its live matching signals."""
    supporting_dir = binding["supporting_direction"]
    contra_dir = threshold.get("contradiction_direction") or _opposite(supporting_dir)
    broken_consecutive = int(threshold.get("broken_consecutive", 2))
    challenged_conf_min = threshold.get("challenged_confidence_min", "low")
    watch_stale_days = int(threshold.get("watch_stale_days", 120))

    supporting = [s for s in signals if s.direction == supporting_dir]
    contradicting = [s for s in signals if s.direction == contra_dir]
    sup_ids = [s.signal_id for s in supporting]
    con_ids = [s.signal_id for s in contradicting]

    if contradicting:
        worst_run = max(s.contradiction_run for s in contradicting)
        strong = [s for s in contradicting if _conf_ge(s.confidence, challenged_conf_min)]
        if worst_run >= broken_consecutive:
            return Decision(
                "broken",
                f"contradicting signal persisted {worst_run} consecutive periods "
                f"(>= {broken_consecutive})",
                sup_ids,
                con_ids,
            )
        if strong:
            return Decision(
                "challenged",
                f"contradicting {contra_dir} signal at >= {challenged_conf_min} confidence",
                sup_ids,
                con_ids,
            )
        return Decision(
            "watch", f"weak contradicting {contra_dir} signal below confidence floor", sup_ids, con_ids
        )

    if supporting:
        freshest_age = min((ref_date - s.as_of).days for s in supporting)
        if freshest_age > watch_stale_days:
            return Decision(
                "watch",
                f"supporting signal stale ({freshest_age}d > {watch_stale_days}d)",
                sup_ids,
                con_ids,
            )
        return Decision("intact", "supporting signal holding", sup_ids, con_ids)

    return Decision("intact", "no contradicting evidence", sup_ids, con_ids)


def _opposite(direction: str) -> str:
    return {"improving": "deteriorating", "deteriorating": "improving"}.get(direction, "neutral")


# --------------------------------------------------------------------------- #
# DB-backed evaluation
# --------------------------------------------------------------------------- #
def _contradiction_run(session: Session, live_id: int, contra_dir: str) -> int:
    """Trailing consecutive periods in the contradiction direction, walking the
    supersede chain backward from the live signal."""
    run = 0
    cur: int | None = live_id
    while cur is not None:
        sig = session.get(Signal, cur)
        if sig is None or sig.direction != contra_dir:
            break
        run += 1
        cur = session.scalars(select(Signal.id).where(Signal.superseded_by == cur)).first()
    return run


def _matching_live_signals(
    session: Session, thesis: Thesis, binding: dict, contra_dir: str
) -> list[SignalView]:
    metric_id = session.execute(
        select(MetricSeries.id).where(MetricSeries.code == binding["metric_code"])
    ).scalar_one()
    sigs = session.scalars(
        select(Signal).where(
            Signal.geography_id == thesis.geography_id,
            Signal.domain == binding["domain"],
            Signal.metric_ref == metric_id,
            Signal.superseded_by.is_(None),
        )
    ).all()
    views = []
    for s in sigs:
        run = _contradiction_run(session, s.id, contra_dir) if s.direction == contra_dir else 0
        views.append(SignalView(s.id, s.direction, s.confidence, s.as_of, run))
    return views


def evaluate_thesis(session: Session, thesis_id: int, *, ref_date: date | None = None) -> list[ThesisEvent]:
    """Re-evaluate every assumption of a thesis, applying transitions and
    emitting events. Returns the events created this run."""
    ref = ref_date or date.today()
    thesis = session.get(Thesis, thesis_id)
    if thesis is None:
        raise ValueError(f"no thesis {thesis_id}")
    assumptions = session.scalars(
        select(Assumption).where(Assumption.thesis_id == thesis_id)
    ).all()

    events: list[ThesisEvent] = []
    for a in assumptions:
        binding = a.supporting_signal_query
        threshold = a.invalidation_threshold
        contra_dir = threshold.get("contradiction_direction") or _opposite(
            binding["supporting_direction"]
        )
        views = _matching_live_signals(session, thesis, binding, contra_dir)
        decision = decide_state(binding, threshold, views, ref_date=ref)

        if decision.state == a.state:
            continue

        prior = a.state
        a.state = decision.state
        a.state_changed_at = _now_ts(session)
        if decision.state in ("challenged", "broken"):
            a.needs_response = True

        ev = ThesisEvent(
            thesis_id=thesis_id,
            assumption_id=a.id,
            event_type="state_change",
            from_state=prior,
            to_state=decision.state,
            detail=decision.reason,
            signal_refs=(decision.supporting_ids + decision.contradicting_ids) or None,
        )
        session.add(ev)
        events.append(ev)

        # Owner alert + thesis-level escalation for challenged/broken.
        if decision.state in ("challenged", "broken"):
            session.add(
                ThesisEvent(
                    thesis_id=thesis_id,
                    assumption_id=a.id,
                    event_type="alert",
                    to_state=decision.state,
                    detail=f"owner {thesis.owner}: assumption {decision.state} — {decision.reason}",
                    signal_refs=decision.contradicting_ids or None,
                )
            )
        if decision.state == "broken" and thesis.status == "active":
            thesis.status = "under_review"

    session.commit()
    return events


def evaluate_all(session: Session, *, ref_date: date | None = None) -> int:
    """Evaluate every non-closed thesis (the nightly/on-new-signal pass, TDS §16).
    Wired into the recompute DAG in E10; callable directly meanwhile."""
    ids = session.scalars(select(Thesis.id).where(Thesis.status != "closed")).all()
    n = 0
    for tid in ids:
        n += len(evaluate_thesis(session, tid, ref_date=ref_date))
    return n


def _now_ts(session: Session):
    from sqlalchemy import func

    return session.scalar(select(func.now()))
