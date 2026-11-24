#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
legacy

Read-only copies of the old dataprep metadata models, so files written before
the redesign can still be read and converted:

    DownloadedDataMeta@1    -> DownloadedMeta@1   (upgrade_downloaded)
    ConsolidatedDataMeta@1  -> read only; raw files get rebuilt by the new
                               consolidator instead of converted

The field shapes match what the old models wrote exactly (checked against real
files), with two simplifications that don't change the JSON:
- `market` is a plain str (the old model resolved it against MarketRegistry).
- no rich rendering, no add_test_result() (these are never built, only read).

extra="forbid" on purpose: if an old file holds anything unexpected, reading
it fails instead of the converter silently dropping it.

Delete this module once no file on disk carries a legacy type id.
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from fxt.core.versioned import VersionedModel

from ._registry import DATA_MODELS
from .base import DatasetKey
from .downloaded import DownloadedMeta

__all__ = [
    "LegacyModelError",
    "LegacySource", "LegacyDataset", "LegacyCheck",
    "DownloadedDataMeta", "ConsolidatedDataMeta",
    "upgrade_downloaded",
]


class LegacyModelError(TypeError):
    """ Raised when trying to write a legacy model to a file. """


#!================================================================================(80)
#! components (old shapes)
#!--------------------------------------------------------------------------------(80)
class _Legacy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

class LegacySource(_Legacy):
    """ old SourceComponent """
    id: str                      # "dukascopy"
    method: str | None = None    # "dukascopy-python"

class LegacyDataset(_Legacy):
    """ old DatasetIdentity """
    source: LegacySource
    symbol: str                  # source spelling: "AUD/CAD"
    interval: str                # "TICK"
    market: str                  # "forex"

class LegacyCheck(_Legacy):
    """ old ConsolidationTestComponent """
    id: str
    status: Literal["passed", "failed"]
    reason: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)


#!================================================================================(80)
#! meta (old shapes, registered so old files can be read)
#!--------------------------------------------------------------------------------(80)
class _LegacyMeta(VersionedModel):
    """ Shared fields of the old BaseMeta + DownloadedDataMeta. """
    model_config = ConfigDict(frozen=True, extra="forbid")

    other: dict[str, str] = Field(default_factory=dict)
    dataset: LegacyDataset
    start: AwareDatetime
    end: AwareDatetime
    created_at: AwareDatetime    # local time with offset in the old files

    @model_validator(mode="after")
    def _check_period(self) -> Self:
        if self.start >= self.end:
            raise ValueError(f"start must be before end (start={self.start}, end={self.end})")
        return self

    def serialize(self) -> tuple[str, str]:
        raise LegacyModelError(
            f"{self.get_id()} is read-only: write the current model instead "
            f"(see fxt.data.models.legacy)."
        )
#

@DATA_MODELS.register("DownloadedDataMeta", 1)
class DownloadedDataMeta(_LegacyMeta):
    pass

@DATA_MODELS.register("ConsolidatedDataMeta", 1)
class ConsolidatedDataMeta(_LegacyMeta):
    consolidation_tests: tuple[LegacyCheck, ...] = ()


#!================================================================================(80)
#! upgrades
#!--------------------------------------------------------------------------------(80)
def upgrade_downloaded(
    old: DownloadedDataMeta,
    *,
    rows: int,
) -> DownloadedMeta:
    """ DownloadedDataMeta@1 -> DownloadedMeta@1.

        - dataset: rebuilt with DatasetKey.from_refdata, so every value is
          refdata's official name ("AUD/CAD" -> "AUDCAD")
        - other["status"]: dropped; must be "success" (only days with data have files)
        - created_at: kept (it's when the data was downloaded), converted to UTC
        - rows: from the file's frame (the old meta didn't store it)
    """
    other = dict(old.other)
    status = other.pop("status", "success")
    if status != "success":
        raise ValueError(f"old meta has status={status!r}; only 'success' files can be upgraded")
    if other:
        raise ValueError(f"old meta has unexpected `other` keys: {sorted(other)}")
    if not old.dataset.source.method:
        raise ValueError("old meta has no source.method")

    ds = old.dataset
    return DownloadedMeta(
        dataset=DatasetKey.from_refdata(ds.source.id, ds.market, ds.symbol, ds.interval),
        start=old.start,
        end=old.end,
        created_at=old.created_at,
        rows=rows,
        method=ds.source.method,
    )
#-
