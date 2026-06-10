"""E2 acceptance: Census BPS fetch → land → normalize, with quarantine.

Network egress to census.gov is not used here; the real ``CensusBpsClient`` is
covered by interface, and the pipeline is exercised end-to-end with the
``FixtureBpsClient`` over a canned metro file — matching the "real interfaces,
mock the source" stance. The write path runs through the restricted app role, so
this also proves ingestion needs no privilege beyond INSERT/SELECT (+ run-status
UPDATE).

Backlog ACs covered:
* A successful run lands a raw payload + ingestion_run, then normalizes.
* Valid rows commit to observation with full provenance; an unmappable
  geography lands in quarantine with a reason, not in observations.
* Re-running the same period is idempotent — no duplicate observations.
* A fetch failure leaves prior observations intact and marks the run failed
  (staleness), after bounded retries.
"""

from __future__ import annotations

import datetime as dt
import os
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.ingestion.bps_client import BpsFetchError, BpsFetchResult, FixtureBpsClient
from app.ingestion.fetch import run_fetch
from app.ingestion.parser import parse_bps_metro
from app.ingestion.pipeline import ingest_bps
from app.ingestion.raw_store import LocalRawStore
from app.models import NormalizationQuarantine, Observation
from app.observations import value_as_of

APP_URL = os.environ["MIP_APP_DATABASE_URL"]
PERIOD = dt.date(2023, 12, 1)
FIXTURE = (Path(__file__).parent / "fixtures" / "ma2312c.txt").read_text()


@pytest.fixture(scope="module")
def app_sessionmaker():
    eng = create_engine(APP_URL, future=True)
    yield sessionmaker(bind=eng, future=True, expire_on_commit=False)
    eng.dispose()


@pytest.fixture()
def clean_period(app_sessionmaker):
    """Remove any rows from prior runs for the test period via the owner role
    (the app role can't delete). Keeps idempotency/count assertions isolated."""
    owner = create_engine(os.environ["MIP_DATABASE_URL"], future=True)
    with owner.begin() as c:
        c.execute(
            text("DELETE FROM observation WHERE period = :p"), {"p": PERIOD}
        )
        c.execute(
            text(
                "DELETE FROM normalization_quarantine q USING ingestion_run r "
                "WHERE q.ingest_run_id = r.id AND q.raw_period = :p"
            ),
            {"p": PERIOD.isoformat()},
        )
    owner.dispose()
    yield


def _fixture_client(body: str = FIXTURE, release: dt.date = dt.date(2024, 1, 18)):
    return FixtureBpsClient({"202312": body}, release_date=release)


# --------------------------------------------------------------------------- #
# Parser (no DB)
# --------------------------------------------------------------------------- #
def test_parser_reads_metro_file():
    recs = parse_bps_metro(FIXTURE)
    assert len(recs) == 3
    dallas = next(r for r in recs if r.cbsa_code == "19100")
    # Embedded comma in the quoted name is handled by the CSV reader.
    assert dallas.cbsa_name == "Dallas-Fort Worth-Arlington, TX"
    assert dallas.period == PERIOD
    assert dallas.total_units == 2700  # 1000 + 0 + 200 + 1500
    assert dallas.units_5plus == 1500


# --------------------------------------------------------------------------- #
# Pipeline (DB, restricted app role)
# --------------------------------------------------------------------------- #
def test_successful_run_lands_payload_commits_and_quarantines(
    app_sessionmaker, clean_period, tmp_path
):
    store = LocalRawStore(tmp_path)
    with app_sessionmaker() as s:
        result = ingest_bps(s, client=_fixture_client(), raw_store=store, period=PERIOD)

    fetch, norm = result.fetch, result.normalize
    assert fetch.status == "succeeded"
    assert fetch.raw_key is not None
    # Raw payload landed verbatim and is reloadable (provenance: run → file).
    assert store.get(fetch.raw_key).body == FIXTURE

    # Dallas + Austin × 2 metrics = 4 observations; Nowhere (99999) → 2 quarantined.
    assert norm.committed == 4
    assert norm.quarantined == 2

    with app_sessionmaker() as s:
        obs = s.scalars(
            select(Observation).where(Observation.ingest_run_id == fetch.run_id)
        ).all()
        assert len(obs) == 4
        # Full provenance on every row.
        assert all(o.source_id is not None and o.ingest_run_id == fetch.run_id for o in obs)

        q = s.scalars(
            select(NormalizationQuarantine).where(
                NormalizationQuarantine.ingest_run_id == fetch.run_id
            )
        ).all()
        assert len(q) == 2
        assert {row.raw_geography for row in q} == {"99999"}
        assert all(row.reason == "unmapped_geography" for row in q)


