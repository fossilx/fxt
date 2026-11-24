#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxt.data.derived.jobs

Every derived data set is a DerivedJob: one definition that both front ends
(the Textual picker and the `derive` CLI) run the same way.

    job = JOBS["bars-1min"]
    for key, src in job.scan(lake):
        state = job.state(lake, key, src)          # missing / current / stale / failed
        run = run_job(job, lake, key, src)         # pre-checks -> build -> checks -> stamp

A job declares
    inputs      which lake files it reads (lake type + partition filters)
    out_path    where the output for an input goes
    build       writes the output (stores a BuildResult in ctx.cache)
    pre_checks  run on the input first; a failure blocks the build (unless force)
    checks      run on the output; results go into its meta
    stamp       writes the output's meta from the build + full check report
    expected    (name, version) of the transform a current output must carry

Up to date ("current") means all of these hold, not just "the file exists":
    the output exists and has meta, its checks passed, its transform name and
    version are the ones this code would write, and every InputRef still matches
    its input (same path and sha256). Hashes are cached (fxt.core.io.hash_cache),
    so each input is hashed once until it changes.

Adding a transform = one more DerivedJob in JOBS. Both front ends pick it up.
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Any

from fxt.core.checks import (
    Check, CheckReport, CheckResult, flatten_checks, run_checks, skip_checks,
)
from fxt.core.io.hash_cache import HashCache
from fxt.core.versioned import TYPE_KEY
from fxt.data.jobs import JobContext, LogFn
from fxt.data.models import BarsMeta, DerivedMeta, get_meta_io, get_store
from fxt.data.paths import Lake, LakeType, PartitionKey

from . import bar_checks as bc
from .bars import RESAMPLE_BARS, TICK_INTERVAL, TICKS_TO_BARS, build_bars
from .meta import input_meta_checks, remember_build, stamp_bars

__all__ = [
    "Outcome", "State", "InputSpec", "DerivedJob", "JobRun",
    "hash_cache", "run_job", "time_bars", "JOBS", "get_job", "job_for_interval",
]

HASH_CACHE_NAME = ".sha256-cache.db"


@cache
def hash_cache(lake_root: Path | str) -> HashCache:
    """ One cache per lake, stored at <lake>/.sha256-cache.db. """
    return HashCache(Path(lake_root).resolve() / HASH_CACHE_NAME)


#!================================================================================(80)
#! results
#!--------------------------------------------------------------------------------(80)
class Outcome(StrEnum):
    PASSED        = "PASSED"
    FAILED        = "FAILED"            # built (or verified), some check failed
    BLOCKED       = "BLOCKED"           # pre-checks failed, build not run
    ACTION_FAILED = "ACTION FAILED"     # build raised
    SKIPPED       = "SKIPPED"           # verify: no output to check
#

class State(StrEnum):
    MISSING = "missing"                 # no output yet
    CURRENT = "current"                 # up to date, checks passed
    STALE   = "stale"                   # output exists but is out of date (see reason)
    FAILED  = "failed"                  # up to date, but its checks failed
#

@dataclass(frozen=True)
class JobRun:
    report: CheckReport
    outcome: Outcome
    elapsed: float
#


#!================================================================================(80)
#! job definition
#!--------------------------------------------------------------------------------(80)
@dataclass(frozen=True)
class InputSpec:
    laketype: LakeType
    filters: dict[str, str] = field(default_factory=dict)

    def scan(self, lake: Lake) -> list[tuple[PartitionKey, Path]]:
        return lake.scan(self.laketype, **self.filters)
#

Build = Callable[[JobContext], None]
Stamp = Callable[[JobContext, CheckReport, Outcome], Any]

