"""Convergence recompute (TDS §10, E5.1).

For each active market, collapse live signals into a per-domain stance matrix,
then assess breadth and coherence. In V1 only the supply domain has real signals;
economy/operator/capital render explicit ``no_read``. The assessment is upserted
per (geography, as_of, transform_version) so re-running is idempotent, and prior
as_of assessments are retained.

No scalar is ever produced — the output is a categorical matrix plus a count and
an enum.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..models import ConvergenceAssessment, Geography
from ..signals.reads import live_signals
from .collapse import DOMAINS, NO_READ, DomainSignal, DomainStance, breadth, coherence, collapse_domain

log = logging.getLogger(__name__)

TRANSFORM_VERSION = "convergence_v1"


@dataclass
class ConvergenceResult:
    assessments: int
    transform_version: str
    as_of: date


def _assess_market(session: Session, geo_id: int, as_of: date) -> dict:
    conn = session.connection()
    live = live_signals(conn, geo_id, ref_date=as_of)
    by_domain: dict[str, list[DomainSignal]] = {d: [] for d in DOMAINS}
    for s in live:
        if s.domain in by_domain:
            by_domain[s.domain].append(
                DomainSignal(s.id, s.direction, s.confidence, s.salience, s.as_of)
            )
    per_domain = {d: collapse_domain(by_domain[d]) for d in DOMAINS}
    return {
        "per_domain_stance": {
            d: {
                "stance": st.stance,
                "confidence": st.confidence,
                "contributing_signal_ids": st.contributing_signal_ids,
            }
            for d, st in per_domain.items()
        },
        "breadth": breadth(per_domain),
        "coherence": coherence(per_domain),
        "weakest_data_flag": _weakest_flag(per_domain),
        "synthesis_text": _synthesis(per_domain, breadth(per_domain), coherence(per_domain)),
    }


def recompute(session: Session, *, as_of: date | None = None) -> ConvergenceResult:
    ref = as_of or date.today()
    geo_ids = session.execute(
        select(Geography.id).where(
            Geography.is_active.is_(True), Geography.geo_type == "metro"
        )
    ).scalars().all()

    n = 0
    for geo_id in geo_ids:
        payload = _assess_market(session, geo_id, ref)
        ins = pg_insert(ConvergenceAssessment).values(
            geography_id=geo_id,
            as_of=ref,
            per_domain_stance=payload["per_domain_stance"],
            breadth=payload["breadth"],
            coherence=payload["coherence"],
            weakest_data_flag=payload["weakest_data_flag"],
            synthesis_text=payload["synthesis_text"],
            transform_version=TRANSFORM_VERSION,
        )
        stmt = ins.on_conflict_do_update(
            constraint="uq_convergence_key",
            set_={
                "per_domain_stance": ins.excluded.per_domain_stance,
                "breadth": ins.excluded.breadth,
                "coherence": ins.excluded.coherence,
                "weakest_data_flag": ins.excluded.weakest_data_flag,
                "synthesis_text": ins.excluded.synthesis_text,
                "created_at": func.now(),
            },
        )
        session.execute(stmt)
        n += 1

    session.commit()
    log.info("convergence recompute as_of=%s assessments=%d", ref, n)
    return ConvergenceResult(assessments=n, transform_version=TRANSFORM_VERSION, as_of=ref)


def _weakest_flag(per_domain: dict[str, DomainStance]) -> str:
    no_read = [d for d, st in per_domain.items() if st.stance == NO_READ]
    if no_read:
        return "no read: " + ", ".join(no_read)
    return "all domains reporting"


def _synthesis(per_domain: dict[str, DomainStance], b: int, coh: str) -> str:
    """Deterministic, honest one-liner (no AI; narration is E9). Describes the
    matrix without inventing precision."""
    parts = []
    for d in DOMAINS:
        st = per_domain[d]
        if st.stance == NO_READ:
            parts.append(f"{d}: no read")
        else:
            parts.append(f"{d}: {st.stance} ({st.confidence})")
    return "; ".join(parts) + f". Breadth {b}/4, coherence {coh}."
