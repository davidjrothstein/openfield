"""E1.2 / E8.1 acceptance: lineage walk + integrity check + endpoint.

Backlog ACs covered:
* A lineage walk from a node returns the chain to source with as-of dates.
  (Signals/features don't exist yet — the chain registered so far is
  observation → ingestion_run → source; derived layers extend the registry in
  E3–E5 without touching the walker.)
* The integrity check flags a derived row with a dangling input reference
  (exercised via a registered array-ref checker, the mechanism E3+ will use).
* GET /lineage/{node_type}/{node_id} returns the full chain; unknown nodes 404.

Runs through the restricted app role end-to-end (the API holds no extra
privilege).
"""

from __future__ import annotations

import datetime as dt
import os
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app import lineage
from app.ingestion.bps_client import FixtureBpsClient
from app.ingestion.pipeline import ingest_bps
from app.ingestion.raw_store import LocalRawStore
from app.lineage import IntegrityViolation, run_integrity_check, walk

APP_URL = os.environ["MIP_APP_DATABASE_URL"]
PERIOD = dt.date(2023, 11, 1)
FIXTURE_BODY = (
    'Census BPS metro current\n'
    'Date,CBSA,Name,1u B,1u U,1u V,2u B,2u U,2u V,34u B,34u U,34u V,5pu B,5pu U,5pu V\n'
    '202311,38060,"Phoenix-Mesa-Chandler, AZ",500,500,75000,0,0,0,10,40,6000,20,900,120000\n'
)


@pytest.fixture(scope="module")
def app_engine():
    eng = create_engine(APP_URL, future=True)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def ingested(app_engine, tmp_path_factory):
    """Land one real-shaped run so there is provenance to walk."""
    owner = create_engine(os.environ["MIP_DATABASE_URL"], future=True)
    with owner.begin() as c:
        # Clear derived features (recomputable) so the integrity check starts
        # from a clean slate not polluted by other tests' deletions.
        c.execute(text("DELETE FROM feature"))
        c.execute(text("DELETE FROM observation WHERE period = :p"), {"p": PERIOD})
    owner.dispose()

    store = LocalRawStore(tmp_path_factory.mktemp("raw"))
    client = FixtureBpsClient({"202311": FIXTURE_BODY}, release_date=dt.date(2023, 12, 18))
    with sessionmaker(bind=app_engine, future=True)() as s:
        result = ingest_bps(s, client=client, raw_store=store, period=PERIOD)
    assert result.normalize.committed == 2
    return result


def _first_obs_id(conn, run_id: int) -> int:
    return conn.execute(
        text("SELECT id FROM observation WHERE ingest_run_id = :r ORDER BY id LIMIT 1"),
        {"r": run_id},
    ).scalar_one()


def test_walk_reaches_source_with_as_of_dates(app_engine, ingested):
    with app_engine.connect() as conn:
        obs_id = _first_obs_id(conn, ingested.fetch.run_id)
        node = walk(conn, "observation", obs_id)

    # The observation itself carries its vintage (the as-of) and value.
    assert node.attrs["vintage"] == "2023-12-18"
    assert node.attrs["period"] == "2023-11-01"

    by_type = {n.node_type: n for n in _flatten(node)}
    # Chain reaches the run (with the stored fetch/file record) and the source.
    assert by_type["ingestion_run"].attrs["raw_payload_key"] == ingested.fetch.raw_key
    assert by_type["source"].attrs["code"] == "census_bps"
    assert by_type["source"].attrs["publisher"] == "U.S. Census Bureau"
    # Registry context resolves too.
    assert by_type["geography"].attrs["cbsa_code"] == "38060"
    assert by_type["metric_series"].attrs["domain"] == "supply"
    # Source is a terminus.
    assert by_type["source"].inputs == []


def test_walk_unknown_type_and_missing_node(app_engine):
    with app_engine.connect() as conn:
        with pytest.raises(lineage.UnknownNodeType):
            walk(conn, "gauge", 1)  # never a gauge
        with pytest.raises(lineage.NodeNotFound):
            walk(conn, "observation", 10**12)


def test_integrity_check_clean_then_flags_dangling_ref(app_engine, ingested):
    with app_engine.connect() as conn:
        assert run_integrity_check(conn) == []

    # Register a checker that reports a dangling array ref — the exact mechanism
    # the feature/signal layers (E3+) will use for their non-FK *_refs columns.
    def dangling(conn):
        return [IntegrityViolation("feature", 999, "feature_refs -> missing observation 10**12")]

    lineage.register_integrity_check(dangling)
    try:
        with app_engine.connect() as conn:
            violations = run_integrity_check(conn)
        assert any(v.node_type == "feature" and v.node_id == 999 for v in violations)
    finally:
        lineage._ARRAY_REF_CHECKS.remove(dangling)


def test_lineage_endpoint(app_engine, ingested):
    from app.main import app

    client = TestClient(app)
    with app_engine.connect() as conn:
        obs_id = _first_obs_id(conn, ingested.fetch.run_id)

    resp = client.get(f"/api/v1/lineage/observation/{obs_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["node_type"] == "observation"
    types = {n["node_type"] for n in _flatten_dict(body)}
    assert {"observation", "ingestion_run", "source", "geography", "metric_series"} <= types

    assert client.get("/api/v1/lineage/observation/999999999999").status_code == 404
    assert client.get("/api/v1/lineage/nonsense/1").status_code == 404


def _flatten(node):
    yield node
    for child in node.inputs:
        yield from _flatten(child)


def _flatten_dict(d):
    yield d
    for child in d["inputs"]:
        yield from _flatten_dict(child)
