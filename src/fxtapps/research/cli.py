#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxtapps: example

Example cli app structure.
"""


#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

import click
from rich import print as rprint
from rich.panel import Panel


#!================================================================================(80)
#! cli
#!--------------------------------------------------------------------------------(80)
@click.command()
# @click.option("--source",     "-b", default="dukascopy", help="Data broker/source. Prompted if omitted.")
# @click.option("--symbol",     "-i", default=["EURJPY", "GBPJPY"], multiple=True, help="Ticker symbol (can specify multiple this option multiple times).")
# @click.option("--full/--no-full", default=False, help="If set, shows full networking info.")
def cli():
    """ 
    """
    rprint(Panel(
        "[green]BASIC CLI EXAMPLE FOR: [bold]RESEARCH APPS[/][/]"
        #title="[cyan bold]Example Params from CLICK[/]", title_align="left"
    ))
#


#!================================================================================(80)
#! gogogogog
#!--------------------------------------------------------------------------------(80)
if __name__ == "__main__":
    cli()


