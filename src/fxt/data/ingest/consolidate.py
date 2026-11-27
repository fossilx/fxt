#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxt.data.ingest.consolidate

Daily download files for one (dataset, year) -> one lake/raw file:

    lake/raw/source=<s>/market=<m>/symbol=<SYM>/interval=<I>/year=<YYYY>/
        <SYM>-<YYYY>.parquet           data + RawMeta@1
        consolidated-manifest.db       the merged month manifests (lineage)

consolidated-manifest.db is self-describing:
    financial_files   every row of the month manifests; `path` is relative to
                      the downloads root (see paths_relative_to)
    manifest_info     key/value: what the file is, what its paths are relative
                      to, what it was built from and when (INFO_KEYS below)
To check an entry: <downloads root> / path, then compare its sha256 with `digest`.

Steps (consolidate_year)
    1. existing output and not force          -> "exists" (nothing read)
       no downloads for that year             -> "no-data"
    2. merge the month manifest.db files (a key in two manifests is an error)
    3. read each daily file's meta + schema (footers only, cheap)
    4. run the year checks (below); results go into RawMeta.checks
    5. unless dry: write the manifest copy, then the data with RawMeta
       (data via ParquetStore: temp file + rename; manifest the same way)

Hard errors (ConsolidateError, nothing written) are problems that make a
correct file impossible: unreadable/inconsistent manifests, files listed but
missing, wrong meta type or dataset, schemas that differ between files.

Everything else is a recorded check. Like bars, the file is written even when
a check fails: RawMeta.passed is False, and derived builds refuse it.

Year checks
    manifest   one dataset in the merged manifest
    coverage   every day except Saturdays has a manifest row with status
               success or empty, through min(year end, today); "error" rows
               and missing rows both fail
    files      every success row's file exists; extra parquet files -> WARN
    rows       manifest `rows` == each file's row count
    periods    each file's meta covers exactly its manifest day
    method     every file has the same meta `method`
    schema     the files' schema includes the core columns for the kind
    gaps       longest run of days without data: WARN >= gap_warn (3),
               FAIL >= gap_fail (7). Catches e.g. EURJPY 2012 (1 day, then
               nothing until Feb 9).
    time       no null times, sorted, all inside the year
    duplicates adjacent identical rows / rows < max_dupe_fraction (1e-6)
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

import polars as pl

from fxt.core.checks import CheckResult, Status
from fxt.core.versioned import TYPE_KEY, VersionedModelIO
from fxt.data.models import CheckRecord, DatasetKey, DownloadedMeta, RawMeta, get_meta_io
from fxt.data.paths import Lake
from fxt.data.schemas import CORE, check_schema, kind_of

from . import layout
from .manifest import (
    CONSOLIDATED_MANIFEST_NAME, MANIFEST_TABLE, ManifestError,
    find_manifests, merge_to_memory, unique_values, write_info, write_to_file,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ConsolidateError", "YearStatus", "YearResult", "Thresholds",
    "consolidate_year", "raw_paths", "missing_days", "longest_gap", "INFO_KEYS",
]

#! keys written to manifest_info, in order
INFO_KEYS = (
    "description", "format", "paths_relative_to", "paths_relative_to_help",
    "dataset", "year", "period_start", "period_end",
    "rows_table", "month_manifests", "month_manifest_paths",
    "days_success", "days_empty", "days_other", "data_file",
    "created_by", "created_at", "fxt_version",
)


def _fxt_version() -> str | None:
    try:
        from importlib.metadata import version
        return version("fxt")
    except Exception:
        return None


class ConsolidateError(RuntimeError):
    """ A correct raw file can't be built for this year; nothing was written. """


YearStatus = Literal["written", "dry", "exists", "no-data"]

@dataclass(frozen=True)
class YearResult:
    key: DatasetKey
    year: int
    status: YearStatus
    path: Path
    rows: int = 0
    days: int = 0                                   # days with data
    checks: tuple[CheckRecord, ...] = ()

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)
#

