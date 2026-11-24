#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxtapps.ingest.resolve

Fills in whatever wasn't passed on the command line, in dependency order:

    source -> market -> symbols -> interval -> years / days

Each value comes from (first that applies):
    1. the command line (checked against the choices)
    2. the only available choice (pick_fuzzy auto-selects it)
    3. a prompt, if allowed (not --auto, and stdin/stdout are a terminal)
    4. otherwise: a click.UsageError naming the missing option

Choices come from refdata for `download` and from the downloads folder for
`consolidate`/`verify` (see choices.py).
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

import click

from fxt.data.models import DatasetKey
from fxt.data.refdata import sources
from fxt.term import is_term
from fxt.term.prompts import pick_datetime, pick_fuzzy

from . import choices
from .options import ALL, split_symbols

__all__ = ["Scope", "Resolver", "parse_day"]

Scope = Literal["refdata", "downloads"]


def parse_day(text: str) -> date:
    """ "2024-03-05" or any ISO datetime -> its UTC date. """
    dt = datetime.fromisoformat(text.strip())
    return (dt.astimezone(UTC) if dt.tzinfo else dt).date()


#!================================================================================(80)
#! resolver
#!--------------------------------------------------------------------------------(80)
class Resolver:
    """ One per command invocation.

        pick_one / pick_many / pick_day are injectable so tests can answer
        prompts without a terminal.
    """
    def __init__(
        self,
        *,
        scope: Scope,
        downloads: Path,
        auto: bool = False,
        interactive: bool | None = None,
        pick_one: Callable[[str, Sequence[str]], str] | None = None,
        pick_many: Callable[[str, Sequence[str]], list[str]] | None = None,
        pick_day: Callable[[str, str | None], date] | None = None,
    ) -> None:
        self.scope = scope
        self.downloads = downloads
        self.auto = auto
        self.can_prompt = (not auto) and (is_term(interactive=True) if interactive is None else interactive)
        self._pick_one = pick_one or (lambda msg, ch: pick_fuzzy(msg, list(ch)))
        self._pick_many = pick_many or _fuzzy_many
        self._pick_day = pick_day or (lambda msg, default: pick_datetime(msg, default=default).date())

    #! ---- helpers -------------------------------------------------------------
    def _missing(self, option: str, choices: Sequence[str] = ()) -> click.UsageError:
        hint = f" Choices: {', '.join(map(str, choices))}" if choices and len(choices) <= 30 else ""
        why = "--auto was given" if self.auto else "not running in a terminal"
        return click.UsageError(f"Missing {option} ({why}).{hint}")

    def _one(self, option: str, label: str, value: str | None, options: Sequence[str]) -> str:
        if not options:
            raise click.UsageError(f"No {label} available{self._where()}.")
        if value is not None:
            return value                       # checked later via refdata
        if len(options) == 1:
            return options[0]                  # same as pick_fuzzy's auto-select, without a terminal
        if not self.can_prompt:
            raise self._missing(option, options)
        return self._pick_one(f"Pick a {label}:", options)

    def _where(self) -> str:
        return f" in {self.downloads}" if self.scope == "downloads" else " in refdata"

    #! ---- values --------------------------------------------------------------
    def source(self, value: str | None) -> str:
        return self._one("-b/--source", "SOURCE", value, choices.refdata_sources())

    def market(self, value: str | None, source: str, symbols: list[str]) -> str:
        if value is None and symbols and symbols != [ALL]:
            try:                               # infer from the first symbol, if unambiguous
                return sources()[source].market_of(_squash_for_source(source, symbols[0]))
            except (KeyError, LookupError):
                pass
        return self._one("-m/--market", "MARKET", value, choices.source_markets(source))

    def symbols(self, values: list[str], source: str, market: str) -> list[str]:
        available = (choices.source_symbols(source, market) if self.scope == "refdata"
                     else choices.downloaded_symbols(self.downloads, source, market))
        if not available:
            raise click.UsageError(f"No symbols for {source}/{market}{self._where()}.")
        if any(v.upper() == ALL for v in values):
            if len(values) > 1:
                raise click.UsageError("-i ALL can't be combined with other symbols.")
            return available
        if values:
            if self.scope == "downloads":     # must exist on disk, not just in refdata
                names = [DatasetKey.from_refdata(source, market, v, _any_interval(source)).symbol
                         for v in values]
                missing = [n for n in names if n not in available]
                if missing:
                    raise click.UsageError(f"Not downloaded: {', '.join(missing)}{self._where()}.")
                return names
            return values
        if len(available) == 1:
            return available
        if not self.can_prompt:
            raise self._missing("-i/--symbol", available)
        picked = self._pick_many("Pick SYMBOL(s):", available)
        if not picked:
            raise click.UsageError("No symbols picked.")
        return picked

    def interval(self, value: str | None, source: str, market: str, symbols: list[str]) -> str:
        options = (choices.source_intervals(source) if self.scope == "refdata"
                   else choices.downloaded_intervals(self.downloads, source, market, symbols))
        return self._one("-t/--interval", "INTERVAL", value, options)

    def years(self, value: list[int] | str | None, source: str, market: str,
              symbols: list[str], interval: str) -> tuple[int, ...]:
        """ For consolidate/verify: the years to process, always a real list.

            ALL (from -y ALL or picked in the prompt) expands to every year
            folder on disk for these symbols (union across symbols).
            Explicit years must exist on disk for at least one symbol.
        """
        on_disk = choices.downloaded_years(self.downloads, source, market, symbols, interval)
        if not on_disk:
            raise click.UsageError(f"No years for {', '.join(symbols)} {interval}{self._where()}.")
        if value == ALL:
            return tuple(on_disk)
        if value is not None:
            missing = sorted(set(value) - set(on_disk))      # type: ignore[arg-type]
            if missing:
                raise click.UsageError(
                    f"Not downloaded: {', '.join(map(str, missing))} "
                    f"(on disk: {', '.join(map(str, on_disk))}).")
            return tuple(value)                              # type: ignore[arg-type]
        if len(on_disk) == 1:
            return tuple(on_disk)
        if not self.can_prompt:
            raise self._missing("-y/--years (or -y ALL)", [str(y) for y in on_disk])
        picked = self._pick_many("Pick YEAR(s):", [ALL, *map(str, on_disk)])
        if not picked:
            raise click.UsageError("No years picked.")
        if ALL in picked:
            return tuple(on_disk)
        return tuple(sorted(int(y) for y in picked))

    def days(self, years: list[int] | str | None, start: str | None,
             end: str | None) -> tuple[date, date]:
        """ For download: [start, end) from -y, or --start/--end, or prompts.

            No -y and no --start: prompts for START, then for END with today
            pre-filled (Enter accepts it). --start given without --end: END
            defaults to today with no prompt, so scripts never stop.
            END isn't included and is capped at today (UTC), so only complete
            days are requested: END = today means "through yesterday".
        """
        today = datetime.now(UTC).date()
        if years == ALL:
            raise click.UsageError("download needs explicit years or --start/--end (-y ALL isn't allowed).")
        if years is not None and (start or end):
            raise click.UsageError("Use either -y/--years or --start/--end, not both.")
        if years is not None:
            ys = list(years)                   # type: ignore[arg-type]
            if ys != list(range(ys[0], ys[-1] + 1)):
                raise click.UsageError("download years must be one contiguous range, e.g. 2020-2024.")
            s, e = date(ys[0], 1, 1), date(ys[-1] + 1, 1, 1)
        else:
            prompted = False
            if start is None:
                if not self.can_prompt:
                    raise self._missing("-y/--years or -s/--start")
                s = self._pick_day("Pick the START day:", None)
                prompted = True
            else:
                s = parse_day(start)
            if end is not None:
                e = parse_day(end)
            elif prompted:
                e = self._pick_day("Pick the END day (not included; Enter = today):", "today")
            else:
                e = today                      # default: through yesterday
        return s, min(e, today)
#


#!================================================================================(80)
#! private
#!--------------------------------------------------------------------------------(80)
def _fuzzy_many(message: str, options: Sequence[str]) -> list[str]:
    """ pick_fuzzy with multiselect; always returns a list (it returns a bare
        str when it auto-selects the only choice).
    """
    picked = pick_fuzzy(message, list(options), multiselect=True)
    return [picked] if isinstance(picked, str) else list(picked)


def _any_interval(source: str) -> str:
    return choices.source_intervals(source)[0]


def _squash_for_source(source: str, symbol: str) -> str:
    """ Any spelling -> something Source.market_of accepts (source spelling or official). """
    src = sources()[source]
    try:
        return src.from_source_symbol(symbol).name
    except KeyError:
        return "".join(ch for ch in symbol if ch.isalnum()).upper()
#-
