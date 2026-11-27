#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxtapps: research

One entry point for every research project. Projects are found by package
layout, so adding a project needs no registration here:

    fxtapps/research/<group>/<project>/cli.py     must define a click command `cli`

    pixi run research list
    pixi run research <group> <project> [ARGS...]
    pixi run research examples p00_smoke --help
"""


#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

import click
from rich.console import Console
from rich.table import Table

from fxt.research.paths import APPS_PACKAGE, RESERVED_GROUPS, RESERVED_PROJECTS, SLUG_RE

__all__ = ["cli", "discover", "main"]

console = Console()


#!================================================================================(80)
#! discovery
#!--------------------------------------------------------------------------------(80)
def _subpackages(pkg: ModuleType, reserved: frozenset[str]) -> list[str]:
    return sorted(
        m.name for m in pkgutil.iter_modules(pkg.__path__)
        if m.ispkg and m.name not in reserved and SLUG_RE.match(m.name)
    )


def discover() -> dict[str, list[str]]:
    """ {group: [project, ...]} from the package tree; doesn't import project code. """
    root = importlib.import_module(APPS_PACKAGE)
    found: dict[str, list[str]] = {}
    for group in _subpackages(root, RESERVED_GROUPS):
        gpkg = importlib.import_module(f"{APPS_PACKAGE}.{group}")
        found[group] = _subpackages(gpkg, RESERVED_PROJECTS)
    return found


def _load_project_cli(group: str, project: str) -> click.Command:
    mod = importlib.import_module(f"{APPS_PACKAGE}.{group}.{project}.cli")
    cmd = getattr(mod, "cli", None)
    if not isinstance(cmd, click.Command):
        raise click.ClickException(f"{mod.__name__} has no click command named `cli`")
    return cmd


#!================================================================================(80)
#! cli
#!--------------------------------------------------------------------------------(80)
class _GroupCommands(click.Group):
    """ `research <group> <project> ...`: projects load only when invoked. """

    def __init__(self, group: str, projects: list[str]):
        super().__init__(name=group, help=f"Projects in group `{group}`.")
        self._group = group
        self._projects = projects

    def list_commands(self, ctx):
        return list(self._projects)

    def get_command(self, ctx, name):
        if name not in self._projects:
            return None
        return _load_project_cli(self._group, name)


class _ResearchCommands(click.Group):
    def list_commands(self, ctx):
        return [*super().list_commands(ctx), *discover().keys()]

    def get_command(self, ctx, name):
        if (cmd := super().get_command(ctx, name)) is not None:
            return cmd
        projects = discover().get(name)
        return _GroupCommands(name, projects) if projects is not None else None


@click.group(cls=_ResearchCommands)
def cli():
    """ Research projects: `research <group> <project> ...` """


@cli.command("list")
def list_projects():
    """ Every group/project and where its data goes. """
    from fxt.research.paths import Project

    table = Table(title="research projects", title_justify="left")
    table.add_column("group", style="cyan")
    table.add_column("project", style="green")
    table.add_column("data")
    for group, projects in discover().items():
        if not projects:
            table.add_row(group, "[dim](none)[/]", "")
        for pid in projects:
            table.add_row(group, pid, str(Project(group, pid).paths().root))
    console.print(table)


#!================================================================================(80)
#! gogogogog
#!--------------------------------------------------------------------------------(80)
def main() -> None:
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n[orchid2]KeyboardInterrupt[/]: canceled.")
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
