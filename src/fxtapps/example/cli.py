#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxtapps: test-app

Meant to ensure the environment can access the correct version of python and
the packages (stuff in `src/`).
"""


#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations
import sys
from datetime import datetime
from collections.abc import Sequence
from pathlib import Path
from pprint import pformat

import click
from rich import print
from rich.panel import Panel
from rich.pretty import Pretty
from rich.console import Console

#fxt
from fxt.core.geo import home_geo


__all__ = ["cli"]

console = Console()


#!================================================================================(80)
#! cli
#!--------------------------------------------------------------------------------(80)
@click.command()
@click.option("--source",     "-b", default="dukascopy", help="Data broker/source. Prompted if omitted.")
@click.option("--symbol",     "-i", default=["EURJPY", "GBPJPY"], multiple=True, help="Ticker symbol (can specify multiple this option multiple times).")
@click.option("--full/--no-full", default=False, help="If set, shows full networking info.")
def cli(
        source,
        symbol,
        full:bool
    ):
    """ 
    """
    args = {
        "source": source,
        "symbol": symbol,
        "full": full
    }

    print(Panel(
        Pretty(args),
        title="[cyan bold]Example Params from CLICK[/]", title_align="left"
    ))

    p:Panel
    if(full):
        p = Panel(
            Pretty(home_geo()),
            title="[orchid2 bold]networking (full)[/]", title_align="left"
        )
    else:
        p = Panel(
            Pretty(str(home_geo())),
            title="[green bold]networking (short)[/]", title_align="left"
        )
    print(p)
    
#



#!================================================================================(80)
#! gogogogog
#!--------------------------------------------------------------------------------(80)
def main() -> None:
    try:
        cli()
    except KeyboardInterrupt:              # InquirerPy prompts raise this on ctrl-c
        console.print("\n[orchid2]KeyboardInterrupt[/]: canceled.")
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()

