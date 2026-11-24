#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxtapps.ingest: download, consolidate and verify source data.

    pixi run ingest --help
    pixi run ingest download    -i AUDCAD,EURJPY -y 2024
    pixi run ingest consolidate -i ALL -y ALL --auto
    pixi run ingest verify      -i EURJPY
    pixi run ingest run         -i EURJPY -s 2026-01-01

Every subcommand follows the same steps:
    click values -> Resolver (fills gaps: only choice / prompt / error)
                 -> request model (refdata-official names, validated)
                 -> confirm (skipped with --auto) -> handler
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import click
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty

from fxt.settings import get_settings

from . import handlers
from .options import common_options, split_symbols
from .request import ConsolidateRequest, DownloadRequest, IngestRequest, RunRequest, VerifyRequest
from .resolve import Resolver, Scope

__all__ = ["cli"]

console = Console()


@dataclass(frozen=True)
class AppContext:
    data_root: Path
    verbose: int


#!================================================================================(80)
#! shared flow
#!--------------------------------------------------------------------------------(80)
def _resolve_common(app: AppContext, scope: Scope, *, source, market, symbols, interval,
                    auto) -> tuple[Resolver, dict]:
    r = Resolver(scope=scope, downloads=app.data_root / "ingest" / "downloads", auto=auto)
    syms = split_symbols(symbols)
    src = r.source(source)
    mkt = r.market(market, src, syms)
    names = r.symbols(syms, src, mkt)
    iv = r.interval(interval, src, mkt, names)
    return r, {"data_root": app.data_root, "source": src, "market": mkt,
               "interval": iv, "symbols": tuple(names)}


def _build(model: type[IngestRequest], **fields) -> IngestRequest:
    try:
        return model(**fields)
    except (ValidationError, KeyError, LookupError) as e:
        raise click.UsageError(str(e)) from None


def _confirm_and_run(req: IngestRequest, handler) -> None:
    title = f"[cyan bold]{type(req).__name__}[/]" + ("  [yellow](dry run)[/]" if req.dry else "")
    console.print(Panel(Pretty(req.model_dump(exclude={"auto"})), title=title, title_align="left"))
    if not req.auto and not click.confirm("Continue?", default=True):
        raise click.Abort()
    if handler(req) is False:          # a stage reported errors / failed checks
        raise SystemExit(1)


#!================================================================================(80)
#! group
#!--------------------------------------------------------------------------------(80)
@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--root", type=click.Path(path_type=Path, file_okay=False), default=None,
    help="Data root holding ingest/ and lake/ (default: settings paths.data).")
@click.option("-v", "--verbose", count=True, help="-v info, -vv debug.")
@click.pass_context
def cli(ctx: click.Context, root: Path | None, verbose: int) -> None:
    """ Download, consolidate and verify source data. """
    logging.basicConfig(level=[logging.WARNING, logging.INFO, logging.DEBUG][min(verbose, 2)])
    ctx.obj = AppContext(data_root=(root or get_settings().paths.data).expanduser().resolve(),
                         verbose=verbose)


#!================================================================================(80)
#! subcommands
#!--------------------------------------------------------------------------------(80)
@cli.command()
@common_options
@click.option("-s", "--start", default=None, help="First day, e.g. 2024-01-01 (instead of -y).")
@click.option("-e", "--end", default=None,
    help="Day after the last day to download (default and cap: today, UTC).")
@click.pass_obj
def download(app: AppContext, source, market, symbols, interval, years, dry, auto, start, end):
    """ Fetch daily files from a source into ingest/downloads.
        Symbols/intervals come from refdata (what the source provides).
    """
    r, common = _resolve_common(app, "refdata", source=source, market=market, symbols=symbols,
                                interval=interval, auto=auto)
    s, e = r.days(years, start, end)
    req = _build(DownloadRequest, **common, start=s, end=e, dry=dry, auto=auto)
    _confirm_and_run(req, handlers.download)


@cli.command()
@common_options
@click.option("--force", is_flag=True, default=False, help="Replace years already in lake/raw.")
@click.pass_obj
def consolidate(app: AppContext, source, market, symbols, interval, years, dry, auto, force):
    """ Combine daily files into yearly lake/raw files, with year checks.
        Symbols/intervals/years come from what's in ingest/downloads.
    """
    r, common = _resolve_common(app, "downloads", source=source, market=market, symbols=symbols,
                                interval=interval, auto=auto)
    ys = r.years(years, common["source"], common["market"], list(common["symbols"]), common["interval"])
    req = _build(ConsolidateRequest, **common, years=ys, force=force, dry=dry, auto=auto)
    _confirm_and_run(req, handlers.consolidate)


@cli.command()
@common_options
@click.pass_obj
def verify(app: AppContext, source, market, symbols, interval, years, dry, auto):
    """ Check downloads <-> manifests <-> lake/raw.  (placeholder) """
    r, common = _resolve_common(app, "downloads", source=source, market=market, symbols=symbols,
                                interval=interval, auto=auto)
    ys = r.years(years, common["source"], common["market"], list(common["symbols"]), common["interval"])
    req = _build(VerifyRequest, **common, years=ys, dry=dry, auto=auto)
    _confirm_and_run(req, handlers.verify)


@cli.command()
@common_options
@click.option("-s", "--start", default=None, help="First day, e.g. 2024-01-01 (instead of -y).")
@click.option("-e", "--end", default=None, help="Day after the last day (default and cap: today, UTC).")
@click.option("--force", is_flag=True, default=False, help="Replace years already in lake/raw.")
@click.pass_obj
def run(app: AppContext, source, market, symbols, interval, years, dry, auto, start, end, force):
    """ download -> consolidate -> verify, for the same symbols and days. """
    r, common = _resolve_common(app, "refdata", source=source, market=market, symbols=symbols,
                                interval=interval, auto=auto)
    s, e = r.days(years, start, end)
    req = _build(RunRequest, **common, start=s, end=e, force=force, dry=dry, auto=auto)
    _confirm_and_run(req, handlers.run)


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
