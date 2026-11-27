from __future__ import annotations

from pathlib import Path

import pytest

from fxt.data.paths import Lake
from fxt.research.paths import (
    DataDir,
    Group,
    Project,
    group_from_module,
    lockbox_db,
    project_from_module,
)

GROUP = Group("examples", {"features": DataDir("shared")})
PROJECT = Project(GROUP, "p00_smoke", {"scratch": DataDir()})


def test_layout(tmp_path: Path):
    p = PROJECT.paths(tmp_path)
    assert p.root == tmp_path / "examples" / "p00_smoke"
    assert p.experiments_db == p.root / "experiments.db"
    assert p.run_dir("r1") == p.root / "artifacts" / "r1"
    assert p.lockbox_db == tmp_path / "lockbox.db" == lockbox_db(tmp_path)


def test_scopes_have_the_same_shape(tmp_path: Path):
    p = PROJECT.paths(tmp_path)
    assert p.data.data == p.root / "data"
    assert p.common.data == tmp_path / "examples" / "common" / "data"
    for scope in (p.data, p.common):
        assert isinstance(scope.lake, Lake)
        assert scope.lake.root == scope.data / "lake"
    assert p.data.dir("scratch") == p.root / "data" / "scratch"
    assert p.common.dir("features") == tmp_path / "examples" / "common" / "data" / "features"


def test_scope_lake_uses_main_lake_layout(tmp_path: Path):
    lake = PROJECT.paths(tmp_path).data.lake
    path = lake.derived.path(source="dukascopy", market="forex", symbol="EURJPY",
                             interval="1HOUR", year=2020, must_exist=False)
    assert path.relative_to(lake.root) == Path(
        "derived/source=dukascopy/market=forex/symbol=EURJPY/interval=1HOUR/year=2020")


def test_undeclared_dir_is_an_error(tmp_path: Path):
    p = PROJECT.paths(tmp_path)
    with pytest.raises(KeyError, match="isn't declared"):
        p.data.dir("features")          # declared by the group, not the project
    with pytest.raises(KeyError):
        p.common.dir("scratch")


def test_ensure_is_idempotent(tmp_path: Path):
    p = PROJECT.paths(tmp_path)
    p.ensure()
    p.ensure()
    for d in (p.data.data / "lake", p.data.dir("scratch"), p.artifacts,
              p.common.data / "lake", p.common.dir("features")):
        assert d.is_dir(), d
    assert not p.experiments_db.exists()   # databases are created by their owners


def test_identity():
    assert PROJECT.key == "examples/p00_smoke"
    assert PROJECT.module == "fxtapps.research.examples.p00_smoke"
    assert Project("examples", "p00_smoke") == PROJECT     # declarations don't change identity
    assert hash(Project("examples", "p00_smoke")) == hash(PROJECT)


@pytest.mark.parametrize("group,pid", [
    ("Forex", "p01"), ("forex-pooled", "p01"), ("1forex", "p01"),
    ("forex", "01_single"), ("forex", ""), ("common", "p01"), ("forex", "cli"), ("forex", "common"),
])
def test_bad_slugs(group, pid):
    with pytest.raises(ValueError):
        Project(group, pid)


@pytest.mark.parametrize("name", ["lake", "Lake", "my-dir", ""])
def test_bad_data_dir_names(name):
    with pytest.raises(ValueError):
        Project("examples", "p00_smoke", {name: DataDir()})


def test_data_dirs_are_read_only():
    with pytest.raises(TypeError):
        PROJECT.data_dirs["x"] = DataDir()


def test_from_module():
    assert group_from_module("fxtapps.research.examples.common") == Group("examples")
    assert project_from_module("fxtapps.research.examples.p00_smoke.cli") == PROJECT
    with pytest.raises(ValueError):
        group_from_module("fxtapps.research.examples.p00_smoke")   # groups declare in common/
    with pytest.raises(ValueError):
        project_from_module("fxtapps.research.other.p00_smoke", group=GROUP)
    for bad in ("fxtapps.research.examples", "fxt.research.paths", "fxtapps.ingest.cli"):
        with pytest.raises(ValueError):
            project_from_module(bad)


@pytest.mark.parametrize("run_id", ["", ".", "..", "a/b", "a\\b"])
def test_bad_run_ids(tmp_path: Path, run_id: str):
    with pytest.raises(ValueError):
        PROJECT.paths(tmp_path).run_dir(run_id)


#! ---- partitioned declared dirs -----------------------------------------------
from fxt.data.paths import LakeKey  # noqa: E402
from fxt.research.paths import FeatureKey  # noqa: E402

KEYED = Group("examples", {"features": DataDir("f", key=FeatureKey), "notes": DataDir()})


def test_partitioned_declared_dir(tmp_path: Path):
    scope = KEYED.common(tmp_path)
    features = scope.partitioned("features")
    assert features.root == scope.dir("features")
    lk = LakeKey(source="dukascopy", market="forex", symbol="EURJPY", interval="1HOUR", year=2020)
    fk = FeatureKey.for_lake("abc123", lk)
    f = features.file(fk)
    assert f.relative_to(features.root) == Path(
        "config=abc123/source=dukascopy/market=forex/symbol=EURJPY/interval=1HOUR/year=2020/EURJPY-2020.parquet")
    f.parent.mkdir(parents=True)
    f.write_bytes(b"")
    assert features.scan(symbol="EURJPY") == [(fk, f)]
    assert features.scan(config="other") == []
    assert fk.lake_key() == lk


def test_partitioned_needs_a_key(tmp_path: Path):
    scope = KEYED.common(tmp_path)
    with pytest.raises(TypeError, match="without a key"):
        scope.partitioned("notes")
    with pytest.raises(KeyError):
        scope.partitioned("nope")


def test_datadir_key_must_be_a_partition_key():
    with pytest.raises(TypeError):
        DataDir("x", key=dict)
