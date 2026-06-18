"""Regime assertion via human action, with thesis re-review (TDS §11.2/§11.3).

Every path that writes a ``regime`` row requires a human:
* ``set_regime`` — the 60-day manual analyst tag (``assigned_by`` = the analyst).
* ``confirm_proposal`` — copies an engine proposal into a regime with
  ``assigned_by`` = the confirming principal.

The 90-day rule engine writes only ``regime_proposal`` (pending); it never writes
``regime`` directly. A transition closes the prior regime (``effective_to`` +
``superseded_by``) rather than overwriting it, and triggers re-review of every
thesis on that market (a confirmed regime change re-evaluates regime-conditioned
convictions).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Regime, RegimeProposal, Thesis
from ..thesis.evaluate import evaluate_thesis


@dataclass
class RegimeResult:
    regime: Regime
    rereviewed_thesis_ids: list[int] = field(default_factory=list)


def current_regime(session: Session, geography_id: int) -> Regime | None:
    return session.scalars(
        select(Regime).where(
            Regime.geography_id == geography_id, Regime.effective_to.is_(None)
        )
    ).one_or_none()


def _rereview_theses(session: Session, geography_id: int, ref_date: date) -> list[int]:
    """A confirmed regime change re-reviews theses conditioned on that regime.
    V1: re-evaluate all non-closed theses for the market."""
    ids = session.scalars(
        select(Thesis.id).where(
            Thesis.geography_id == geography_id, Thesis.status != "closed"
        )
    ).all()
    for tid in ids:
        evaluate_thesis(session, tid, ref_date=ref_date)
    return list(ids)


def _close_prior(prior: Regime | None, new_id: int, effective_from: date) -> None:
    if prior is not None:
        prior.effective_to = effective_from
        prior.superseded_by = new_id


def set_regime(
    session: Session,
    *,
    geography_id: int,
    regime_type: str,
    assigned_by: str,
    effective_from: date | None = None,
    confidence: str | None = None,
    evidence_refs: dict | None = None,
) -> RegimeResult:
    """Manual analyst regime tag (the 60-day human action)."""
    eff = effective_from or date.today()
    prior = current_regime(session, geography_id)  # capture before inserting the new one
    regime = Regime(
        geography_id=geography_id,
        regime_type=regime_type,
        effective_from=eff,
        assigned_by=assigned_by,
        confidence=confidence,
        evidence_refs=evidence_refs,
    )
    session.add(regime)
    session.flush()
    _close_prior(prior, regime.id, eff)
    rereviewed = _rereview_theses(session, geography_id, eff)
    session.commit()
    return RegimeResult(regime=regime, rereviewed_thesis_ids=rereviewed)


def confirm_proposal(
    session: Session,
    proposal_id: int,
    *,
    assigned_by: str,
    effective_from: date | None = None,
) -> RegimeResult:
    """Confirm an engine proposal: copy it into a regime asserted by a human."""
    proposal = session.get(RegimeProposal, proposal_id)
    if proposal is None:
        raise ValueError(f"no regime_proposal {proposal_id}")
    if proposal.status != "pending":
        raise ValueError(f"proposal {proposal_id} is {proposal.status}, not pending")
    eff = effective_from or date.today()
    prior = current_regime(session, proposal.geography_id)  # before inserting the new one
    regime = Regime(
        geography_id=proposal.geography_id,
        regime_type=proposal.regime_type,
        effective_from=eff,
        assigned_by=assigned_by,  # the confirming user
        confidence=proposal.confidence,
        evidence_refs=proposal.evidence_refs,
        source_proposal_id=proposal.id,
    )
    session.add(regime)
    session.flush()
    _close_prior(prior, regime.id, eff)
    proposal.status = "confirmed"
    rereviewed = _rereview_theses(session, proposal.geography_id, eff)
    session.commit()
    return RegimeResult(regime=regime, rereviewed_thesis_ids=rereviewed)


def reject_proposal(session: Session, proposal_id: int) -> None:
    proposal = session.get(RegimeProposal, proposal_id)
    if proposal is None:
        raise ValueError(f"no regime_proposal {proposal_id}")
    proposal.status = "rejected"  # no regime row is written
    session.commit()
