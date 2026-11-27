from __future__ import annotations

from pathlib import Path

import pytest

from fxt.core.io.partitioned import PartitionedDir
from fxt.data.paths import Lake, LakeKey, LakeType

KEY = LakeKey(source="dukascopy", market="forex", symbol="EURJPY", interval="TICK", year=2015)


def test_layers(tmp_path: Path):
    lake = Lake(root=tmp_path)
    assert isinstance(lake.raw, PartitionedDir)
    assert lake.raw.root == tmp_path / "raw"
    assert lake.derived.root == tmp_path / "derived"
    assert lake.layer("raw") == lake.raw
    assert lake.layer(LakeType.DERIVED) == lake.derived
    with pytest.raises(ValueError):
        lake.layer("research")


def test_same_paths_as_before(tmp_path: Path):
    """ The layout the existing lake on disk uses. """
    lake = Lake(root=tmp_path)
    assert lake.raw.file(KEY) == tmp_path / (
        "raw/source=dukascopy/market=forex/symbol=EURJPY/interval=TICK/year=2015/EURJPY-2015.parquet")
    assert lake.raw.path(source="dukascopy", market="forex", must_exist=False) == (
        tmp_path / "raw/source=dukascopy/market=forex")


def test_key_of(tmp_path: Path):
    lake = Lake(root=tmp_path)
    assert lake.key_of(lake.derived.file(KEY)) == (LakeType.DERIVED, KEY)


def test_scan_roundtrip(tmp_path: Path):
    lake = Lake(root=tmp_path)
    f = lake.raw.file(KEY)
    f.parent.mkdir(parents=True)
    f.write_bytes(b"")
    assert lake.raw.scan(symbol="EURJPY") == [(KEY, f)]
    assert lake.derived.scan() == []
