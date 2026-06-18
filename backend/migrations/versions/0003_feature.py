"""feature table: derived, versioned, recomputable detector inputs.

Epic E3 / Story 1 — Feature table + recompute pass (TDS §5.2).

Features are derived from observations and fully recomputable, so this table is
NOT under the append-only observation invariant — the recompute pass rewrites it
(idempotently). But lineage is still mandatory (CLAUDE.md #2): every feature row
stores ``input_observation_ids`` (array refs to the observations that produced
it), which the lineage walker resolves and the integrity check validates.

Two invariants enforced here:
* ``insufficient_data`` is NOT NULL — never a silent null (CLAUDE.md). A check
  constraint guarantees a present value xor the insufficient flag: a null value
  must carry ``insufficient_data = true``.
* ``transform_version`` is part of the unique key, so a new transform version
  never overwrites an older one in place (historical detector behavior stays
  auditable, TDS §5.2).

Revision ID: 0003_feature
Revises: 0002_normalization_quarantine
Create Date: 2026-06-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_feature"
down_revision: Union[str, None] = "0002_normalization_quarantine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "mip_app"


def upgrade() -> None:
    op.create_table(
        "feature",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "geography_id", sa.BigInteger, sa.ForeignKey("geography.id"), nullable=False
        ),
        sa.Column(
            "metric_id", sa.Integer, sa.ForeignKey("metric_series.id"), nullable=False
        ),
        # 'delta_yoy','delta_qoq','zscore_xs','zscore_long', ...
        sa.Column("feature_type", sa.Text, nullable=False),
        sa.Column("period", sa.Date, nullable=False),
        sa.Column("value", sa.Numeric),  # nullable: null iff insufficient_data
        sa.Column(
            "insufficient_data",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("transform_version", sa.Text, nullable=False),
        sa.Column("input_vintage_hi", sa.Date, nullable=False),  # max obs vintage used
        # Lineage: the observations this feature was computed from (CLAUDE.md #2).
        sa.Column(
            "input_observation_ids",
            postgresql.ARRAY(sa.BigInteger),
            nullable=False,
            server_default=sa.text("'{}'::bigint[]"),
        ),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "geography_id",
            "metric_id",
            "feature_type",
            "period",
            "transform_version",
            name="uq_feature_key",
        ),
        # Never a silent null: a missing value must be flagged insufficient.
        sa.CheckConstraint(
            "value IS NOT NULL OR insufficient_data = true",
            name="ck_feature_no_silent_null",
        ),
    )
    # Detector / cross-sectional scans over a metric+type for a period.
    op.create_index(
        "ix_feature_metric_type_period",
        "feature",
        ["metric_id", "feature_type", "period"],
    )

    # Feature is recomputable (not append-only): the engine upserts via the
    # unique key, so it needs INSERT + UPDATE (+ SELECT). No DELETE: stable ids
    # keep downstream feature_refs valid across recomputes.
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON feature TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE feature_id_seq TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("feature")
