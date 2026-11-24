"""
Fixtures for fxt.data tests: a namespaced ParquetStore + meta IO that don't
need the project settings, and helpers that write files in the OLD format.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

from fxt.core.io.parquet_store import ParquetStore, ParquetStoreSettings
from fxt.core.versioned import VersionedModelIO
from fxt.data.models import DATA_MODELS

#! real footers, copied from AUDCAD files (2013-01-01 daily, 2013 consolidated)
OLD_DOWNLOADED_JSON = """{
  "other": {"status": "success"},
  "dataset": {"source": {"id": "dukascopy", "method": "dukascopy-python"},
              "symbol": "AUD/CAD", "interval": "TICK", "market": "forex"},
  "start": "2013-01-01T00:00:00Z",
  "end": "2013-01-02T00:00:00Z",
  "created_at": "2026-11-22T07:42:38.180968-05:00"
}"""

OLD_CONSOLIDATED_JSON = """{
  "other": {},
  "dataset": {"source": {"id": "dukascopy", "method": "dukascopy-python"},
              "symbol": "AUD/CAD", "interval": "TICK", "market": "forex"},
  "start": "2013-01-01T00:00:00Z",
  "end": "2014-01-01T00:00:00Z",
  "created_at": "2026-11-22T12:16:02.422249-05:00",
  "consolidation_tests": [
    {"id": "check-manifest", "status": "passed", "reason": null, "values": {}}
  ]
}"""

MANIFEST_DDL = """
CREATE TABLE financial_files (
    dataset TEXT, id TEXT, path TEXT, status TEXT, rows INTEGER, algo TEXT,
    digest TEXT, size INTEGER, error TEXT, ingested_at TEXT, first_ts TEXT, last_ts TEXT,
    PRIMARY KEY (dataset, id)
)"""


@pytest.fixture
def store() -> ParquetStore:
    return ParquetStore(settings=ParquetStoreSettings(namespace="fxt-data"))


@pytest.fixture
def meta_io(store: ParquetStore) -> VersionedModelIO:
    return VersionedModelIO(DATA_MODELS, store)


def tick_frame(n: int = 5) -> pl.DataFrame:
    t0 = datetime(2013, 1, 1, tzinfo=UTC)
    return pl.DataFrame({
        "dtime": pl.datetime_range(t0, t0 + pl.duration(seconds=n - 1), "1s",
                                   time_unit="ms", time_zone="UTC", eager=True),
        "bidPrice": [1.0 + i / 1e4 for i in range(n)],
        "askPrice": [1.0001 + i / 1e4 for i in range(n)],
        "bidVolume": [1.5] * n,
        "askVolume": [2.5] * n,
    })


def write_old_daily(store: ParquetStore, path: Path, df: pl.DataFrame,
                    json: str = OLD_DOWNLOADED_JSON, *, manifest: bool = True) -> Path:
    """ A daily file + manifest row exactly like the old downloader wrote them. """
    store.write(df, path, metadata={"type": "DownloadedDataMeta@1", "json": json})
    if manifest:
        db = path.parent / "manifest.db"
        con = sqlite3.connect(db)
        with con:
            con.execute(MANIFEST_DDL.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS"))
            con.execute(
                "INSERT INTO financial_files (dataset, id, path, status, rows, algo, digest, size)"
                " VALUES (?, ?, ?, 'success', ?, 'sha256', 'olddigest', 1)",
                ("dukascopy/AUD/CAD/TICK", path.stem[-10:], path.name, df.height),
            )
        con.close()
    return path