@dataclass(frozen=True)
class Thresholds:
    gap_warn: int = 3                    # days without data in a row
    gap_fail: int = 7
    max_dupe_fraction: float = 1e-6
    skip_weekdays: frozenset[int] = field(default_factory=lambda: frozenset({5}))   # Saturday
#


#!================================================================================(80)
#! helpers
#!--------------------------------------------------------------------------------(80)
def raw_paths(lake_dir: Path, key: DatasetKey, year: int) -> tuple[Path, Path]:
    """ (data file, consolidated manifest) for a raw year. """
    folder = Lake(root=lake_dir).raw.path(source=key.source, market=key.market, symbol=key.symbol,
                                     interval=key.interval, year=year, must_exist=False)
    return folder / f"{key.symbol}-{year}.parquet", folder / CONSOLIDATED_MANIFEST_NAME


def missing_days(present: set[date], start: date, end: date,
                 skip_weekdays: frozenset[int] = frozenset()) -> list[date]:
    """ Days in [start, end) not in `present`, ignoring `skip_weekdays` (Mon=0..Sun=6). """
    out, d = [], start
    while d < end:
        if d.weekday() not in skip_weekdays and d not in present:
            out.append(d)
        d += timedelta(days=1)
    return out


def longest_gap(data_days: list[date], start: date, end: date) -> tuple[int, date | None]:
    """ Longest run of days in [start, end) with no data, and the day it starts.
        Counts the stretches before the first and after the last data day too.
    """
    if not data_days:
        return (end - start).days, start
    best, at = 0, None
    prev = start - timedelta(days=1)
    for d in [*sorted(data_days), end]:
        run = (d - prev).days - 1
        if run > best:
            best, at = run, prev + timedelta(days=1)
        prev = d
    return best, at


