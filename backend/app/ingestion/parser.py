"""Deterministic, versioned parser for the Census BPS metro file format.

Schema evolution (TDS §6.2): the parser is pinned to a known report layout via
``PARSER_VERSION``. A format change fails structural validation *loudly* rather
than corrupting data — a malformed row raises ``BpsParseError`` and the fetch
run is quarantined/failed, never silently coerced.

Target layout — the Census Building Permits Survey "metro, current month" file
(``https://www2.census.gov/econ/bps/Metro/ma<YY><MM>c.txt``). After a 2-line
header, each data row is comma-separated:

    0  Date (YYYYMM)         8  2-units Value
    1  CBSA code             9  3-4 units Bldgs
    2  CBSA name            10  3-4 units Units
    3  1-unit Bldgs         11  3-4 units Value
    4  1-unit Units         12  5+ units Bldgs
    5  1-unit Value         13  5+ units Units
    6  2-units Bldgs        14  5+ units Value
    7  2-units Units

We keep the two metrics V1 registered: total units authorized (sum of the four
unit columns) and units in 5+-unit structures (the multifamily series).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date

PARSER_VERSION = "bps_metro_monthly_v1"

# Column indices in the pinned layout.
_COL_DATE = 0
_COL_CBSA = 1
_COL_NAME = 2
_UNIT_COLS = (4, 7, 10, 13)  # 1-unit, 2-units, 3-4 units, 5+ units (Units)
_COL_5PLUS = 13
_MIN_COLS = 14


class BpsParseError(ValueError):
    """Raised on structurally invalid BPS content (wrong shape / unparseable)."""


@dataclass(frozen=True)
class BpsRecord:
    cbsa_code: str
    cbsa_name: str
    period: date
    total_units: int
    units_5plus: int


def _parse_period(raw: str) -> date:
    raw = raw.strip()
    if len(raw) != 6 or not raw.isdigit():
        raise BpsParseError(f"unparseable period {raw!r} (expected YYYYMM)")
    year, month = int(raw[:4]), int(raw[4:6])
    if not (1 <= month <= 12):
        raise BpsParseError(f"period month out of range in {raw!r}")
    return date(year, month, 1)


def _parse_int(raw: str, *, field: str, row_no: int) -> int:
    raw = raw.strip()
    if raw == "":
        return 0
    try:
        return int(float(raw))  # BPS values are integers; tolerate "12.0"
    except ValueError as exc:
        raise BpsParseError(f"row {row_no}: non-numeric {field} {raw!r}") from exc


def parse_bps_metro(text: str, *, header_rows: int = 2) -> list[BpsRecord]:
    """Parse a Census BPS metro file body into structured records.

    Raises ``BpsParseError`` on any structurally invalid row — schema drift is
    surfaced, not coerced. Semantic validation (value ranges, geography
    resolvability) happens later, in normalization."""
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    data_rows = rows[header_rows:]
    if not data_rows:
        raise BpsParseError("no data rows after header")

    records: list[BpsRecord] = []
    for i, row in enumerate(data_rows, start=header_rows + 1):
        if len(row) < _MIN_COLS:
            raise BpsParseError(
                f"row {i}: expected >= {_MIN_COLS} columns, got {len(row)}"
            )
        cbsa = row[_COL_CBSA].strip()
        if not cbsa:
            raise BpsParseError(f"row {i}: missing CBSA code")
        period = _parse_period(row[_COL_DATE])
        total = sum(
            _parse_int(row[c], field=f"units[{c}]", row_no=i) for c in _UNIT_COLS
        )
        five_plus = _parse_int(row[_COL_5PLUS], field="5+ units", row_no=i)
        records.append(
            BpsRecord(
                cbsa_code=cbsa,
                cbsa_name=row[_COL_NAME].strip(),
                period=period,
                total_units=total,
                units_5plus=five_plus,
            )
        )
    return records
