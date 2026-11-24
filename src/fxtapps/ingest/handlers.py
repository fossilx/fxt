#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxtapps.ingest.handlers

The work behind each subcommand. PLACEHOLDERS for now: each prints the request
it received. Each will become a thin call into fxt.data.ingest (download.py,
consolidate.py, verify.py) plus progress display; no ingest logic lives here.
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

from rich.console import Console
from rich.table import Table

from fxt.data.ingest.consolidate import ConsolidateError, YearResult, consolidate_year

from .request import ConsolidateRequest, DownloadRequest, RunRequest, VerifyRequest

__all__ = ["download", "consolidate", "verify", "run"]

console = Console()


def _todo(name: str, req: object) -> None:
    console.print(f"[yellow]TODO[/] [bold]{name}[/] not implemented yet; would run with:")
    console.print(req)


#!================================================================================(80)
#! handlers
#!--------------------------------------------------------------------------------(80)
def download(req: DownloadRequest) -> None:
    #! for key in req.keys: fxt.data.ingest.download(key, req.start, req.end, root=req.downloads_dir, dry=req.dry)
    _todo("download", req)

_STATUS_STYLE = {"written": "green", "dry": "cyan", "exists": "dim", "no-data": "dim"}


def _checks_cell(r: YearResult) -> str:
    if r.status in ("exists", "no-data"):
        return ""
    bad = [c for c in r.checks if not c.ok]
    warn = [c for c in r.checks if c.status == "warn"]
    parts = [f"[red]FAIL {c.name}[/]: {c.detail}" for c in bad]
    parts += [f"[yellow]warn {c.name}[/]: {c.detail}" for c in warn]
    return "\n".join(parts) if parts else f"[green]{len(r.checks)} passed[/]"


def consolidate(req: ConsolidateRequest) -> bool:
    """ Every (symbol, year) in the request; one year failing doesn't stop the rest.
        Returns False if any year errored or failed a check.
    """
    table = Table(title="consolidate" + (" (dry run)" if req.dry else ""), title_justify="left")
    for col in ("symbol", "year", "status", "rows", "days", "checks"):
        table.add_column(col, justify="right" if col in ("year", "rows", "days") else "left")

    ok = True
    for key in req.keys:
        for year in req.years:
            with console.status(f"{key.symbol} {year}") as status:
                try:
                    r = consolidate_year(key, year, downloads=req.downloads_dir, lake_dir=req.lake_dir,
                                         force=req.force, dry=req.dry,
                                         log=lambda m: status.update(m))
                except ConsolidateError as e:
                    ok = False
                    table.add_row(key.symbol, str(year), "[red]error[/]", "", "", f"[red]{e}[/]")
                    continue
            ok &= r.passed
            style = _STATUS_STYLE[r.status] if r.passed else "red"
            table.add_row(key.symbol, str(year), f"[{style}]{r.status}[/]",
                          f"{r.rows:,}" if r.rows else "", str(r.days or ""), _checks_cell(r))
    console.print(table)
    return ok

def verify(req: VerifyRequest) -> None:
    _todo("verify", req)

def run(req: RunRequest) -> bool:
    """ download -> consolidate -> verify; stops at the first stage that fails. """
    if download(req) is False:
        return False
    if consolidate(req.consolidate()) is False:
        return False
    return verify(req.verify()) is not False
#-
