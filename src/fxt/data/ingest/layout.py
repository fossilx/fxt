#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxt.data.ingest.layout

Where daily download files live (plain folders, not hive key=value):

    <downloads>/<source>/<market>/<SYMBOL>/<INTERVAL>/<YYYY>/<MM>/<SYMBOL>-<YYYY-MM-DD>.parquet
    <downloads>/<source>/<market>/<SYMBOL>/<INTERVAL>/<YYYY>/<MM>/manifest.db

Manifest rows store `path` relative to the manifest's own folder (the file
name), so whole folders can be moved without touching the manifests.
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

from datetime import date
from pathlib import Path

from fxt.data.models import DatasetKey

__all__ = ["dataset_dir", "year_dir", "month_dir", "daily_filename", "daily_path"]


def dataset_dir(downloads: Path, key: DatasetKey) -> Path:
    return downloads / key.source / key.market / key.symbol / key.interval

def year_dir(downloads: Path, key: DatasetKey, year: int) -> Path:
    return dataset_dir(downloads, key) / f"{year:04d}"

def month_dir(downloads: Path, key: DatasetKey, day: date) -> Path:
    return year_dir(downloads, key, day.year) / f"{day.month:02d}"

def daily_filename(key: DatasetKey, day: date) -> str:
    return f"{key.symbol}-{day.isoformat()}.parquet"

def daily_path(downloads: Path, key: DatasetKey, day: date) -> Path:
    return month_dir(downloads, key, day) / daily_filename(key, day)
#-
