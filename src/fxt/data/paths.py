#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
`fxt.data.paths`

Paths for the data lake, built on `fxt.core.io.partitioned`.

    lake/
    ├── raw/        PartitionedDir[LakeKey]   source of truth (data from broker/source)
    ╰── derived/    PartitionedDir[LakeKey]   deterministic transforms of raw

    lake = Lake(root=...)
    lake.raw.path(source="dukascopy", market="forex")         a dir (must exist by default)
    lake.derived.file(key)                                    the file for a full LakeKey
    lake.raw.scan(symbol="EURJPY", interval="TICK")           [(LakeKey, Path), ...]
    lake.layer(LakeType.RAW)                                  same as lake.raw

The same layout works anywhere: `Lake(root=runs/<group>/<project>/data/lake)` is
a project's own lake, so a dataset built there can be moved to the main lake.

TODO: rename Lake to something else? LakePaths? or something like that
"""


#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from fxt.core.io.partitioned import PartitionedDir, PartitionKey, PartitionNotFound

__all__ = ["Lake", "LakeKey", "LakeType", "PartitionNotFound"]


class LakeType(StrEnum):
    RAW = "raw"            # source of truth (data from broker/source)
    DERIVED = "derived"    # deterministic transforms of raw, one correct answer
    #! anything that depends on a parameter choice (features, events, labels,
    #! weights) is keyed by its own PartitionKey (e.g. with a config level) and
    #! lives in a research scope: see fxt.research.paths


class LakeKey(PartitionKey):
    """ One yearly file of one dataset: source/market/symbol/interval/year. """
    FILE_GLOB: ClassVar[str] = "*.parquet"

    source:   str
    market:   str
    symbol:   str
    interval: str
    year:     int

    @property
    def filename(self) -> str:
        return f"{self.symbol}-{self.year}.parquet"


#!================================================================================(80)
#! main
#!--------------------------------------------------------------------------------(80)
class Lake(BaseModel):
    """
        lake/raw
            the source of truth (aka data from broker/source)
        lake/derived
            holds deterministic transforms of raw that have one correct answer

        Anything that depends on a parameter choice (features, events, labels,
        weights) is keyed by a config hash and lives in a research scope
        (runs/<group>/.../data/), never in the main lake.
    """
    model_config = ConfigDict(frozen=True)
    root: Path

    def layer(self, laketype: LakeType | str) -> PartitionedDir[LakeKey]:
        """ raw/ or derived/ as a partitioned dir. """
        return PartitionedDir(self.root / LakeType(laketype), LakeKey)   # ValueError on a bad type

    @property
    def raw(self) -> PartitionedDir[LakeKey]:
        return self.layer(LakeType.RAW)

    @property
    def derived(self) -> PartitionedDir[LakeKey]:
        return self.layer(LakeType.DERIVED)

    def key_of(self, path: Path | str) -> tuple[LakeType, LakeKey]:
        """ (layer, key) of a file anywhere in this lake. """
        rel = Path(path).relative_to(self.root)
        return LakeType(rel.parts[0]), LakeKey.from_path(rel)


#!================================================================================(80)
#! gogogogog
#!--------------------------------------------------------------------------------(80)
if __name__ == "__main__":
    from rich import print
    from rich.panel import Panel
    from rich.pretty import pprint

    from fxt.services import get_lake, get_settings

    lake = get_lake()

    def _exists_str(p: Path) -> str:
        return "[green]exists[/]" if p.exists() else "[red]doesnt exist[/]"

    def summary():
        values = {"source": "dukascopy", "market": "forex", "symbol": "EURJPY",
                  "interval": "TICK", "year": 2015}
        names = LakeKey.partitions()
        for ty in LakeType:
            lines = []
            for i in range(1, len(names) + 1):
                p = lake.layer(ty).path(must_exist=False, **{k: values[k] for k in names[:i]})
                lines.append(f" - {p} ~ {_exists_str(p)}")
            print(Panel("\n".join(lines), title=f"[bold cyan]{ty}", title_align="left"))

    summary()
    pprint(get_settings().paths)
    #pprint(lake.raw.scan(interval="TICK"))
