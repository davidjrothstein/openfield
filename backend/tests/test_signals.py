"""E4 acceptance: signal engine — detectors, persistence, supersede, lineage.

Backlog ACs covered:
* Same inputs always produce the same signals (deterministic detectors).
* A leading-domain signal is not down-weighted for lacking corroboration
  (corroboration is never a confidence input).
* Detector params live in versioned config, not scattered in code.
* Re-firing on the same condition supersedes the prior signal; both rows persist.
* A signal's feature_refs resolve to real features (lineage intact).

Pure detectors + confidence/decay are unit-tested without a DB; the engine is
tested end-to-end (observations → features → signals) through the app role.
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app import lineage, signals  # noqa: F401  (signals registers lineage)
from app.features import engine as fe
from app.features.transforms import month_add
from app.lineage import run_integrity_check, walk
from app.models import Signal
from app.signals import engine as se
from app.signals.confidence import confidence, salience
from app.signals.detectors import FeatureValue, threshold, trend_break
from app.signals.reads import live_signals

OWNER_URL = os.environ["MIP_DATABASE_URL"]
APP_URL = os.environ["MIP_APP_DATABASE_URL"]

METRIC_CODE = "permits_5plus_units"
START = dt.date(2022, 1, 1)
N_MONTHS = 15
VINTAGE = dt.date(2023, 4, 1)
# A=Dallas, B, C rise slowly; D=Houston rises fast → cross-sectional outlier.
MARKETS = {"19100": (100, 5), "12420": (110, 5), "38060": (120, 5), "26420": (100, 30)}
RUN_AS_OF = dt.date(2023, 4, 1)


# --------------------------------------------------------------------------- #
# Pure detectors (no DB)
# --------------------------------------------------------------------------- #
def _fv(ftype, period, value, insufficient=False, fid=1):
    return FeatureValue(fid, ftype, period, value, insufficient)


def test_threshold_detector():
    params = dict(
        feature_type="zscore_xs", high=1.0, low=-1.0,
        high_direction="deteriorating", low_direction="improving",
        domain="supply", metric_ref=7,
    )
    # Above high → deteriorating; below low → improving; within band → None.
    assert threshold([_fv("zscore_xs", START, 1.5)], params).direction == "deteriorating"
    assert threshold([_fv("zscore_xs", START, -1.4)], params).direction == "improving"
    assert threshold([_fv("zscore_xs", START, 0.3)], params) is None
    # Insufficient features are ignored → nothing usable → None.
    assert threshold([_fv("zscore_xs", START, 9.0, insufficient=True)], params) is None


def test_trend_break_detector():
    params = dict(
        feature_type="delta_yoy", n=3, up_direction="deteriorating",
        down_direction="improving", domain="supply", metric_ref=7,
    )
    rising = [_fv("delta_yoy", month_add(START, m), 10.0, fid=m) for m in range(3)]
    assert trend_break(rising, params).direction == "deteriorating"
    falling = [_fv("delta_yoy", month_add(START, m), -10.0, fid=m) for m in range(3)]
    assert trend_break(falling, params).direction == "improving"
    mixed = [_fv("delta_yoy", month_add(START, m), v, fid=m) for m, v in enumerate([10, -3, 5])]
    assert trend_break(mixed, params) is None
    assert trend_break(rising[:2], params) is None  # fewer than n


def test_confidence_excludes_corroboration_and_reflects_freshness():
    fresh = dt.date(2023, 3, 1)
    ref = dt.date(2023, 4, 1)
    # Detector type sets the base: threshold > trend_break.
    assert confidence("threshold", as_of=fresh, ref_date=ref, cadence="monthly", depth=1) == "high"
    assert confidence("trend_break", as_of=fresh, ref_date=ref, cadence="monthly", depth=3) == "moderate"
    # Staleness downgrades; corroboration is never even an argument.
    stale = dt.date(2022, 1, 1)
    assert confidence("threshold", as_of=stale, ref_date=ref, cadence="monthly", depth=1) == "moderate"


def test_salience_decays_with_age():
    ref = dt.date(2023, 4, 1)
    assert salience(ref, ref) == 1.0
    older = salience(dt.date(2023, 1, 1), ref, half_life_days=90)
    newer = salience(dt.date(2023, 3, 1), ref, half_life_days=90)
    assert 0 < older < newer <= 1.0


# --------------------------------------------------------------------------- #
# Engine (DB, app role): observations → features → signals
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def app_sessionmaker():
    eng = create_engine(APP_URL, future=True)
    yield sessionmaker(bind=eng, future=True, expire_on_commit=False)
    eng.dispose()


def _insert_month(conn, geo_id, metric_id, source_id, run_id, period, value):
    conn.execute(
        text(
            "INSERT INTO observation (geography_id, metric_id, period, value, vintage, "
            "release_date, source_id, ingest_run_id) "
            "VALUES (:g,:m,:p,:v,:vt,:rd,:s,:r) "
            "ON CONFLICT (geography_id, metric_id, period, vintage) DO NOTHING"
        ),
        {"g": geo_id, "m": metric_id, "p": period, "v": value, "vt": VINTAGE,
         "rd": VINTAGE, "s": source_id, "r": run_id},
    )


@pytest.fixture(scope="module")
def seeded(app_sessionmaker):
    owner = create_engine(OWNER_URL, future=True)
    with owner.begin() as c:
        metric_id = c.execute(
            text("SELECT id FROM metric_series WHERE code=:c"), {"c": METRIC_CODE}
        ).scalar_one()
        source_id = c.execute(text("SELECT id FROM source WHERE code='census_bps'")).scalar_one()
        geo_ids = {
            cbsa: c.execute(
                text("SELECT id FROM geography WHERE cbsa_code=:c"), {"c": cbsa}
            ).scalar_one()
            for cbsa in MARKETS
        }
        # Clean derived layers and this metric's observations for our markets.
        c.execute(text("DELETE FROM signal"))
        c.execute(text("DELETE FROM feature"))
        c.execute(
            text("DELETE FROM observation WHERE metric_id=:m AND geography_id = ANY(:g)"),
            {"m": metric_id, "g": list(geo_ids.values())},
        )
        run_id = c.execute(
            text("INSERT INTO ingestion_run (source_id, status) VALUES (:s,'succeeded') RETURNING id"),
            {"s": source_id},
        ).scalar_one()
        for cbsa, (base, step) in MARKETS.items():
            for m in range(N_MONTHS):
                _insert_month(c, geo_ids[cbsa], metric_id, source_id, run_id,
                              month_add(START, m), base + m * step)
    owner.dispose()

    with app_sessionmaker() as s:
        fe.recompute(s, as_of=RUN_AS_OF)
    return {"metric_id": metric_id, "geo_ids": geo_ids, "source_id": source_id}


def _live(session, detector, geo_id, metric_id):
    return session.scalars(
        select(Signal).where(
            Signal.detector == detector,
            Signal.geography_id == geo_id,
            Signal.metric_ref == metric_id,
            Signal.superseded_by.is_(None),
        )
    ).one_or_none()


def test_signal_run_fires_detectors_with_lineage(app_sessionmaker, seeded):
    metric_id = seeded["metric_id"]
    dallas = seeded["geo_ids"]["19100"]
    houston = seeded["geo_ids"]["26420"]

    with app_sessionmaker() as s:
        result = se.run(s, as_of=RUN_AS_OF)
    # 4 trend_break (rising series, all markets) + 1 threshold (Houston outlier).
    assert result.inserted == 5
    assert result.superseded == 0

    with app_sessionmaker() as s:
        tb = _live(s, "trend_break", dallas, metric_id)
        assert tb.direction == "deteriorating"  # accelerating supply
        assert tb.domain == "supply"
        assert tb.confidence == "moderate"  # trend_break base, fresh
        assert len(tb.feature_refs) == 3

        th = _live(s, "threshold", houston, metric_id)
        assert th is not None and th.direction == "deteriorating"
        assert th.confidence == "high"  # threshold base, fresh
        # Only Houston is the cross-sectional outlier; Dallas has no threshold.
        assert _live(s, "threshold", dallas, metric_id) is None

        # Lineage: signal → features → observations → source.
        conn = s.connection()
        node = walk(conn, "signal", tb.id)
        types = {n.node_type for n in _flatten(node)}
        assert {"signal", "feature", "observation", "source"} <= types
        assert any(
            n.node_type == "source" and n.attrs["code"] == "census_bps"
            for n in _flatten(node)
        )
        assert run_integrity_check(conn) == []


def test_signal_run_is_idempotent(app_sessionmaker, seeded):
    with app_sessionmaker() as s:
        se.run(s, as_of=RUN_AS_OF)  # ensure baseline exists
    with app_sessionmaker() as s:
        again = se.run(s, as_of=RUN_AS_OF)
    assert again.inserted == 0
    assert again.unchanged == 5


def test_refire_supersedes_prior_signal(app_sessionmaker, seeded):
    metric_id = seeded["metric_id"]
    dallas = seeded["geo_ids"]["19100"]
    base, step = MARKETS["19100"]

    with app_sessionmaker() as s:
        se.run(s, as_of=RUN_AS_OF)
        prior = _live(s, "trend_break", dallas, metric_id)
        prior_id = prior.id

    # New month for Dallas only → its trend_break re-fires with a new as_of.
    owner = create_engine(OWNER_URL, future=True)
    with owner.begin() as c:
        run_id = c.execute(
            text("INSERT INTO ingestion_run (source_id, status) VALUES (:s,'succeeded') RETURNING id"),
            {"s": seeded["source_id"]},
        ).scalar_one()
        _insert_month(c, dallas, metric_id, seeded["source_id"], run_id,
                      month_add(START, N_MONTHS), base + N_MONTHS * step)
    owner.dispose()

    later = dt.date(2023, 4, 15)
    with app_sessionmaker() as s:
        fe.recompute(s, as_of=later)
    with app_sessionmaker() as s:
        result = se.run(s, as_of=later)

    assert result.superseded == 1
    assert result.inserted == 1
    with app_sessionmaker() as s:
        # Both rows persist; the old one points at the new live one.
        old = s.get(Signal, prior_id)
        new = _live(s, "trend_break", dallas, metric_id)
        assert new.id != prior_id
        assert old.superseded_by == new.id
        assert new.as_of == month_add(START, N_MONTHS)  # 2023-04
        # Exactly one live signal for the (detector, geo, metric) key.
        n_live = s.scalar(
            text(
                "SELECT count(*) FROM signal WHERE detector='trend_break' "
                "AND geography_id=:g AND metric_ref=:m AND superseded_by IS NULL"
            ),
            {"g": dallas, "m": metric_id},
        )
        assert n_live == 1


def test_live_signals_read_applies_decay(app_sessionmaker, seeded):
    dallas = seeded["geo_ids"]["19100"]
    with app_sessionmaker() as s:
        se.run(s, as_of=RUN_AS_OF)
    with app_sessionmaker() as s:
        conn = s.connection()
        near = {ls.id: ls.salience for ls in live_signals(conn, dallas, ref_date=dt.date(2023, 4, 1))}
        far = {ls.id: ls.salience for ls in live_signals(conn, dallas, ref_date=dt.date(2024, 4, 1))}
    assert near and far
    # The same signals read a year later have strictly lower salience.
    for sid, near_s in near.items():
        assert 0 < far[sid] < near_s <= 1.0


def _flatten(node):
    yield node
    for child in node.inputs:
        yield from _flatten(child)
