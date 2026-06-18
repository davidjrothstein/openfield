"""End-to-end ingest for one source-period: fetch → land → normalize.

A successful fetch triggers normalization (TDS §6.1 AC). A failed fetch returns
the failed outcome and does *not* normalize — prior observations stay intact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from .bps_client import BpsClient
from .fetch import FetchOutcome, run_fetch
from .normalize import NormalizeResult, normalize_run
from .raw_store import RawStore

CENSUS_BPS = "census_bps"


@dataclass
class IngestResult:
    fetch: FetchOutcome
    normalize: NormalizeResult | None


def ingest_bps(
    session: Session,
    *,
    client: BpsClient,
    raw_store: RawStore,
    period: date,
    **fetch_kwargs,
) -> IngestResult:
    outcome = run_fetch(
        session,
        client=client,
        raw_store=raw_store,
        source_code=CENSUS_BPS,
        period=period,
        **fetch_kwargs,
    )
    if outcome.status != "succeeded":
        return IngestResult(outcome, None)
    norm = normalize_run(
        session, run_id=outcome.run_id, payload=outcome.payload, raw_store=raw_store
    )
    return IngestResult(outcome, norm)
