#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxt.data.schemas

Core columns every dataset of a kind must have, and the schema check used by
the downloader, the consolidator and the source-adapter tests.

    TICK_CORE   raw ticks (lake/raw interval=TICK, and the daily downloads)
    BAR_CORE    bars fxt computes (lake/derived)

Naming convention (on purpose, so a file's kind shows in its column names):
    camelCase   source-shaped data: downloads, and lake/raw (consolidated, unchanged)
    snake_case  anything fxt computes: lake/derived, research tables
A source that only provides bars keeps its own (camelCase) names in raw; the
step that turns them into derived bars renames them to BAR_CORE.

Rules
- A source adapter declares the full schema it writes per interval. It must
  *include* the core for that kind (extras allowed): check_schema(exact=False).
- Every daily file of one dataset (source, market, symbol, interval) has exactly
  the adapter's schema, and every file the consolidator merges matches the
  first: check_schema(exact=True).
- Derived code (bars, research) only relies on the core columns.

Ticks: dukascopy_python's names, `dtime` in ms. Bars: the bar builder's names,
`time` in us. Changing either means rebuilding every file of that kind.
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

from typing import Literal

import polars as pl

__all__ = [
    "Kind", "kind_of",
    "TICK_TIME", "TICK_CORE", "BAR_TIME", "BAR_SIDES", "BAR_OHLC", "BAR_CORE", "CORE",
    "check_schema", "empty_frame",
]

Kind = Literal["ticks", "bars"]


def kind_of(interval: str) -> Kind:
    """ "TICK" -> "ticks"; any bar interval ("1MIN", "1HOUR", ...) -> "bars". """
    return "ticks" if interval.upper() == "TICK" else "bars"


#!================================================================================(80)
#! core schemas
#!--------------------------------------------------------------------------------(80)
TICK_TIME = "dtime"
TICK_CORE = pl.Schema({
    TICK_TIME:   pl.Datetime("ms", "UTC"),
    "bidPrice":  pl.Float64(),
    "askPrice":  pl.Float64(),
    "bidVolume": pl.Float64(),
    "askVolume": pl.Float64(),
})

BAR_TIME = "time"                                  # bar open time
BAR_SIDES = ("bid", "ask", "mid")
BAR_OHLC = ("open", "high", "low", "close")
BAR_CORE = pl.Schema({
    BAR_TIME: pl.Datetime("us", "UTC"),
    **{f"{s}_{x}": pl.Float64() for s in BAR_SIDES for x in BAR_OHLC},
    "bid_volume":  pl.Float64(),
    "ask_volume":  pl.Float64(),
    "tick_count":  pl.UInt32(),
    "spread_mean": pl.Float64(),
    "spread_min":  pl.Float64(),
    "spread_max":  pl.Float64(),
})

CORE: dict[Kind, pl.Schema] = {"ticks": TICK_CORE, "bars": BAR_CORE}


#!================================================================================(80)
#! checks
#!--------------------------------------------------------------------------------(80)
def _dtype_str(t: pl.DataType) -> str:
    """ Strict dtype identity: polars treats Datetime("ms") as equal to
        Datetime("ms", "UTC") in some comparisons; the repr doesn't.
    """
    return repr(t)


def check_schema(actual: pl.Schema, expected: pl.Schema, *, exact: bool) -> list[str]:
    """ Problems found; empty list = OK.

        exact=True   same columns, same order, same dtypes (time unit + timezone
                     included). Daily file vs adapter schema; file vs file.
        exact=False  every expected column present with the same dtype; extra
                     columns and order don't matter. Adapter schema vs core.
    """
    problems: list[str] = []
    missing = [c for c in expected if c not in actual]
    if missing:
        problems.append(f"missing columns: {', '.join(missing)}")
    for col, want in expected.items():
        if col in actual and _dtype_str(actual[col]) != _dtype_str(want):
            problems.append(f"{col}: dtype {actual[col]!r}, expected {want!r}")
    if exact:
        extra = [c for c in actual if c not in expected]
        if extra:
            problems.append(f"extra columns: {', '.join(extra)}")
        if not missing and not extra and list(actual) != list(expected):
            problems.append(f"column order {list(actual)}, expected {list(expected)}")
    return problems


def empty_frame(schema: pl.Schema) -> pl.DataFrame:
    """ Zero rows, exactly `schema` (for tests and error paths). """
    return pl.DataFrame(schema=schema)
#-
