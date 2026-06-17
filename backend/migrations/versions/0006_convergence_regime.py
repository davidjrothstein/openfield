"""convergence_assessment + regime + regime_proposal.

Epic E5 (TDS §5.4, §10, §11).

convergence_assessment — per-domain stance (JSONB, four domains, each with
stance + confidence + contributing_signal_ids), breadth (0–4), coherence enum,
weakest_data_flag, and a deterministic synthesis sentence. There is deliberately
NO scalar field: nothing reduces the assessment to a single number (CLAUDE.md,
PRD/TDS §10.4). Recomputed per run, retained with as_of.

regime / regime_proposal — regimes are versioned and time-bounded and are never
asserted without a human action: ``regime.assigned_by`` is NOT NULL. The 90-day
rule engine writes only ``regime_proposal`` (pending); confirmation copies a
proposal into ``regime`` with assigned_by = the confirming user. The 60-day path
is a manual analyst tag, which is itself the human action. Transitions preserve
the prior row via ``superseded_by`` (never overwritten).

Revision ID: 0006_convergence_regime
Revises: 0005_thesis
Create Date: 2026-06-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_convergence_regime"
down_revision: Union[str, None] = "0005_thesis"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "mip_app"

_REGIMES = (
    "expansion",
    "oversupply_digestion",
    "late_cycle_topping",
    "recovery",
    "structural_decline",
)
_REGIME_CHECK = "regime_type IN (" + ",".join(f"'{r}'" for r in _REGIMES) + ")"


def upgrade() -> None:
    op.create_table(
        "convergence_assessment",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("geography_id", sa.BigInteger, sa.ForeignKey("geography.id"), nullable=False),
        sa.Column("as_of", sa.Date, nullable=False),
        # {economy|supply|operator|capital: {stance, confidence, contributing_signal_ids}}
        sa.Column("per_domain_stance", postgresql.JSONB, nullable=False),
        sa.Column("breadth", sa.Integer, nullable=False),
        sa.Column("coherence", sa.Text, nullable=False),
        sa.Column("weakest_data_flag", sa.Text),
        # Deterministic template sentence; FK-to-narration is a 90-day refinement.
        sa.Column("synthesis_text", sa.Text),
        sa.Column("transform_version", sa.Text, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.UniqueConstraint(
            "geography_id", "as_of", "transform_version", name="uq_convergence_key"
        ),
        sa.CheckConstraint("breadth BETWEEN 0 AND 4", name="ck_convergence_breadth"),
        sa.CheckConstraint("coherence IN ('yes','partial','no')", name="ck_convergence_coherence"),
    )
    op.create_index(
        "ix_convergence_geo_asof", "convergence_assessment", ["geography_id", "as_of"]
    )

    op.create_table(
        "regime_proposal",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("geography_id", sa.BigInteger, sa.ForeignKey("geography.id"), nullable=False),
        sa.Column("regime_type", sa.Text, nullable=False),
        sa.Column("evidence_refs", postgresql.JSONB),
        sa.Column("confidence", sa.Text),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'pending'")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.CheckConstraint(_REGIME_CHECK, name="ck_regime_proposal_type"),
        sa.CheckConstraint(
            "status IN ('pending','confirmed','rejected')", name="ck_regime_proposal_status"
        ),
    )

    op.create_table(
        "regime",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("geography_id", sa.BigInteger, sa.ForeignKey("geography.id"), nullable=False),
        sa.Column("regime_type", sa.Text, nullable=False),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date),  # null = current
        sa.Column("evidence_refs", postgresql.JSONB),
        sa.Column("confidence", sa.Text),
        # The human who asserted it — NOT NULL: no regime without a human action.
        sa.Column("assigned_by", sa.Text, nullable=False),
        sa.Column("source_proposal_id", sa.BigInteger, sa.ForeignKey("regime_proposal.id")),
        sa.Column("superseded_by", sa.BigInteger, sa.ForeignKey("regime.id")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.CheckConstraint(_REGIME_CHECK, name="ck_regime_type"),
    )
    op.create_index(
        "ix_regime_current",
        "regime",
        ["geography_id"],
        postgresql_where=sa.text("effective_to IS NULL"),
    )

    op.execute(f"GRANT SELECT, INSERT, UPDATE ON convergence_assessment TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON regime TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON regime_proposal TO {APP_ROLE}")
    for seq in (
        "convergence_assessment_id_seq",
        "regime_id_seq",
        "regime_proposal_id_seq",
    ):
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {seq} TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("regime")
    op.drop_table("regime_proposal")
    op.drop_table("convergence_assessment")
