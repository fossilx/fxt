#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
base

Building blocks shared by every data file's metadata model.

    Component    small immutable value object embedded in metadata
    DatasetKey   which dataset a file belongs to (mirrors the partition folders)
    CheckRecord  result of one verification check run before the file was written
    InputRef     one input file: where it was, what meta type it carried, its hash
    Transform    what produced a derived file: name + algorithm version + params

    FileMeta     unregistered base for every file: dataset + period
    CheckedMeta  unregistered: FileMeta + checks (raw and derived files)
    DerivedMeta  unregistered: CheckedMeta + inputs + transform

Design rules
- Metadata is built once, right before the file is written, then never changed:
  every model is frozen, and collections are tuples.
- extra="forbid": a file holding fields the model doesn't know fails loudly.
  Adding or changing fields means registering a new version.
- Catalog values (source, market, symbol, interval) are plain strings in their
  canonical, filesystem-safe form ("EURJPY", not "EUR/JPY"). Check them against
  fxt.data.refdata when *building* metadata, never in a validator, so reading a
  file never needs the catalog DB.
- `start`/`end` is the period the file covers, half-open: [start, end).
  For a yearly file: start=2020-01-01T00:00Z, end=2021-01-01T00:00Z.
  This isn't the first/last timestamp in the data, so files for neighbouring
  periods line up exactly (end of one == start of the next).
- Datetimes are stored in UTC.
- Bump `Transform.version` when an algorithm's output would change. Bump the
  *model* version only when the metadata fields change.
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from fxt.core.versioned import VersionedModel

__all__ = [
    "utcnow",
    "Component", "DatasetKey", "CheckStatus", "BAD_CHECK_STATUSES", "CheckRecord",
    "InputRef", "Transform",
    "FileMeta", "CheckedMeta", "DerivedMeta",
]


#!================================================================================(80)
#! helpers
#!--------------------------------------------------------------------------------(80)
def utcnow() -> datetime:
    return datetime.now(UTC)


