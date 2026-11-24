#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxt.data.lake_check

Compares the lake against refdata's lake_requirements: for every required
(source, market, symbol, tier, interval) and every expected year, one Finding.

    findings = check_lake(lake)
    problems = [f for f in findings if f.status != "ok"]

Status per (data set, year)
    ok        file present; raw: RawMeta passed; derived: up to date and passed
    missing   no file
    failed    raw: RawMeta checks failed; derived: up to date but checks failed
    stale     raw: legacy/unknown meta; derived: input/transform/meta changed
    blocked   derived: its input file is missing (fix the input first)

Expected years: first_year..last_year from the merged requirement, where
first_year NULL = the first raw year on disk (see sql/lake-requirements.sql)
and last_year NULL = the current year.

Each problem carries a `fix`: the command that would address it, or None when
the fix is upstream (blocked) or needs a look first.
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from fxt.core.versioned import TYPE_KEY
from fxt.data.derived.jobs import State, job_for_interval
from fxt.data.models import RawMeta, get_meta_io, get_store
from fxt.data.paths import Lake, LakeType, PartitionKey
from fxt.data.refdata import LakeRequirement, required_datasets

__all__ = ["FindingStatus", "Finding", "check_lake", "expected_years", "compress_years"]

FindingStatus = Literal["ok", "missing", "failed", "stale", "blocked"]


@dataclass(frozen=True)
class Finding:
    source: str
    market: str
    symbol: str
    tier: str
    interval: str
    year: int | None                  # None: the whole data set (e.g. no raw data at all)
    status: FindingStatus
    reason: str = ""
    fix: str | None = None

    @property
    def dataset(self) -> tuple[str, str, str, str, str]:
        return (self.source, self.market, self.symbol, self.tier, self.interval)
#


#!================================================================================(80)
#! helpers
#!--------------------------------------------------------------------------------(80)
def compress_years(years: Iterable[int]) -> str:
    """ [2013, 2014, 2015, 2018] -> "2013-2015, 2018" """
    ys = sorted(set(years))
    out: list[str] = []
    i = 0
    while i < len(ys):
        j = i
        while j + 1 < len(ys) and ys[j + 1] == ys[j] + 1:
            j += 1
        out.append(str(ys[i]) if i == j else f"{ys[i]}-{ys[j]}")
        i = j + 1
    return ", ".join(out)


def expected_years(req: LakeRequirement, raw_years: dict[str, set[int]], today: date,
                   raw_reqs: Iterable[LakeRequirement] = ()) -> list[int]:
    """ Years req says should exist (first..last, inclusive).

        raw_years: raw interval -> years on disk for the symbol.
        first_year NULL:
            raw      the first year on disk for that interval
            derived  where the symbol's raw requirements start (their first_year,
                     or their first year on disk), so a missing raw year at the
                     start shows up downstream as "blocked"
        last_year NULL: the current year.
    """
    first = req.first_year
    if first is None:
        if req.tier == "raw":
            starts = [min(raw_years[req.interval])] if raw_years.get(req.interval) else []
        else:
            starts = [r.first_year if r.first_year is not None else min(raw_years[r.interval])
                      for r in raw_reqs if r.tier == "raw" and (r.first_year is not None
                                                                or raw_years.get(r.interval))]
            if not starts and raw_years:          # no raw requirement: whatever raw is on disk
                starts = [min(set().union(*raw_years.values()))]
        if not starts:
            return []
        first = min(starts)
    last = req.last_year if req.last_year is not None else today.year
    return list(range(first, last + 1))


def _raw_status(path: Path) -> tuple[FindingStatus, str]:
    kv = get_store().read_meta(path)
    typeid = kv.get(TYPE_KEY)
    if typeid is None:
        return "stale", "no fxt metadata"
    if typeid != RawMeta.get_id():
        return "stale", f"{typeid} (re-consolidate to get {RawMeta.get_id()})"
    meta = get_meta_io().read_meta_as(path, RawMeta)
    if not meta.passed:
        return "failed", "checks failed: " + ", ".join(c.name for c in meta.failed_checks)
    return "ok", ""


