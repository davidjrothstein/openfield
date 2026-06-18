"""data_freshness + notification (E10 — background jobs & notifications).

data_freshness — a read model (TDS §6.4): per (geography, metric), the latest
observed period/vintage and a fresh/aging/stale state vs the metric's expected
cadence, computed centrally so every aggregate can display the freshness of its
weakest input. Upserted each scan.

notification — the in-app review list (E10.3). Deduplicated by ``dedup_key``
(type, target, period) so a flapping signal does not spam the analyst. No email,
no escalation in V1.

Both are derived/operational read models: app role gets INSERT/SELECT/UPDATE
(upsert + mark-read), no DELETE.

Revision ID: 0007_freshness_notification
Revises: 0006_convergence_regime
Create Date: 2026-06-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_freshness_notification"
down_revision: Union[str, None] = "0006_convergence_regime"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "mip_app"


def upgrade() -> None:
    op.create_table(
        "data_freshness",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("geography_id", sa.BigInteger, sa.ForeignKey("geography.id"), nullable=False),
        sa.Column("metric_id", sa.Integer, sa.ForeignKey("metric_series.id"), nullable=False),
        sa.Column("latest_period", sa.Date),
        sa.Column("latest_vintage", sa.Date),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("age_days", sa.Integer),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.UniqueConstraint("geography_id", "metric_id", name="uq_freshness_geo_metric"),
        sa.CheckConstraint(
            "state IN ('fresh','aging','stale','no_data')", name="ck_freshness_state"
        ),
    )

    op.create_table(
        "notification",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("recipient", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("body", sa.Text),
        sa.Column("thesis_id", sa.BigInteger, sa.ForeignKey("thesis.id")),
        sa.Column("assumption_id", sa.BigInteger, sa.ForeignKey("assumption.id")),
        sa.Column("signal_id", sa.BigInteger, sa.ForeignKey("signal.id")),
        sa.Column("dedup_key", sa.Text, nullable=False),
        sa.Column("read", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.UniqueConstraint("dedup_key", name="uq_notification_dedup"),
        sa.CheckConstraint(
            "kind IN ('thesis_invalidation','signal')", name="ck_notification_kind"
        ),
    )
    op.create_index(
        "ix_notification_recipient", "notification", ["recipient", "read", "created_at"]
    )

    op.execute(f"GRANT SELECT, INSERT, UPDATE ON data_freshness TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON notification TO {APP_ROLE}")
    for seq in ("data_freshness_id_seq", "notification_id_seq"):
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {seq} TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("notification")
    op.drop_table("data_freshness")
