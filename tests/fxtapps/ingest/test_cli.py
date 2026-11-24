"""
fxtapps.ingest CLI skeleton: option parsing, choice sources, --auto errors,
and the request each handler receives (handlers are monkeypatched).
"""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from click.testing import CliRunner

from fxtapps.ingest import cli as cli_mod
from fxtapps.ingest import handlers
from fxtapps.ingest.request import ConsolidateRequest, DownloadRequest, RunRequest, VerifyRequest
from fxtapps.ingest.resolve import Resolver


@pytest.fixture
def calls(monkeypatch):
    got: dict[str, object] = {}
    for name in ("download", "consolidate", "verify"):
        monkeypatch.setattr(handlers, name, lambda req, _n=name: got.__setitem__(_n, req))
    return got


@pytest.fixture
def root(tmp_path):
    """ data root with AUDCAD 2013-2014 and EURJPY 2014 TICK downloads + one unknown dir """
    dl = tmp_path / "ingest/downloads/dukascopy/forex"
    for sym, years in {"AUDCAD": (2013, 2014), "EURJPY": (2014,), "NOTREAL": (2014,)}.items():
        for y in years:
            (dl / sym / "TICK" / str(y) / "01").mkdir(parents=True)
    return tmp_path


def invoke(root, *args):
    return CliRunner().invoke(cli_mod.cli, ["--root", str(root), *args], catch_exceptions=False)


#! ---- download -----------------------------------------------------------------
def test_download_normalizes_symbols_and_years(root, calls):
    r = invoke(root, "download", "-i", "aud/cad,EUR-JPY", "-i", "AUDCAD", "-t", "TICK",
               "-y", "2020-2021", "--auto")
    assert r.exit_code == 0, r.output
    req = calls["download"]
    assert isinstance(req, DownloadRequest)
    assert req.symbols == ("AUDCAD", "EURJPY")          # official names, duplicates dropped
    assert (req.source, req.market, req.interval) == ("dukascopy", "forex", "TICK")
    assert (req.start, req.end) == (date(2020, 1, 1), date(2022, 1, 1))
    assert req.downloads_dir == root / "ingest/downloads"


def test_download_all_symbols_comes_from_refdata(root, calls):
    r = invoke(root, "download", "-i", "ALL", "-t", "TICK", "-y", "2024", "--auto")
    assert r.exit_code == 0, r.output
    assert len(calls["download"].symbols) == 28


def test_download_end_capped_at_today(root, calls):
    r = invoke(root, "download", "-i", "AUDCAD", "-t", "TICK", "-s", "2026-01-01",
               "-e", "2999-01-01", "--auto")
    assert r.exit_code == 0, r.output
    assert calls["download"].end == datetime.now(UTC).date()


@pytest.mark.parametrize("args, msg", [
    (["-i", "AUDCAD", "-t", "TICK"], "Missing -y/--years or -s/--start"),
    (["-t", "TICK", "-y", "2024"], "Missing -i/--symbol"),
    (["-i", "AUDCAD", "-t", "TICK", "-y", "ALL"], "-y ALL isn't allowed"),
    (["-i", "AUDCAD", "-t", "TICK", "-y", "2020,2022"], "contiguous"),
    (["-i", "AUDCAD", "-t", "TICK", "-y", "2024", "-s", "2024-01-01"], "not both"),
    (["-i", "XXXYYY", "-t", "TICK", "-y", "2024"], "unknown symbol"),
    (["-i", "ALL,AUDCAD", "-t", "TICK", "-y", "2024"], "can't be combined"),
])
def test_download_auto_errors(root, calls, args, msg):
    r = CliRunner().invoke(cli_mod.cli, ["--root", str(root), "download", *args, "--auto"])
    assert r.exit_code == 2 and msg in r.output, r.output
    assert "download" not in calls


#! ---- consolidate / verify -------------------------------------------------------
def test_consolidate_choices_come_from_disk(root, calls):
    r = invoke(root, "consolidate", "-i", "ALL", "-y", "ALL", "--auto")
    assert r.exit_code == 0, r.output
    req = calls["consolidate"]
    assert isinstance(req, ConsolidateRequest)
    assert req.symbols == ("AUDCAD", "EURJPY")      # NOTREAL ignored (refdata doesn't know it)
    assert req.interval == "TICK"                   # only interval on disk -> auto-picked
    assert req.years == (2013, 2014) and req.force is False   # ALL -> years on disk


def test_consolidate_rejects_symbol_not_downloaded(root, calls):
    r = CliRunner().invoke(cli_mod.cli, ["--root", str(root), "consolidate", "-i", "GBPUSD",
                                         "-y", "ALL", "--auto"])
    assert r.exit_code == 2 and "Not downloaded: GBPUSD" in r.output


def test_consolidate_years_missing_with_auto(root, calls):
    r = CliRunner().invoke(cli_mod.cli, ["--root", str(root), "consolidate", "-i", "AUDCAD", "--auto"])
    assert r.exit_code == 2 and "2013, 2014" in r.output