@dataclass(frozen=True)
class DerivedJob:
    name: str                                         # "bars-1min"
    description: str
    inputs: InputSpec
    out_path: Callable[[Lake, PartitionKey], Path]
    build: Build
    expected: tuple[str, int]                         # transform (name, version) of a current output
    pre_checks: tuple[Check[JobContext], ...] = ()
    checks: tuple[Check[JobContext], ...] = ()
    stamp: Stamp | None = None
    out_interval: str | None = None                   # interval of the output (lake requirements)

    def __post_init__(self) -> None:
        flatten_checks([*self.pre_checks, *self.checks])     # ids unique across both stages

    #! ---- files ---------------------------------------------------------------
    def scan(self, lake: Lake) -> list[tuple[PartitionKey, Path]]:
        return self.inputs.scan(lake)

    def dst(self, lake: Lake, key: PartitionKey) -> Path:
        return self.out_path(lake, key)

    #! ---- up to date? ----------------------------------------------------------
    def state(self, lake: Lake, key: PartitionKey, src: Path,
              hasher: HashCache | None = None, *, verify_inputs: bool = True) -> tuple[State, str]:
        """ (state, reason). Reads the output's footer; hashes inputs via the cache.
            verify_inputs=False skips the sha256 comparison (fast, but can't see
            an input that changed in place).
        """
        dst = self.dst(lake, key)
        if not dst.exists():
            return State.MISSING, "no output"
        if TYPE_KEY not in get_store().read_meta(dst):
            return State.STALE, "output has no meta (incomplete build)"
        try:
            meta = get_meta_io().read_meta(dst)
        except Exception as e:
            return State.STALE, f"output meta unreadable: {type(e).__name__}"
        if not isinstance(meta, DerivedMeta):
            return State.STALE, f"output meta is {meta.get_id()}, not a derived model"
        name, version = self.expected
        if (meta.transform.name, meta.transform.version) != (name, version):
            return State.STALE, (f"transform {meta.transform.name}@{meta.transform.version}, "
                                 f"current is {name}@{version}")
        hasher = hasher or hash_cache(lake.root)
        for ref in meta.inputs:
            path = lake.root / ref.path
            if not path.exists():
                return State.STALE, f"input {ref.path} no longer exists"
            if path.resolve() != src.resolve():
                return State.STALE, f"built from {ref.path}, not {src.relative_to(lake.root)}"
            if verify_inputs and hasher.sha256(path) != ref.sha256:
                return State.STALE, "input changed since the build"
        if not meta.passed:
            return State.FAILED, "checks failed: " + ", ".join(c.name for c in meta.failed_checks)
        return State.CURRENT, ""

    def is_current(self, lake: Lake, key: PartitionKey, src: Path) -> bool:
        return self.state(lake, key, src)[0] is State.CURRENT
#


#!================================================================================(80)
#! running one file (used by both front ends)
#!--------------------------------------------------------------------------------(80)
def _noop(*_a, **_k) -> None: ...

def run_job(
    job: DerivedJob,
    lake: Lake,
    key: PartitionKey,
    src: Path,
    *,
    build: bool = True,
    force: bool = False,
    log: LogFn = _noop,
    on_start: Callable[[Check], None] | None = None,
    on_result: Callable[[Check, CheckResult], None] | None = None,
    on_adhoc: Callable[[str, CheckResult], None] | None = None,
) -> JobRun:
    """ pre-checks -> build -> checks -> stamp, for one input file. Never raises.

        build=False: verify only (pre-checks + checks on the existing output; no
        stamp, the meta keeps describing the file as it was built).
        force=True: build even if pre-checks failed (recorded in the meta).
    """
    t0 = time.perf_counter()
    dst = job.dst(lake, key)
    if not build and not dst.exists():
        log(f"- skip {src.name}: no output to verify")
        return JobRun(CheckReport(), Outcome.SKIPPED, 0.0)

    adhoc = CheckReport()
    def report(name: str, result: CheckResult) -> None:
        adhoc.results[name] = result
        (on_adhoc or _noop)(name, result)

    ctx = JobContext(key=key, src=src, dst=dst, log=log, report=report)
    log(f"▶ {'build' if build else 'verify'} {job.name}: {src.name}")
    full, outcome = CheckReport(), Outcome.ACTION_FAILED
    try:
        pre = run_checks(job.pre_checks, ctx, on_start=on_start, on_result=on_result)
        blocked = build and not pre.ok and not force
        action_ok = True
        if blocked:
            log("✗ pre-checks failed: not building (force builds anyway)")
        elif build:
            if not pre.ok:
                log("! pre-checks failed: building anyway (force)")
            try:
                job.build(ctx)
            except Exception as exc:
                action_ok = False
                log(f"✗ {type(exc).__name__}: {exc}")

        if blocked:
            post = skip_checks(job.checks, "blocked by pre-checks", on_result=on_result)
        elif not action_ok:
            post = skip_checks(job.checks, "build failed", on_result=on_result)
        else:
            post = run_checks(job.checks, ctx, on_start=on_start, on_result=on_result)

        full = pre.merge(adhoc).merge(post)
        if blocked:
            outcome = Outcome.BLOCKED
        elif not action_ok:
            outcome = Outcome.ACTION_FAILED
        elif not full.ok:
            outcome = Outcome.FAILED
            log(f"✗ {len(full.failed)} check(s) failed: {', '.join(full.failed)}")
        else:
            outcome = Outcome.PASSED
            log("✓ finished")

        if job.stamp and build:
            try:
                job.stamp(ctx, full, outcome)
            except Exception as exc:
                log(f"✗ stamp: {type(exc).__name__}: {exc}")
                if outcome is Outcome.PASSED:
                    outcome = Outcome.ACTION_FAILED
    except Exception as exc:                   # bug in the job plumbing: report it, don't hang
        log(f"✗ job crashed: {type(exc).__name__}: {exc}")
    finally:
        ctx.close()
    return JobRun(full, outcome, time.perf_counter() - t0)


