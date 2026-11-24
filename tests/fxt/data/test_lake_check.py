from __future__ import annotations

import os
from datetime import date

from fxt.data.derived.jobs import JOBS, run_job
from fxt.data.lake_check import check_lake, compress_years, expected_years
from fxt.data.refdata import LakeRequirement

TODAY = date(2013, 6, 1)


def reqs(first=2013, last=None, extra=()):
    base = dict(source="dukascopy", market="forex", symbol=None)
    rows = [LakeRequirement(**base, tier="raw", interval="TICK", first_year=first, last_year=last),
            LakeRequirement(**base, tier="derived", interval="1MIN"),
            LakeRequirement(**base, tier="derived", interval="1HOUR"), *extra]
    return {("dukascopy", "forex", "AUDCAD"): {r.key: r for r in rows}}


def by(findings):
    return {(f.tier, f.interval, f.year): f for f in findings}


def test_compress_and_expected_years():
    assert compress_years([2018, 2013, 2014, 2015]) == "2013-2015, 2018"
    r = LakeRequirement(source="s", market="m", tier="derived", interval="1MIN")
    raw = LakeRequirement(source="s", market="m", tier="raw", interval="TICK", first_year=2012)
    on_disk = {"TICK": {2014, 2016}}
    assert expected_years(r, on_disk, date(2016, 3, 1)) == [2014, 2015, 2016]        # first raw on disk
    assert expected_years(r, on_disk, date(2016, 3, 1), [raw]) == [2012, 2013, 2014, 2015, 2016]
    assert expected_years(r, {}, TODAY) == []


def test_raw_ok_derived_missing_then_blocked(small_lake):
    f = by(check_lake(small_lake, datasets=reqs(), today=TODAY))
    assert f[("raw", "TICK", 2013)].status == "ok"
    assert f[("derived", "1MIN", 2013)].status == "missing"
    assert "derive build bars-1min -i AUDCAD -y 2013" in f[("derived", "1MIN", 2013)].fix
    assert f[("derived", "1HOUR", 2013)].status == "blocked"          # its 1MIN input is missing


def test_missing_raw_years_and_fix(small_lake):
    f = by(check_lake(small_lake, datasets=reqs(first=2011), today=TODAY))
    assert f[("raw", "TICK", 2011)].status == "missing"
    assert f[("raw", "TICK", 2011)].fix == "pixi run ingest consolidate -i AUDCAD -y 2011"
    assert f[("derived", "1MIN", 2011)].status == "blocked"           # derived years follow raw


def test_all_ok_after_build_then_stale(small_lake):
    for name in ("bars-1min", "bars-1hour"):
        (key, src), = JOBS[name].scan(small_lake)
        assert run_job(JOBS[name], small_lake, key, src).outcome.value == "PASSED"
    findings = check_lake(small_lake, datasets=reqs(), today=TODAY)
    assert {f.status for f in findings} == {"ok"}

    (key, src), = JOBS["bars-1min"].scan(small_lake)
    with open(src, "ab") as fh:                                       # raw changes in place
        fh.write(b"\0")
    os.utime(src, ns=(1, 1))
    f = by(check_lake(small_lake, datasets=reqs(), today=TODAY))
    assert f[("derived", "1MIN", 2013)].status == "stale"
    quick = by(check_lake(small_lake, datasets=reqs(), today=TODAY, verify_inputs=False))
    assert quick[("derived", "1MIN", 2013)].status == "ok"            # --quick can't see it


def test_filters(small_lake):
    assert check_lake(small_lake, datasets=reqs(), today=TODAY, symbols={"EURJPY"}) == []
    f = check_lake(small_lake, datasets=reqs(first=2011), today=TODAY, years={2013})
    assert {x.year for x in f} == {2013}
