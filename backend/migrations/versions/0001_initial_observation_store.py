"""initial observation store: geography, source, metric_series, ingestion_run,
observation + append-only role, point-in-time helper, and V1 seeds.

Epic E1 / Story 1 — Foundation: Observation Store & Lineage Spine.

This migration is the keystone of the platform. It establishes:

* the registry tables (geography, source, metric_series, ingestion_run);
* the append-only, vintaged ``observation`` table (TDS §5.1);
* the ``mip_app`` application role with **INSERT + SELECT only** on
  ``observation`` — no UPDATE/DELETE — so CLAUDE.md invariant #1 is enforced by
  database privilege, not convention;
* the ``observation_as_of`` point-in-time read function (greatest vintage ≤ an
  as-of date);
* seeds: ~10 active MSAs, the Census Building Permits source, and the registered
  Census permit metrics.

Migrations are forward-only in production (CLAUDE.md); ``downgrade`` exists for
local/test teardown only.

Revision ID: 0001_initial_observation_store
Revises:
Create Date: 2026-06-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_observation_store"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Name of the restricted application role. Mirrors app.config.settings.app_role_name.
APP_ROLE = "mip_app"


# --------------------------------------------------------------------------- #
# Seed data
# --------------------------------------------------------------------------- #
# ~10 hand-picked markets. The 100-MSA universe is a config list; widening
# coverage later is a data flip (is_active), not an architecture change
# (CLAUDE.md V1 scope). Sunbelt-heavy because supply is the one real domain in
# V1 and these are the active multifamily-supply stories.
SEED_MSAS = [
    # (cbsa_code, name, state)
    ("35620", "New York-Newark-Jersey City, NY-NJ-PA", "NY"),
    ("31080", "Los Angeles-Long Beach-Anaheim, CA", "CA"),
    ("19100", "Dallas-Fort Worth-Arlington, TX", "TX"),
    ("26420", "Houston-The Woodlands-Sugar Land, TX", "TX"),
    ("12060", "Atlanta-Sandy Springs-Alpharetta, GA", "GA"),
    ("38060", "Phoenix-Mesa-Chandler, AZ", "AZ"),
    ("12420", "Austin-Round Rock-Georgetown, TX", "TX"),
    ("33100", "Miami-Fort Lauderdale-Pompano Beach, FL", "FL"),
    ("19740", "Denver-Aurora-Lakewood, CO", "CO"),
    ("47900", "Washington-Arlington-Alexandria, DC-VA-MD-WV", "DC"),
]


def upgrade() -> None:
    _create_tables()
    _create_point_in_time_function()
    _create_app_role_and_grants()
    _seed()


def downgrade() -> None:
    # Forward-only in production; this path is for local/test teardown.
    # Table-level grants to the app role disappear with the tables. The
    # ``mip_app`` role itself is cluster-global and may be shared, so it is left
    # in place (upgrade re-creates it idempotently). Only the schema-level grant
    # is revoked here, best-effort.
    op.execute("DROP FUNCTION IF EXISTS observation_as_of(bigint, integer, date)")
    op.drop_table("observation")
    op.drop_table("ingestion_run")
    op.drop_table("metric_series")
    op.drop_table("source")
    op.drop_table("geography")
    op.execute(
        f"""
        DO $$
        BEGIN
           IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
              EXECUTE 'REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}';
           END IF;
        END
        $$;
        """
    )


# --------------------------------------------------------------------------- #
# Tables
# --------------------------------------------------------------------------- #
def _create_tables() -> None:
    op.create_table(
        "geography",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("geo_type", sa.Text, nullable=False),  # 'metro' | 'submarket'
        sa.Column("cbsa_code", sa.Text),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("state", sa.Text),
        sa.Column("parent_id", sa.BigInteger, sa.ForeignKey("geography.id")),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("geo_type", "cbsa_code", name="uq_geography_type_cbsa"),
        sa.CheckConstraint(
            "geo_type IN ('metro','submarket')", name="ck_geography_geo_type"
        ),
    )

    op.create_table(
        "source",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.Text, nullable=False, unique=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("publisher", sa.Text),
        sa.Column("retrieval_method", sa.Text, nullable=False),
        sa.Column("license_terms", sa.Text),
        sa.Column(
            "retention_policy",
            sa.Text,
            nullable=False,
            server_default=sa.text("'retain_raw'"),
        ),
        sa.Column("url", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "retrieval_method IN ('api','analyst_upload','file')",
            name="ck_source_retrieval_method",
        ),
        sa.CheckConstraint(
            "retention_policy IN ('retain_raw','derived_only')",
            name="ck_source_retention_policy",
        ),
    )

    op.create_table(
        "metric_series",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.Text, nullable=False, unique=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("domain", sa.Text, nullable=False),
        sa.Column("unit", sa.Text),
        sa.Column("frequency", sa.Text, nullable=False),
        sa.Column(
            "canonical_source_id", sa.Integer, sa.ForeignKey("source.id")
        ),
        sa.Column("description", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "domain IN ('economy','supply','operator','capital')",
            name="ck_metric_series_domain",
        ),
        sa.CheckConstraint(
            "frequency IN ('monthly','quarterly','annual')",
            name="ck_metric_series_frequency",
        ),
    )

    op.create_table(
        "ingestion_run",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "source_id", sa.Integer, sa.ForeignKey("source.id"), nullable=False
        ),
        sa.Column(
            "status", sa.Text, nullable=False, server_default=sa.text("'running'")
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("raw_payload_key", sa.Text),
        sa.Column("row_count", sa.Integer),
        sa.Column("error", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('running','succeeded','failed')",
            name="ck_ingestion_run_status",
        ),
    )

    op.create_table(
        "observation",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "geography_id",
            sa.BigInteger,
            sa.ForeignKey("geography.id"),
            nullable=False,
        ),
        sa.Column(
            "metric_id",
            sa.Integer,
            sa.ForeignKey("metric_series.id"),
            nullable=False,
        ),
        sa.Column("period", sa.Date, nullable=False),  # period the value describes
        sa.Column("value", sa.Numeric, nullable=False),
        sa.Column("vintage", sa.Date, nullable=False),  # when published/known
        sa.Column("release_date", sa.Date, nullable=False),
        sa.Column(
            "source_id", sa.Integer, sa.ForeignKey("source.id"), nullable=False
        ),
        sa.Column(
            "ingest_run_id",
            sa.BigInteger,
            sa.ForeignKey("ingestion_run.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "geography_id",
            "metric_id",
            "period",
            "vintage",
            name="uq_observation_geo_metric_period_vintage",
        ),
    )
    # Point-in-time read path: per (geo, metric, period), find greatest vintage
    # ≤ as-of. The unique constraint above already indexes the leading columns;
    # this descending-vintage index makes the DISTINCT ON lookup cheap.
    op.create_index(
        "ix_observation_pit",
        "observation",
        ["geography_id", "metric_id", "period", sa.text("vintage DESC")],
    )
    # Lineage / provenance lookups.
    op.create_index("ix_observation_ingest_run", "observation", ["ingest_run_id"])
    op.create_index("ix_observation_source", "observation", ["source_id"])
    # Metric-wide scans for the feature engine.
    op.create_index("ix_observation_metric_period", "observation", ["metric_id", "period"])


# --------------------------------------------------------------------------- #
# Point-in-time read helper (TDS §5.1)
# --------------------------------------------------------------------------- #
def _create_point_in_time_function() -> None:
    # Returns the vintage-correct series for a (geography, metric) as known on
    # an as-of date: per period, the row with the greatest vintage ≤ as-of.
    # SETOF observation so callers get the full, lineage-bearing rows.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION observation_as_of(
            p_geography_id bigint,
            p_metric_id    integer,
            p_as_of        date
        )
        RETURNS SETOF observation
        LANGUAGE sql
        STABLE
        AS $$
            SELECT DISTINCT ON (o.period) o.*
            FROM observation o
            WHERE o.geography_id = p_geography_id
              AND o.metric_id    = p_metric_id
              AND o.vintage     <= p_as_of
            ORDER BY o.period, o.vintage DESC, o.id DESC
        $$;
        """
    )
    op.execute(
        "COMMENT ON FUNCTION observation_as_of(bigint, integer, date) IS "
        "'Point-in-time read: greatest vintage <= as-of per period (TDS 5.1).'"
    )


