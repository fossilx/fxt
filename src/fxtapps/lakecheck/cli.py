#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxtapps.lakecheck: is everything refdata's lake_requirements asks for in the lake?

    pixi run lake-check                         every required data set, all years
    pixi run lake-check -i EURJPY,GBPJPY -y 2020-2024
    pixi run lake-check --details               one row per (data set, year), ok ones too
    pixi run lake-check --fixes                 commands that would fix the problems
    pixi run lake-check --quick                 don't hash inputs (can't see changed inputs)

Exit code 1 if anything isn't ok. Requirements: fxt/data/refdata/sql/lake-requirements.sql.
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text

from fxt.data.lake_check import Finding, check_lake, compress_years
from fxt.data.paths import Lake

from fxtapps.ingest.options import ALL, YEARS, split_symbols

__all__ = ["cli"]

console = Console()
STYLE = {"ok": "green", "missing": "red", "failed": "red", "stale": "yellow", "blocked": "magenta"}
ORDER = ("missing", "failed", "stale", "blocked")


def _years_arg(years: list[int]) -> str:
    """ -y value the YEARS option accepts: 2014-2026 if contiguous, else 2014,2016 """
    ys = sorted(set(years))
    if len(ys) > 1 and ys == list(range(ys[0], ys[-1] + 1)):
        return f"{ys[0]}-{ys[-1]}"
    return ",".join(map(str, ys))


def _fixes(findings: list[Finding]) -> list[str]:
    """ One command per (command prefix, symbol), years merged: -y 2019,2020 """
    grouped: dict[tuple[str, str], list[int]] = defaultdict(list)
    singles: list[str] = []
    for f in findings:
        if not f.fix:
            continue
        if f.year is None or f" -y {f.year}" not in f.fix:
            singles.append(f.fix)
            continue
        head, tail = f.fix.split(f" -y {f.year}", 1)
        grouped[(head, tail)].append(f.year)
    cmds = [f"{head} -y {_years_arg(ys)}{tail}" for (head, tail), ys in grouped.items()]
    return sorted(set(cmds + singles), key=lambda c: (" derive " in c, c))   # ingest fixes first


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--lake", "lake_dir", type=click.Path(path_type=Path, file_okay=False), default=None,
    help="Lake root (default: settings paths.lake).")
@click.option("-i", "--symbol", "symbols", multiple=True,
    help="Only these symbols (repeat or comma-separate). Default: all.")
@click.option("-y", "--years", type=YEARS, default=None, help="Only these years. Default: all.")
@click.option("--details", is_flag=True, default=False, help="One row per (data set, year).")
@click.option("--fixes", is_flag=True, default=False, help="Print commands that would fix the problems.")
@click.option("--quick", is_flag=True, default=False,
    help="Don't hash inputs: faster, but a changed input isn't seen as stale.")
def cli(lake_dir, symbols, years, details, fixes, quick) -> None:
    """ Check the lake against refdata's lake_requirements. """
    if lake_dir is None:
        from fxt.services import get_lake
        lake = get_lake()
    else:
        lake = Lake(root=lake_dir.expanduser().resolve())

    syms = split_symbols(symbols)
    sym_filter = None if not syms or any(s.upper() == ALL for s in syms) else \
        {"".join(c for c in s if c.isalnum()).upper() for s in syms}
    year_filter = None if years in (None, ALL) else set(years)

    with console.status("checking") as spinner:
        findings = check_lake(lake, symbols=sym_filter, years=year_filter, verify_inputs=not quick,
                              on_progress=lambda m: spinner.update(f"checking {m}"))
    if not findings:
        console.print("[yellow]nothing to check: no requirements match[/]")
        return

    if details:
        t = Table(title=f"lake check  ({lake.root})", title_justify="left")
        for col in ("symbol", "tier", "interval", "year", "status", "reason"):
            t.add_column(col, justify="right" if col == "year" else "left")
        for f in findings:
            t.add_row(f.symbol, f.tier, f.interval, str(f.year or ""), Text(f.status, STYLE[f.status]), f.reason)
        console.print(t)
    else:
        by_ds: dict[tuple, list[Finding]] = defaultdict(list)
        for f in findings:
            by_ds[f.dataset].append(f)
        t = Table(title=f"lake check  ({lake.root})", title_justify="left")
        for col in ("symbol", "tier", "interval", "years", "ok", "problems"):
            t.add_column(col, justify="right" if col == "ok" else "left")
        for ds, fs in by_ds.items():
            yrs = [f.year for f in fs if f.year is not None]
            problems = Text()
            for st in ORDER:
                bad = [f for f in fs if f.status == st]
                if bad:
                    if problems:
                        problems.append(" · ")
                    when = compress_years(f.year for f in bad if f.year is not None) or bad[0].reason
                    problems.append(f"{st} {when}", STYLE[st])
            n_ok = sum(f.status == "ok" for f in fs)
            t.add_row(ds[2], ds[3], ds[4], compress_years(yrs), Text(str(n_ok), "green" if n_ok == len(fs) else ""),
                      problems)
        console.print(t)

    counts = {st: sum(f.status == st for f in findings) for st in ("ok", *ORDER)}
    console.print("  " + "  ".join(f"[{STYLE[s]}]{n} {s}[/]" for s, n in counts.items() if n))
    bad = [f for f in findings if f.status != "ok"]
    if fixes and bad:
        console.print("\n[bold]fixes[/] (derived builds after the ingest ones; blocked/failed rows need a look):")
        for c in _fixes(bad):
            console.print(f"  {c}", soft_wrap=True, highlight=False)   # copy-pasteable: no wrapping
    if bad:
        raise SystemExit(1)


def main() -> None:
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n[orchid2]KeyboardInterrupt[/]: canceled.")
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
