#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxt.data.models

Metadata models for data files (downloads, lake/raw, lake/derived), and the IO
that reads/writes them.

    base.py        shared components + unregistered bases
    downloaded.py  DownloadedMeta@1    daily download files
    raw.py         RawMeta@1           lake/raw yearly files
    bars.py        BarsMeta@1          lake/derived bar files
    legacy.py      DownloadedDataMeta@1, ConsolidatedDataMeta@1 (read-only)
    store.py       registry bound to ParquetStore, lineage helpers

Every model module must be imported here: models register on import, and a
file can only be read back if its model is registered. Import the registry
from this package (not from ._registry) so every model is registered first.
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from ._registry import DATA_MODELS
from .base import (
    BAD_CHECK_STATUSES, CheckRecord, CheckStatus, CheckedMeta, Component, DatasetKey,
    DerivedMeta, FileMeta, InputRef, Transform, utcnow,
)
from .downloaded import DownloadedMeta
from .raw import RawMeta
from .bars import BarsMeta
from . import legacy
from .store import get_meta_io, get_store, input_ref, sha256_file


__all__ = [
    "DATA_MODELS",
    "BAD_CHECK_STATUSES", "CheckRecord", "CheckStatus", "Component", "DatasetKey",
    "InputRef", "Transform", "utcnow",
    "FileMeta", "CheckedMeta", "DerivedMeta",
    "DownloadedMeta", "RawMeta", "BarsMeta",
    "legacy",
    "get_meta_io", "get_store", "input_ref", "sha256_file",
]
