#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxt.data.models.downloaded

Metadata for daily download files in data/ingest/downloads.

One file per (dataset, day) that had data; days without data have no file
and are recorded as "empty" in the month's manifest.db instead.
"""


#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

from pydantic import Field

from ._registry import DATA_MODELS
from .base import FileMeta


#!================================================================================(80)
#! main
#!--------------------------------------------------------------------------------(80)
@DATA_MODELS.register("DownloadedMeta", 1)
class DownloadedMeta(FileMeta):
    """ Period = one day, [day 00:00Z, next day 00:00Z).
        `created_at` = when the data was downloaded and saved.
    """
    rows: int = Field(ge=1)
    method: str       # how the source was accessed, e.g. "dukascopy-python"
#-



#!================================================================================(80)
#! gogogogog
#!--------------------------------------------------------------------------------(80)
if(__name__ == "__main__"):
    from pathlib import Path
    from rich import print

    print()
    print(f"hi2u ~ from [bold cyan]{Path(__file__).name}~[/]")
    print()
