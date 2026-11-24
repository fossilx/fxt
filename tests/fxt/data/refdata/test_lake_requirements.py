from __future__ import annotations

from fxt.data.refdata import (
    LakeRequirement, lake_requirements, merge_requirements, required_datasets, sources,
)


def R(**kw) -> LakeRequirement:
    base = dict(source="dukascopy", market="forex", symbol=None, tier="derived", interval="1HOUR")
    return LakeRequirement(**{**base, **kw})


def test_seed_covers_every_forex_pair():
    ds = required_datasets()
    n_pairs = sum(1 for e in sources()["dukascopy"].symbols if e.market == "forex")
    assert len(ds) == n_pairs == 28
    reqs = ds[("dukascopy", "forex", "EURJPY")]
    assert set(reqs) == {("raw", "TICK"), ("derived", "1MIN"), ("derived", "1HOUR")}
    assert reqs[("raw", "TICK")].first_year == 2013
    assert all(r.symbol is None for r in lake_requirements())     # seed: market-wide rows only


def test_symbol_rows_override_add_and_cancel():
    rows = [
        R(tier="raw", interval="TICK", first_year=2013),
        R(interval="1MIN"),
        R(interval="1HOUR"),
        R(symbol="GBPJPY", tier="raw", interval="TICK", first_year=2016),      # override
        R(symbol="GBPJPY", interval="1HOUR", required=False),                   # cancel
        R(symbol="EURJPY", tier="raw", interval="1MIN", first_year=2010),       # add
    ]
    g = merge_requirements(rows, "dukascopy", "forex", "GBPJPY")
    assert set(g) == {("raw", "TICK"), ("derived", "1MIN")}
    assert g[("raw", "TICK")].first_year == 2016 and g[("raw", "TICK")].symbol == "GBPJPY"

    e = merge_requirements(rows, "dukascopy", "forex", "EURJPY")
    assert set(e) == {("raw", "TICK"), ("raw", "1MIN"), ("derived", "1MIN"), ("derived", "1HOUR")}
    assert e[("raw", "TICK")].first_year == 2013                                # market row

    assert merge_requirements(rows, "dukascopy", "forex", "AUDCAD").keys() == {
        ("raw", "TICK"), ("derived", "1MIN"), ("derived", "1HOUR")}
    assert merge_requirements(rows, "other", "forex", "AUDCAD") == {}
