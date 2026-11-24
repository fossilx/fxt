"""
fxt.data.derived.jobs: the DerivedJob spec, run_job, and the up-to-date state.
Builds a tiny raw year with the real consolidator, then 1MIN and 1HOUR bars.
"""
from __future__ import annotations

import os

import pytest

from fxt.core.io.hash_cache import HashCache
from fxt.data.derived.jobs import JOBS, Outcome, State, get_job, run_job
from fxt.data.models import BarsMeta

@pytest.fixture
def lake(small_lake):
    return small_lake


def test_registry_order_and_lookup():
    assert list(JOBS) == ["bars-1min", "bars-1hour"]
    assert get_job("BARS-1MIN") is JOBS["bars-1min"]
    with pytest.raises(KeyError, match="known"):
        get_job("nope")


def test_build_chain_and_states(lake):
    j1, j2 = JOBS["bars-1min"], JOBS["bars-1hour"]
    (key, src), = j1.scan(lake)
    assert j1.state(lake, key, src)[0] is State.MISSING

    run = run_job(j1, lake, key, src)
    assert run.outcome is Outcome.PASSED, run.report.failed
    assert j1.state(lake, key, src) == (State.CURRENT, "")
    from fxt.data.models import get_meta_io
    m = get_meta_io().read_meta(j1.dst(lake, key))
    assert isinstance(m, BarsMeta) and m.passed and m.inputs[0].path.startswith("raw/")

    (key2, src2), = j2.scan(lake)                     # 1MIN output is the 1HOUR input
    assert run_job(j2, lake, key2, src2).outcome is Outcome.PASSED
    assert j2.state(lake, key2, src2)[0] is State.CURRENT

    #! input changes -> both stale (1MIN directly; 1HOUR once 1MIN is rebuilt)
    os.utime(src, ns=(1, 1))                          # new mtime: cache must rehash
    with open(src, "ab") as f:
        f.write(b"\0")
    state, reason = j1.state(lake, key, src)
    assert state is State.STALE and "input changed" in reason


def test_verify_only_and_skip(lake):
    j1 = JOBS["bars-1min"]
    (key, src), = j1.scan(lake)
    assert run_job(j1, lake, key, src, build=False).outcome is Outcome.SKIPPED
    run_job(j1, lake, key, src)
    mtime = j1.dst(lake, key).stat().st_mtime_ns
    assert run_job(j1, lake, key, src, build=False).outcome is Outcome.PASSED
    assert j1.dst(lake, key).stat().st_mtime_ns == mtime        # verify never rewrites


def test_transform_version_change_is_stale(lake):
    from dataclasses import replace
    j1 = JOBS["bars-1min"]
    (key, src), = j1.scan(lake)
    run_job(j1, lake, key, src)
    newer = replace(j1, expected=("ticks_to_bars", 99))
    state, reason = newer.state(lake, key, src)
    assert state is State.STALE and "ticks_to_bars@1" in reason


def test_hash_cache(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"abc")
    hc = HashCache(tmp_path / "c.db")
    assert hc.cached(p) is None
    h = hc.sha256(p)
    assert hc.cached(p) == h
    p.write_bytes(b"abcd")
    assert hc.cached(p) is None and hc.sha256(p) != h
