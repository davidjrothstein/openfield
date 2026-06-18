"""The nightly recompute DAG (E10.1, TDS §16).

A single, explicit, in-code pipeline (no Airflow): features → signals →
convergence → thesis evaluation → freshness scan → notifications. Each stage is
idempotent, so the whole pass is idempotent and re-runnable after a failure —
running it twice over the same observations produces the same derived state and
no duplicate notifications.

Runs on the RQ queue on a nightly schedule; also callable directly from a
cron-invoked management command or a backtest at a past ``as_of``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session, sessionmaker

from ..convergence import engine as convergence_engine
from ..features import engine as feature_engine
from ..signals import engine as signal_engine
from ..thesis import evaluate as thesis_eval
from . import freshness, notifications

log = logging.getLogger(__name__)


@dataclass
class RecomputeSummary:
    as_of: date
    features: int
    signals: int
    convergence: int
    thesis_events: int
    freshness_rows: int
    notifications: int


def recompute_all(session: Session, *, as_of: date | None = None) -> RecomputeSummary:
    """Run the full derived pipeline once. Idempotent."""
    ref = as_of or date.today()

    feat = feature_engine.recompute(session, as_of=ref)
    sig = signal_engine.run(session, as_of=ref)
    conv = convergence_engine.recompute(session, as_of=ref)
    thesis_events = thesis_eval.evaluate_all(session, ref_date=ref)
    fresh = freshness.scan(session, as_of=ref)
    notes = notifications.generate(session)

    summary = RecomputeSummary(
        as_of=ref,
        features=feat.features,
        signals=sig.inserted,
        convergence=conv.assessments,
        thesis_events=thesis_events,
        freshness_rows=fresh.rows,
        notifications=notes.created,
    )
    log.info("nightly recompute complete: %s", summary)
    return summary


def run_nightly(session_factory: sessionmaker, *, as_of: date | None = None) -> RecomputeSummary:
    """Entry point for the scheduler / RQ worker: opens a session and runs the DAG."""
    with session_factory() as session:
        return recompute_all(session, as_of=as_of)
