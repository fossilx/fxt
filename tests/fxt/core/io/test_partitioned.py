from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import ValidationError

from fxt.core.io.partitioned import PartitionedDir, PartitionKey, PartitionNotFound


class K(PartitionKey):
    FILE_GLOB: ClassVar[str] = "*.parquet"
    a: str
    b: str
    year: int

    @property
    def filename(self) -> str:
        return f"{self.b}-{self.year}.parquet"


def _touch(d: PartitionedDir[K], key: K, name: str | None = None) -> Path:
    p = d.root / key.rel_dir / (name or key.filename)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")
    return p


@pytest.fixture
def d(tmp_path: Path) -> PartitionedDir[K]:
    return PartitionedDir(tmp_path / "root", K)


#! ---- key ---------------------------------------------------------------------
def test_key_basics():
    k = K(a="x", b="y", year=2020)
    assert K.partitions() == ("a", "b", "year")
    assert k.rel_dir == Path("a=x/b=y/year=2020")
    assert K.from_path("/anything/a=x/b=y/year=2020/y-2020.parquet") == k
    assert k.replace(year="2021") == K(a="x", b="y", year=2021)
    with pytest.raises(ValidationError):
        k.replace(year="nope")
    with pytest.raises(ValidationError):
        K(a="x", b="y", year=2020, extra=1)
    with pytest.raises(ValueError, match="missing partition"):
        K.from_path("a=x/year=2020")


def test_base_key_has_no_filename():
    class NoName(PartitionKey):
        a: str
    with pytest.raises(NotImplementedError):
        NoName(a="x").filename


#! ---- path / file -------------------------------------------------------------
def test_path_needs_a_leading_run(d):
    assert d.path(must_exist=False) == d.root
    assert d.path(a="x", must_exist=False) == d.root / "a=x"
    assert d.path(a="x", b="y", year=2020, filename="f", must_exist=False) == d.root / "a=x/b=y/year=2020/f"
    with pytest.raises(ValueError, match="'b' given but 'a' is missing"):
        d.path(b="y", must_exist=False)
    with pytest.raises(ValueError, match="filename given"):
        d.path(a="x", filename="f", must_exist=False)
    with pytest.raises(ValueError, match="unknown"):
        d.path(zzz="1", must_exist=False)
    with pytest.raises(ValueError, match="unsafe"):
        d.path(a="../x", must_exist=False)


def test_must_exist(d):
    with pytest.raises(PartitionNotFound):
        d.path(a="x")
    k = K(a="x", b="y", year=2020)
    with pytest.raises(PartitionNotFound):
        d.file(k, must_exist=True)
    p = _touch(d, k)
    assert d.file(k, must_exist=True) == p
    assert d.path(a="x") == d.root / "a=x"


def test_file_checks_key_type(d):
    class Other(K):
        pass
    d.file(Other(a="x", b="y", year=1))          # subclass is fine
    class Unrelated(PartitionKey):
        a: str
        @property
        def filename(self): return "f"
    with pytest.raises(TypeError):
        d.file(Unrelated(a="x"))


def test_key_of(d):
    k = K(a="x", b="y", year=2020)
    assert d.key_of(d.file(k)) == k
    with pytest.raises(ValueError):
        d.key_of(Path("/elsewhere/a=x/b=y/year=2020/y-2020.parquet"))


#! ---- scan --------------------------------------------------------------------
def test_scan(d):
    keys = [K(a=a, b=b, year=y) for a in ("x", "z") for b in ("p", "q") for y in (2020, 2021)]
    paths = {k: _touch(d, k) for k in keys}
    _touch(d, keys[0], "misnamed.parquet")          # skipped: name != key.filename
    _touch(d, keys[0], "notes.txt")                 # skipped: FILE_GLOB

    assert [k for k, _ in d.scan()] == sorted(keys, key=lambda k: str(paths[k]))
    assert {k for k, _ in d.scan(a="x")} == {k for k in keys if k.a == "x"}
    # a gap: b given without a -> globbed, not an error
    assert {k for k, _ in d.scan(b="q")} == {k for k in keys if k.b == "q"}
    # typed values compare as strings
    assert {k for k, _ in d.scan(year=2021)} == {k for k, _ in d.scan(year="2021")}
    assert all(p == paths[k] for k, p in d.scan())


def test_scan_missing_root_is_empty(d):
    assert d.scan() == []
    assert d.scan(a="nope") == []
    with pytest.raises(ValueError, match="unknown"):
        d.scan(zzz=1)
