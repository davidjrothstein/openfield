"""E3 acceptance: feature recompute (deltas + z-scores), idempotency, lineage.

Backlog ACs covered:
* Running recompute twice over identical observations yields identical features.
* A window with too little history yields insufficient_data=true, never a
  fabricated value.
* Deltas and z-scores appear as features with correct lineage to observations.

Pure transforms are unit-tested without a DB; the engine is tested against a
controlled set of observations through the restricted app role.
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app import lineage
from app.features import engine as fe
from app.features.transforms import (
    Point,
    XsObs,
    compute_delta,
    compute_zscore_long,
    compute_zscore_xs,
    month_add,
)
from app.lineage import run_integrity_check, walk
from app.models import Feature

OWNER_URL = os.environ["MIP_DATABASE_URL"]
APP_URL = os.environ["MIP_APP_DATABASE_URL"]

# Controlled series: 4 markets × 15 monthly periods (2022-01 .. 2023-03).
MARKETS = {"19100": (1000, 10), "12420": (2000, 20), "38060": (1500, 5), "26420": (3000, 30)}
N_MONTHS = 15
START = dt.date(2022, 1, 1)
VINTAGE = dt.date(2023, 4, 1)
METRIC_CODE = "permits_total_units"


def _periods():
    return [month_add(START, m) for m in range(N_MONTHS)]


# --------------------------------------------------------------------------- #
# Pure transforms (no DB)
# --------------------------------------------------------------------------- #
def _line(step: int) -> list[Point]:
    return [
        Point(period=month_add(START, m), value=1000 + m * step, obs_id=1000 + m, vintage=VINTAGE)
        for m in range(N_MONTHS)
    ]


def test_delta_yoy_and_insufficient():
    rows = compute_delta(1, 1, _line(10), lag_months=12, feature_type="delta_yoy")
    by_p = {r.period: r for r in rows}
    # First 12 months: no t-12 observation → insufficient, value None.
    assert by_p[dt.date(2022, 1, 1)].insufficient_data is True
    assert by_p[dt.date(2022, 1, 1)].value is None
    # 2023-01 (month 12) = value(m12) - value(m0) = 120, with 2 input obs.
    jan = by_p[dt.date(2023, 1, 1)]
    assert jan.insufficient_data is False
    assert jan.value == 120
    assert len(jan.input_observation_ids) == 2


def test_zscore_long_insufficient_until_min_history():
    rows = compute_zscore_long(1, 1, _line(10))
    by_p = {r.period: r for r in rows}
    assert by_p[dt.date(2022, 1, 1)].insufficient_data is True  # 0 prior points
    feb_2023 = by_p[dt.date(2023, 2, 1)]  # month 13 → 13 prior points >= 12
    assert feb_2023.insufficient_data is False
    assert feb_2023.value > 0  # rising series, latest above its trailing mean


def test_zscore_xs_cross_section_and_too_few_markets():
    period = dt.date(2022, 1, 1)
    peers = [
        XsObs(geography_id=1, value=1000, obs_id=1, vintage=VINTAGE),
        XsObs(geography_id=2, value=2000, obs_id=2, vintage=VINTAGE),
        XsObs(geography_id=3, value=3000, obs_id=3, vintage=VINTAGE),
    ]
    rows = {r.geography_id: r for r in compute_zscore_xs(1, period, peers)}
    assert rows[1].value < 0 < rows[3].value  # lowest below peers, highest above
    assert rows[1].insufficient_data is False
    # Each row's lineage references the whole peer set.
    assert sorted(rows[1].input_observation_ids) == [1, 2, 3]

    # Two markets < min_markets → all insufficient.
    few = compute_zscore_xs(1, period, peers[:2])
    assert all(r.insufficient_data for r in few)


# --------------------------------------------------------------------------- #
# Engine (DB, restricted app role)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def app_sessionmaker():
    eng = create_engine(APP_URL, future=True)
    yield sessionmaker(bind=eng, future=True, expire_on_commit=False)
    eng.dispose()


@pytest.fixture(scope="module")
def seeded_observations():
    """Replace the controlled metric's observations for our 4 markets, via the
    owner role, then yield the id maps for assertions. Module-scoped so the two
    engine tests share stable observation ids (re-seeding would orphan the first
    test's features)."""
    owner = create_engine(OWNER_URL, future=True)
    with owner.begin() as c:
        # Features are derived/recomputable; clear them so a stale row from a
        # prior run can't reference observations we're about to replace.
        c.execute(text("DELETE FROM feature"))
        metric_id = c.execute(
            text("SELECT id FROM metric_series WHERE code = :code"), {"code": METRIC_CODE}
        ).scalar_one()
        source_id = c.execute(
            text("SELECT id FROM source WHERE code = 'census_bps'")
        ).scalar_one()
        geo_ids = {
            cbsa: c.execute(
                text("SELECT id FROM geography WHERE cbsa_code = :c"), {"c": cbsa}
            ).scalar_one()
            for cbsa in MARKETS
        }
        # Clean our period range for these markets so counts are deterministic.
        c.execute(
            text(
                "DELETE FROM observation WHERE metric_id = :m AND geography_id = ANY(:g) "
                "AND period >= :lo AND period <= :hi"
            ),
            {"m": metric_id, "g": list(geo_ids.values()), "lo": START, "hi": month_add(START, N_MONTHS - 1)},
        )
        run_id = c.execute(
            text(
                "INSERT INTO ingestion_run (source_id, status) VALUES (:s, 'succeeded') "
                "RETURNING id"
            ),
            {"s": source_id},
        ).scalar_one()
        for cbsa, (base, step) in MARKETS.items():
            for m in range(N_MONTHS):
                c.execute(
                    text(
                        "INSERT INTO observation (geography_id, metric_id, period, value, "
                        "vintage, release_date, source_id, ingest_run_id) VALUES "
                        "(:g,:m,:p,:v,:vt,:rd,:s,:r)"
                    ),
                    {
                        "g": geo_ids[cbsa],
                        "m": metric_id,
                        "p": month_add(START, m),
                        "v": base + m * step,
                        "vt": VINTAGE,
                        "rd": VINTAGE,
                        "s": source_id,
                        "r": run_id,
                    },
                )
    owner.dispose()
    return {"metric_id": metric_id, "geo_ids": geo_ids}


def _feature(session, geo_id, metric_id, ftype, period):
    return session.scalars(
        select(Feature).where(
            Feature.geography_id == geo_id,
            Feature.metric_id == metric_id,
            Feature.feature_type == ftype,
            Feature.period == period,
            Feature.transform_version == fe.TRANSFORM_VERSION,
        )
    ).one()


def test_recompute_produces_deltas_zscores_with_lineage(app_sessionmaker, seeded_observations):
    metric_id = seeded_observations["metric_id"]
    dallas = seeded_observations["geo_ids"]["19100"]
    houston = seeded_observations["geo_ids"]["26420"]

    with app_sessionmaker() as s:
        fe.recompute(s)

    with app_sessionmaker() as s:
        # delta_yoy 2023-01 for Dallas = step*12 = 120, with 2 observation inputs.
        yoy = _feature(s, dallas, metric_id, "delta_yoy", dt.date(2023, 1, 1))
        assert yoy.insufficient_data is False
        assert float(yoy.value) == 120.0
        assert len(yoy.input_observation_ids) == 2

        # Insufficient where the window is too thin — value is None, flag is set.
        yoy0 = _feature(s, dallas, metric_id, "delta_yoy", dt.date(2022, 1, 1))
        assert yoy0.insufficient_data is True and yoy0.value is None
        zl0 = _feature(s, dallas, metric_id, "zscore_long", dt.date(2022, 1, 1))
        assert zl0.insufficient_data is True and zl0.value is None

        # Cross-sectional: Houston (highest) > 0, Dallas (lowest) < 0 in 2022-01.
        xs_h = _feature(s, houston, metric_id, "zscore_xs", dt.date(2022, 1, 1))
        xs_d = _feature(s, dallas, metric_id, "zscore_xs", dt.date(2022, 1, 1))
        assert float(xs_d.value) < 0 < float(xs_h.value)
        assert xs_h.insufficient_data is False

        # Lineage: walk the delta_yoy feature to its observations and on to source.
        conn = s.connection()
        node = walk(conn, "feature", yoy.id)
        types = {n.node_type for n in _flatten(node)}
        assert {"feature", "observation", "ingestion_run", "source"} <= types
        assert any(
            n.node_type == "source" and n.attrs["code"] == "census_bps"
            for n in _flatten(node)
        )

        # Integrity check passes (registered feature checker + sample walk).
        assert run_integrity_check(conn) == []


def test_recompute_is_idempotent(app_sessionmaker, seeded_observations):
    def snapshot(session):
        rows = session.execute(
            select(
                Feature.geography_id,
                Feature.metric_id,
                Feature.feature_type,
                Feature.period,
                Feature.transform_version,
                Feature.value,
                Feature.insufficient_data,
            )
        ).all()
        return {(r[0], r[1], r[2], r[3], r[4]): (r[5], r[6]) for r in rows}

    with app_sessionmaker() as s:
        fe.recompute(s)
        first = snapshot(s)
        first_ids = {
            (f.geography_id, f.metric_id, f.feature_type, f.period): f.id
            for f in s.scalars(select(Feature)).all()
        }

    with app_sessionmaker() as s:
        fe.recompute(s)
        second = snapshot(s)
        second_ids = {
            (f.geography_id, f.metric_id, f.feature_type, f.period): f.id
            for f in s.scalars(select(Feature)).all()
        }

    assert first == second  # identical values + flags
    assert first_ids == second_ids  # stable ids → downstream feature_refs survive


def _flatten(node):
    yield node
    for child in node.inputs:
        yield from _flatten(child)
