"""Scheduled fetch + atomic landing for one public source-run (TDS §6.1, §6.2).

A fetch run is atomic: it opens an ``ingestion_run``, fetches with bounded
retries, lands the raw payload, and only then marks the run succeeded so
normalization can proceed. A persistent failure marks the run ``failed``, raises
a (logged) staleness signal, and leaves prior observations completely untouched
— corrections only ever arrive as new appended vintages.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import IngestionRun, Source
from .bps_client import BpsClient, BpsFetchError
from .parser import PARSER_VERSION
from .raw_store import RawPayload, RawStore, make_key

log = logging.getLogger(__name__)


def retry_with_backoff(
    fn: Callable[[], "object"],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    exc: type[BaseException] = Exception,
    sleep: Callable[[float], None] = time.sleep,
):
    """Call ``fn`` up to ``attempts`` times with exponential backoff (TDS §6.2:
    3 attempts). Re-raises the last exception on persistent failure."""
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except exc as e:  # type: ignore[misc]
            last = e
            if i < attempts - 1:
                sleep(base_delay * (2**i))
    assert last is not None
    raise last


@dataclass
class FetchOutcome:
    run_id: int
    status: str  # 'succeeded' | 'failed'
    raw_key: str | None
    payload: RawPayload | None
    error: str | None


def run_fetch(
    session: Session,
    *,
    client: BpsClient,
    raw_store: RawStore,
    source_code: str,
    period: date,
    attempts: int = 3,
    base_delay: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> FetchOutcome:
    """Fetch one source-period and land it atomically. Never raises on fetch
    failure — it records the failed run and returns the outcome."""
    source = session.execute(
        select(Source).where(Source.code == source_code)
    ).scalar_one()

    run = IngestionRun(source_id=source.id, status="running")
    session.add(run)
    session.flush()  # assign run.id

    try:
        result = retry_with_backoff(
            lambda: client.fetch(period),
            attempts=attempts,
            base_delay=base_delay,
            exc=BpsFetchError,
            sleep=sleep,
        )
    except BpsFetchError as e:
        run.status = "failed"
        run.error = str(e)
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
        # Staleness flag (consumed later by the freshness scan / notifications).
        log.warning(
            "ingest source=%s period=%s FAILED after %d attempts; prior data "
            "intact, staleness raised: %s",
            source_code,
            period,
            attempts,
            e,
        )
        return FetchOutcome(run.id, "failed", None, None, str(e))

    fetched_at = datetime.now(timezone.utc)
    payload = RawPayload(
        source_code=source_code,
        period_label=result.period_label,
        vintage=result.release_date,
        release_date=result.release_date,
        parser_version=PARSER_VERSION,
        body=result.body,
        fetched_at=fetched_at,
    )
    key = make_key(source_code, result.period_label, fetched_at)
    raw_store.put(key, payload)

    run.raw_payload_key = key
    run.status = "succeeded"
    run.finished_at = fetched_at
    session.commit()
    log.info("ingest source=%s period=%s landed key=%s", source_code, period, key)
    return FetchOutcome(run.id, "succeeded", key, payload, None)
