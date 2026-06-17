"""FastAPI application (TDS §14).

Read-mostly REST under ``/api/v1``. First endpoint: lineage (E8.1) — walking any
node to its sources is core to traceability and is built alongside the first
data layer, never retrofitted.

Requests run on the restricted ``mip_app`` engine; the API process holds no
privilege beyond what the migrations granted. OIDC auth + role middleware is
E1.3 and wraps these routes when it lands.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from . import features as _features  # noqa: F401  (registers feature lineage resolver)
from . import lineage
from . import signals as _signals  # noqa: F401  (registers signal lineage resolver)
from .db import SessionLocal, engine
from .thesis import health as thesis_health_mod
from .thesis import service as thesis_service

app = FastAPI(title="Multifamily Market Intelligence Platform", version="0.1.0")


def get_conn():
    with engine.connect() as conn:
        yield conn


def get_session():
    with SessionLocal() as session:
        yield session


@app.get("/api/v1/lineage/{node_type}/{node_id}")
def get_lineage(node_type: str, node_id: int, conn: Connection = Depends(get_conn)) -> dict:
    """Walk lineage from any node to its sources, with as-of dates and the
    stored file/fetch record at the provenance end of the chain."""
    try:
        node = lineage.walk(conn, node_type, node_id)
    except lineage.UnknownNodeType:
        raise HTTPException(
            status_code=404,
            detail=f"unknown node type {node_type!r}; known: {lineage.registered_node_types()}",
        )
    except lineage.NodeNotFound:
        raise HTTPException(status_code=404, detail=f"no {node_type} with id {node_id}")
    return node.to_dict()


# --------------------------------------------------------------------------- #
# Thesis system (E6)
# --------------------------------------------------------------------------- #
class AssumptionIn(BaseModel):
    statement: str
    supporting_signal_query: dict
    invalidation_threshold: dict


class ThesisIn(BaseModel):
    geography_id: int
    owner: str
    claim: str
    conviction: str
    horizon: str
    assumptions: list[AssumptionIn] = Field(min_length=1, max_length=6)


class RespondIn(BaseModel):
    response: str  # dismiss | downgrade | revise
    author: str
    rationale: str


@app.post("/api/v1/theses", status_code=201)
def create_thesis(body: ThesisIn, session: Session = Depends(get_session)) -> dict:
    try:
        thesis = thesis_service.create_thesis(
            session,
            geography_id=body.geography_id,
            owner=body.owner,
            claim=body.claim,
            conviction=body.conviction,
            horizon=body.horizon,
            assumptions=[
                thesis_service.AssumptionSpec(
                    statement=a.statement,
                    supporting_signal_query=a.supporting_signal_query,
                    invalidation_threshold=a.invalidation_threshold,
                )
                for a in body.assumptions
            ],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": thesis.id, "status": thesis.status}


@app.get("/api/v1/theses/{thesis_id}/health")
def get_thesis_health(thesis_id: int, session: Session = Depends(get_session)) -> dict:
    try:
        return thesis_health_mod.thesis_health(session, thesis_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"no thesis {thesis_id}")


@app.post("/api/v1/theses/{thesis_id}/assumptions/{assumption_id}/respond")
def respond(
    thesis_id: int,
    assumption_id: int,
    body: RespondIn,
    session: Session = Depends(get_session),
) -> dict:
    try:
        ev = thesis_service.respond_to_assumption(
            session,
            assumption_id,
            response=body.response,
            author=body.author,
            rationale=body.rationale,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"event_id": ev.id, "to_state": ev.to_state}


@app.get("/api/v1/healthz")
def healthz() -> dict:
    return {"status": "ok"}
