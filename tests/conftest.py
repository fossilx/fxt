'''
Shared test config

Fixtures used by both tests/fxt and tests/fxtapps:
    fake_downloads   writes daily download files + month manifests in the
                     current format (DownloadedMeta@1), like the downloader does
'''
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

MANIFEST_DDL = """
CREATE TABLE financial_files (
    dataset TEXT, id TEXT, path TEXT, status TEXT, rows INTEGER, algo TEXT,
    digest TEXT, size INTEGER, error TEXT, ingested_at TEXT, first_ts TEXT, last_ts TEXT,
    PRIMARY KEY (dataset, id)
)"""


def day_ticks(day: date, n: int = 4) -> pl.DataFrame:
    """ n ticks, one per second from 01:00 UTC; exactly fxt.data.schemas.TICK_CORE. """
    t0 = datetime(day.year, day.month, day.day, 1, tzinfo=UTC)
    return pl.DataFrame({
        "dtime": pl.datetime_range(t0, t0 + timedelta(seconds=n - 1), "1s",
                                   time_unit="ms", time_zone="UTC", eager=True),
        "bidPrice": [1.0 + i / 1e4 for i in range(n)],
        "askPrice": [1.0002 + i / 1e4 for i in range(n)],
        "bidVolume": [1.5] * n,
        "askVolume": [2.5] * n,
    })


@dataclass
class FakeDownloads:
    root: Path              # the downloads root (<data>/ingest/downloads)
    meta_io: object
    ticks = staticmethod(day_ticks)

    def add_day(self, day: date, *, status: str = "success", df: pl.DataFrame | None = None,
                key=None, manifest_rows: int | None = None, meta_key=None,
                method: str = "dukascopy-python") -> None:
        """ One manifest row, plus the file for success days. """
        from fxt.data.ingest import layout
        from fxt.data.models import DatasetKey, DownloadedMeta
        key = key or DatasetKey(source="dukascopy", market="forex", symbol="AUDCAD", interval="TICK")
        folder = layout.month_dir(self.root, key, day)
        folder.mkdir(parents=True, exist_ok=True)
        name = layout.daily_filename(key, day)
        rows = None
        if status == "success":
            df = day_ticks(day) if df is None else df
            start = datetime(day.year, day.month, day.day, tzinfo=UTC)
            meta = DownloadedMeta(dataset=meta_key or key, start=start, end=start + timedelta(days=1),
                                  rows=max(df.height, 1), method=method)
            self.meta_io.write(df, folder / name, meta)          # type: ignore[attr-defined]
            rows = df.height
        con = sqlite3.connect(folder / "manifest.db")
        with con:
            con.execute(MANIFEST_DDL.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS"))
            con.execute("INSERT INTO financial_files (dataset, id, path, status, rows, algo, digest, size)"
                        " VALUES (?, ?, ?, ?, ?, 'sha256', 'x', 1)",
                        (str(key), day.isoformat(), name if status == "success" else None, status,
                         manifest_rows if manifest_rows is not None else rows))
        con.close()

    def week(self, **kw) -> None:
        """ 2013-01-01 (Tue) .. 01-06 (Sun): data Jan 1-4, Saturday has no row, Sunday empty. """
        for d in (1, 2, 3, 4):
            self.add_day(date(2013, 1, d), **kw)
        self.add_day(date(2013, 1, 6), status="empty")


@pytest.fixture
def fake_downloads(tmp_path) -> FakeDownloads:
    from fxt.core.io.parquet_store import ParquetStore, ParquetStoreSettings
    from fxt.core.versioned import VersionedModelIO
    from fxt.data.models import DATA_MODELS
    io = VersionedModelIO(DATA_MODELS, ParquetStore(settings=ParquetStoreSettings(namespace="fxt-data")))
    return FakeDownloads(root=tmp_path / "ingest/downloads", meta_io=io)


@pytest.fixture
def small_lake(tmp_path, fake_downloads):
    """ A lake with one passing raw TICK year: AUDCAD 2013 (Jan 1-4 data), built by
        the real consolidator. Returns the fxt.data.paths.Lake.
    """
    from fxt.data.ingest.consolidate import consolidate_year
    from fxt.data.models import DatasetKey
    from fxt.data.paths import Lake
    fake_downloads.week()
    key = DatasetKey(source="dukascopy", market="forex", symbol="AUDCAD", interval="TICK")
    r = consolidate_year(key, 2013, downloads=fake_downloads.root, lake_dir=tmp_path / "lake",
                         meta_io=fake_downloads.meta_io, today=date(2013, 1, 7))
    assert r.passed, r.checks
    return Lake(root=tmp_path / "lake")