def test_verify_single_year_on_disk_is_auto_picked(root, calls):
    r = invoke(root, "verify", "-i", "EURJPY", "--auto")
    assert r.exit_code == 0, r.output
    assert isinstance(calls["verify"], VerifyRequest) and calls["verify"].years == (2014,)


#! ---- run --------------------------------------------------------------------------
def test_run_chains_all_three(root, calls):
    r = invoke(root, "run", "-i", "EURJPY", "-t", "TICK", "-y", "2014", "--force", "--auto")
    assert r.exit_code == 0, r.output
    assert isinstance(calls["download"], RunRequest)
    assert calls["consolidate"].years == (2014,) and calls["consolidate"].force
    assert calls["verify"].years == (2014,)


#! ---- prompts (answered by injected pickers) ----------------------------------------
def test_resolver_prompts_when_interactive(root):
    asked: list[str] = []
    r = Resolver(scope="downloads", downloads=root / "ingest/downloads", interactive=True,
                 pick_one=lambda m, ch: (asked.append(m), ch[0])[1],
                 pick_many=lambda m, ch: (asked.append(m), [ch[-1]])[1])
    src = r.source(None)                                # one source -> no prompt
    mkt = r.market(None, src, [])                       # one market -> no prompt
    syms = r.symbols([], src, mkt)                      # two on disk -> prompt
    iv = r.interval(None, src, mkt, syms)               # one on disk -> no prompt
    assert (src, mkt, syms, iv) == ("dukascopy", "forex", ["EURJPY"], "TICK")
    assert len(asked) == 1 and "SYMBOL" in asked[0]


def test_resolver_prompts_start_then_optional_end(root):
    asked: list[tuple[str, str | None]] = []
    def pick_day(msg, default):
        asked.append((msg, default))
        return date(2024, 1, 1) if default is None else datetime.now(UTC).date()
    r = Resolver(scope="refdata", downloads=root, interactive=True, pick_day=pick_day)
    s, e = r.days(None, None, None)
    assert (s, e) == (date(2024, 1, 1), datetime.now(UTC).date())
    assert [d for _, d in asked] == [None, "today"]          # END prompt pre-filled with today


def test_resolver_start_given_end_not_prompted(root):
    r = Resolver(scope="refdata", downloads=root, interactive=True,
                 pick_day=lambda m, d: pytest.fail("should not prompt"))
    assert r.days(None, "2024-01-01", None) == (date(2024, 1, 1), datetime.now(UTC).date())


def test_consolidate_explicit_year_not_on_disk(root, calls):
    r = CliRunner().invoke(cli_mod.cli, ["--root", str(root), "consolidate", "-i", "AUDCAD",
                                         "-y", "2013,2020", "--auto"])
    assert r.exit_code == 2 and "Not downloaded: 2020" in r.output


def test_years_prompt_all_expands(root):
    r = Resolver(scope="downloads", downloads=root / "ingest/downloads", interactive=True,
                 pick_many=lambda m, ch: [ch[0]])              # highlight "ALL", press enter
    assert r.years(None, "dukascopy", "forex", ["AUDCAD", "EURJPY"], "TICK") == (2013, 2014)


def test_years_prompt_specific(root):
    r = Resolver(scope="downloads", downloads=root / "ingest/downloads", interactive=True,
                 pick_many=lambda m, ch: ["2014"])
    assert r.years(None, "dukascopy", "forex", ["AUDCAD"], "TICK") == (2014,)


#! ---- consolidate, end to end (real handler) ----------------------------------------
def test_consolidate_end_to_end(tmp_path, fake_downloads, monkeypatch):
    from datetime import date as _date

    import fxt.data.ingest.consolidate as con
    from fxt.data.models import RawMeta

    fake_downloads.week()
    real = con.consolidate_year
    monkeypatch.setattr(handlers, "consolidate_year",
                        lambda *a, **k: real(*a, **k, today=_date(2013, 1, 7),
                                             meta_io=fake_downloads.meta_io))

    r = invoke(tmp_path, "consolidate", "-i", "audcad", "-y", "ALL", "--auto")
    assert r.exit_code == 0, r.output
    assert "written" in r.output
    out = tmp_path / "lake/raw/source=dukascopy/market=forex/symbol=AUDCAD/interval=TICK/year=2013/AUDCAD-2013.parquet"
    assert fake_downloads.meta_io.read_meta_as(out, RawMeta).passed

    r = CliRunner().invoke(cli_mod.cli, ["--root", str(tmp_path), "consolidate", "-i", "AUDCAD",
                                         "-y", "2013", "--auto"])
    assert r.exit_code == 0 and "exists" in r.output


def test_consolidate_failed_check_exits_1(tmp_path, fake_downloads):
    fake_downloads.week()                         # real "today": most of 2013 has no manifest rows
    r = CliRunner().invoke(cli_mod.cli, ["--root", str(tmp_path), "consolidate", "-i", "AUDCAD",
                                         "-y", "2013", "--auto"])
    assert r.exit_code == 1 and "coverage" in r.output
