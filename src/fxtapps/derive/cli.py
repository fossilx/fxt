#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxtapps.derive: build derived lake data sets (fxt.data.derived.jobs.JOBS).

    pixi run derive list                                  jobs, in build order
    pixi run derive status bars-1min -i EURJPY            up-to-date state per file
    pixi run derive pick bars-1min                        Textual picker
    pixi run derive build bars-1min bars-1hour -i ALL -y ALL --auto
    pixi run derive build ALL -i ALL -y ALL --auto        every job, in order

`build` only builds files that aren't up to date (missing or stale) unless
--rebuild is given. Jobs run in the order given (ALL = registry order, which
is dependency order), so `bars-1min bars-1hour` rebuilds 1HOUR from fresh 1MIN.

Up to date means: output exists, checks passed, current transform version,
and the input is unchanged (sha256, cached). See fxt.data.derived.jobs.
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text

from fxt.data.derived.jobs import JOBS, DerivedJob, Outcome, State, get_job, run_job
from fxt.data.paths import Lake, PartitionKey
from fxt.term import is_term
from fxt.term.prompts import pick_fuzzy

from fxtapps.ingest.options import ALL, YEARS, split_symbols

__all__ = ["cli"]

console = Console()

STATE_STYLE = {State.CURRENT: "green", State.STALE: "yellow", State.FAILED: "red", State.MISSING: "dim"}
OUTCOME_STYLE = {Outcome.PASSED: "green", Outcome.FAILED: "red", Outcome.BLOCKED: "red",
                 Outcome.ACTION_FAILED: "bold red", Outcome.SKIPPED: "dim"}


@dataclass(frozen=True)
class AppContext:
    lake: Lake
    verbose: int


#!================================================================================(80)
#! selection
#!--------------------------------------------------------------------------------(80)
def _jobs(names: tuple[str, ...]) -> list[DerivedJob]:
    if not names:
        raise click.UsageError(f"Name a job (or ALL): {', '.join(JOBS)}")
    if any(n.upper() == ALL for n in names):
        return list(JOBS.values())
    try:
        return [get_job(n) for n in names]
    except KeyError as e:
        raise click.UsageError(str(e.args[0])) from None


def _norm_symbol(text: str, available: set[str], entries: list[PartitionKey]) -> str:
    """ Any spelling -> the lake's symbol name, via refdata when possible. """
    squashed = "".join(ch for ch in text if ch.isalnum()).upper()
    if squashed in available:
        return squashed
    try:
        from fxt.data.models import DatasetKey
        k = entries[0]
        return DatasetKey.from_refdata(k.source, k.market, text, "TICK").symbol
    except Exception:
        return squashed


def _pick_many(message: str, options: list[str]) -> list[str]:
    picked = pick_fuzzy(message, options, multiselect=True)
    return [picked] if isinstance(picked, str) else list(picked)


def select(job: DerivedJob, lake: Lake, symbols: tuple[str, ...], years, auto: bool
           ) -> list[tuple[PartitionKey, Path]]:
    """ The job's input files, filtered by -i / -y (prompting for missing ones). """
    entries = job.scan(lake)
    if not entries:
        raise click.UsageError(f"{job.name}: no input files in {lake.root} "
                               f"({job.inputs.laketype}, {job.inputs.filters})")
    can_prompt = not auto and is_term(interactive=True)
    keys = [k for k, _ in entries]

    available = sorted({k.symbol for k in keys})
    syms = split_symbols(symbols)
    if any(s.upper() == ALL for s in syms):
        chosen = set(available)
    elif syms:
        chosen = {_norm_symbol(s, set(available), keys) for s in syms}
        if missing := sorted(chosen - set(available)):
            raise click.UsageError(f"{job.name}: no input for {', '.join(missing)}")
    elif len(available) == 1:
        chosen = set(available)
    elif can_prompt:
        chosen = set(_pick_many(f"{job.name}: pick SYMBOL(s):", [ALL, *available]))
        if ALL in chosen:
            chosen = set(available)
    else:
        raise click.UsageError(f"Missing -i/--symbol (or -i ALL). Choices: {', '.join(available)}")

    yrs_on_disk = sorted({k.year for k in keys if k.symbol in chosen})
    if years == ALL:
        wanted = set(yrs_on_disk)
    elif years is not None:
        wanted = set(years)
    elif len(yrs_on_disk) == 1:
        wanted = set(yrs_on_disk)
    elif can_prompt:
        picked = _pick_many(f"{job.name}: pick YEAR(s):", [ALL, *map(str, yrs_on_disk)])
        wanted = set(yrs_on_disk) if ALL in picked else {int(y) for y in picked}
    else:
        raise click.UsageError(f"Missing -y/--years (or -y ALL). On disk: "
                               f"{', '.join(map(str, yrs_on_disk))}")

    out = [(k, p) for k, p in entries if k.symbol in chosen and k.year in wanted]
    if not out:
        raise click.UsageError(f"{job.name}: nothing matches those symbols/years")
    return out


#!================================================================================(80)
#! group
#!--------------------------------------------------------------------------------(80)
@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--lake", "lake_dir", type=click.Path(path_type=Path, file_okay=False), default=None,
    help="Lake root (default: settings paths.lake).")
@click.option("-v", "--verbose", count=True, help="-v: show job log lines.")
@click.pass_context
def cli(ctx: click.Context, lake_dir: Path | None, verbose: int) -> None:
    """ Build derived lake data sets. """
    logging.basicConfig(level=logging.WARNING)
    if lake_dir is None:
        from fxt.services import get_lake
        lake = get_lake()
    else:
        lake = Lake(root=lake_dir.expanduser().resolve())
    ctx.obj = AppContext(lake=lake, verbose=verbose)


