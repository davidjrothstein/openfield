"""Verifies the E1/Story-1 acceptance criteria against a real Postgres.

Acceptance criteria (backlog E1.1):

1. Inserting a second value for the same (geo,metric,period) with a new vintage
   creates a 2nd row; the old row is unchanged.
2. The app role cannot UPDATE or DELETE an observation (permission denied).
3. A point-in-time query for a past as-of returns the value known then, not the
   latest.

Plus: the seeds (10 active MSAs, Census source, registered permit metrics) exist.

Run against a migrated database. Connection strings come from MIP_DATABASE_URL
(owner) and MIP_APP_DATABASE_URL (restricted app role).
"""

from __future__ import annotations

import datetime as dt
import os
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from app.observations import read_as_of, value_as_of

OWNER_URL = os.environ["MIP_DATABASE_URL"]
APP_URL = os.environ["MIP_APP_DATABASE_URL"]


@pytest.fixture(scope="module")
def owner_engine():
    eng = create_engine(OWNER_URL, future=True)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def app_engine():
    eng = create_engine(APP_URL, future=True)
    yield eng
    eng.dispose()


@pytest.fixture()
def fixture_ids(owner_engine):
    """Return the (geo, metric, source) ids these tests use, and clear any rows
    from a prior run so the fixed (geo,metric,period,vintage) tuples are free.

    Cleanup uses the owner role (the app role can't delete); the observation
    writes under test still go through the app role to exercise the real grant
    set. These tests use 2025 periods, exclusive to this module."""
    with owner_engine.begin() as c:
        geo_id = c.execute(
            text("SELECT id FROM geography WHERE cbsa_code = '19100'")
        ).scalar_one()
        metric_id = c.execute(
            text("SELECT id FROM metric_series WHERE code = 'permits_5plus_units'")
        ).scalar_one()
        source_id = c.execute(
            text("SELECT id FROM source WHERE code = 'census_bps'")
        ).scalar_one()
        c.execute(
            text(
                "DELETE FROM observation WHERE geography_id = :g AND metric_id = :m "
                "AND period >= DATE '2025-01-01'"
            ),
            {"g": geo_id, "m": metric_id},
        )
    return geo_id, metric_id, source_id


def _open_run(conn, source_id: int) -> int:
    return conn.execute(
        text(
            "INSERT INTO ingestion_run (source_id, status) "
            "VALUES (:s, 'succeeded') RETURNING id"
        ),
        {"s": source_id},
    ).scalar_one()


def _insert_obs(conn, **kw) -> int:
    return conn.execute(
        text(
            """
            INSERT INTO observation
              (geography_id, metric_id, period, value, vintage, release_date,
               source_id, ingest_run_id)
            VALUES
              (:geography_id, :metric_id, :period, :value, :vintage, :release_date,
               :source_id, :ingest_run_id)
            RETURNING id
            """
        ),
        kw,
    ).scalar_one()


def test_seeds_present(owner_engine):
    with owner_engine.connect() as c:
        active = c.execute(
            text("SELECT count(*) FROM geography WHERE is_active AND geo_type='metro'")
        ).scalar_one()
        assert active == 10
        assert c.execute(
            text("SELECT count(*) FROM source WHERE code='census_bps'")
        ).scalar_one() == 1
        permit_metrics = c.execute(
            text("SELECT count(*) FROM metric_series WHERE code LIKE 'permits_%'")
        ).scalar_one()
        assert permit_metrics == 2


