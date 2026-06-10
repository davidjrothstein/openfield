"""Raw payload landing (TDS §3.4, §6.3).

Every fetched payload is stored verbatim under a generated key before it is
parsed, so provenance is complete: observation → ingestion_run.raw_payload_key →
the stored envelope (what we fetched, when, and the vintage it carried). In
production this is S3 with versioning; for V1/local it is the filesystem behind
the same ``RawStore`` interface.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class RawPayload:
    """A landed payload plus the metadata normalization needs."""

    source_code: str
    period_label: str  # e.g. '202312'
    vintage: date  # when this data was published/known
    release_date: date
    parser_version: str
    body: str  # the raw file content, verbatim
    fetched_at: datetime

    def to_envelope(self) -> str:
        d = asdict(self)
        d["vintage"] = self.vintage.isoformat()
        d["release_date"] = self.release_date.isoformat()
        d["fetched_at"] = self.fetched_at.isoformat()
        return json.dumps(d)

    @staticmethod
    def from_envelope(s: str) -> "RawPayload":
        d = json.loads(s)
        return RawPayload(
            source_code=d["source_code"],
            period_label=d["period_label"],
            vintage=date.fromisoformat(d["vintage"]),
            release_date=date.fromisoformat(d["release_date"]),
            parser_version=d["parser_version"],
            body=d["body"],
            fetched_at=datetime.fromisoformat(d["fetched_at"]),
        )


class RawStore(Protocol):
    def put(self, key: str, payload: RawPayload) -> str: ...
    def get(self, key: str) -> RawPayload: ...


class LocalRawStore:
    """Filesystem-backed RawStore for V1/local and tests."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents and p != self.root.resolve():
            raise ValueError(f"key escapes store root: {key!r}")
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def put(self, key: str, payload: RawPayload) -> str:
        self._path(key).write_text(payload.to_envelope())
        return key

    def get(self, key: str) -> RawPayload:
        return RawPayload.from_envelope(self._path(key).read_text())


def make_key(source_code: str, period_label: str, fetched_at: datetime) -> str:
    """A stable-ish object key: source/period/timestamp."""
    ts = fetched_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{source_code}/{period_label}/{ts}.json"
