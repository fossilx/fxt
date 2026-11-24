"""
fxt.data.ingest.consolidate: daily downloads (new format) -> lake/raw year.
"""
from __future__ import annotations

import hashlib
import shutil
import sqlite3
from datetime import UTC, date, datetime, timedelta

import polars as pl
import pytest

from fxt.data.ingest import layout
from fxt.data.ingest.consolidate import (
    ConsolidateError, Thresholds, consolidate_year, longest_gap, missing_days, raw_paths,
)
from fxt.data.models import DatasetKey, DownloadedMeta, RawMeta

KEY = DatasetKey(source="dukascopy", market="forex", symbol="AUDCAD", interval="TICK")


@pytest.fixture
def fd(fake_downloads):
    return fake_downloads


@pytest.fixture
def downloads(fd):
    return fd.root


@pytest.fixture
def meta_io(fd):
    return fd.meta_io


@pytest.fixture
def lake(tmp_path):
    return tmp_path / "lake"


def run(downloads, lake, meta_io, **kw):
    kw.setdefault("today", date(2013, 1, 7))
    return consolidate_year(KEY, 2013, downloads=downloads, lake_dir=lake, meta_io=meta_io, **kw)


def checks(r):
    return {c.name: c for c in r.checks}


#! ---- happy path --------------------------------------------------------------------
def test_writes_raw_year(fd, downloads, lake, meta_io):
    fd.week()
    r = run(downloads, lake, meta_io)
    assert r.status == "written" and r.passed, [c for c in r.checks if not c.ok]
    assert (r.rows, r.days) == (16, 4)

    data, manifest = raw_paths(lake, KEY, 2013)
    assert data == r.path and data.parts[-6:] == (
        "source=dukascopy", "market=forex", "symbol=AUDCAD", "interval=TICK", "year=2013", "AUDCAD-2013.parquet")
    meta = meta_io.read_meta_as(data, RawMeta)
    assert meta.dataset == KEY and meta.rows == 16 and meta.days == 4 and meta.passed
    assert meta.method == "dukascopy-python"
    assert meta.manifest_sha256 == hashlib.sha256(manifest.read_bytes()).hexdigest()

    df = pl.read_parquet(data, hive_partitioning=False)
    assert df.height == 16 and df["dtime"].is_sorted()
    paths = [p for (p,) in sqlite3.connect(manifest).execute(
        "SELECT path FROM financial_files WHERE status='success' ORDER BY id")]
    assert paths[0] == "dukascopy/forex/AUDCAD/TICK/2013/01/AUDCAD-2013-01-01.parquet"
    assert (downloads / paths[0]).is_file()                 # entries resolve from the downloads root


def test_manifest_describes_itself(fd, downloads, lake, meta_io):
    from fxt.data.ingest.consolidate import INFO_KEYS
    from fxt.data.ingest.manifest import read_info
    fd.week()
    run(downloads, lake, meta_io)
    info = read_info(raw_paths(lake, KEY, 2013)[1])
    assert tuple(info) == INFO_KEYS
    assert info["paths_relative_to"] == "downloads"
    assert info["dataset"] == "dukascopy/forex/AUDCAD/TICK" and info["year"] == "2013"
    assert info["month_manifest_paths"] == "dukascopy/forex/AUDCAD/TICK/2013/01/manifest.db"
    assert (info["days_success"], info["days_empty"], info["days_other"]) == ("4", "1", "0")
    assert info["data_file"] == "AUDCAD-2013.parquet"
    assert read_info(layout.month_dir(downloads, KEY, date(2013, 1, 1)) / "manifest.db") == {}


def test_exists_force_dry_nodata(fd, downloads, lake, meta_io):
    fd.week()
    assert run(downloads, lake, meta_io, dry=True).status == "dry"
    assert not raw_paths(lake, KEY, 2013)[0].exists()
    assert run(downloads, lake, meta_io).status == "written"
    assert run(downloads, lake, meta_io).status == "exists"
    assert run(downloads, lake, meta_io, force=True).status == "written"
    assert consolidate_year(KEY, 2014, downloads=downloads, lake_dir=lake, meta_io=meta_io).status == "no-data"


#! ---- recorded checks (file still written) ----------------------------------------------
def test_gap_and_coverage(fd, downloads, lake, meta_io):
    fd.add_day(date(2013, 1, 1))
    for d in range(2, 20):                                   # empty rows, Jan 2-19 (no Saturdays needed)
        if date(2013, 1, d).weekday() != 5:
            fd.add_day(date(2013, 1, d), status="empty")
    fd.add_day(date(2013, 1, 21))           # Jan 20 (Sun) has no row at all
    r = run(downloads, lake, meta_io, today=date(2013, 1, 22))
    c = checks(r)
    assert r.status == "written" and not r.passed
    assert c["gaps: days without data"].status == "fail" and c["gaps: days without data"].value == 19
    assert c["coverage: every day in a manifest"].status == "fail"
    assert "2013-01-20" in c["coverage: every day in a manifest"].detail
    assert not meta_io.read_meta_as(r.path, RawMeta).passed