# --------------------------------------------------------------------------- #
# Append-only application role (CLAUDE.md invariant #1)
# --------------------------------------------------------------------------- #
def _create_app_role_and_grants() -> None:
    # The role is a NOLOGIN privilege (group) role: authentication is an infra
    # concern (a LOGIN user is GRANTed this role), but the *privilege set* — the
    # invariant — lives here, in the reviewed migration. Created idempotently
    # because roles are cluster-global.
    op.execute(
        f"""
        DO $$
        BEGIN
           IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
              CREATE ROLE {APP_ROLE} NOLOGIN;
           END IF;
        END
        $$;
        """
    )

    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")

    # Registry tables are managed by migrations/admin; the app only reads them.
    op.execute(f"GRANT SELECT ON geography, metric_series, source TO {APP_ROLE}")

    # The app opens ingestion runs, so it may INSERT (and update run status on
    # completion). Sequence usage required for the bigserial id.
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON ingestion_run TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE ingestion_run_id_seq TO {APP_ROLE}")

    # THE INVARIANT: observation is append-only for the app role.
    # Revoke first (defensive/explicit), then grant exactly SELECT + INSERT.
    # No UPDATE, no DELETE, no TRUNCATE — ever.
    op.execute(f"REVOKE ALL ON observation FROM {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON observation TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE observation_id_seq TO {APP_ROLE}")

    # The point-in-time read is part of the app's normal read path.
    op.execute(
        f"GRANT EXECUTE ON FUNCTION observation_as_of(bigint, integer, date) "
        f"TO {APP_ROLE}"
    )