#!================================================================================(80)
#! time bars
#!--------------------------------------------------------------------------------(80)
def time_bars(source_interval: str, interval: str, *,
              pre_checks: Iterable[Check | Iterable[Check]] | None = None) -> DerivedJob:
    """ One job per step: TICK -> 1MIN (from raw), 1MIN -> 1HOUR (from derived), ... """
    from_ticks = source_interval == TICK_INTERVAL

    def out_path(lake: Lake, key: PartitionKey) -> Path:
        out = key.replace(interval=interval)
        return lake.derived(**out.model_dump(), filename=out.filename, must_exist=False)

    def build(ctx: JobContext) -> None:
        assert ctx.dst is not None
        ctx.log(f"src: {ctx.src}")
        ctx.log(f"dst: {ctx.dst}")
        remember_build(ctx, build_bars(ctx.src, ctx.dst, source_interval=ctx.key.interval,
                                       interval=interval, log=ctx.log))

    def stamp(ctx: JobContext, report: CheckReport, outcome: Outcome) -> BarsMeta | None:
        lake_root = _lake_root_of(ctx.dst)
        return stamp_bars(ctx, report, outcome, lake_root=lake_root)

    if pre_checks is None:
        pre_checks = ([bc.placement("src"), input_meta_checks(), bc.raw_tick_checks()] if from_ticks
                      else [bc.placement("src", group=source_interval), input_meta_checks()])
    return DerivedJob(
        name=f"bars-{interval.lower()}",
        description=f"{source_interval} -> {interval} time bars",
        inputs=InputSpec(LakeType.RAW if from_ticks else LakeType.DERIVED,
                         {"interval": source_interval}),
        out_path=out_path,
        build=build,
        expected=TICKS_TO_BARS if from_ticks else RESAMPLE_BARS,
        pre_checks=tuple(flatten_checks(pre_checks)),
        checks=tuple(flatten_checks([bc.placement("dst"), bc.bar_checks()])),
        stamp=stamp,
        out_interval=interval,
    )


def _lake_root_of(path: Path | None) -> Path:
    """ <lake>/derived/source=.../file -> <lake> (the folder above raw/ or derived/). """
    assert path is not None
    for parent in Path(path).resolve().parents:
        if parent.name in (LakeType.RAW.value, LakeType.DERIVED.value):
            return parent.parent
    raise ValueError(f"{path} isn't inside a lake")


#!================================================================================(80)
#! registry (dependency order: a job's inputs come from jobs before it)
#!--------------------------------------------------------------------------------(80)
JOBS: dict[str, DerivedJob] = {j.name: j for j in [
    time_bars(TICK_INTERVAL, "1MIN"),
    time_bars("1MIN", "1HOUR"),
]}


def job_for_interval(interval: str) -> DerivedJob | None:
    """ The job whose output is `interval` (e.g. "1HOUR" -> bars-1hour), if any. """
    return next((j for j in JOBS.values() if j.out_interval == interval), None)


def get_job(name: str) -> DerivedJob:
    try:
        return JOBS[name.lower()]
    except KeyError:
        raise KeyError(f"unknown job {name!r}; known: {', '.join(JOBS)}") from None
#-