def test_error_day_fails_coverage(fd, downloads, lake, meta_io):
    fd.week()
    fd.add_day(date(2013, 1, 7), status="error")
    c = checks(run(downloads, lake, meta_io, today=date(2013, 1, 8)))["coverage: every day in a manifest"]
    assert c.status == "fail" and "status error: 2013-01-07" in c.detail


def test_short_gap_warns(fd, downloads, lake, meta_io):
    for d in (1, 2):
        fd.add_day(date(2013, 1, d))
    for d in (3, 4, 6):
        fd.add_day(date(2013, 1, d), status="empty")
    fd.add_day(date(2013, 1, 7))
    r = run(downloads, lake, meta_io, today=date(2013, 1, 8))
    assert checks(r)["gaps: days without data"].status == "warn" and r.passed     # 4 days: warn only


def test_duplicates_rows_and_order(fd, downloads, lake, meta_io):
    df = fd.ticks(date(2013, 1, 2))
    fd.add_day(date(2013, 1, 1), df=fd.ticks(date(2013, 1, 1)).reverse())  # unsorted
    fd.add_day(date(2013, 1, 2), df=pl.concat([df, df.tail(1)]))           # 1 dupe
    fd.add_day(date(2013, 1, 3), manifest_rows=99)                          # wrong rows
    r = run(downloads, lake, meta_io, today=date(2013, 1, 4))
    c = checks(r)
    assert c["time: sorted, in year, no nulls"].status == "fail"
    assert c["duplicates: adjacent identical rows"].status == "fail" and c["duplicates: adjacent identical rows"].value == 1
    assert c["rows: manifest matches files"].status == "fail"


def test_unlisted_file_warns(fd, downloads, lake, meta_io):
    fd.week()
    stray = layout.month_dir(downloads, KEY, date(2013, 1, 1)) / "AUDCAD-2013-01-05.parquet"
    stray.write_bytes(b"")
    assert checks(run(downloads, lake, meta_io))["files: none unlisted"].status == "warn"


#! ---- hard errors (nothing written) ----------------------------------------------------
def test_schema_mismatch_is_an_error(fd, downloads, lake, meta_io):
    fd.add_day(date(2013, 1, 1))
    fd.add_day(date(2013, 1, 2),
            df=fd.ticks(date(2013, 1, 2)).with_columns(tickVolume=pl.lit(4.0)))
    with pytest.raises(ConsolidateError, match="schema differs"):
        run(downloads, lake, meta_io)
    assert not raw_paths(lake, KEY, 2013)[0].exists()


def test_dataset_mismatch_is_an_error(fd, downloads, lake, meta_io):
    fd.add_day(date(2013, 1, 1), meta_key=KEY.model_copy(update={"symbol": "EURJPY"}))
    with pytest.raises(ConsolidateError, match="dataset"):
        run(downloads, lake, meta_io)


def test_missing_file_is_an_error(fd, downloads, lake, meta_io):
    fd.add_day(date(2013, 1, 1))
    layout.daily_path(downloads, KEY, date(2013, 1, 1)).unlink()
    with pytest.raises(ConsolidateError, match="missing"):
        run(downloads, lake, meta_io)


def test_day_in_two_manifests_is_an_error(fd, downloads, lake, meta_io):
    fd.add_day(date(2013, 1, 1))
    other = layout.year_dir(downloads, KEY, 2013) / "02"
    other.mkdir(parents=True)
    shutil.copy(layout.month_dir(downloads, KEY, date(2013, 1, 1)) / "manifest.db", other / "manifest.db")
    with pytest.raises(ConsolidateError, match="manifests"):
        run(downloads, lake, meta_io)


#! ---- helpers ----------------------------------------------------------------------------
def test_longest_gap():
    d = lambda n: date(2013, 1, n)  # noqa: E731
    assert longest_gap([d(1), d(2), d(6)], d(1), d(8)) == (3, d(3))
    assert longest_gap([d(5)], d(1), d(8)) == (4, d(1))          # before the first data day
    assert longest_gap([], d(1), d(8)) == (7, d(1))


def test_missing_days_skips_saturday():
    assert missing_days({date(2013, 1, 1)}, date(2013, 1, 1), date(2013, 1, 7), frozenset({5})) == [
        date(2013, 1, 2), date(2013, 1, 3), date(2013, 1, 4), date(2013, 1, 6)]
