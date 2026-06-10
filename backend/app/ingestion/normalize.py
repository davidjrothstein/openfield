"""Normalization: raw BPS records → canonical observations, or quarantine.

Maps each parsed record to the registered metrics, resolving geography to a
canonical id and validating values. Anything unmappable or implausible is
*quarantined with a reason* (TDS §4.2, §6.2) — never silently dropped. Valid
rows are appended to ``observation`` with full provenance (run → file →
who/when). Commits use ``ON CONFLICT DO NOTHING`` so re-running the same period
is idempotent (no duplicate observations) and never needs UPDATE/DELETE — the
append-only grant suffices.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..models import Geography, IngestionRun, MetricSeries, NormalizationQuarantine, Observation, Source
from .parser import BpsParseError, BpsRecord, parse_bps_metro
from .raw_store import RawPayload, RawStore

log = logging.getLogger(__name__)

# A metro's monthly permitted unit count above this is implausible — quarantine
# rather than trust it (semantic validation, TDS §6.2).
VALUE_MAX = 1_000_000
MIN_YEAR = 1980

# Which registered metric each field of a BpsRecord feeds.
_METRIC_FIELDS = (
    ("permits_total_units", "total_units"),
    ("permits_5plus_units", "units_5plus"),
)


@dataclass
class NormalizeResult:
    run_id: int
    committed: int
    quarantined: int


def normalize_run(
    session: Session,
    *,
    run_id: int,
    payload: RawPayload | None = None,
    raw_store: RawStore | None = None,
) -> NormalizeResult:
    """Normalize a landed run. Provide ``payload`` directly, or a ``raw_store``
    to load it from the run's ``raw_payload_key``."""
    run = session.get(IngestionRun, run_id)
    if run is None:
        raise ValueError(f"no ingestion_run {run_id}")
    if payload is None:
        if raw_store is None or run.raw_payload_key is None:
            raise ValueError("need payload or raw_store + landed raw_payload_key")
        payload = raw_store.get(run.raw_payload_key)

    source = session.execute(
        select(Source).where(Source.code == payload.source_code)
    ).scalar_one()

    committed = 0
    quarantined = 0

    def quarantine(rec: BpsRecord | None, *, raw_metric: str | None, reason: str, raw_value=None) -> None:
        nonlocal quarantined
        session.add(
            NormalizationQuarantine(
                ingest_run_id=run_id,
                source_id=source.id,
                raw_geography=rec.cbsa_code if rec else None,
                raw_metric=raw_metric,
                raw_period=rec.period.isoformat() if rec else None,
                raw_value=None if raw_value is None else str(raw_value),
                reason=reason,
                payload=_record_payload(rec) if rec else None,
            )
        )
        quarantined += 1

    # Structural parse: a format change fails loudly; the whole file is
    # quarantined rather than producing partial/garbage observations.
    try:
        records = parse_bps_metro(payload.body)
    except BpsParseError as e:
        quarantine(None, raw_metric=None, reason=f"structural_parse_error: {e}")
        session.commit()
        log.warning("normalize run=%s structural parse error: %s", run_id, e)
        return NormalizeResult(run_id, 0, quarantined)

    # Metric registry + active-geography crosswalk (resolve to canonical ids).
    metric_ids = {
        code: session.execute(
            select(MetricSeries.id).where(MetricSeries.code == code)
        ).scalar_one()
        for code, _ in _METRIC_FIELDS
    }
    geo_by_cbsa = dict(
        session.execute(
            select(Geography.cbsa_code, Geography.id).where(
                Geography.geo_type == "metro", Geography.cbsa_code.isnot(None)
            )
        ).all()
    )

    for rec in records:
        geo_id = geo_by_cbsa.get(rec.cbsa_code)
        for metric_code, field in _METRIC_FIELDS:
            value = getattr(rec, field)
            if geo_id is None:
                quarantine(rec, raw_metric=metric_code, reason="unmapped_geography", raw_value=value)
                continue
            if not _period_ok(rec.period):
                quarantine(rec, raw_metric=metric_code, reason="period_out_of_range", raw_value=value)
                continue
            if value < 0 or value > VALUE_MAX:
                quarantine(rec, raw_metric=metric_code, reason="value_out_of_range", raw_value=value)
                continue

            stmt = (
                pg_insert(Observation)
                .values(
                    geography_id=geo_id,
                    metric_id=metric_ids[metric_code],
                    period=rec.period,
                    value=value,
                    vintage=payload.vintage,
                    release_date=payload.release_date,
                    source_id=source.id,
                    ingest_run_id=run_id,
                )
                .on_conflict_do_nothing(
                    constraint="uq_observation_geo_metric_period_vintage"
                )
            )
            result = session.execute(stmt)
            committed += result.rowcount or 0  # 0 when the vintage already existed

    session.commit()
    log.info(
        "normalize run=%s committed=%d quarantined=%d", run_id, committed, quarantined
    )
    return NormalizeResult(run_id, committed, quarantined)


def _period_ok(period: date) -> bool:
    return MIN_YEAR <= period.year <= date.today().year + 1


def _record_payload(rec: BpsRecord) -> dict:
    return {
        "cbsa_code": rec.cbsa_code,
        "cbsa_name": rec.cbsa_name,
        "period": rec.period.isoformat(),
        "total_units": rec.total_units,
        "units_5plus": rec.units_5plus,
    }
