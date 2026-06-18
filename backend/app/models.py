"""ORM models for the observation store and its registry tables (TDS §5.1).

These mirror the authoritative hand-written migration
``0001_initial_observation_store``. The migration — not autogenerate — is the
source of truth, because the invariant machinery (the restricted ``mip_app``
role, the grant set, and the point-in-time SQL function) cannot be expressed in
ORM metadata. The models exist so application code has typed access and so
Alembic can diff for accidental drift.

Keystone invariant (CLAUDE.md #1): ``observation`` is append-only. There is no
``UPDATE``/``DELETE`` path in code, and the runtime DB role is not granted those
privileges. Corrections are new vintages, never mutations.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Geography(Base):
    """Canonical geography. Metro-level in V1; ``parent_id`` keeps the schema
    submarket-ready (TDS §1.4) even though submarket data is not populated.

    ``is_active`` is the ~10-market V1 switch: the 100-MSA universe is a config
    list, so widening coverage is a data flip, not an architecture change
    (CLAUDE.md V1 scope)."""

    __tablename__ = "geography"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    geo_type: Mapped[str] = mapped_column(Text, nullable=False)  # 'metro' | 'submarket'
    cbsa_code: Mapped[str | None] = mapped_column(Text)  # Census CBSA code
    name: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("geography.id")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("geo_type", "cbsa_code", name="uq_geography_type_cbsa"),
        CheckConstraint(
            "geo_type IN ('metro','submarket')", name="ck_geography_geo_type"
        ),
    )


class Source(Base):
    """A provenance origin for observations (TDS §4.1, §6.3, §7.4).

    ``retrieval_method`` records *how* data lawfully entered — public ``api`` or
    analyst ``upload``. ``retention_policy`` is the per-source raw-vs-derived
    flag (TDS §7.4) so the unresolved licensed-storage legal decision never
    blocks the build; public sources default to ``retain_raw``."""

    __tablename__ = "source"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    publisher: Mapped[str | None] = mapped_column(Text)
    retrieval_method: Mapped[str] = mapped_column(Text, nullable=False)
    license_terms: Mapped[str | None] = mapped_column(Text)
    retention_policy: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="retain_raw"
    )
    url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "retrieval_method IN ('api','analyst_upload','file')",
            name="ck_source_retrieval_method",
        ),
        CheckConstraint(
            "retention_policy IN ('retain_raw','derived_only')",
            name="ck_source_retention_policy",
        ),
    )


class MetricSeries(Base):
    """The metric registry. ``metric_id`` everything downstream references
    (TDS §4.2). ``domain`` ties a metric to one of the four convergence domains;
    ``frequency`` is the expected cadence used by the freshness scan (TDS §6.4)."""

    __tablename__ = "metric_series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str | None] = mapped_column(Text)
    frequency: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("source.id")
    )
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "domain IN ('economy','supply','operator','capital')",
            name="ck_metric_series_domain",
        ),
        CheckConstraint(
            "frequency IN ('monthly','quarterly','annual')",
            name="ck_metric_series_frequency",
        ),
    )


class IngestionRun(Base):
    """One atomic fetch/upload run (TDS §4.1, §6.1). Every observation points at
    a run, which points at a stored payload/fetch record — so provenance is
    complete (run → file → who/when/whence)."""

    __tablename__ = "ingestion_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("source.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="running"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_payload_key: Mapped[str | None] = mapped_column(Text)  # object-storage key
    row_count: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('running','succeeded','failed')",
            name="ck_ingestion_run_status",
        ),
    )


class Observation(Base):
    """The keystone, append-only, vintaged source of truth (TDS §5.1).

    Append-only mechanics: ``(geography_id, metric_id, period, vintage)`` is
    unique. A revision is a *new row with a later vintage*; prior vintages are
    never mutated. A point-in-time read takes the greatest ``vintage`` ≤ an
    as-of date (see ``app.observations`` / the ``observation_as_of`` SQL
    function). No UPDATE/DELETE grant exists for the application role."""

    __tablename__ = "observation"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    geography_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("geography.id"), nullable=False
    )
    metric_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("metric_series.id"), nullable=False
    )
    period: Mapped[date] = mapped_column(Date, nullable=False)  # period described
    value: Mapped[float] = mapped_column(Numeric, nullable=False)
    vintage: Mapped[date] = mapped_column(Date, nullable=False)  # when known/published
    release_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("source.id"), nullable=False
    )
    ingest_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingestion_run.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "geography_id",
            "metric_id",
            "period",
            "vintage",
            name="uq_observation_geo_metric_period_vintage",
        ),
        # Point-in-time lookup: greatest vintage <= as-of per (geo, metric, period).
        Index(
            "ix_observation_pit",
            "geography_id",
            "metric_id",
            "period",
            text("vintage DESC"),
        ),
        # Lineage / provenance and feature-engine scans.
        Index("ix_observation_ingest_run", "ingest_run_id"),
        Index("ix_observation_source", "source_id"),
        Index("ix_observation_metric_period", "metric_id", "period"),
    )


class Feature(Base):
    """Derived, versioned, recomputable detector input (TDS §5.2).

    Not append-only — the recompute pass rewrites features idempotently — but
    lineage is mandatory: ``input_observation_ids`` are array refs to the
    observations the feature was computed from (CLAUDE.md #2). ``insufficient_data``
    is never null and a null ``value`` must be flagged insufficient (the engine
    never fabricates a value for a thin window)."""

    __tablename__ = "feature"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    geography_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("geography.id"), nullable=False
    )
    metric_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("metric_series.id"), nullable=False
    )
    feature_type: Mapped[str] = mapped_column(Text, nullable=False)
    period: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[float | None] = mapped_column(Numeric)
    insufficient_data: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    transform_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_vintage_hi: Mapped[date] = mapped_column(Date, nullable=False)
    input_observation_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger), nullable=False, server_default=text("'{}'::bigint[]")
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "geography_id",
            "metric_id",
            "feature_type",
            "period",
            "transform_version",
            name="uq_feature_key",
        ),
        CheckConstraint(
            "value IS NOT NULL OR insufficient_data = true",
            name="ck_feature_no_silent_null",
        ),
        Index(
            "ix_feature_metric_type_period",
            "metric_id",
            "feature_type",
            "period",
        ),
    )


class Signal(Base):
    """Derived, append-only, superseding detector output (TDS §5.3, §9).

    A re-fire supersedes its predecessor via ``superseded_by`` (the old row
    persists, never deleted). Salience decays at read time as a function of
    ``as_of`` age — never a stored mutation. Lineage: ``feature_refs`` are array
    refs to the features the detector consumed. Single-signal confidence excludes
    corroboration by design (TDS §9.3), so a leading-domain signal is never
    down-weighted merely for lacking it."""

    __tablename__ = "signal"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    geography_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("geography.id"), nullable=False
    )
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    detector: Mapped[str] = mapped_column(Text, nullable=False)
    detector_version: Mapped[str] = mapped_column(Text, nullable=False)
    metric_ref: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("metric_series.id")
    )
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    magnitude: Mapped[float | None] = mapped_column(Numeric)
    confidence: Mapped[str] = mapped_column(Text, nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    feature_refs: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), nullable=False)
    superseded_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("signal.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "domain IN ('economy','supply','operator','capital')",
            name="ck_signal_domain",
        ),
        CheckConstraint(
            "direction IN ('improving','deteriorating','neutral')",
            name="ck_signal_direction",
        ),
        CheckConstraint(
            "confidence IN ('high','moderate','low')", name="ck_signal_confidence"
        ),
        Index(
            "ix_signal_live",
            "geography_id",
            "domain",
            postgresql_where=text("superseded_by IS NULL"),
        ),
        Index(
            "ix_signal_detector_key",
            "detector",
            "geography_id",
            "metric_ref",
            postgresql_where=text("superseded_by IS NULL"),
        ),
    )


class NormalizationQuarantine(Base):
    """Rows that could not be safely mapped to a canonical observation (TDS §4.2,
    §6.2). Normalization *quarantines with a reason* — it never silently drops.
    The offending raw record is retained for review and reprocessing."""

    __tablename__ = "normalization_quarantine"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ingest_run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingestion_run.id"), nullable=False
    )
    source_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("source.id"))
    raw_geography: Mapped[str | None] = mapped_column(Text)
    raw_metric: Mapped[str | None] = mapped_column(Text)
    raw_period: Mapped[str | None] = mapped_column(Text)
    raw_value: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_quarantine_run", "ingest_run_id"),
    )


class Thesis(Base):
    """The mutable head of a conviction (TDS §5.4, §12.1). Every change appends a
    ``ThesisVersion`` so the head stays current while the history stays
    immutable. Status flows draft → active → under_review → closed."""

    __tablename__ = "thesis"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    geography_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("geography.id"), nullable=False
    )
    owner: Mapped[str] = mapped_column(Text, nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    conviction: Mapped[str] = mapped_column(Text, nullable=False)
    horizon: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','active','under_review','closed')", name="ck_thesis_status"
        ),
        CheckConstraint(
            "conviction IN ('low','medium','high')", name="ck_thesis_conviction"
        ),
    )


class ThesisVersion(Base):
    """Append-only thesis history — the audit trail (TDS §12.4). One row per
    change, never overwritten."""

    __tablename__ = "thesis_version"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    thesis_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("thesis.id"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    claim: Mapped[str | None] = mapped_column(Text)
    conviction: Mapped[str | None] = mapped_column(Text)
    horizon: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("thesis_id", "version_no", name="uq_thesis_version_no"),
    )


class Assumption(Base):
    """A load-bearing assumption with a pre-committed kill-criterion (TDS §12.2).

    Binding is a stored predicate (``supporting_signal_query``), not a static FK,
    so newly emitted signals are evaluated automatically on every run.
    Per-assumption state machine: intact → watch → challenged → broken."""

    __tablename__ = "assumption"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    thesis_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("thesis.id"), nullable=False
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_signal_query: Mapped[dict] = mapped_column(JSONB, nullable=False)
    invalidation_threshold: Mapped[dict] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="intact")
    needs_response: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    state_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "state IN ('intact','watch','challenged','broken')", name="ck_assumption_state"
        ),
        Index("ix_assumption_thesis", "thesis_id"),
    )


class ThesisEvent(Base):
    """State transitions, owner alerts, and analyst responses — the audit trail
    and (until E10) the in-app alert feed (TDS §12.4)."""

    __tablename__ = "thesis_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    thesis_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("thesis.id"), nullable=False
    )
    assumption_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("assumption.id")
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    from_state: Mapped[str | None] = mapped_column(Text)
    to_state: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text)
    signal_refs: Mapped[list[int] | None] = mapped_column(ARRAY(BigInteger))
    actor: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('state_change','alert','response')", name="ck_thesis_event_type"
        ),
        Index("ix_thesis_event_thesis", "thesis_id", "created_at"),
    )


class ConvergenceAssessment(Base):
    """Per-domain stance matrix — the intellectual core (TDS §10).

    ``per_domain_stance`` is JSONB with four keys (economy/supply/operator/
    capital), each ``{stance, confidence, contributing_signal_ids}``. There is
    deliberately NO scalar field — nothing reduces this to a single number. A
    domain with no fresh signals reads ``no_read`` (distinct from ``neutral``).
    Recomputed per run, retained with ``as_of``."""

    __tablename__ = "convergence_assessment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    geography_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("geography.id"), nullable=False
    )
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    per_domain_stance: Mapped[dict] = mapped_column(JSONB, nullable=False)
    breadth: Mapped[int] = mapped_column(Integer, nullable=False)
    coherence: Mapped[str] = mapped_column(Text, nullable=False)
    weakest_data_flag: Mapped[str | None] = mapped_column(Text)
    synthesis_text: Mapped[str | None] = mapped_column(Text)
    transform_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "geography_id", "as_of", "transform_version", name="uq_convergence_key"
        ),
        CheckConstraint("breadth BETWEEN 0 AND 4", name="ck_convergence_breadth"),
        CheckConstraint(
            "coherence IN ('yes','partial','no')", name="ck_convergence_coherence"
        ),
        Index("ix_convergence_geo_asof", "geography_id", "as_of"),
    )


class RegimeProposal(Base):
    """Engine-proposed regime awaiting human confirmation (TDS §11.2). The 90-day
    rule engine writes here; nothing is asserted until a principal confirms."""

    __tablename__ = "regime_proposal"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    geography_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("geography.id"), nullable=False
    )
    regime_type: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_refs: Mapped[dict | None] = mapped_column(JSONB)
    confidence: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','confirmed','rejected')", name="ck_regime_proposal_status"
        ),
    )


class Regime(Base):
    """A versioned, time-bounded regime assertion (TDS §11.3). ``assigned_by`` is
    NOT NULL — no regime exists without a human action (manual tag or a confirmed
    proposal). Transitions preserve the prior row via ``superseded_by``."""

    __tablename__ = "regime"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    geography_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("geography.id"), nullable=False
    )
    regime_type: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    evidence_refs: Mapped[dict | None] = mapped_column(JSONB)
    confidence: Mapped[str | None] = mapped_column(Text)
    assigned_by: Mapped[str] = mapped_column(Text, nullable=False)
    source_proposal_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("regime_proposal.id")
    )
    superseded_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("regime.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_regime_current",
            "geography_id",
            postgresql_where=text("effective_to IS NULL"),
        ),
    )


class DataFreshness(Base):
    """Per (geography, metric) freshness read model (TDS §6.4). Computed centrally
    so every aggregate can show the freshness of its weakest input. Upserted each
    scan; not append-only."""

    __tablename__ = "data_freshness"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    geography_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("geography.id"), nullable=False
    )
    metric_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("metric_series.id"), nullable=False
    )
    latest_period: Mapped[date | None] = mapped_column(Date)
    latest_vintage: Mapped[date | None] = mapped_column(Date)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    age_days: Mapped[int | None] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("geography_id", "metric_id", name="uq_freshness_geo_metric"),
        CheckConstraint(
            "state IN ('fresh','aging','stale','no_data')", name="ck_freshness_state"
        ),
    )


class Notification(Base):
    """In-app review list (E10.3). Deduplicated by ``dedup_key`` (type, target,
    period) so a flapping signal does not spam the analyst. No email/escalation
    in V1."""

    __tablename__ = "notification"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    recipient: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    thesis_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("thesis.id"))
    assumption_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("assumption.id")
    )
    signal_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("signal.id"))
    dedup_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('thesis_invalidation','signal')", name="ck_notification_kind"
        ),
        Index("ix_notification_recipient", "recipient", "read", "created_at"),
    )
