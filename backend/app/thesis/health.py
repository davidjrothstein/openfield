"""Thesis health view (TDS §12.3, E6.3).

Per assumption, shows supporting AND contradicting signals side by side —
including contradictions in domains the assumption did not model. The system
confronts; it does not adjudicate. Every signal id is lineage-walkable.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Assumption, MetricSeries, Signal, Thesis
from ..signals.confidence import salience
from .evaluate import _opposite


def _signal_summary(s: Signal, ref: date) -> dict:
    return {
        "id": s.id,
        "domain": s.domain,
        "detector": s.detector,
        "direction": s.direction,
        "magnitude": None if s.magnitude is None else float(s.magnitude),
        "confidence": s.confidence,
        "as_of": s.as_of.isoformat(),
        "salience": round(salience(s.as_of, ref), 4),
    }


def thesis_health(session: Session, thesis_id: int, *, ref_date: date | None = None) -> dict:
    """Assemble the health view: thesis head + per-assumption supporting and
    contradicting signals, plus contradictions in unmodeled domains."""
    ref = ref_date or date.today()
    thesis = session.get(Thesis, thesis_id)
    if thesis is None:
        raise ValueError(f"no thesis {thesis_id}")

    live = session.scalars(
        select(Signal).where(
            Signal.geography_id == thesis.geography_id, Signal.superseded_by.is_(None)
        )
    ).all()

    assumptions = session.scalars(
        select(Assumption).where(Assumption.thesis_id == thesis_id)
    ).all()

    modeled_domains = set()
    rows = []
    for a in assumptions:
        binding = a.supporting_signal_query
        modeled_domains.add(binding["domain"])
        metric_id = session.execute(
            select(MetricSeries.id).where(MetricSeries.code == binding["metric_code"])
        ).scalar_one()
        supporting_dir = binding["supporting_direction"]
        contra_dir = a.invalidation_threshold.get("contradiction_direction") or _opposite(
            supporting_dir
        )
        matching = [
            s for s in live if s.domain == binding["domain"] and s.metric_ref == metric_id
        ]
        rows.append(
            {
                "id": a.id,
                "statement": a.statement,
                "state": a.state,
                "needs_response": a.needs_response,
                "supporting": [
                    _signal_summary(s, ref) for s in matching if s.direction == supporting_dir
                ],
                "contradicting": [
                    _signal_summary(s, ref) for s in matching if s.direction == contra_dir
                ],
            }
        )

    # Contradictions the analyst did not model: live deteriorating signals in
    # domains no assumption bound to (TDS §12.3, "unmodeled domain surfaces too").
    unmodeled = [
        _signal_summary(s, ref)
        for s in live
        if s.domain not in modeled_domains and s.direction == "deteriorating"
    ]

    return {
        "thesis": {
            "id": thesis.id,
            "claim": thesis.claim,
            "owner": thesis.owner,
            "conviction": thesis.conviction,
            "horizon": thesis.horizon,
            "status": thesis.status,
        },
        "assumptions": rows,
        "unmodeled_domain_contradictions": unmodeled,
    }
