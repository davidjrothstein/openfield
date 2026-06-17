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
from sqlalchemy.engine import Connection

from . import features as _features  # noqa: F401  (registers feature lineage resolver)
from . import lineage
from . import signals as _signals  # noqa: F401  (registers signal lineage resolver)
from .db import engine

app = FastAPI(title="Multifamily Market Intelligence Platform", version="0.1.0")


def get_conn():
    with engine.connect() as conn:
        yield conn


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


@app.get("/api/v1/healthz")
def healthz() -> dict:
    return {"status": "ok"}
