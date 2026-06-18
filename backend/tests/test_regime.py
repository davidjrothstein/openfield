"""E5.3 acceptance: regime — human-confirmed, versioned, time-bounded.

Backlog ACs covered:
* No regime row is written without a human action (manual tag or confirmation).
* A regime transition preserves the prior regime row (superseded_by), never
  overwrites.
* Confirming a regime change re-reviews theses conditioned on that regime.
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from app.models import Regime, RegimeProposal, Thesis
from app.regime import service as rs
from app.thesis import service as thesis_service

OWNER_URL = os.environ["MIP_DATABASE_URL"]
APP_URL = os.environ["MIP_APP_DATABASE_URL"]

BINDING = {"domain": "supply", "metric_code": "permits_5plus_units", "supporting_direction": "improving"}
THRESHOLD = {"contradiction_direction": "deteriorating", "broken_consecutive": 2}


@pytest.fixture(scope="module")
def app_sm():
    eng = create_engine(APP_URL, future=True)
    yield sessionmaker(bind=eng, future=True, expire_on_commit=False)
    eng.dispose()


@pytest.fixture()
def geo(app_sm):
    owner = create_engine(OWNER_URL, future=True)
    with owner.begin() as c:
        gid = c.execute(text("SELECT id FROM geography WHERE cbsa_code='38060'")).scalar_one()
        # Clean regimes/proposals for this market so transitions are isolated.
        c.execute(text("DELETE FROM regime WHERE geography_id=:g"), {"g": gid})
        c.execute(text("DELETE FROM regime_proposal WHERE geography_id=:g"), {"g": gid})
    owner.dispose()
    return gid


def test_manual_tag_then_transition_preserves_prior(app_sm, geo):
    with app_sm() as s:
        rs.set_regime(s, geography_id=geo, regime_type="expansion", assigned_by="anna",
                      effective_from=dt.date(2023, 1, 1))
    with app_sm() as s:
        cur = rs.current_regime(s, geo)
        assert cur.regime_type == "expansion"
        assert cur.assigned_by == "anna"  # human action recorded
        first_id = cur.id

    # Transition → prior row preserved (effective_to + superseded_by), new is live.
    with app_sm() as s:
        rs.set_regime(s, geography_id=geo, regime_type="oversupply_digestion",
                      assigned_by="ben", effective_from=dt.date(2023, 6, 1))
    with app_sm() as s:
        prior = s.get(Regime, first_id)
        assert prior.effective_to == dt.date(2023, 6, 1)
        assert prior.superseded_by is not None
        cur = rs.current_regime(s, geo)
        assert cur.regime_type == "oversupply_digestion" and cur.id == prior.superseded_by
        # Exactly one current (effective_to IS NULL) regime.
        n_live = s.scalar(
            select(func.count()).select_from(Regime).where(
                Regime.geography_id == geo, Regime.effective_to.is_(None)
            )
        )
        assert n_live == 1


def test_proposal_alone_writes_no_regime_until_confirmed(app_sm, geo):
    owner = create_engine(OWNER_URL, future=True)
    with owner.begin() as c:
        pid = c.execute(
            text(
                "INSERT INTO regime_proposal (geography_id, regime_type, confidence, status) "
                "VALUES (:g,'recovery','moderate','pending') RETURNING id"
            ),
            {"g": geo},
        ).scalar_one()
    owner.dispose()

    # A pending proposal asserts nothing: no regime row exists from it yet.
    with app_sm() as s:
        assert rs.current_regime(s, geo) is None

    # Confirmation is the human action → regime asserted by the confirming user.
    with app_sm() as s:
        result = rs.confirm_proposal(s, pid, assigned_by="paula", effective_from=dt.date(2023, 9, 1))
        assert result.regime.assigned_by == "paula"
        assert result.regime.source_proposal_id == pid
    with app_sm() as s:
        assert s.get(RegimeProposal, pid).status == "confirmed"
        assert rs.current_regime(s, geo).regime_type == "recovery"


def test_reject_proposal_writes_no_regime(app_sm, geo):
    owner = create_engine(OWNER_URL, future=True)
    with owner.begin() as c:
        pid = c.execute(
            text(
                "INSERT INTO regime_proposal (geography_id, regime_type, status) "
                "VALUES (:g,'late_cycle_topping','pending') RETURNING id"
            ),
            {"g": geo},
        ).scalar_one()
    owner.dispose()
    with app_sm() as s:
        rs.reject_proposal(s, pid)
    with app_sm() as s:
        assert s.get(RegimeProposal, pid).status == "rejected"
        assert rs.current_regime(s, geo) is None


def test_regime_change_rereviews_theses(app_sm, geo):
    with app_sm() as s:
        thesis = thesis_service.create_thesis(
            s, geography_id=geo, owner="anna", claim="Phoenix recovery", conviction="medium",
            horizon="12m",
            assumptions=[thesis_service.AssumptionSpec("supply easing", BINDING, THRESHOLD)],
        )
        tid = thesis.id

    with app_sm() as s:
        result = rs.set_regime(s, geography_id=geo, regime_type="recovery", assigned_by="anna")
        # A confirmed regime change re-reviews theses conditioned on that market.
        assert tid in result.rereviewed_thesis_ids
