#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
raw

Metadata for yearly source files in lake/raw (the source of truth), written by
the consolidator straight from the daily downloads.

Lineage: the consolidated-manifest.db beside the file lists every daily file
(path, digest, status), so the meta stores that manifest's hash instead of one
InputRef per day.
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

from pydantic import Field

from ._registry import DATA_MODELS
from .base import CheckedMeta

__all__ = ["RawMeta"]


#!================================================================================(80)
#! main
#!--------------------------------------------------------------------------------(80)
@DATA_MODELS.register("RawMeta", 1)
class RawMeta(CheckedMeta):
    """ Period = one year. Checks = the consolidator's year checks
        (manifest complete, no 3+ day gaps, time order, ...).
    """
    rows: int = Field(ge=0)
    days: int = Field(ge=0)             # daily files consolidated (days with data)
    method: str                         # copied from the daily files, e.g. "dukascopy-python"
    manifest_sha256: str                # consolidated-manifest.db written beside this file
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
