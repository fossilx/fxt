#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxtapps.ingest.request

What each subcommand hands to the library once every value is known.

These models only *validate*; they never prompt. Prompting happens before,
in resolve.py, so a request can be built in a test or a script with no
terminal. Building one normalizes every name through refdata
(DatasetKey.from_refdata), so a request only ever holds official names.

    IngestRequest        shared fields (unregistered base)
    DownloadRequest      + start/end days
    ConsolidateRequest   + years, force
    VerifyRequest        + years
    RunRequest           download + consolidate + verify
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fxt.data.models import DatasetKey

__all__ = ["IngestRequest", "DownloadRequest", "ConsolidateRequest", "VerifyRequest", "RunRequest"]


#!================================================================================(80)
#! base
#!--------------------------------------------------------------------------------(80)
class IngestRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    data_root: Path
    source: str
    market: str
    interval: str
    symbols: tuple[str, ...] = Field(min_length=1)
    dry: bool = False
    auto: bool = False

    @model_validator(mode="before")
    @classmethod
    def _official_names(cls, data: Any) -> Any:
        """ Every name -> refdata's official form ("aud/cad" -> "AUDCAD"). """
        if not isinstance(data, dict):
            return data
        src, mkt, iv = data.get("source"), data.get("market"), data.get("interval")
        syms = data.get("symbols") or ()
        if not (src and mkt and iv and syms):
            return data          # let field validation report what's missing
        keys = [DatasetKey.from_refdata(src, mkt, s, iv) for s in syms]
        names: list[str] = []
        for k in keys:
            if k.symbol not in names:
                names.append(k.symbol)
        return {**data, "source": keys[0].source, "market": keys[0].market,
                "interval": keys[0].interval, "symbols": tuple(names)}

    @property
    def keys(self) -> tuple[DatasetKey, ...]:
        return tuple(DatasetKey(source=self.source, market=self.market, symbol=s,
                                interval=self.interval) for s in self.symbols)

    @property
    def downloads_dir(self) -> Path:
        return self.data_root / "ingest" / "downloads"

    @property
    def lake_dir(self) -> Path:
        return self.data_root / "lake"
#


#!================================================================================(80)
#! per command
#!--------------------------------------------------------------------------------(80)
class DownloadRequest(IngestRequest):
    """ Days to download: [start, end), like the meta periods. """
    start: date
    end: date

    @model_validator(mode="after")
    def _check_days(self) -> Self:
        if self.start >= self.end:
            raise ValueError(f"start ({self.start}) must be before end ({self.end})")
        return self
#

class ConsolidateRequest(IngestRequest):
    years: tuple[int, ...] = Field(min_length=1)   # ALL already expanded to the years on disk
    force: bool = False                            # replace existing lake/raw years
#

class VerifyRequest(IngestRequest):
    years: tuple[int, ...] = Field(min_length=1)
#

class RunRequest(DownloadRequest):
    force: bool = False

    @property
    def years(self) -> tuple[int, ...]:
        """ Years touched by [start, end). """
        last = self.end.year if (self.end.month, self.end.day) != (1, 1) else self.end.year - 1
        return tuple(range(self.start.year, last + 1))

    def consolidate(self) -> ConsolidateRequest:
        return ConsolidateRequest(**self._shared(), years=self.years, force=self.force)

    def verify(self) -> VerifyRequest:
        return VerifyRequest(**self._shared(), years=self.years)

    def _shared(self) -> dict[str, Any]:
        return self.model_dump(include=set(IngestRequest.model_fields))
#-
