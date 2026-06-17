"""E5.1 acceptance: convergence — honest 4-domain matrix, no scalar.

Backlog ACs covered:
* A domain with no fresh signals shows 'no_read', visually distinct from
  'neutral'.
* There is no single convergence number in the schema or the UI.
* Every shown stance decomposes to its contributing signal IDs.

Pure collapse logic is unit-tested without a DB; the engine runs the whole chain
observations → features → signals → convergence through the app role.
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.convergence import engine as ce
from app.convergence.collapse import (
    NO_READ,
    DomainSignal,
    DomainStance,
    breadth,
    coherence,
    collapse_domain,
)
from app.features import engine as fe
from app.features.transforms import month_add
from app.lineage import run_integrity_check, walk
from app.models import ConvergenceAssessment
from app.signals import engine as se

OWNER_URL = os.environ["MIP_DATABASE_URL"]
APP_URL = os.environ["MIP_APP_DATABASE_URL"]
METRIC_CODE = "permits_5plus_units"
START = dt.date(2022, 1, 1)
AS_OF = dt.date(2023, 4, 1)


# --------------------------------------------------------------------------- #
# Pure collapse (no DB)
# --------------------------------------------------------------------------- #
def _ds(direction, conf="moderate", sal=1.0, sid=1, as_of=AS_OF):
    return DomainSignal(sid, direction, conf, sal, as_of)


def test_collapse_no_signals_is_no_read():
    st = collapse_domain([])
    assert st.stance == NO_READ
    assert st.contributing_signal_ids == []


def test_collapse_stale_signals_is_no_read():
    # All signals decayed below the freshness floor → no_read, not a stance.
    st = collapse_domain([_ds("improving", sal=0.05)])
    assert st.stance == NO_READ


def test_collapse_agreement_and_conflict():
    agree = collapse_domain([_ds("improving", sid=1), _ds("improving", sid=2)])
    assert agree.stance == "improving"
    assert set(agree.contributing_signal_ids) == {1, 2}

    # Comparable two-sided weight → mixed, never averaged into a false neutral.
    conflict = collapse_domain([_ds("improving", sid=1), _ds("deteriorating", sid=2)])
    assert conflict.stance == "mixed"


def test_breadth_and_coherence_need_multiple_domains():
    per = {
        "economy": DomainStance(NO_READ, "none", []),
        "supply": DomainStance("improving", "moderate", [1], AS_OF),
        "operator": DomainStance(NO_READ, "none", []),
        "capital": DomainStance(NO_READ, "none", []),
    }
    assert breadth(per) == 1
    assert coherence(per) == "no"  # only one directional domain → nothing to confirm


# --------------------------------------------------------------------------- #
# Engine (DB): observations → features → signals → convergence
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def app_sm():
    eng = create_engine(APP_URL, future=True)
    yield sessionmaker(bind=eng, future=True, expire_on_commit=False)
    eng.dispose()


@pytest.fixture(scope="module")
def supply_signal(app_sm):
    """Seed declining permits for Dallas → a real 'improving' supply signal, then
    recompute features + signals. Returns dallas geo id."""
    owner = create_engine(OWNER_URL, future=True)
    with owner.begin() as c:
        dallas = c.execute(text("SELECT id FROM geography WHERE cbsa_code='19100'")).scalar_one()
        metric_id = c.execute(text("SELECT id FROM metric_series WHERE code=:c"), {"c": METRIC_CODE}).scalar_one()
        source_id = c.execute(text("SELECT id FROM source WHERE code='census_bps'")).scalar_one()
        c.execute(text("DELETE FROM convergence_assessment"))
        c.execute(text("DELETE FROM signal"))
        c.execute(text("DELETE FROM feature"))
        c.execute(text("DELETE FROM observation WHERE metric_id=:m"), {"m": metric_id})
        run_id = c.execute(
            text("INSERT INTO ingestion_run (source_id, status) VALUES (:s,'succeeded') RETURNING id"),
            {"s": source_id},
        ).scalar_one()
        for m in range(15):
            c.execute(
                text(
                    "INSERT INTO observation (geography_id, metric_id, period, value, vintage, "
                    "release_date, source_id, ingest_run_id) VALUES (:g,:m,:p,:v,:vt,:vt,:s,:r)"
                ),
                {"g": dallas, "m": metric_id, "p": month_add(START, m), "v": 5000 - 100 * m,
                 "vt": AS_OF, "s": source_id, "r": run_id},
            )
    owner.dispose()
    with app_sm() as s:
        fe.recompute(s, as_of=AS_OF)
    with app_sm() as s:
        se.run(s, as_of=AS_OF)
    return dallas


def test_convergence_matrix_supply_real_rest_no_read(app_sm, supply_signal):
    dallas = supply_signal
    with app_sm() as s:
        ce.recompute(s, as_of=AS_OF)

    with app_sm() as s:
        a = s.scalars(
            select(ConvergenceAssessment).where(ConvergenceAssessment.geography_id == dallas)
        ).one()
        per = a.per_domain_stance
        # Supply is real and improving (permits decelerating); rest are no_read.
        assert per["supply"]["stance"] == "improving"
        assert per["supply"]["contributing_signal_ids"]  # decomposes to signals
        for d in ("economy", "operator", "capital"):
            assert per[d]["stance"] == NO_READ
        assert a.breadth == 1
        # NO scalar: the ORM/columns carry no single convergence number.
        cols = set(ConvergenceAssessment.__table__.columns.keys())
        assert not (cols & {"score", "convergence_score", "value", "rating"})


def test_convergence_lineage_to_source(app_sm, supply_signal):
    with app_sm() as s:
        ce.recompute(s, as_of=AS_OF)
        # Dallas is the market with a real supply signal; other markets are
        # no_read and would not link to signals.
        a = s.scalars(
            select(ConvergenceAssessment).where(
                ConvergenceAssessment.geography_id == supply_signal
            )
        ).one()
        conn = s.connection()
        node = walk(conn, "convergence_assessment", a.id)
        types = {n.node_type for n in _flatten(node)}
        assert {"convergence_assessment", "signal", "feature", "observation", "source"} <= types
        assert run_integrity_check(conn) == []


def test_convergence_recompute_idempotent(app_sm, supply_signal):
    def snap(s):
        rows = s.execute(
            select(
                ConvergenceAssessment.geography_id,
                ConvergenceAssessment.per_domain_stance,
                ConvergenceAssessment.breadth,
                ConvergenceAssessment.coherence,
            )
        ).all()
        return {r[0]: (r[1], r[2], r[3]) for r in rows}

    with app_sm() as s:
        ce.recompute(s, as_of=AS_OF)
        first = snap(s)
    with app_sm() as s:
        ce.recompute(s, as_of=AS_OF)
        second = snap(s)
    assert first == second


def test_market_view_api(app_sm, supply_signal):
    from app.main import app

    with app_sm() as s:
        ce.recompute(s, as_of=AS_OF)
    client = TestClient(app)
    resp = client.get(f"/api/v1/markets/{supply_signal}")
    assert resp.status_code == 200
    body = resp.json()
    conv = body["convergence"]
    assert conv["per_domain_stance"]["supply"]["stance"] == "improving"
    assert conv["per_domain_stance"]["economy"]["stance"] == NO_READ
    # No single convergence number surfaced.
    assert "score" not in conv and "convergence_score" not in conv
    assert set(conv["per_domain_stance"]) == {"economy", "supply", "operator", "capital"}


def _flatten(node):
    yield node
    for child in node.inputs:
        yield from _flatten(child)
