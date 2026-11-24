#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
Load meta models from the database.

Every loader follows the same shape:
    rows from the db -> dicts (nested lists attached) -> Model.model_validate -> Registry
Each registry is built once per process (cached).
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations
from pathlib import Path
from functools import cache
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict

#local
from .db import query
from .models import Interval, LakeRequirement, Market, Source, Symbol
from .registry import Registry, SymbolRegistry



#!================================================================================(80)
#! private
#!--------------------------------------------------------------------------------(80)


#!================================================================================(80)
#! main
#!--------------------------------------------------------------------------------(80)
@cache
def markets() -> Registry[str, Market]:
    """
    """
    rows = query("SELECT name FROM markets ORDER BY name")
    return Registry("market", {r["name"]: Market.model_validate(r) for r in rows})
#

@cache
def intervals() -> Registry[str, Interval]:
    """
    """
    rows = query("SELECT name, seconds FROM intervals ORDER BY seconds IS NOT NULL, seconds")
    return Registry("interval", {r["name"]: Interval.model_validate(r) for r in rows})
#

@cache
def symbols() -> SymbolRegistry:
    """
    """
    data: dict[tuple[str, str], dict[str, Any]] = {
        (r["market"], r["name"]): {**r, "aliases": []}
        for r in query("SELECT market, name FROM symbols ORDER BY market, name")
    }
    for r in query("SELECT market, name, alias FROM symbol_aliases ORDER BY alias"):
        data[(r["market"], r["name"])]["aliases"].append(r["alias"])

    return SymbolRegistry({key: Symbol.model_validate(d) for key, d in data.items()})
#

@cache
def sources() -> Registry[str, Source]:
    """
    """
    data: dict[str, dict[str, Any]] = {
        r["name"]: {**r, "symbols": [], "intervals": []}
        for r in query("SELECT name, website FROM sources ORDER BY name")
    }
    for r in query(
        "SELECT source, market, name, source_symbol FROM source_symbols "
        "ORDER BY source, market, name"
    ):
        source = r.pop("source")
        data[source]["symbols"].append(r)
    for r in query(
        "SELECT source, interval_name, source_interval FROM source_intervals "
        "ORDER BY source, interval_name"
    ):
        source = r.pop("source")
        data[source]["intervals"].append(r)

    return Registry("source", {name: Source.model_validate(d) for name, d in data.items()})


@cache
def lake_requirements() -> tuple[LakeRequirement, ...]:
    """ Every lake_requirements row, checked against the rest of refdata:
        a symbol row's symbol must be carried by its source, and a raw row's
        interval must be one the source provides.
    """
    rows = query(
        "SELECT source, market, symbol, tier, interval, first_year, last_year, required, notes "
        "FROM lake_requirements ORDER BY source, market, symbol IS NOT NULL, symbol, tier DESC, interval"
    )
    reqs = tuple(LakeRequirement.model_validate(r) for r in rows)
    srcs = sources()
    for r in reqs:
        src = srcs[r.source]
        if r.symbol is not None and not src.has_symbol(r.symbol, r.market):
            raise ValueError(f"lake_requirements: {r.source} doesn't carry {r.market}/{r.symbol}")
        if r.tier == "raw" and not src.has_interval(r.interval):
            raise ValueError(f"lake_requirements: {r.source} has no {r.interval} data (raw row)")
    return reqs


def merge_requirements(rows: Iterable[LakeRequirement], source: str, market: str,
                       symbol: str) -> dict[tuple[str, str], LakeRequirement]:
    """ Market-wide rows, updated by the symbol's own rows (keyed by (tier, interval));
        rows with required=0 then removed. Pure: works on any rows.
    """
    rows = list(rows)
    merged: dict[tuple[str, str], LakeRequirement] = {}
    for scope_symbol in (None, symbol):
        for r in rows:
            if (r.source, r.market, r.symbol) == (source, market, scope_symbol):
                merged[r.key] = r
    return {k: r for k, r in merged.items() if r.required}


def requirements_for(source: str, market: str, symbol: str) -> dict[tuple[str, str], LakeRequirement]:
    """ Merged requirements for one symbol from refdata (see merge_requirements). """
    return merge_requirements(lake_requirements(), source, market, symbol)


def required_datasets() -> dict[tuple[str, str, str], dict[tuple[str, str], LakeRequirement]]:
    """ (source, market, symbol) -> merged requirements, for every symbol any
        requirement applies to (market-wide rows cover all the source's symbols
        in that market). Symbols left with no requirements are omitted.
    """
    scopes = {(r.source, r.market) for r in lake_requirements()}
    out: dict[tuple[str, str, str], dict[tuple[str, str], LakeRequirement]] = {}
    for source, market in sorted(scopes):
        for e in sources()[source].symbols:
            if e.market != market:
                continue
            if reqs := requirements_for(source, market, e.name):
                out[(source, market, e.name)] = reqs
    return out


def clear_caches() -> None:
    """ Drop cached registries (and the db), e.g. after editing the SQL files 
        in a session.
    """
    from .db import meta_db

    for fn in (markets, intervals, symbols, sources, lake_requirements, meta_db):
        fn.cache_clear()



#!================================================================================(80)
#! gogogogog
#!--------------------------------------------------------------------------------(80)
if(__name__ == "__main__"):
    from rich import print

    print()
    print("# [bold green]gogogogogo[/]")

