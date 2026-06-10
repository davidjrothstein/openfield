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
