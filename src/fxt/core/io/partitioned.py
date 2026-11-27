#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
`fxt.core.io.partitioned`

Hive-style partitioned directories (`root/k1=v1/k2=v2/.../<file>`), defined by
a key model. The key's field order is the directory order, and the key owns the
file name, so a layout is declared once:

    class LakeKey(PartitionKey):
        FILE_GLOB: ClassVar[str] = "*.parquet"
        
        #ORDER MATTERS FOR FIELDS
        source: str
        market: str
        symbol: str
        interval: str
        year: int

        @property
        def filename(self) -> str:
            return f"{self.symbol}-{self.year}.parquet"

    d = PartitionedDir(root, LakeKey)

Two ways in, on purpose:

    d.path(source=..., market=...)   a real dir/file: keys must be a leading run
                                     (no gaps), so the result is never a pattern
    d.file(key)                      the file for a full key
    d.scan(symbol="EURJPY")          any subset of keys; missing levels match
                                     anything. Returns [(key, path)] for files
                                     whose name matches their key's filename.
    d.key_of(path)                   key of a file inside this dir
"""


#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict

__all__ = [
    "SAFE_VALUE",
    "PartitionKey",
    "PartitionNotFound",
    "PartitionedDir",
]

#: allowed characters in a partition value (it becomes part of a dir name)
SAFE_VALUE = re.compile(r"[A-Za-z0-9_.\-]+")


class PartitionNotFound(FileNotFoundError):
    """ A partition path that must exist doesn't. """


#!================================================================================(80)
#! key
#!--------------------------------------------------------------------------------(80)
class PartitionKey(BaseModel):
    """ Base for a partition layout. Subclass with fields in directory order and
        a `filename` property; set FILE_GLOB to narrow what `scan` looks at. """
    model_config = ConfigDict(frozen=True, extra="forbid")

    #: glob for candidate files in a leaf dir (each must also match `filename`)
    FILE_GLOB: ClassVar[str] = "*"

    @classmethod
    def partitions(cls) -> tuple[str, ...]:
        """ Partition names, in directory order. """
        return tuple(cls.model_fields)

    @property
    def filename(self) -> str:
        raise NotImplementedError(f"{type(self).__name__} must define `filename`")

    @property
    def rel_dir(self) -> Path:
        """ `k1=v1/k2=v2/...` for this key. """
        return Path(*_segments(type(self), self.model_dump()))

    @classmethod
    def from_path(cls, path: Path | str) -> Self:
        """ Key from the `k=v` parts of a path. Parts without `=` are ignored,
            so a path relative to any ancestor of the partition dirs works. """
        parts = dict(p.split("=", 1) for p in Path(path).parts if "=" in p)
        missing = [k for k in cls.partitions() if k not in parts]
        if missing:
            raise ValueError(f"{path}: missing partition level(s) {missing} for {cls.__name__}")
        return cls(**{k: parts[k] for k in cls.partitions()})

    def replace(self, **changes: Any) -> Self:
        """ Copy with changes; re-validates (unlike model_copy). """
        return type(self)(**{**self.model_dump(), **changes})


def _segments(key: type[PartitionKey], values: dict[str, Any]) -> list[str]:
    """ `k=v` segments for the leading run of `values` in key order. Raises on
        unknown keys, gaps, or unsafe values. """
    names = key.partitions()
    if bad := set(values) - set(names):
        raise ValueError(f"unknown partition key(s) for {key.__name__}: {sorted(bad)}")
    out: list[str] = []
    missing: str | None = None
    for name in names:
        v = values.get(name)
        if v is None:
            missing = missing or name
            continue
        if missing:
            raise ValueError(f"{name!r} given but {missing!r} is missing")
        s = str(v)
        if not SAFE_VALUE.fullmatch(s):
            raise ValueError(f"unsafe {name} value: {s!r}")
        out.append(f"{name}={s}")
    return out


#!================================================================================(80)
#! directory
#!--------------------------------------------------------------------------------(80)
@dataclass(frozen=True, slots=True)
class PartitionedDir[K: PartitionKey]:
    """ A directory laid out by key model `key`. Builds paths; creates nothing.
    """
    root: Path
    key: type[K]

    #! ---- exact paths --------------------------------------------------------
    def path(self, *, filename: str | None = None, must_exist: bool = True, **prefix: Any) -> Path:
        """ Path for a leading run of keys (e.g. source, market), optionally a
            file in it. `filename` needs every level. """
        segs = _segments(self.key, prefix)
        if filename is not None and len(segs) != len(self.key.partitions()):
            raise ValueError(f"filename given but not every level is: {self.key.partitions()}")
        p = self.root.joinpath(*segs)
        if filename is not None:
            p /= filename
        if must_exist and not p.exists():
            raise PartitionNotFound(f"doesn't exist: {p}")
        return p

    def file(self, key: K, *, must_exist: bool = False) -> Path:
        """ The file for a full key. """
        if not isinstance(key, self.key):
            raise TypeError(f"expected {self.key.__name__}, got {type(key).__name__}")
        p = self.root / key.rel_dir / key.filename
        if must_exist and not p.exists():
            raise PartitionNotFound(f"doesn't exist: {p}")
        return p

    def key_of(self, path: Path | str) -> K:
        """ Key of a path inside this dir (only levels below `root` are read). """
        return self.key.from_path(Path(path).relative_to(self.root))

    #! ---- discovery ----------------------------------------------------------
    def scan(self, **filters: Any) -> list[tuple[K, Path]]:
        """ Files matching any subset of keys, sorted by path. Misnamed files
            (name != key.filename) are skipped. """
        names = self.key.partitions()
        if bad := set(filters) - set(names):
            raise ValueError(f"unknown partition key(s) for {self.key.__name__}: {sorted(bad)}")

        # the leading run of filters becomes a real dir prefix; the rest is globbed
        prefix: dict[str, Any] = {}
        for name in names:
            if name not in filters:
                break
            prefix[name] = filters[name]
        base = self.path(must_exist=False, **prefix)
        if not base.is_dir():
            return []

        pattern = "/".join([*(f"{n}=*" for n in names[len(prefix):]), self.key.FILE_GLOB])
        out: list[tuple[K, Path]] = []
        for p in sorted(base.glob(pattern)):
            if not p.is_file():
                continue
            key = self.key_of(p)
            if p.name != key.filename:
                continue
            if all(str(getattr(key, k)) == str(v) for k, v in filters.items()):
                out.append((key, p))
        return out
