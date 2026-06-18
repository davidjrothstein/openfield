"""signal table: derived, append-only, superseding detector output.

Epic E4 / Story 1 — Signal table, decay, supersede, dedup (TDS §5.3, §9).

Signals are derived from features and append-only: a re-fire supersedes its
predecessor via ``superseded_by`` (the predecessor row persists, never deleted).
The app role therefore gets INSERT + SELECT + UPDATE — UPDATE only to set
``superseded_by`` — but no DELETE. Salience decay is a read-time function of
``as_of`` age (TDS §9.2), never a stored mutation. Lineage is mandatory:
``feature_refs`` are array refs to the feature rows that produced the signal.

"One live signal per (detector, geography, metric)" is maintained by the engine
(insert new, then point the old row's ``superseded_by`` at it) and verified by
the lineage integrity check, rather than a partial unique index — a DB
constraint would reject the transient two-live state during a supersede.

Revision ID: 0004_signal
Revises: 0003_feature
Create Date: 2026-06-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_signal"
down_revision: Union[str, None] = "0003_feature"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "mip_app"


def upgrade() -> None:
    op.create_table(
        "signal",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "geography_id", sa.BigInteger, sa.ForeignKey("geography.id"), nullable=False
        ),
        sa.Column("domain", sa.Text, nullable=False),  # economy|supply|operator|capital
        sa.Column("detector", sa.Text, nullable=False),  # threshold|trend_break
        sa.Column("detector_version", sa.Text, nullable=False),
        sa.Column("metric_ref", sa.Integer, sa.ForeignKey("metric_series.id")),
        sa.Column("direction", sa.Text, nullable=False),  # improving|deteriorating|neutral
        sa.Column("magnitude", sa.Numeric),
        sa.Column("confidence", sa.Text, nullable=False),  # high|moderate|low
        sa.Column("as_of", sa.Date, nullable=False),  # date of the evidence
        sa.Column(
            "feature_refs",
            postgresql.ARRAY(sa.BigInteger),
            nullable=False,  # lineage to feature rows
        ),
        sa.Column("superseded_by", sa.BigInteger, sa.ForeignKey("signal.id")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "domain IN ('economy','supply','operator','capital')",
            name="ck_signal_domain",
        ),
        sa.CheckConstraint(
            "direction IN ('improving','deteriorating','neutral')",
            name="ck_signal_direction",
        ),
        sa.CheckConstraint(
            "confidence IN ('high','moderate','low')", name="ck_signal_confidence"
        ),
    )
    # Read path: the live signals for a market (decay/convergence read these).
    op.create_index(
        "ix_signal_live",
        "signal",
        ["geography_id", "domain"],
        postgresql_where=sa.text("superseded_by IS NULL"),
    )
    # Dedup lookup: the current live signal for a (detector, geo, metric).
    op.create_index(
        "ix_signal_detector_key",
        "signal",
        ["detector", "geography_id", "metric_ref"],
        postgresql_where=sa.text("superseded_by IS NULL"),
    )

    # Append-only-with-supersede: INSERT + SELECT + UPDATE (superseded_by only),
    # never DELETE.
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON signal TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE signal_id_seq TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("signal")
