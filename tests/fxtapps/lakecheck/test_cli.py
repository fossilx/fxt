from __future__ import annotations

from datetime import date

import pytest
from click.testing import CliRunner

import fxt.data.lake_check as lc
from fxt.data.refdata import LakeRequirement
from fxtapps.lakecheck.cli import cli


@pytest.fixture(autouse=True)
def only_audcad(monkeypatch):
    base = dict(source="dukascopy", market="forex", symbol=None)
    rows = [LakeRequirement(**base, tier="raw", interval="TICK", first_year=2012, last_year=2013),
            LakeRequirement(**base, tier="derived", interval="1MIN", last_year=2013),
            LakeRequirement(**base, tier="derived", interval="1HOUR", last_year=2013)]
    monkeypatch.setattr(lc, "required_datasets",
                        lambda: {("dukascopy", "forex", "AUDCAD"): {r.key: r for r in rows}})


def invoke(lake, *args):
    return CliRunner().invoke(cli, ["--lake", str(lake.root), *args], terminal_width=200)


def test_summary_and_fixes(small_lake):
    r = invoke(small_lake, "--fixes")
    assert r.exit_code == 1, r.output
    assert "missing 2012" in r.output                                # raw 2012 not consolidated
    assert "pixi run ingest consolidate -i AUDCAD -y 2012" in r.output
    assert "pixi run derive build bars-1min -i AUDCAD -y 2013" in r.output
    assert r.output.index("ingest consolidate") < r.output.index("derive build")


def test_details_and_filters(small_lake):
    r = invoke(small_lake, "--details", "-y", "2013", "-i", "audcad")
    assert r.exit_code == 1 and "blocked" in r.output and "2012" not in r.output
    r = invoke(small_lake, "-i", "EURJPY")
    assert r.exit_code == 0 and "nothing to check" in r.output


def test_fix_years_as_range():
    from fxtapps.lakecheck.cli import _years_arg
    from fxtapps.ingest.options import YEARS
    assert _years_arg([2016, 2014, 2015]) == "2014-2016"
    assert _years_arg([2014, 2016]) == "2014,2016"
    assert YEARS.convert("2014-2016", None, None) == [2014, 2015, 2016]    # the CLI accepts it
