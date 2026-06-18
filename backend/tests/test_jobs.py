"""E10 acceptance: nightly recompute DAG, freshness scan, in-app notifications.

Backlog ACs covered:
* Nightly recompute is idempotent and re-runnable after failure.
* Every aggregate can show its weakest input's freshness.
* Invalidation events surface in-app, deduplicated.
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from app.features.transforms import month_add
from app.jobs import freshness
from app.jobs.recompute import recompute_all
from app.models import ConvergenceAssessment, Notification, Signal
from app.thesis import service

OWNER_URL = os.environ["MIP_DATABASE_URL"]
APP_URL = os.environ["MIP_APP_DATABASE_URL"]
METRIC_CODE = "permits_5plus_units"
START = dt.date(2022, 1, 1)
OWNER = "jobs_anna"
BINDING = {"domain": "supply", "metric_code": METRIC_CODE, "supporting_direction": "improving"}
THRESHOLD = {"contradiction_direction": "deteriorating", "broken_consecutive": 2,
             "challenged_confidence_min": "moderate"}


# --------------------------------------------------------------------------- #
# Pure freshness classification
# --------------------------------------------------------------------------- #
def test_classify_freshness():
    assert freshness._classify(30, "monthly") == "fresh"
    assert freshness._classify(100, "monthly") == "aging"
    assert freshness._classify(200, "monthly") == "stale"
    assert freshness._classify(None, "monthly") == "no_data"


# --------------------------------------------------------------------------- #
# Recompute DAG (DB)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def app_sm():
    eng = create_engine(APP_URL, future=True)
    yield sessionmaker(bind=eng, future=True, expire_on_commit=False)
    eng.dispose()


@pytest.fixture(scope="module")
def env(app_sm):
    owner = create_engine(OWNER_URL, future=True)
    with owner.begin() as c:
        dallas = c.execute(text("SELECT id FROM geography WHERE cbsa_code='19100'")).scalar_one()
        metric_id = c.execute(text("SELECT id FROM metric_series WHERE code=:c"), {"c": METRIC_CODE}).scalar_one()
        source_id = c.execute(text("SELECT id FROM source WHERE code='census_bps'")).scalar_one()
        c.execute(text("DELETE FROM notification"))
        c.execute(text("DELETE FROM data_freshness"))
        c.execute(text("DELETE FROM convergence_assessment"))
        c.execute(text("DELETE FROM signal"))
        c.execute(text("DELETE FROM feature"))
        c.execute(text("DELETE FROM observation WHERE metric_id=:m"), {"m": metric_id})
        run_id = c.execute(
            text("INSERT INTO ingestion_run (source_id, status) VALUES (:s,'succeeded') RETURNING id"),
            {"s": source_id},
        ).scalar_one()
        # Declining permits → an 'improving' supply signal.
        for m in range(15):
            c.execute(
                text(
                    "INSERT INTO observation (geography_id, metric_id, period, value, vintage, "
                    "release_date, source_id, ingest_run_id) VALUES (:g,:m,:p,:v,:vt,:vt,:s,:r)"
                ),
                {"g": dallas, "m": metric_id, "p": month_add(START, m), "v": 5000 - 100 * m,
                 "vt": dt.date(2023, 4, 1), "s": source_id, "r": run_id},
            )
    owner.dispose()
    return {"dallas": dallas, "metric_id": metric_id, "source_id": source_id}


def _append(env, values: dict[int, int], vintage: dt.date):
    owner = create_engine(OWNER_URL, future=True)
    with owner.begin() as c:
        run_id = c.execute(
            text("INSERT INTO ingestion_run (source_id, status) VALUES (:s,'succeeded') RETURNING id"),
            {"s": env["source_id"]},
        ).scalar_one()
        for m, v in values.items():
            c.execute(
                text(
                    "INSERT INTO observation (geography_id, metric_id, period, value, vintage, "
                    "release_date, source_id, ingest_run_id) VALUES (:g,:m,:p,:v,:vt,:vt,:s,:r)"
                ),
                {"g": env["dallas"], "m": env["metric_id"], "p": month_add(START, m), "v": v,
                 "vt": vintage, "s": env["source_id"], "r": run_id},
            )
    owner.dispose()


def test_recompute_all_runs_full_pipeline(app_sm, env):
    with app_sm() as s:
        summary = recompute_all(s, as_of=dt.date(2023, 4, 1))
    assert summary.features > 0
    assert summary.signals >= 1  # the supply trend_break
    assert summary.convergence >= 1
    assert summary.freshness_rows > 0

    with app_sm() as s:
        # Convergence + signals + freshness all materialized.
        assert s.scalar(select(func.count()).select_from(ConvergenceAssessment)) >= 1
        assert s.scalar(
            select(func.count()).select_from(Signal).where(Signal.geography_id == env["dallas"])
        ) >= 1
        # Weakest-input freshness available for the market.
        assert freshness.weakest_freshness(s, env["dallas"]) in ("fresh", "aging", "stale")


def test_recompute_all_idempotent(app_sm, env):
    with app_sm() as s:
        recompute_all(s, as_of=dt.date(2023, 4, 1))
    with app_sm() as s:
        again = recompute_all(s, as_of=dt.date(2023, 4, 1))
    # Re-running over identical observations churns nothing.
    assert again.signals == 0  # no new/superseded signals
    assert again.notifications == 0  # no duplicate notifications


def test_invalidation_surfaces_as_deduped_notification(app_sm, env):
    # Author a thesis that the declining-permits 'improving' signal supports.
    with app_sm() as s:
        thesis = service.create_thesis(
            s, geography_id=env["dallas"], owner=OWNER,
            claim="Dallas supply easing", conviction="high", horizon="12m",
            assumptions=[service.AssumptionSpec("supply easing", BINDING, THRESHOLD)],
        )
        tid = thesis.id
    with app_sm() as s:
        recompute_all(s, as_of=dt.date(2023, 4, 1))  # intact: improving signal holds

    # Reverse permits → signal flips deteriorating → assumption challenged.
    _append(env, {15: 6000, 16: 6100, 17: 6200}, vintage=dt.date(2023, 7, 1))
    with app_sm() as s:
        summary = recompute_all(s, as_of=dt.date(2023, 7, 1))
    assert summary.notifications >= 1

    with app_sm() as s:
        notes = s.scalars(
            select(Notification).where(Notification.recipient == OWNER)
        ).all()
        assert any(n.kind == "thesis_invalidation" and n.thesis_id == tid for n in notes)
        count_after_first = len(notes)

    # Re-running does not duplicate the notification (deduped).
    with app_sm() as s:
        again = recompute_all(s, as_of=dt.date(2023, 7, 15))
    assert again.notifications == 0
    with app_sm() as s:
        notes = s.scalars(select(Notification).where(Notification.recipient == OWNER)).all()
        assert len(notes) == count_after_first

    # The in-app list surfaces it.
    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/v1/notifications", params={"recipient": OWNER})
    assert resp.status_code == 200
    assert any(n["thesis_id"] == tid for n in resp.json()["notifications"])