def _sha256(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _fmt_days(days: list[date], n: int = 5) -> str:
    s = ", ".join(d.isoformat() for d in days[:n])
    return s + (f", ... (+{len(days) - n})" if len(days) > n else "")


def _rec(name: str, status: Status | str, detail: str = "", value=None) -> CheckRecord:
    return CheckRecord.from_result(name, CheckResult(status=Status(status), detail=detail, value=value))


#!================================================================================(80)
#! main
#!--------------------------------------------------------------------------------(80)
def consolidate_year(
    key: DatasetKey,
    year: int,
    *,
    downloads: Path,
    lake_dir: Path,
    force: bool = False,
    dry: bool = False,
    thresholds: Thresholds = Thresholds(),
    today: date | None = None,
    meta_io: VersionedModelIO | None = None,
    log: Callable[[str], None] = logger.info,
) -> YearResult:
    """ Build (or with dry=True, only check) the lake/raw file for one year. """
    io = meta_io or get_meta_io()
    today = today or datetime.now(UTC).date()
    out_path, out_manifest = raw_paths(lake_dir, key, year)

    #! 1. skip cases
    if out_path.exists() and not force:
        return YearResult(key, year, "exists", out_path)
    src_dir = layout.year_dir(downloads, key, year)
    manifests = find_manifests(src_dir)
    if not manifests:
        return YearResult(key, year, "no-data", out_path)

    #! 2. manifests
    log(f"{key.symbol} {year}: merging {len(manifests)} manifests")
    try:
        mem = merge_to_memory(manifests, base=downloads, on_conflict="error")
    except Exception as e:
        raise ConsolidateError(f"{key.symbol} {year}: manifests: {type(e).__name__}: {e}") from e

    rows = list(mem[MANIFEST_TABLE].rows)
    by_day: dict[date, dict] = {}
    for r in rows:
        try:
            by_day[date.fromisoformat(str(r["id"]))] = r
        except ValueError as e:
            raise ConsolidateError(f"{key.symbol} {year}: manifest id {r['id']!r} isn't a day") from e
    success = {d: r for d, r in by_day.items() if r["status"] == "success"}
    if not success:
        raise ConsolidateError(f"{key.symbol} {year}: no days with data in the manifests")
    files = {d: downloads / r["path"] for d, r in sorted(success.items())}

    missing_files = [str(p) for p in files.values() if not p.is_file()]
    if missing_files:
        raise ConsolidateError(f"{key.symbol} {year}: {len(missing_files)} files listed but missing, "
                               f"e.g. {missing_files[0]}")

    #! 3. footers: meta + schema
    log(f"{key.symbol} {year}: reading {len(files)} file footers")
    metas: dict[date, DownloadedMeta] = {}
    schemas: dict[date, pl.Schema] = {}
    counts: dict[date, int] = {}
    for d, p in files.items():
        typeid = io.backend.read_meta(p).get(TYPE_KEY)
        if typeid != DownloadedMeta.get_id():
            raise ConsolidateError(f"{p}: meta type {typeid!r}, expected {DownloadedMeta.get_id()}")
        m = io.read_meta_as(p, DownloadedMeta)
        if m.dataset != key:
            raise ConsolidateError(f"{p}: dataset {m.dataset}, expected {key}")
        metas[d] = m
        schemas[d] = pl.read_parquet_schema(p)
        counts[d] = pl.scan_parquet(p, hive_partitioning=False).select(pl.len()).collect().item()

    first_day = next(iter(files))
    ref_schema = schemas[first_day]
    for d, s in schemas.items():
        if problems := check_schema(s, ref_schema, exact=True):
            raise ConsolidateError(f"{files[d]}: schema differs from {files[first_day].name}: "
                                   + "; ".join(problems))

    #! 4. checks
    checks: list[CheckRecord] = []
    y0, y1 = date(year, 1, 1), date(year + 1, 1, 1)
    cover_end = min(y1, today)

    datasets = unique_values(mem, "dataset")
    checks.append(_rec("manifest: one dataset", "pass" if len(datasets) == 1 else "fail",
                       ", ".join(map(str, datasets)), len(datasets)))

    resolved = {d for d, r in by_day.items() if r["status"] in ("success", "empty")}
    errored = sorted(d for d, r in by_day.items() if r["status"] not in ("success", "empty"))
    uncovered = missing_days(resolved, y0, cover_end, thresholds.skip_weekdays)
    no_row = [d for d in uncovered if d not in by_day]
    detail = "; ".join(x for x in (
        f"{len(no_row)} without a row: {_fmt_days(no_row)}" if no_row else "",
        f"{len(errored)} with status error: {_fmt_days(errored)}" if errored else "",
    ) if x) or f"through {cover_end - timedelta(days=1)}"
    checks.append(_rec("coverage: every day in a manifest", "fail" if uncovered or errored else "pass",
                       detail, len(uncovered) + len([d for d in errored if d not in uncovered])))

    listed = {p.resolve() for p in files.values()}
    extra = sorted(p for p in src_dir.rglob("*.parquet") if p.resolve() not in listed)
    checks.append(_rec("files: none unlisted", "warn" if extra else "pass",
                       f"{len(extra)} not in a manifest, e.g. {extra[0].name}" if extra else "",
                       len(extra)))

    bad_rows = [d for d, r in success.items() if r.get("rows") is not None and r["rows"] != counts[d]]
    checks.append(_rec("rows: manifest matches files", "fail" if bad_rows else "pass",
                       _fmt_days(bad_rows), len(bad_rows)))

    one_day = timedelta(days=1)
    bad_periods = [d for d, m in metas.items()
                   if (m.start.date(), m.end.date()) != (d, d + one_day)
                   or m.start.time() != datetime.min.time() or m.end.time() != datetime.min.time()]
    checks.append(_rec("periods: meta matches day", "fail" if bad_periods else "pass",
                       _fmt_days(bad_periods), len(bad_periods)))

    methods = sorted({m.method for m in metas.values()})
    checks.append(_rec("method: one per year", "pass" if len(methods) == 1 else "fail",
                       ", ".join(methods), len(methods)))

    core = CORE[kind_of(key.interval)]
    core_problems = check_schema(ref_schema, core, exact=False)
    checks.append(_rec("schema: has core columns", "fail" if core_problems else "pass",
                       "; ".join(core_problems)))

    gap, gap_at = longest_gap(list(files), y0, cover_end)
    gap_status = ("fail" if gap >= thresholds.gap_fail else
                  "warn" if gap >= thresholds.gap_warn else "pass")
    checks.append(_rec("gaps: days without data", gap_status,
                       f"longest {gap} days from {gap_at}" if gap else "", gap))

    #! the frame (lazy, streamed): files in day order
    lf = pl.scan_parquet([files[d] for d in files], hive_partitioning=False)
    time_col = ref_schema.names()[0]
    t = pl.col(time_col)
    lo = datetime(year, 1, 1, tzinfo=UTC)
    hi = datetime(year + 1, 1, 1, tzinfo=UTC)
    log(f"{key.symbol} {year}: checking {sum(counts.values()):,} rows")
    stats = lf.select(
        pl.len().alias("rows"),
        t.null_count().alias("nulls"),
        (t.diff() < pl.duration(milliseconds=0)).sum().alias("unsorted"),
        ((t < lo) | (t >= hi)).sum().alias("outside"),
        pl.all_horizontal([pl.col(c) == pl.col(c).shift(1) for c in ref_schema.names()])
            .sum().alias("dupes"),
    ).collect(engine="streaming").row(0, named=True)

    time_bad = stats["nulls"] or stats["unsorted"] or stats["outside"]
    checks.append(_rec("time: sorted, in year, no nulls", "fail" if time_bad else "pass",
                       f"nulls={stats['nulls']} unsorted={stats['unsorted']} outside={stats['outside']}"
                       if time_bad else ""))
    n_rows = int(stats["rows"])
    frac = stats["dupes"] / n_rows if n_rows else 0.0
    checks.append(_rec("duplicates: adjacent identical rows",
                       "fail" if frac >= thresholds.max_dupe_fraction else "pass",
                       f"{stats['dupes']} of {n_rows:,}", int(stats["dupes"])))

    if dry:
        return YearResult(key, year, "dry", out_path, n_rows, len(files), tuple(checks))

    #! 5. write: manifest copy (temp -> rename), then data with RawMeta
    out_path.parent.mkdir(parents=True, exist_ok=True)
    statuses = [r["status"] for r in rows]
    write_info(mem, {
        "description": "Daily download files consolidated into the lake/raw file beside this manifest.",
        "format": "fxt consolidated-manifest 1",
        "paths_relative_to": "downloads",
        "paths_relative_to_help": "financial_files.path is relative to the downloads root "
                                  "(<data>/ingest/downloads by default); empty days have no path",
        "dataset": str(key),
        "year": year,
        "period_start": lo.isoformat(),
        "period_end": hi.isoformat(),
        "rows_table": MANIFEST_TABLE,
        "month_manifests": len(manifests),
        "month_manifest_paths": "\n".join(p.resolve().relative_to(downloads.resolve()).as_posix()
                                          for p in manifests),
        "days_success": statuses.count("success"),
        "days_empty": statuses.count("empty"),
        "days_other": len(statuses) - statuses.count("success") - statuses.count("empty"),
        "data_file": out_path.name,
        "created_by": __name__,
        "created_at": datetime.now(UTC).isoformat(),
        "fxt_version": _fxt_version(),
    })
    tmp_manifest = out_manifest.with_name(out_manifest.name + ".tmp")
    write_to_file(mem, tmp_manifest, overwrite=True)
    meta = RawMeta(dataset=key, start=lo, end=hi, rows=n_rows, days=len(files),
                   method=methods[0], manifest_sha256=_sha256(tmp_manifest), checks=tuple(checks))
    log(f"{key.symbol} {year}: writing {out_path.name}")
    try:
        io.write(lf, out_path, meta, overwrite=True)
    except BaseException:
        tmp_manifest.unlink(missing_ok=True)
        raise
    os.replace(tmp_manifest, out_manifest)
    return YearResult(key, year, "written", out_path, n_rows, len(files), tuple(checks))
#-
