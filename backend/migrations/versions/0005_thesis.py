"""thesis system: thesis (head) + thesis_version (history) + assumption +
thesis_event.

Epic E6 — the 60-day validation milestone (TDS §5.4, §12).

* ``thesis`` is the mutable head (claim, conviction, horizon, status).
* ``thesis_version`` is the append-only audit history — one row per change with
  author + timestamp + rationale. "What did we believe, when, why."
* ``assumption`` binds to signals via a stored predicate (JSONB), NOT a static
  FK, so newly emitted signals are evaluated automatically. It carries the
  analyst's pre-committed ``invalidation_threshold`` and a per-assumption state
  machine (intact → watch → challenged → broken).
* ``thesis_event`` records state transitions, owner alerts, and analyst
  responses — the audit trail and (until E10's notification table) the in-app
  alert feed.

App-role grants: human + engine writes only. thesis/assumption are updatable
(head + state); thesis_version/thesis_event are append-only (INSERT+SELECT). No
DELETE anywhere. The AI role (E9) is never granted any of these.

Revision ID: 0005_thesis
Revises: 0004_signal
Create Date: 2026-06-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_thesis"
down_revision: Union[str, None] = "0004_signal"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "mip_app"


def upgrade() -> None:
    op.create_table(
        "thesis",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "geography_id", sa.BigInteger, sa.ForeignKey("geography.id"), nullable=False
        ),
        sa.Column("owner", sa.Text, nullable=False),
        sa.Column("claim", sa.Text, nullable=False),
        sa.Column("conviction", sa.Text, nullable=False),
        sa.Column("horizon", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'draft'")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.CheckConstraint(
            "status IN ('draft','active','under_review','closed')", name="ck_thesis_status"
        ),
        sa.CheckConstraint(
            "conviction IN ('low','medium','high')", name="ck_thesis_conviction"
        ),
    )

    op.create_table(
        "thesis_version",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("thesis_id", sa.BigInteger, sa.ForeignKey("thesis.id"), nullable=False),
        sa.Column("version_no", sa.Integer, nullable=False),
        sa.Column("claim", sa.Text),
        sa.Column("conviction", sa.Text),
        sa.Column("horizon", sa.Text),
        sa.Column("status", sa.Text),
        sa.Column("author", sa.Text, nullable=False),
        sa.Column("rationale", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.UniqueConstraint("thesis_id", "version_no", name="uq_thesis_version_no"),
    )

    op.create_table(
        "assumption",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("thesis_id", sa.BigInteger, sa.ForeignKey("thesis.id"), nullable=False),
        sa.Column("statement", sa.Text, nullable=False),
        # Stored predicate (domain/metric/direction), not a static FK to signals.
        sa.Column("supporting_signal_query", postgresql.JSONB, nullable=False),
        # Pre-committed kill-criterion.
        sa.Column("invalidation_threshold", postgresql.JSONB, nullable=False),
        sa.Column("state", sa.Text, nullable=False, server_default=sa.text("'intact'")),
        sa.Column("needs_response", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("state_changed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.CheckConstraint(
            "state IN ('intact','watch','challenged','broken')", name="ck_assumption_state"
        ),
    )
    op.create_index("ix_assumption_thesis", "assumption", ["thesis_id"])

    op.create_table(
        "thesis_event",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("thesis_id", sa.BigInteger, sa.ForeignKey("thesis.id"), nullable=False),
        sa.Column("assumption_id", sa.BigInteger, sa.ForeignKey("assumption.id")),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("from_state", sa.Text),
        sa.Column("to_state", sa.Text),
        sa.Column("detail", sa.Text),
        sa.Column("signal_refs", postgresql.ARRAY(sa.BigInteger)),
        sa.Column("actor", sa.Text),  # set for analyst responses; null for system events
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.CheckConstraint(
            "event_type IN ('state_change','alert','response')", name="ck_thesis_event_type"
        ),
    )
    op.create_index("ix_thesis_event_thesis", "thesis_event", ["thesis_id", "created_at"])

    # thesis + assumption: human/engine updatable head + state (no DELETE).
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON thesis TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON assumption TO {APP_ROLE}")
    # thesis_version + thesis_event: append-only audit.
    op.execute(f"GRANT SELECT, INSERT ON thesis_version TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON thesis_event TO {APP_ROLE}")
    for seq in ("thesis_id_seq", "thesis_version_id_seq", "assumption_id_seq", "thesis_event_id_seq"):
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {seq} TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("thesis_event")
    op.drop_table("assumption")
    op.drop_table("thesis_version")
    op.drop_table("thesis")
