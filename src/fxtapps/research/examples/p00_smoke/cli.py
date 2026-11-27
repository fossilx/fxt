#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
examples/p00_smoke: cli

    pixi run research examples p00_smoke paths
    pixi run research examples p00_smoke init
"""
from __future__ import annotations

import click
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty

from fxtapps.research.examples.common import banner

from . import PROJECT

__all__ = ["cli"]

console = Console()


def _scope(s) -> dict:
    return {
        "data": str(s.data),
        "lake": str(s.lake.root),
        "declared": {
            name: f"{s.dir(name)}" + (f"  [{'/'.join(d.key.partitions())}]" if d.key else "  [free-form]")
            for name, d in s.declared.items()
        },
    }


@click.group()
def cli():
    """ Template project: shows where this project's data goes. """


@cli.command()
def paths():
    """ Print the project's data paths (creates nothing). """
    p = PROJECT.paths()
    console.print(Panel(
        Pretty({
            "project": PROJECT.key,
            "module": PROJECT.module,
            "root": str(p.root),
            "project data": _scope(p.data),
            "group common": _scope(p.common),
            "experiments_db": str(p.experiments_db),
            "artifacts": str(p.artifacts),
            "lockbox_db": str(p.lockbox_db),
        }),
        title=f"[cyan bold]{banner(PROJECT.key)}[/]", title_align="left",
    ))


@cli.command()
def init():
    """ Create the project's data skeleton and the group's common scope under runs/. """
    p = PROJECT.paths().ensure()
    console.print(f"[green]ok[/]: {p.root}")
    console.print(f"[green]ok[/]: {p.common.root}")