_symbols_opt = click.option("-i", "--symbol", "symbols", multiple=True,
    help="Symbol(s): repeat or comma-separate, or ALL. Prompted if omitted.")
_years_opt = click.option("-y", "--years", type=YEARS, default=None,
    help="Year(s): 2024, 2020-2024, 2020,2023, or ALL. Prompted if omitted.")
_auto_opt = click.option("--auto", is_flag=True, default=False,
    help="Never prompt; missing values are an error.")


#!================================================================================(80)
#! commands
#!--------------------------------------------------------------------------------(80)
@cli.command("list")
@click.pass_obj
def list_jobs(app: AppContext) -> None:
    """ Jobs, in build (dependency) order. """
    t = Table(title=f"derived jobs  ({app.lake.root})", title_justify="left")
    for col in ("job", "builds", "input", "inputs found"):
        t.add_column(col)
    for j in JOBS.values():
        f = " ".join(f"{k}={v}" for k, v in j.inputs.filters.items())
        t.add_row(j.name, j.description, f"{j.inputs.laketype} {f}", str(len(j.scan(app.lake))))
    console.print(t)


@cli.command()
@click.argument("jobs", nargs=-1)
@_symbols_opt
@_years_opt
@_auto_opt
@click.pass_obj
def status(app: AppContext, jobs, symbols, years, auto) -> None:
    """ Up-to-date state of each selected file (hashes inputs once, then cached). """
    for job in _jobs(jobs):
        files = select(job, app.lake, symbols, years, auto)
        t = Table(title=job.name, title_justify="left")
        for col in ("symbol", "year", "state", "reason"):
            t.add_column(col)
        counts: dict[State, int] = {}
        with console.status(f"{job.name}: checking {len(files)} files"):
            for key, src in files:
                state, reason = job.state(app.lake, key, src)
                counts[state] = counts.get(state, 0) + 1
                t.add_row(key.symbol, str(key.year), Text(state.value, STATE_STYLE[state]), reason)
        console.print(t)
        console.print("  " + ", ".join(f"{n} {s.value}" for s, n in counts.items()))


@cli.command()
@click.argument("job")
@click.pass_obj
def pick(app: AppContext, job: str) -> None:
    """ Browse/select a job's input files in the Textual picker. """
    from .picker import LakePicker            # textual only loads for this command
    try:
        j = get_job(job)
    except KeyError as e:
        raise click.UsageError(str(e.args[0])) from None
    LakePicker(j, lake=app.lake).run()


@cli.command()
@click.argument("jobs", nargs=-1)
@_symbols_opt
@_years_opt
@click.option("--rebuild", is_flag=True, default=False,
    help="Build every selected file, even ones already up to date.")
@click.option("--force", is_flag=True, default=False,
    help="Build even if pre-checks fail (recorded in the meta).")
@click.option("--verify", "verify_only", is_flag=True, default=False,
    help="Only run the checks on existing outputs; build and stamp nothing.")
@click.option("--dry", is_flag=True, default=False, help="Show what would be built; build nothing.")
@_auto_opt
@click.pass_obj
def build(app: AppContext, jobs, symbols, years, rebuild, force, verify_only, dry, auto) -> None:
    """ Build (or --verify) the selected files of each job, in order.

        Symbols/years are chosen once, against the first job's inputs. Later
        jobs are scanned when their turn comes, since their inputs may only
        exist once an earlier job has built them (1MIN before 1HOUR).
    """
    todo = _jobs(jobs)
    first = select(todo[0], app.lake, symbols, years, auto)
    wanted = {(k.symbol, k.year) for k, _ in first}
    ok = True
    for i, job in enumerate(todo):
        files = first if i == 0 else [(k, p) for k, p in job.scan(app.lake)
                                      if (k.symbol, k.year) in wanted]
        if not files:
            console.print(f"[yellow]{job.name}: no inputs for the selection (did an earlier job fail?)[/]")
            ok = False if not dry else ok
            continue
        ok &= _run(app, job, files, rebuild=rebuild, force=force, verify_only=verify_only, dry=dry)
    if not ok:
        raise SystemExit(1)


def _run(app: AppContext, job: DerivedJob, files, *, rebuild, force, verify_only, dry) -> bool:
    t = Table(title=f"{job.name}" + (" (verify)" if verify_only else "") + (" (dry run)" if dry else ""),
              title_justify="left")
    for col in ("symbol", "year", "before", "result", "secs", "detail"):
        t.add_column(col, justify="right" if col in ("year", "secs") else "left")
    ok = True
    with console.status(f"{job.name}") as spinner:
        for key, src in files:
            spinner.update(f"{job.name} {key.symbol} {key.year}: state")
            state, reason = job.state(app.lake, key, src)
            before = Text(state.value, STATE_STYLE[state])
            todo = verify_only or rebuild or state in (State.MISSING, State.STALE)
            if dry or not todo:
                t.add_row(key.symbol, str(key.year), before,
                          "would build" if (dry and todo) else "-", "", reason)
                continue

            def log(msg: str, _k=key) -> None:
                spinner.update(f"{job.name} {_k.symbol} {_k.year}: {msg}")
                if app.verbose:
                    console.print(f"[dim]{msg}[/]")

            run = run_job(job, app.lake, key, src, build=not verify_only, force=force, log=log)
            ok &= run.outcome in (Outcome.PASSED, Outcome.SKIPPED)
            detail = ", ".join(run.report.failed) if run.report.failed else reason
            t.add_row(key.symbol, str(key.year), before,
                      Text(run.outcome.value, OUTCOME_STYLE[run.outcome]),
                      f"{run.elapsed:.1f}", detail)
    console.print(t)
    return ok


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
