"""Census Building Permits Survey fetcher (TDS §6.1).

This is the ONLY external data client in V1 (CLAUDE.md). It targets a *public*
Census endpoint — no credentials, no licensed vendor — so it does not breach the
licensed-data wall (invariant #6).

The client is an interface (`BpsClient`) with two implementations:

* `CensusBpsClient` — real HTTP fetch of the metro monthly file.
* `FixtureBpsClient` — returns a canned body, for offline dev and tests.

A client only *fetches bytes*; parsing and validation happen downstream, so a
source format change fails loudly at the parser rather than here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class BpsFetchResult:
    period_label: str  # 'YYYYMM'
    body: str
    # The vintage the source carries — when this release was published. For the
    # "current month" file this is the release date of that month's estimates.
    release_date: date


class BpsFetchError(RuntimeError):
    """Transient or permanent fetch failure (network, HTTP status, empty body)."""


class BpsClient(Protocol):
    def fetch(self, period: date) -> BpsFetchResult: ...


def _metro_filename(period: date) -> str:
    # ma<YY><MM>c.txt — metro, current-month estimates.
    return f"ma{period:%y%m}c.txt"


class CensusBpsClient:
    """Fetches the metro monthly permits file over HTTPS from census.gov."""

    BASE = "https://www2.census.gov/econ/bps/Metro"

    def __init__(self, *, base_url: str | None = None, timeout: float = 30.0):
        self.base_url = (base_url or self.BASE).rstrip("/")
        self.timeout = timeout

    def fetch(self, period: date) -> BpsFetchResult:
        url = f"{self.base_url}/{_metro_filename(period)}"
        req = Request(url, headers={"User-Agent": "mip-bps-ingest/1.0"})
        try:
            with urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 (public gov URL)
                body = resp.read().decode("latin-1")
        except (HTTPError, URLError, TimeoutError) as exc:
            raise BpsFetchError(f"fetch failed for {url}: {exc}") from exc
        if not body.strip():
            raise BpsFetchError(f"empty body for {url}")
        # The current-month file's release date is treated as the fetch period's
        # publication; callers may override with the official release calendar.
        return BpsFetchResult(period_label=f"{period:%Y%m}", body=body, release_date=date.today())


class FixtureBpsClient:
    """Returns canned bodies keyed by period label, for offline use and tests."""

    def __init__(self, bodies: dict[str, str], *, release_date: date | None = None):
        self._bodies = bodies
        self._release_date = release_date or date.today()

    def fetch(self, period: date) -> BpsFetchResult:
        label = f"{period:%Y%m}"
        if label not in self._bodies:
            raise BpsFetchError(f"no fixture body for period {label}")
        return BpsFetchResult(
            period_label=label, body=self._bodies[label], release_date=self._release_date
        )