def _req_order(tier: str, interval: str) -> tuple:
    """ raw first, then derived; within a tier by interval length (TICK, 1MIN, 1HOUR). """
    from fxt.data.refdata import intervals
    ivs = intervals()
    secs = ivs[interval].seconds if interval in ivs else None
    return (tier != "raw", secs is not None, secs or 0, interval)


_STATE: dict[State, FindingStatus] = {
    State.CURRENT: "ok", State.MISSING: "missing", State.STALE: "stale", State.FAILED: "failed",
}


#!================================================================================(80)
#! main
#!--------------------------------------------------------------------------------(80)
def check_lake(
    lake: Lake,
    *,
    datasets: dict[tuple[str, str, str], dict[tuple[str, str], LakeRequirement]] | None = None,
    symbols: set[str] | None = None,
    years: set[int] | None = None,
    today: date | None = None,
    verify_inputs: bool = True,
    on_progress: Callable[[str], None] | None = None,
) -> list[Finding]:
    """ One Finding per required (data set, year). Filters: symbols, years.
        verify_inputs=False: derived staleness without hashing inputs (faster).
    """
    today = today or datetime.now(UTC).date()
    datasets = required_datasets() if datasets is None else datasets
    progress = on_progress or (lambda _m: None)
    out: list[Finding] = []

    for (source, market, symbol), reqs in sorted(datasets.items()):
        if symbols is not None and symbol not in symbols:
            continue
        progress(f"{symbol}")
        raw_files: dict[str, dict[int, Path]] = {}
        for key, path in lake.scan(LakeType.RAW, source=source, market=market, symbol=symbol):
            raw_files.setdefault(key.interval, {})[key.year] = path
        raw_years = {iv: set(ys) for iv, ys in raw_files.items()}

        for (tier, interval), req in sorted(reqs.items(), key=lambda kv: _req_order(*kv[0])):
            def finding(year, status, reason="", fix=None, _t=tier, _i=interval):
                out.append(Finding(source, market, symbol, _t, _i, year, status, reason, fix))

            exp = expected_years(req, raw_years, today, reqs.values())
            if not exp:
                finding(None, "missing", "no raw data on disk to start from (set first_year?)",
                        f"pixi run ingest consolidate -i {symbol} -y ALL" if tier == "raw" else None)
                continue
            if years is not None:
                exp = [y for y in exp if y in years]

            if tier == "raw":
                for y in exp:
                    path = raw_files.get(interval, {}).get(y)
                    if path is None:
                        finding(y, "missing", "", f"pixi run ingest consolidate -i {symbol} -y {y}")
                        continue
                    try:
                        status, reason = _raw_status(path)
                    except Exception as e:
                        status, reason = "stale", f"meta unreadable: {type(e).__name__}: {e}"
                    fix = (f"pixi run ingest consolidate -i {symbol} -y {y} --force" if status == "stale"
                           else None)          # failed raw: the downloads need a look first
                    finding(y, status, reason, fix)
                continue

            #! derived
            job = job_for_interval(interval)
            if job is None:
                for y in exp:
                    finding(y, "failed", f"no derive job produces {interval}")
                continue
            in_interval = job.inputs.filters.get("interval")
            for y in exp:
                key = PartitionKey(source=source, market=market, symbol=symbol,
                                   interval=in_interval or interval, year=y)
                src = lake._partition_path(job.inputs.laketype, **key.model_dump(),
                                           filename=key.filename, must_exist=False)
                if not src.exists():
                    finding(y, "blocked", f"input {in_interval} {y} missing")
                    continue
                try:
                    state, reason = job.state(lake, key, src, verify_inputs=verify_inputs)
                except Exception as e:
                    state, reason = State.STALE, f"{type(e).__name__}: {e}"
                status = _STATE[state]
                fix = {
                    "missing": f"pixi run derive build {job.name} -i {symbol} -y {y}",
                    "stale":   f"pixi run derive build {job.name} -i {symbol} -y {y}",
                    "failed":  f"pixi run derive status {job.name} -i {symbol} -y {y}",
                }.get(status)
                finding(y, status, reason, fix)
    return out
#-
