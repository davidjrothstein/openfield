"""E6 acceptance: the thesis system — the 60-day validation milestone.

Backlog ACs covered:
* Editing a thesis appends a version; prior versions remain readable.
* An assumption's kill-criterion is captured at authoring time; new matching
  signals are evaluated automatically on recompute.
* Invalidation is per-assumption, never wholesale.
* A stale supporting signal moves an assumption to 'watch' on staleness alone.
* A challenged assumption requires a recorded response.
* 60-day milestone: a real permit-driven signal reversal moves a real thesis's
  assumption to 'challenged' (then 'broken') and alerts the owner.

The state-machine core (decide_state) is unit-tested without a DB; the milestone
runs the whole chain observations → features → signals → thesis through the app
role.
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.features import engine as fe
from app.features.transforms import month_add
from app.models import Assumption, Thesis, ThesisEvent, ThesisVersion
from app.signals import engine as se
from app.thesis import service
from app.thesis.evaluate import Decision, SignalView, decide_state, evaluate_thesis
from app.thesis.health import thesis_health

OWNER_URL = os.environ["MIP_DATABASE_URL"]
APP_URL = os.environ["MIP_APP_DATABASE_URL"]
METRIC_CODE = "permits_5plus_units"
START = dt.date(2022, 1, 1)

BINDING = {"domain": "supply", "metric_code": METRIC_CODE, "supporting_direction": "improving"}
THRESHOLD = {
    "contradiction_direction": "deteriorating",
    "broken_consecutive": 2,
    "challenged_confidence_min": "moderate",
    "watch_stale_days": 120,
}


# --------------------------------------------------------------------------- #
# Pure state machine (no DB)
# --------------------------------------------------------------------------- #
def test_decide_state_transitions():
    ref = dt.date(2023, 6, 15)
    intact = decide_state(BINDING, THRESHOLD, [SignalView(1, "improving", "moderate", ref, 0)], ref_date=ref)
    assert intact.state == "intact"

    stale = decide_state(
        BINDING, THRESHOLD, [SignalView(1, "improving", "moderate", dt.date(2023, 1, 1), 0)], ref_date=ref
    )
    assert stale.state == "watch"  # freshness alone

    challenged = decide_state(
        BINDING, THRESHOLD, [SignalView(2, "deteriorating", "moderate", ref, 1)], ref_date=ref
    )
    assert challenged.state == "challenged"
    assert challenged.contradicting_ids == [2]

    broken = decide_state(
        BINDING, THRESHOLD, [SignalView(2, "deteriorating", "high", ref, 2)], ref_date=ref
    )
    assert broken.state == "broken"

    weak = decide_state(
        BINDING, THRESHOLD, [SignalView(2, "deteriorating", "low", ref, 1)], ref_date=ref
    )
    assert weak.state == "watch"  # below confidence floor → watch, not challenged


# --------------------------------------------------------------------------- #
# Authoring + versioning (DB)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def app_sm():
    eng = create_engine(APP_URL, future=True)
    yield sessionmaker(bind=eng, future=True, expire_on_commit=False)
    eng.dispose()


@pytest.fixture()
def dallas_id():
    owner = create_engine(OWNER_URL, future=True)
    with owner.begin() as c:
        gid = c.execute(text("SELECT id FROM geography WHERE cbsa_code='19100'")).scalar_one()
    owner.dispose()
    return gid


def _spec():
    return service.AssumptionSpec(
        statement="Multifamily supply pressure is easing (permits decelerating).",
        supporting_signal_query=BINDING,
        invalidation_threshold=THRESHOLD,
    )


def test_authoring_appends_versions_and_keeps_history(app_sm, dallas_id):
    with app_sm() as s:
        thesis = service.create_thesis(
            s, geography_id=dallas_id, owner="anna", claim="Austin-style digestion easing",
            conviction="medium", horizon="12-18m", assumptions=[_spec()],
        )
        tid = thesis.id

    with app_sm() as s:
        service.edit_thesis(s, tid, author="anna", rationale="raise conviction on fresh read",
                            conviction="high")

    with app_sm() as s:
        versions = s.scalars(
            select(ThesisVersion).where(ThesisVersion.thesis_id == tid).order_by(ThesisVersion.version_no)
        ).all()
        assert [v.version_no for v in versions] == [1, 2]
        assert versions[0].conviction == "medium"  # prior version still readable
        assert versions[1].conviction == "high"
        assert s.get(Thesis, tid).conviction == "high"  # head updated


def test_authoring_rejects_too_many_assumptions(app_sm, dallas_id):
    with app_sm() as s:
        with pytest.raises(ValueError):
            service.create_thesis(
                s, geography_id=dallas_id, owner="x", claim="c", conviction="low", horizon="h",
                assumptions=[_spec() for _ in range(7)],
            )


# --------------------------------------------------------------------------- #
# The 60-day milestone: real permit reversal → challenged → broken
# --------------------------------------------------------------------------- #
def _seed_clean(owner_engine, dallas_id):
    with owner_engine.begin() as c:
        metric_id = c.execute(text("SELECT id FROM metric_series WHERE code=:c"), {"c": METRIC_CODE}).scalar_one()
        source_id = c.execute(text("SELECT id FROM source WHERE code='census_bps'")).scalar_one()
        # Clear derived layers + all permits_5plus observations for a clean slate.
        c.execute(text("DELETE FROM signal"))
        c.execute(text("DELETE FROM feature"))
        c.execute(text("DELETE FROM observation WHERE metric_id=:m"), {"m": metric_id})
    return metric_id, source_id


def _append_months(owner_engine, dallas_id, metric_id, source_id, values: dict[int, int], vintage: dt.date):
    with owner_engine.begin() as c:
        run_id = c.execute(
            text("INSERT INTO ingestion_run (source_id, status) VALUES (:s,'succeeded') RETURNING id"),
            {"s": source_id},
        ).scalar_one()
        for m, val in values.items():
            c.execute(
                text(
                    "INSERT INTO observation (geography_id, metric_id, period, value, vintage, "
                    "release_date, source_id, ingest_run_id) VALUES (:g,:m,:p,:v,:vt,:vt,:s,:r)"
                ),
                {"g": dallas_id, "m": metric_id, "p": month_add(START, m), "v": val,
                 "vt": vintage, "s": source_id, "r": run_id},
            )


def _pipeline(app_sm, as_of):
    with app_sm() as s:
        fe.recompute(s, as_of=as_of)
    with app_sm() as s:
        se.run(s, as_of=as_of)


def test_60day_milestone_reversal_challenges_then_breaks(app_sm, dallas_id):
    owner = create_engine(OWNER_URL, future=True)
    metric_id, source_id = _seed_clean(owner, dallas_id)

    # Phase A — declining permits for 15 months → trend_break 'improving' (supply easing).
    declining = {m: 5000 - 100 * m for m in range(15)}
    _append_months(owner, dallas_id, metric_id, source_id, declining, vintage=dt.date(2023, 4, 1))
    _pipeline(app_sm, dt.date(2023, 4, 1))

    with app_sm() as s:
        thesis = service.create_thesis(
            s, geography_id=dallas_id, owner="anna",
            claim="Supply pressure easing in Dallas multifamily.",
            conviction="high", horizon="12-18m", assumptions=[_spec()],
        )
        tid = thesis.id
        aid = s.scalars(select(Assumption.id).where(Assumption.thesis_id == tid)).one()

    with app_sm() as s:
        evaluate_thesis(s, tid, ref_date=dt.date(2023, 4, 15))
    with app_sm() as s:
        assert s.get(Assumption, aid).state == "intact"  # supporting improving signal holds

    # Phase B — permits reverse upward for 3 months → trend_break 'deteriorating' (run 1).
    rising_b = {15: 6000, 16: 6100, 17: 6200}
    _append_months(owner, dallas_id, metric_id, source_id, rising_b, vintage=dt.date(2023, 7, 1))
    _pipeline(app_sm, dt.date(2023, 7, 1))
    with app_sm() as s:
        evaluate_thesis(s, tid, ref_date=dt.date(2023, 7, 15))

    with app_sm() as s:
        a = s.get(Assumption, aid)
        assert a.state == "challenged"  # real permit-driven reversal
        assert a.needs_response is True
        # Owner is alerted.
        alerts = s.scalars(
            select(ThesisEvent).where(
                ThesisEvent.thesis_id == tid, ThesisEvent.event_type == "alert"
            )
        ).all()
        assert alerts and "anna" in alerts[-1].detail

    # A challenged assumption requires a recorded response.
    with app_sm() as s:
        ev = service.respond_to_assumption(
            s, aid, response="dismiss", author="anna", rationale="single-month spike, watching"
        )
        assert ev.event_type == "response"
    with app_sm() as s:
        a = s.get(Assumption, aid)
        assert a.needs_response is False
        # The response is itself a recorded version.
        last = s.scalars(
            select(ThesisVersion).where(ThesisVersion.thesis_id == tid).order_by(ThesisVersion.version_no.desc())
        ).first()
        assert "response to challenge" in last.rationale

    # Phase C — contradiction persists a 2nd consecutive period → 'broken', thesis under review.
    rising_c = {18: 6300}
    _append_months(owner, dallas_id, metric_id, source_id, rising_c, vintage=dt.date(2023, 8, 1))
    _pipeline(app_sm, dt.date(2023, 8, 1))
    with app_sm() as s:
        evaluate_thesis(s, tid, ref_date=dt.date(2023, 8, 15))

    with app_sm() as s:
        assert s.get(Assumption, aid).state == "broken"
        assert s.get(Thesis, tid).status == "under_review"

        # Health view shows supporting vs contradicting side by side.
        health = thesis_health(s, tid, ref_date=dt.date(2023, 8, 15))
        row = next(r for r in health["assumptions"] if r["id"] == aid)
        assert row["state"] == "broken"
        assert row["contradicting"]  # the deteriorating signal is surfaced
    owner.dispose()


# --------------------------------------------------------------------------- #
# API surface
# --------------------------------------------------------------------------- #
def test_thesis_api_roundtrip(app_sm, dallas_id):
    from app.main import app

    client = TestClient(app)
    body = {
        "geography_id": dallas_id,
        "owner": "ben",
        "claim": "API-authored thesis",
        "conviction": "medium",
        "horizon": "12m",
        "assumptions": [
            {"statement": "supply easing", "supporting_signal_query": BINDING,
             "invalidation_threshold": THRESHOLD}
        ],
    }
    resp = client.post("/api/v1/theses", json=body)
    assert resp.status_code == 201
    tid = resp.json()["id"]

    health = client.get(f"/api/v1/theses/{tid}/health")
    assert health.status_code == 200
    assert health.json()["thesis"]["owner"] == "ben"

    with app_sm() as s:
        aid = s.scalars(select(Assumption.id).where(Assumption.thesis_id == tid)).first()
    r = client.post(
        f"/api/v1/theses/{tid}/assumptions/{aid}/respond",
        json={"response": "revise", "author": "ben", "rationale": "tighten criterion"},
    )
    assert r.status_code == 200

    # Too many assumptions is rejected.
    bad = {**body, "assumptions": body["assumptions"] * 7}
    assert client.post("/api/v1/theses", json=bad).status_code == 422
