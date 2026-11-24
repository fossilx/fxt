#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
One-off: convert daily download files DownloadedDataMeta@1 -> DownloadedMeta@1
in place, and sync each month's manifest.db (see fxt.data.ingest.migrate).

    pixi run migrate-downloads data/dataprep/downloads/dukascopy/forex/AUDCAD --dry
    pixi run migrate-downloads data/dataprep/downloads --workers 8

BACK UP THE DOWNLOADS FIRST. Run on a copy of one symbol before the real run.
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeRemainingColumn

from fxt.data.ingest import migrate


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, help="downloads dir (or any dir below it)")
    ap.add_argument("--dry", action="store_true", help="report only; change nothing")
    ap.add_argument("--workers", type=int, default=1, help="processes (default 1)")
    ap.add_argument("--keep-going", action="store_true",
                    help="continue past manifest errors (frame/meta mismatches always stop)")
    args = ap.parse_args()

    console = Console()
    logging.basicConfig(level=logging.WARNING)
    if not args.root.is_dir():
        console.print(f"[red]not a directory:[/] {args.root}")
        return 2

    total = sum(1 for _ in migrate.iter_downloads(args.root))
    counts: Counter[str] = Counter()
    console.print(f"{'[yellow]DRY RUN[/] ' if args.dry else ''}{total:,} files under {args.root}")

    with Progress(TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(),
                  TimeRemainingColumn(), console=console) as progress:
        task = progress.add_task("converting", total=total)

        def on_result(r: migrate.Result) -> None:
            counts[f"file {r.file}"] += 1
            counts[f"manifest {r.manifest}"] += 1
            progress.advance(task)

        def on_error(p: Path, e: BaseException) -> None:
            progress.console.print(f"[red]ERROR[/] {p}\n    {type(e).__name__}: {e}")
            progress.advance(task)

        _, errors = migrate.convert_tree(
            args.root, dry=args.dry, workers=args.workers,
            on_result=on_result, on_error=on_error, stop_on_error=not args.keep_going,
        )

    for k in sorted(counts):
        console.print(f"  {k:<24} {counts[k]:>8,}")
    console.print(f"  {'errors':<24} {len(errors):>8,}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