def test_reingest_same_period_is_idempotent(app_sessionmaker, clean_period, tmp_path):
    store = LocalRawStore(tmp_path)
    with app_sessionmaker() as s:
        first = ingest_bps(s, client=_fixture_client(), raw_store=store, period=PERIOD)
    assert first.normalize.committed == 4

    # Same period, same vintage (same release date) → no new observations.
    with app_sessionmaker() as s:
        second = ingest_bps(s, client=_fixture_client(), raw_store=store, period=PERIOD)
    assert second.normalize.committed == 0

    with app_sessionmaker() as s:
        total = s.scalar(
            select(func.count())
            .select_from(Observation)
            .where(Observation.period == PERIOD)
        )
    assert total == 4


def test_revision_is_a_new_vintage(app_sessionmaker, clean_period, tmp_path):
    """A later release with a revised value appends a new vintage; point-in-time
    reads stay correct (E2 feeding the E1 vintaging guarantee)."""
    store = LocalRawStore(tmp_path)
    with app_sessionmaker() as s:
        ingest_bps(
            s,
            client=_fixture_client(release=dt.date(2024, 1, 18)),
            raw_store=store,
            period=PERIOD,
        )
        geo_id = s.scalar(text("SELECT id FROM geography WHERE cbsa_code='19100'"))
        metric_id = s.scalar(
            text("SELECT id FROM metric_series WHERE code='permits_5plus_units'")
        )

    revised = FIXTURE.replace(
        "30,1500,200000", "30,1600,210000"
    )  # Dallas 5+ units 1500 → 1600
    with app_sessionmaker() as s:
        ingest_bps(
            s,
            client=_fixture_client(body=revised, release=dt.date(2024, 2, 18)),
            raw_store=store,
            period=PERIOD,
        )

    with app_sessionmaker() as s:
        conn = s.connection()
        # As known after the first release: 1500. After the revision: 1600.
        assert value_as_of(conn, geo_id, metric_id, PERIOD, dt.date(2024, 1, 20)) == Decimal("1500")
        assert value_as_of(conn, geo_id, metric_id, PERIOD, dt.date(2024, 3, 1)) == Decimal("1600")
        # Both vintages persist.
        n = s.scalar(
            select(func.count())
            .select_from(Observation)
            .where(
                Observation.geography_id == geo_id,
                Observation.metric_id == metric_id,
                Observation.period == PERIOD,
            )
        )
        assert n == 2


# --------------------------------------------------------------------------- #
# Failure handling
# --------------------------------------------------------------------------- #
class _FailingClient:
    def __init__(self):
        self.calls = 0

    def fetch(self, period):
        self.calls += 1
        raise BpsFetchError("simulated source outage")


def test_fetch_failure_marks_run_failed_and_retries(app_sessionmaker, clean_period, tmp_path):
    store = LocalRawStore(tmp_path)
    client = _FailingClient()
    with app_sessionmaker() as s:
        outcome = run_fetch(
            s,
            client=client,
            raw_store=store,
            source_code="census_bps",
            period=PERIOD,
            attempts=3,
            base_delay=0,
            sleep=lambda _d: None,
        )
    assert client.calls == 3  # bounded retries
    assert outcome.status == "failed"
    assert outcome.error and "outage" in outcome.error

    # Prior data intact: the failed run produced no observations.
    with app_sessionmaker() as s:
        n = s.scalar(
            select(func.count())
            .select_from(Observation)
            .where(Observation.ingest_run_id == outcome.run_id)
        )
    assert n == 0
