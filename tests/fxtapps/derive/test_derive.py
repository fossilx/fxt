"""
fxtapps.derive: CLI (list/status/build) and the Textual picker (headless).
"""
from __future__ import annotations

import pytest
from click.testing import CliRunner

from fxtapps.derive.cli import cli


def invoke(lake, *args):
    return CliRunner().invoke(cli, ["--lake", str(lake.root), *args], terminal_width=160)


def test_list(small_lake):
    r = invoke(small_lake, "list")
    assert r.exit_code == 0, r.output
    assert "bars-1min" in r.output and "bars-1hour" in r.output


def test_build_chain_then_skip_then_rebuild(small_lake):
    r = invoke(small_lake, "build", "ALL", "-i", "audcad", "-y", "ALL", "--auto")
    assert r.exit_code == 0, r.output
    assert r.output.count("PASSED") == 2                # 1MIN then 1HOUR from the fresh 1MIN

    r = invoke(small_lake, "status", "ALL", "-i", "ALL", "-y", "2013", "--auto")
    assert r.exit_code == 0 and r.output.count("current") >= 2, r.output

    r = invoke(small_lake, "build", "ALL", "-i", "ALL", "-y", "ALL", "--auto")
    assert r.exit_code == 0 and "PASSED" not in r.output        # all current: nothing to do

    r = invoke(small_lake, "build", "bars-1min", "-i", "ALL", "-y", "ALL", "--rebuild", "--auto")
    assert r.exit_code == 0 and r.output.count("PASSED") == 1

    r = invoke(small_lake, "build", "bars-1hour", "-i", "ALL", "-y", "ALL", "--dry", "--auto")
    assert "would build" in r.output                     # 1MIN was rebuilt: 1HOUR is stale


def test_verify_only(small_lake):
    assert invoke(small_lake, "build", "bars-1min", "-i", "ALL", "-y", "ALL", "--auto").exit_code == 0
    r = invoke(small_lake, "build", "bars-1min", "-i", "ALL", "-y", "ALL", "--verify", "--auto")
    assert r.exit_code == 0 and "PASSED" in r.output and "(verify)" in r.output


@pytest.mark.parametrize("args, msg", [
    (["build"], "Name a job"),
    (["build", "nope", "-i", "ALL", "-y", "ALL", "--auto"], "unknown job"),
    (["build", "bars-1min", "-i", "ALL", "-y", "2099", "--auto"], "nothing matches"),
    (["build", "bars-1min", "-i", "EURJPY", "-y", "ALL", "--auto"], "no input for EURJPY"),
])
def test_usage_errors(small_lake, args, msg):
    r = invoke(small_lake, *args)
    assert r.exit_code == 2 and msg in r.output, r.output


def test_picker_headless(small_lake):
    pytest.importorskip("textual")
    import asyncio

    from fxt.data.derived.jobs import JOBS, State
    from fxtapps.derive.picker import LakePicker

    async def go():
        app = LakePicker(JOBS["bars-1min"], lake=small_lake)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert len(app.entries) == 1
            entry = app.entries[0]
            assert app._state(entry)[0] is State.MISSING
            app.marked[entry.path] = entry
            await pilot.press("ctrl+r")
            for _ in range(200):                         # wait for the worker thread
                await pilot.pause(0.05)
                if not app.busy and app.reports:
                    break
            report, _, outcome = app.reports[entry.path]
            assert outcome.value == "PASSED", report.failed
            assert app._state(entry, refresh=True)[0] is State.CURRENT
    asyncio.run(go())
