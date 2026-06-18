"""Scheduling for background jobs (E10.1, TDS §16).

A lightweight APScheduler wires the nightly recompute DAG and the monthly Census
fetch — no external workflow engine. Heavy work can also be pushed onto the RQ
queue via ``enqueue_nightly`` when a Redis worker is deployed; the DAG function
is the same either way. APScheduler/RQ are imported lazily so the package has no
hard dependency on them (and tests don't require them).
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import sessionmaker

from ..ingestion import scheduler as ingestion_scheduler
from .recompute import run_nightly

log = logging.getLogger(__name__)


def register(scheduler, session_factory: sessionmaker, *, raw_store_root: str) -> None:
    """Register all scheduled jobs on an APScheduler instance."""
    # Nightly full recompute (after the data day; cadence is slow).
    scheduler.add_job(
        run_nightly,
        trigger="cron",
        hour=3,
        id="nightly_recompute",
        replace_existing=True,
        kwargs={"session_factory": session_factory},
    )
    log.info("registered nightly_recompute job (cron hour=3)")
    # Monthly Census BPS fetch on the release calendar.
    ingestion_scheduler.register(scheduler, session_factory, raw_store_root=raw_store_root)


def enqueue_nightly(queue, session_factory: sessionmaker) -> None:
    """Push the nightly recompute onto an RQ queue (when a Redis worker exists)."""
    queue.enqueue(run_nightly, session_factory)