# --------------------------------------------------------------------------- #
# Seeds
# --------------------------------------------------------------------------- #
def _seed() -> None:
    bind = op.get_bind()

    # The one real V1 source: Census Building Permits Survey. Public-domain,
    # fetched via public API (TDS §6.1). retain_raw is fine — it is not licensed.
    source_id = bind.execute(
        sa.text(
            """
            INSERT INTO source
                (code, name, publisher, retrieval_method, license_terms,
                 retention_policy, url)
            VALUES
                (:code, :name, :publisher, :retrieval_method, :license_terms,
                 :retention_policy, :url)
            RETURNING id
            """
        ),
        {
            "code": "census_bps",
            "name": "U.S. Census Bureau — Building Permits Survey",
            "publisher": "U.S. Census Bureau",
            "retrieval_method": "api",
            "license_terms": "public domain",
            "retention_policy": "retain_raw",
            "url": "https://www.census.gov/construction/bps/",
        },
    ).scalar_one()

    # Register the Census permit metrics (supply domain). Permits are the
    # highest-value free leading signal (CLAUDE.md / TDS §6.1). Both total units
    # and 5+-unit structures (the multifamily-relevant series) are registered;
    # permits-to-stock is computed later in the feature engine.
    metrics = [
        {
            "code": "permits_total_units",
            "name": "Residential Building Permits — Total Units",
            "domain": "supply",
            "unit": "units",
            "frequency": "monthly",
            "canonical_source_id": source_id,
            "description": "Total residential units authorized by building permits (BPS).",
        },
        {
            "code": "permits_5plus_units",
            "name": "Residential Building Permits — Units in 5+ Unit Structures",
            "domain": "supply",
            "unit": "units",
            "frequency": "monthly",
            "canonical_source_id": source_id,
            "description": "Units authorized in structures with 5 or more units "
            "(multifamily) per BPS.",
        },
    ]
    bind.execute(
        sa.text(
            """
            INSERT INTO metric_series
                (code, name, domain, unit, frequency, canonical_source_id, description)
            VALUES
                (:code, :name, :domain, :unit, :frequency, :canonical_source_id,
                 :description)
            """
        ),
        metrics,
    )

    # ~10 active MSAs. is_active=true marks them as in-scope for V1.
    bind.execute(
        sa.text(
            """
            INSERT INTO geography (geo_type, cbsa_code, name, state, is_active)
            VALUES ('metro', :cbsa_code, :name, :state, true)
            """
        ),
        [
            {"cbsa_code": c, "name": n, "state": s}
            for (c, n, s) in SEED_MSAS
        ],
    )
