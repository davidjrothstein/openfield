"""Thesis authoring and analyst actions (TDS §12.1, E6.1/E6.2/E6.3).

Every mutation appends a ``ThesisVersion`` so the head stays current and the
history stays immutable. Authoring captures 3–6 assumptions with their
kill-criteria up front, before commitment. A challenged assumption requires a
recorded response — also captured as a version.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Assumption, Thesis, ThesisEvent, ThesisVersion

_VALID_RESPONSES = {"dismiss", "downgrade", "revise"}


@dataclass
class AssumptionSpec:
    statement: str
    supporting_signal_query: dict
    invalidation_threshold: dict


def _next_version_no(session: Session, thesis_id: int) -> int:
    current = session.scalar(
        select(func.max(ThesisVersion.version_no)).where(
            ThesisVersion.thesis_id == thesis_id
        )
    )
    return (current or 0) + 1


def _append_version(session: Session, thesis: Thesis, *, author: str, rationale: str) -> ThesisVersion:
    v = ThesisVersion(
        thesis_id=thesis.id,
        version_no=_next_version_no(session, thesis.id),
        claim=thesis.claim,
        conviction=thesis.conviction,
        horizon=thesis.horizon,
        status=thesis.status,
        author=author,
        rationale=rationale,
    )
    session.add(v)
    return v


def create_thesis(
    session: Session,
    *,
    geography_id: int,
    owner: str,
    claim: str,
    conviction: str,
    horizon: str,
    assumptions: list[AssumptionSpec],
    status: str = "active",
    rationale: str = "initial authoring",
) -> Thesis:
    """Author a thesis with its load-bearing assumptions and pre-committed
    kill-criteria. Records the initial version."""
    if not 1 <= len(assumptions) <= 6:
        raise ValueError("a thesis carries 1–6 load-bearing assumptions (TDS §12.1)")
    thesis = Thesis(
        geography_id=geography_id,
        owner=owner,
        claim=claim,
        conviction=conviction,
        horizon=horizon,
        status=status,
    )
    session.add(thesis)
    session.flush()
    for spec in assumptions:
        session.add(
            Assumption(
                thesis_id=thesis.id,
                statement=spec.statement,
                supporting_signal_query=spec.supporting_signal_query,
                invalidation_threshold=spec.invalidation_threshold,
            )
        )
    _append_version(session, thesis, author=owner, rationale=rationale)
    session.commit()
    return thesis


def edit_thesis(
    session: Session,
    thesis_id: int,
    *,
    author: str,
    rationale: str,
    claim: str | None = None,
    conviction: str | None = None,
    horizon: str | None = None,
    status: str | None = None,
) -> ThesisVersion:
    """Apply a change to the head and append an immutable version with rationale."""
    thesis = session.get(Thesis, thesis_id)
    if thesis is None:
        raise ValueError(f"no thesis {thesis_id}")
    if claim is not None:
        thesis.claim = claim
    if conviction is not None:
        thesis.conviction = conviction
    if horizon is not None:
        thesis.horizon = horizon
    if status is not None:
        thesis.status = status
    thesis.updated_at = session.scalar(select(func.now()))
    version = _append_version(session, thesis, author=author, rationale=rationale)
    session.commit()
    return version


def respond_to_assumption(
    session: Session,
    assumption_id: int,
    *,
    response: str,
    author: str,
    rationale: str,
) -> ThesisEvent:
    """Record an analyst response to a challenged assumption (TDS §12.3).

    The response is recorded as both a thesis_event and a thesis_version (it is
    part of the conviction audit trail). dismiss → back to watch; downgrade →
    thesis conviction lowered; revise → assumption returns to intact for
    re-evaluation. ``needs_response`` clears."""
    if response not in _VALID_RESPONSES:
        raise ValueError(f"response must be one of {_VALID_RESPONSES}")
    a = session.get(Assumption, assumption_id)
    if a is None:
        raise ValueError(f"no assumption {assumption_id}")
    thesis = session.get(Thesis, a.thesis_id)

    a.needs_response = False
    if response == "dismiss":
        a.state = "watch"  # acknowledged as noise but kept on watch
    elif response == "revise":
        a.state = "intact"  # re-armed for re-evaluation against the new criterion
    elif response == "downgrade" and thesis.conviction == "high":
        thesis.conviction = "medium"
    elif response == "downgrade" and thesis.conviction == "medium":
        thesis.conviction = "low"
    a.state_changed_at = session.scalar(select(func.now()))

    ev = ThesisEvent(
        thesis_id=a.thesis_id,
        assumption_id=a.id,
        event_type="response",
        to_state=a.state,
        detail=f"{response}: {rationale}",
        actor=author,
    )
    session.add(ev)
    _append_version(
        session, thesis, author=author, rationale=f"response to challenge ({response}): {rationale}"
    )
    session.commit()
    return ev
