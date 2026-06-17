# MIP Backend — Observation Store & Lineage Spine

Python/FastAPI backend for the Multifamily Market Intelligence Platform. This is
the **E1 / Story 1** foundation: the append-only, vintaged observation store and
its registry tables, established by the initial Alembic migration.

See the governing docs: PRD, TDS (esp. §5 Data Model), and the V1 backlog (E1).

## What this migration establishes

`migrations/versions/0001_initial_observation_store.py` creates, in one reviewed
forward-only migration:

- **Registry tables** — `geography`, `source`, `metric_series`, `ingestion_run`.
- **`observation`** — the keystone, append-only, vintaged source of truth
  (TDS §5.1). `(geography_id, metric_id, period, vintage)` is unique; a revision
  is a *new vintage row*, never a mutation.
- **The append-only invariant, enforced by DB privilege** (CLAUDE.md #1). A
  restricted role `mip_app` is granted **`SELECT, INSERT` on `observation` and
  nothing else** — no `UPDATE`, no `DELETE`. This is a permission, not a
  convention.
- **`observation_as_of(geography_id, metric_id, as_of)`** — the point-in-time
  read helper: per period, the row with the greatest `vintage ≤ as_of`. Wrapped
  by `app/observations.py` (`read_as_of`, `value_as_of`).
- **Seeds** — ~10 active MSAs in `geography`, the Census Building Permits Survey
  `source`, and the registered Census permit metrics (`permits_total_units`,
  `permits_5plus_units`).

## Two database roles (by design)

| Role | Connection setting | Rights | Used by |
|------|--------------------|--------|---------|
| owner / migration | `MIP_DATABASE_URL` | full DDL; owns the schema | Alembic, admin/seeding |
| application | `MIP_APP_DATABASE_URL` | `INSERT+SELECT` on `observation`; no `UPDATE`/`DELETE` | the running service |

`mip_app` is a `NOLOGIN` privilege (group) role created by the migration —
authentication is an infra concern: create a `LOGIN` user and
`GRANT mip_app TO that_user`. The *privilege set* (the invariant) lives in the
reviewed migration.

## Local setup

```bash
pip install -e '.[dev]'        # or: pip install alembic sqlalchemy psycopg2-binary pydantic-settings pytest

# Owner DB + role
createdb mip
psql -c "CREATE ROLE mip_owner LOGIN PASSWORD '...'; ALTER ROLE mip_owner CREATEROLE;"
# (grant ownership of the mip database to mip_owner)

export MIP_DATABASE_URL="postgresql+psycopg2://mip_owner:...@localhost:5432/mip"
alembic upgrade head

# App login user, granted the restricted role created by the migration
psql -d mip -c "CREATE ROLE mip_app_login LOGIN PASSWORD '...'; GRANT mip_app TO mip_app_login;"
export MIP_APP_DATABASE_URL="postgresql+psycopg2://mip_app_login:...@localhost:5432/mip"
```

## Tests

`tests/test_observation_store.py` verifies the backlog acceptance criteria
against a real Postgres:

1. A new vintage for the same `(geo, metric, period)` appends a row; the prior
   row is unchanged.
2. The app role cannot `UPDATE` or `DELETE` an observation (permission denied).
3. A point-in-time read returns the value known *then*, not the latest vintage.

```bash
MIP_DATABASE_URL=... MIP_APP_DATABASE_URL=... pytest -q
```

## Feature engine (E3)

`app/features/` turns vintage-correct observations into detector-ready features.
`transforms.py` holds pure functions (YoY/QoQ deltas, cross-sectional and
longitudinal z-scores) that emit `insufficient_data=true` with a null value
rather than fabricating a number for a thin window. `engine.recompute(as_of=...)`
is the idempotent in-code DAG: it reads each market's series through
`observation_as_of`, upserts features on their unique key (stable ids so
downstream refs survive), and — because it reads vintage-correct — replaying a
past `as_of` is the backtest path for free. Every feature stores
`input_observation_ids` (lineage), and `app/features/lineage.py` registers the
`feature` resolver + array-ref integrity check with the walker.

## Lineage (E1.2 / E8.1)

`app/lineage.py` is the generic walker: given any `(node_type, id)` it returns
the chain to source, via a per-node-type resolver registry. Derived layers
(feature, signal, convergence) **register** into it as they land in E3–E5 — the
walker never changes. Exposed at `GET /api/v1/lineage/{node_type}/{node_id}`
(`app/main.py`, served on the restricted role). The integrity check
(`python -m app.integrity_job`) asserts every derived row references existing
inputs; array-ref layers register checkers the same way.

## Conventions

- Alembic migrations only; **forward-only**, reviewed before running. The
  `downgrade` path is for local/test teardown.
- The hand-written migration is authoritative (it carries roles, grants, and the
  SQL function, which ORM metadata cannot express). `app/models.py` mirrors it;
  `alembic check` guards against accidental drift.
