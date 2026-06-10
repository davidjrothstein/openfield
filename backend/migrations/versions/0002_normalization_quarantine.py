"""normalization quarantine table for unmappable ingest rows.

Epic E2 / Story 2 — Normalization with quarantine. Unmappable geography,
unregistered metric, out-of-range value, or structural parse failure lands here
with a reason instead of being silently dropped (TDS §4.2, §6.2). The
application role gets SELECT + INSERT (it is written during normalization);
like ``observation`` it is never updated or deleted in normal operation.

Revision ID: 0002_normalization_quarantine
Revises: 0001_initial_observation_store
Create Date: 2026-06-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_normalization_quarantine"
down_revision: Union[str, None] = "0001_initial_observation_store"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "mip_app"


def upgrade() -> None:
    op.create_table(
        "normalization_quarantine",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "ingest_run_id",
            sa.BigInteger,
            sa.ForeignKey("ingestion_run.id"),
            nullable=False,
        ),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("source.id")),
        sa.Column("raw_geography", sa.Text),
        sa.Column("raw_metric", sa.Text),
        sa.Column("raw_period", sa.Text),
        sa.Column("raw_value", sa.Text),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_quarantine_run", "normalization_quarantine", ["ingest_run_id"]
    )

    # App role writes quarantine rows during normalization; append-only in spirit.
    op.execute(
        f"GRANT SELECT, INSERT ON normalization_quarantine TO {APP_ROLE}"
    )
    op.execute(
        "GRANT USAGE, SELECT ON SEQUENCE normalization_quarantine_id_seq "
        f"TO {APP_ROLE}"
    )


def downgrade() -> None:
    op.drop_table("normalization_quarantine")