def test_new_vintage_appends_row_old_unchanged(app_engine, fixture_ids):
    """AC1: a revision is a new vintage row; the prior vintage is untouched."""
    geo_id, metric_id, source_id = fixture_ids
    period = dt.date(2025, 1, 1)
    with app_engine.begin() as c:
        run = _open_run(c, source_id)
        first_id = _insert_obs(
            c,
            geography_id=geo_id,
            metric_id=metric_id,
            period=period,
            value=Decimal("1000"),
            vintage=dt.date(2025, 2, 18),
            release_date=dt.date(2025, 2, 18),
            source_id=source_id,
            ingest_run_id=run,
        )
        # A revised figure for the same period — new vintage, new row.
        second_id = _insert_obs(
            c,
            geography_id=geo_id,
            metric_id=metric_id,
            period=period,
            value=Decimal("1120"),
            vintage=dt.date(2025, 3, 18),
            release_date=dt.date(2025, 3, 18),
            source_id=source_id,
            ingest_run_id=run,
        )

    with app_engine.connect() as c:
        rows = c.execute(
            text(
                "SELECT id, value, vintage FROM observation "
                "WHERE geography_id=:g AND metric_id=:m AND period=:p "
                "ORDER BY vintage"
            ),
            {"g": geo_id, "m": metric_id, "p": period},
        ).all()
    assert len(rows) == 2
    assert rows[0].id == first_id and rows[0].value == Decimal("1000")
    assert rows[1].id == second_id and rows[1].value == Decimal("1120")


def test_app_role_cannot_update_or_delete(app_engine, fixture_ids):
    """AC2: the app role has INSERT+SELECT only — UPDATE/DELETE are denied."""
    geo_id, metric_id, source_id = fixture_ids
    period = dt.date(2025, 4, 1)
    with app_engine.begin() as c:
        run = _open_run(c, source_id)
        obs_id = _insert_obs(
            c,
            geography_id=geo_id,
            metric_id=metric_id,
            period=period,
            value=Decimal("500"),
            vintage=dt.date(2025, 5, 18),
            release_date=dt.date(2025, 5, 18),
            source_id=source_id,
            ingest_run_id=run,
        )

    with app_engine.connect() as c:
        with pytest.raises(Exception) as ei:
            c.execute(
                text("UPDATE observation SET value = 999 WHERE id = :i"),
                {"i": obs_id},
            )
        assert "permission denied" in str(ei.value).lower()

    with app_engine.connect() as c:
        with pytest.raises(Exception) as ei:
            c.execute(text("DELETE FROM observation WHERE id = :i"), {"i": obs_id})
        assert "permission denied" in str(ei.value).lower()


def test_point_in_time_read(app_engine, fixture_ids):
    """AC3: an as-of read returns what was known then, not the latest vintage."""
    geo_id, metric_id, source_id = fixture_ids
    period = dt.date(2025, 6, 1)
    with app_engine.begin() as c:
        run = _open_run(c, source_id)
        _insert_obs(
            c, geography_id=geo_id, metric_id=metric_id, period=period,
            value=Decimal("800"), vintage=dt.date(2025, 7, 18),
            release_date=dt.date(2025, 7, 18), source_id=source_id, ingest_run_id=run,
        )
        _insert_obs(
            c, geography_id=geo_id, metric_id=metric_id, period=period,
            value=Decimal("875"), vintage=dt.date(2025, 8, 18),
            release_date=dt.date(2025, 8, 18), source_id=source_id, ingest_run_id=run,
        )

    with app_engine.connect() as c:
        # As of just after the first release: we knew 800, not the later 875.
        early = value_as_of(c, geo_id, metric_id, period, dt.date(2025, 7, 20))
        assert early == Decimal("800")
        # As of after the revision: the latest known vintage is 875.
        late = value_as_of(c, geo_id, metric_id, period, dt.date(2025, 9, 1))
        assert late == Decimal("875")
        # Before anything was published: nothing was known.
        none_yet = value_as_of(c, geo_id, metric_id, period, dt.date(2025, 7, 1))
        assert none_yet is None
        # A full as-of series read returns one row per period (latest ≤ as-of).
        series = read_as_of(c, geo_id, metric_id, dt.date(2025, 7, 20))
        assert any(r.period == period and r.value == Decimal("800") for r in series)
