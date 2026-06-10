"""Scheduler entry for Census BPS on its monthly release cadence (TDS §6.1, §16).

V1 uses a lightweight APScheduler entry rather than an external workflow engine
(CLAUDE.md: no Airflow/Dagster/Celery). One fetch job per source on its cadence;
the job enqueues ingest for the most recently *released* period. APScheduler is
imported lazily so the rest of the package has no hard dependency on it (and
tests don't require it).
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import sessionmaker

from .bps_client import CensusBpsClient
from .pipeline import ingest_bps
from .raw_store import LocalRawStore, RawStore

log = logging.getLogger(__name__)


def _previous_month(today: date) -> date:
    """BPS reports a month with a lag; target the prior month's release."""
    year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return date(year, month, 1)


def run_scheduled_bps(
    session_factory: sessionmaker,
    *,
    raw_store: RawStore,
    client: CensusBpsClient | None = None,
    today: date | None = None,
) -> None:
    """One scheduled BPS ingest tick. Wrapped by the scheduler; also callable
    directly from a cron-invoked management command."""
    client = client or CensusBpsClient()
    period = _previous_month(today or date.today())
    with session_factory() as session:
        result = ingest_bps(session, client=client, raw_store=raw_store, period=period)
    log.info(
        "scheduled BPS tick period=%s status=%s committed=%s",
        period,
        result.fetch.status,
        getattr(result.normalize, "committed", None),
    )


def register(scheduler, session_factory: sessionmaker, *, raw_store_root: str) -> None:
    """Register the monthly BPS job on an APScheduler instance.

    Cadence is monthly; the precise day should track the Census release calendar
    (mid-month). Day 18 is a safe default that the calendar can refine later."""
    raw_store = LocalRawStore(raw_store_root)
    scheduler.add_job(
        run_scheduled_bps,
        trigger="cron",
        day=18,
        hour=12,
        id="census_bps_monthly",
        replace_existing=True,
        kwargs={"session_factory": session_factory, "raw_store": raw_store},
    )
    log.info("registered census_bps_monthly job (cron day=18)")
