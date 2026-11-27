from __future__ import annotations

from click.testing import CliRunner

from fxtapps.research.cli import cli, discover
from fxtapps.research.examples.p00_smoke import PROJECT


def test_discover_finds_example():
    found = discover()
    assert "p00_smoke" in found["examples"]
    assert "common" not in found["examples"]


def test_project_declares_itself_from_package_path():
    assert PROJECT.key == "examples/p00_smoke"
    assert "scratch" in PROJECT.data_dirs and "features" in PROJECT.group.data_dirs


def test_dispatch_to_project():
    r = CliRunner().invoke(cli, ["examples", "p00_smoke", "--help"])
    assert r.exit_code == 0, r.output
    assert "paths" in r.output and "init" in r.output


def test_unknown_group_or_project():
    assert CliRunner().invoke(cli, ["nope"]).exit_code != 0
    assert CliRunner().invoke(cli, ["examples", "nope"]).exit_code != 0


def test_list():
    r = CliRunner().invoke(cli, ["list"])
    assert r.exit_code == 0, r.output
    assert "p00_smoke" in r.output
