from __future__ import annotations

import polars as pl
import pytest

from fxt.data import schemas
from fxt.data.derived.bars import BAR_SCHEMA, _conform, ticks_to_bars
from fxt.data.schemas import BAR_CORE, TICK_CORE, check_schema, empty_frame, kind_of

from .conftest import tick_frame


def test_kind_of():
    assert kind_of("TICK") == "ticks" and kind_of("tick") == "ticks"
    assert kind_of("1MIN") == kind_of("1HOUR") == "bars"


def test_tick_core_matches_files_on_disk():
    """ Copied from AUDCAD-2013-01-01.parquet via pl.read_parquet_schema (2026-11-24). """
    on_disk = pl.Schema({"dtime": pl.Datetime("ms", "UTC"), "bidPrice": pl.Float64,
                         "askPrice": pl.Float64, "bidVolume": pl.Float64, "askVolume": pl.Float64})
    assert check_schema(on_disk, TICK_CORE, exact=True) == []


def test_bar_builder_writes_bar_core():
    bars = _conform(ticks_to_bars(tick_frame(200).lazy(), "1MIN")).collect()   # what gets written
    assert check_schema(bars.schema, BAR_CORE, exact=True) == []
    assert BAR_SCHEMA == dict(BAR_CORE)


def test_exact_catches_everything():
    s = dict(TICK_CORE)
    extra = pl.Schema({**s, "tickVolume": pl.Float64})
    assert check_schema(extra, TICK_CORE, exact=True) == ["extra columns: tickVolume"]
    assert check_schema(extra, TICK_CORE, exact=False) == []           # extras fine vs core

    missing = pl.Schema({k: v for k, v in s.items() if k != "askVolume"})
    assert check_schema(missing, TICK_CORE, exact=False) == ["missing columns: askVolume"]

    reordered = pl.Schema(dict(reversed(list(s.items()))))
    assert check_schema(reordered, TICK_CORE, exact=False) == []
    assert len(check_schema(reordered, TICK_CORE, exact=True)) == 1


@pytest.mark.parametrize("bad", [pl.Datetime("us", "UTC"), pl.Datetime("ms"), pl.Datetime("ms", "America/New_York")])
def test_time_unit_and_zone_are_strict(bad):
    s = pl.Schema({**dict(TICK_CORE), "dtime": bad})
    assert check_schema(s, TICK_CORE, exact=False) != []


def test_empty_frame():
    df = empty_frame(TICK_CORE)
    assert df.height == 0 and df.schema == TICK_CORE