#!================================================================================(80)
#! components
#!--------------------------------------------------------------------------------(80)
class Component(BaseModel):
    """ Small immutable value object embedded in metadata.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
#


class DatasetKey(Component):
    """ Which dataset a file belongs to. Mirrors the partition folders
        (source=/market=/symbol=/interval=). Hashable, so it can be used as
        a dict key or compared directly.
    """
    source: str      # "dukascopy"
    market: str      # "forex"
    symbol: str      # filesystem-safe form: "EURJPY"
    interval: str    # "TICK", "1MIN", "1HOUR"

    @classmethod
    def from_refdata(cls, source: str, market: str, symbol: str, interval: str) -> DatasetKey:
        """ Build a key holding refdata's official names, whatever spelling came in.

            Every value written to a file's metadata comes from refdata, never
            from the input string, so files only ever carry the official form.

            symbol accepts, in order:
                1. the source's spelling        "AUD-CAD"  (current dukascopy_python)
                2. an official name or alias    "AUDCAD", "audcad", "cave"
                3. a separated spelling         "AUD/CAD"  (old files), "aud_cad"
            interval accepts the official name ("TICK") or the source's ("tick").

            Raises KeyError if refdata doesn't know a value, or if the source
            doesn't carry that symbol/interval in that market.
        """
        from fxt.data.refdata import intervals, markets, sources, symbols  # lazy: reading never needs it

        src = sources()[source]
        mkt = markets()[market].name

        #! symbol -> refdata's Symbol (official name comes from it, not from `symbol`)
        try:
            entry = src.from_source_symbol(symbol)
        except KeyError:
            entry = None
        if entry is not None and entry.market == mkt:
            name = entry.name
        else:
            reg = symbols()
            try:
                name = reg.resolve(symbol, mkt).name
            except KeyError:
                squashed = "".join(ch for ch in symbol if ch.isalnum())
                try:
                    name = reg.resolve(squashed, mkt).name
                except KeyError:
                    raise KeyError(f"refdata: unknown symbol {symbol!r} in market {mkt!r}") from None
        if not src.has_symbol(name, mkt):
            raise KeyError(f"refdata: source {src.name!r} doesn't carry {mkt}/{name}")

        #! interval -> official name
        ivs = intervals()
        if interval in ivs:
            iv = ivs[interval].name
        else:
            iv = src.from_source_interval(interval)
        if not src.has_interval(iv):
            raise KeyError(f"refdata: source {src.name!r} has no interval {iv!r}")

        return cls(source=src.name, market=mkt, symbol=name, interval=iv)

    def with_interval(self, interval: str) -> DatasetKey:
        return self.model_copy(update={"interval": interval})

    def __str__(self) -> str:
        return f"{self.source}/{self.market}/{self.symbol}/{self.interval}"
#


CheckStatus = Literal["pass", "warn", "fail", "error", "skip"]
BAD_CHECK_STATUSES: frozenset[str] = frozenset({"fail", "error"})


class CheckRecord(Component):
    """ Stored result of one verification check.

        Mirrors fxt.core.checks.CheckResult (status/detail/value) but keeps the
        status as a plain string, so reading a file never imports the check
        runner. Build one with `CheckRecord.from_result(check_id, result)`.
    """
    name: str                                    # check id, e.g. "bars 1MIN: time unique"
    status: CheckStatus
    detail: str = ""
    value: float | int | str | bool | None = None

    @property
    def ok(self) -> bool:
        """ Same rule as CheckResult.ok: only FAIL and ERROR are bad. """
        return self.status not in BAD_CHECK_STATUSES

    @classmethod
    def from_result(cls, name: str, result: Any) -> CheckRecord:
        """ From an fxt.core.checks.CheckResult (duck-typed: status/detail/value). """
        return cls(name=name, status=str(result.status), detail=result.detail or "", #type: ignore
                   value=result.value)
#


class InputRef(Component):
    """ Lineage entry for one input file. """
    path: str          # posix path relative to the lake root
    typeid: str        # the input's stored type id, copied as-is (e.g. "RawMeta@1")
    sha256: str
#

class Transform(Component):
    """ What produced a derived file. """
    name: str                                            # "ticks_to_bars", "resample_bars"
    version: int                                         # algorithm version
    params: dict[str, str | int | float | bool] = Field(default_factory=dict)
#


#!================================================================================(80)
#! base meta (all unregistered)
#!--------------------------------------------------------------------------------(80)
class FileMeta(VersionedModel):
    """ Unregistered base for every data file's metadata.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset: DatasetKey
    start: AwareDatetime
    end: AwareDatetime
    created_at: AwareDatetime = Field(default_factory=utcnow)

    @field_validator("start", "end", "created_at", mode="after")
    @classmethod
    def _to_utc(cls, v: datetime) -> datetime:
        return v.astimezone(UTC)

    @model_validator(mode="after")
    def _check_period(self) -> Self:
        if self.start >= self.end:
            raise ValueError(f"start must be before end (start={self.start}, end={self.end})")
        return self

    @property
    def identity(self) -> tuple[DatasetKey, datetime, datetime]:
        """ (dataset, start, end): what the file *is*, ignoring when it was made. """
        return (self.dataset, self.start, self.end)
#


class CheckedMeta(FileMeta):
    """ Unregistered base for files that were verified before being written
        (raw and derived). Downstream code should refuse files where
        `passed` is False.
    """
    checks: tuple[CheckRecord, ...] = ()

    @property
    def passed(self) -> bool:
        """ True if no check FAILed or ERRORed (WARN and SKIP don't fail a file). """
        return all(c.ok for c in self.checks)

    @property
    def failed_checks(self) -> tuple[CheckRecord, ...]:
        return tuple(c for c in self.checks if not c.ok)
#


class DerivedMeta(CheckedMeta):
    """ Unregistered base for files computed from other lake files
        (bars now; other deterministic transforms later).
    """
    inputs: tuple[InputRef, ...] = Field(min_length=1)
    transform: Transform
#-


#!================================================================================(80)
#! gogogogog
#!--------------------------------------------------------------------------------(80)
if(__name__ == "__main__"):
    from pathlib import Path
    from rich import print

    print()
    print(f"hi2u ~ from [bold cyan]{Path(__file__).name}~[/]")
    print()


