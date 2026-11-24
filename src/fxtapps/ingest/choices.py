#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxtapps.ingest.choices

Where each subcommand's choices come from:

    download                 refdata: what the source *can* provide
    consolidate / verify     the downloads folder: what's actually on disk,
                             limited to names refdata knows

All functions return official names, sorted.
Downloads layout (plain dirs for now):
    <downloads>/<source>/<market>/<SYMBOL>/<INTERVAL>/<YYYY>/<MM>/
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

import logging
from pathlib import Path

from fxt.data.refdata import sources

logger = logging.getLogger(__name__)

__all__ = [
    "refdata_sources", "source_markets", "source_intervals", "source_symbols",
    "downloaded_symbols", "downloaded_intervals", "downloaded_years",
]


#!================================================================================(80)
#! refdata
#!--------------------------------------------------------------------------------(80)
def refdata_sources() -> list[str]:
    return sorted(s.name for s in sources())

def source_markets(source: str) -> list[str]:
    return sorted({e.market for e in sources()[source].symbols})

def source_intervals(source: str) -> list[str]:
    return sorted(e.interval_name for e in sources()[source].intervals)

def source_symbols(source: str, market: str) -> list[str]:
    return sorted(e.name for e in sources()[source].symbols if e.market == market)


#!================================================================================(80)
#! downloads folder
#!--------------------------------------------------------------------------------(80)
def _subdirs(path: Path) -> list[str]:
    return sorted(p.name for p in path.iterdir() if p.is_dir()) if path.is_dir() else []


def downloaded_symbols(downloads: Path, source: str, market: str) -> list[str]:
    """ Symbol dirs on disk that refdata knows for this source + market. """
    known = set(source_symbols(source, market))
    found = _subdirs(downloads / source / market)
    unknown = sorted(set(found) - known)
    if unknown:
        logger.warning("ignoring symbol dirs refdata doesn't know: %s", ", ".join(unknown))
    return [s for s in found if s in known]


def downloaded_intervals(downloads: Path, source: str, market: str, symbols: list[str]) -> list[str]:
    """ Intervals present for at least one of `symbols`. """
    found: set[str] = set()
    for sym in symbols:
        found.update(_subdirs(downloads / source / market / sym))
    return sorted(found & set(source_intervals(source)))


def downloaded_years(downloads: Path, source: str, market: str, symbols: list[str],
                     interval: str) -> list[int]:
    """ Years present for at least one of `symbols` (union). """
    years: set[int] = set()
    for sym in symbols:
        years.update(int(y) for y in _subdirs(downloads / source / market / sym / interval)
                     if y.isdigit() and len(y) == 4)
    return sorted(years)
#-
