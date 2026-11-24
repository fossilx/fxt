#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxtapps.ingest.options

Click options shared by every ingest subcommand, defined once so names, short
flags and help text can't drift apart between download/consolidate/verify/run.

    @common_options        -b -m -i -t -y --dry --auto
    YEARS                  YearRangeType + "ALL"
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

import click

from fxt.term.click import YearRangeType

__all__ = ["ALL", "YEARS", "YearsType", "common_options", "split_symbols"]

ALL: Final = "ALL"


#!================================================================================(80)
#! param types
#!--------------------------------------------------------------------------------(80)
class YearsType(click.ParamType):
    """ fxt.term.click.YearRangeType plus `ALL` (any case).

            2024 | 2020-2024 | 2020..2024 | 2020,2023,2024  -> sorted list[int]
            ALL                                             -> "ALL"
    """
    name = "years"

    def convert(self, value: Any, param: click.Parameter | None, ctx: click.Context | None):
        if value is None or isinstance(value, list) or value == ALL:
            return value
        if str(value).strip().upper() == ALL:
            return ALL
        return YearRangeType.convert(value, param, ctx)
#

YEARS = YearsType()


def split_symbols(values: tuple[str, ...] | list[str] | None) -> list[str]:
    """ `-i AUDCAD -i eurjpy,GBP/USD` -> ["AUDCAD", "eurjpy", "GBP/USD"] (order kept,
        duplicates dropped). Spellings are normalized later via refdata.
    """
    out: list[str] = []
    for v in values or ():
        for part in str(v).split(","):
            part = part.strip()
            if part and part not in out:
                out.append(part)
    return out


#!================================================================================(80)
#! shared options
#!--------------------------------------------------------------------------------(80)
_COMMON: list[Callable[[Callable], Callable]] = [
    click.option("-b", "--source", default=None,
        help="Data source, e.g. dukascopy. Auto-picked if only one is available."),
    click.option("-m", "--market", default=None,
        help="Market, e.g. forex. Inferred from the symbol, or auto-picked if only one."),
    click.option("-i", "--symbol", "symbols", multiple=True,
        help="Symbol(s): repeat the option or comma-separate (-i AUDCAD,EURJPY), or ALL. "
             "Any spelling refdata knows (AUDCAD, AUD/CAD, AUD-CAD, aliases)."),
    click.option("-t", "--interval", default=None,
        help="Interval, e.g. TICK. Auto-picked if only one is available."),
    click.option("-y", "--years", type=YEARS, default=None,
        help="Year(s): 2024, 2020-2024, 2020..2024, 2020,2023, or ALL."),
    click.option("--dry", is_flag=True, default=False,
        help="Show what would happen; write nothing."),
    click.option("--auto", is_flag=True, default=False,
        help="Never prompt or ask for confirmation; missing values are an error."),
]

def common_options(f: Callable) -> Callable:
    """ Apply the shared options (listed top-to-bottom in --help). """
    for opt in reversed(_COMMON):
        f = opt(f)
    return f
#-
