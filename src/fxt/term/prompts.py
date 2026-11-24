#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
`fxt.term.prompts`

Utils for working with puzzy prompts/etc, specifically part of InquirerPy
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations
import logging
import re
from datetime import datetime, timezone, tzinfo, UTC
from typing import Any, Literal

from InquirerPy.prompts import InputPrompt
from prompt_toolkit.document import Document
from prompt_toolkit.validation import ValidationError, Validator

__ALL__ = [
    'pick_datetime',
    'pick_fuzzy',
    'SafeFuzzyPrompt',
]
#!================================================================================(80)
#! setup (logging, exceptions, etc)
#!--------------------------------------------------------------------------------(80)
from rich.logging import RichHandler
logging.basicConfig(
    #level=logging.DEBUG,
    handlers=[RichHandler(rich_tracebacks=True, markup=True)]
)
logger = logging.getLogger(__name__)
#logger.setLevel(logging.DEBUG)


#!================================================================================(80)
#! constants
#!--------------------------------------------------------------------------------(80)
_HAS_FULL_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ].*)?$")


#!================================================================================(80)
#! prompt: datetime
#!--------------------------------------------------------------------------------(80)
class _DateTimeValidator(Validator):
    """
    """
    def validate(self, document: Document) -> None:
        """
        """
        text = document.text.strip()
        end = len(document.text)

        if not _HAS_FULL_DATE.match(text):
            raise ValidationError(
                message="Year, month and day are required: YYYY-MM-DD [HH:MM[:SS]]",
                cursor_position=end,
            )
        try:
            datetime.fromisoformat(text)
        except ValueError as e:
            raise ValidationError(message=f"Invalid date/time: {e}", cursor_position=end)
#
class DateTimePrompt(InputPrompt):
    """ Text prompt that requires a full YYYY-MM-DD date and returns a datetime.
        Time is optional. Naive input is assumed to be in `tz` (default UTC).

        Args:
            message: prompt message
            default: 
                if None, no default is displayed
                if a datetime, the datetime (as a str) is displayed
                if "today", today's date is displayed
                if "now", the current date and time is displayed

        Based on:
        https://inquirerpy.readthedocs.io/en/latest/pages/prompts/input.html#reference
    """

    def __init__(
        self,
        message: str,
        default: Literal["today", "now"] | datetime | None = None,
        tz: tzinfo = UTC,
        **kwargs: Any,
    ) -> None:
        self._default_tz = tz

        #! process default value
        if default is None:
            default = ""
        elif(default == "today"):
            default = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        elif(default == "now"):
            default = datetime.now(tz)
        elif(isinstance(default, str)):
            if not _HAS_FULL_DATE.match(default):
                raise ValueError(
                    "Can't use specified `default` for pick_datetime; invalid format; "
                    f"provided: {default}"
                    #"YYYY-MM-DD [HH:MM[:SS]]"
                )
            default = datetime.fromisoformat(default)
        #~ convert to str if needed
        if(isinstance(default, datetime)):
            default = default.strftime("%Y-%m-%d %H:%M")

        #print(f"default: {default}")
        #sys.exit()

        #! set defaults
        kwargs.setdefault("instruction", f"(format: YYYY-MM-DD [HH:MM])(default tz: {tz})")
        kwargs.setdefault("validate", _DateTimeValidator())
        kwargs.setdefault("filter", self._parse)
        kwargs.setdefault("transformer", lambda s: s.strip())

        #! ggogogo
        super().__init__(message=message, default=default, **kwargs)
    #

    def _parse(self, text: str) -> datetime:
        dt = datetime.fromisoformat(text.strip())
        return dt if dt.tzinfo else dt.replace(tzinfo=self._default_tz)
    #
    
    def execute(self, raise_keyboard_interrupt: bool | None = None) -> datetime:
        return super().execute(raise_keyboard_interrupt)
    #
#-

def pick_datetime(message: str, **kwargs: Any) -> datetime:
    """ Creates a datetime prompt using `InquirerPy`s api.
    """
    return DateTimePrompt(message, **kwargs).execute()
#-


#!================================================================================(80)
#! prompt: fuzzy
#!--------------------------------------------------------------------------------(80)
from collections.abc import Sequence
from InquirerPy.prompts.fuzzy import FuzzyPrompt

MULTISELECT_HELP = (
    "tab: select + move down · shift+tab: select + move up · ctrl+r: toggle all · "
    "enter: confirm (nothing selected = the highlighted item)"
)

class SafeFuzzyPrompt(FuzzyPrompt):
    """ FuzzyPrompt that ignores keys when the filter hides every choice.

        InquirerPy 0.3.4 bugs, all with 0 visible choices (e.g. after typing a
        space):
        - up/down/tab/shift+tab: `index % choice_count` -> ZeroDivisionError
          (cycle=True, the default)
        - tab/shift+tab: indexes the empty filtered list -> IndexError
        - enter: exits with None (single) or [] (multiselect) instead of
          waiting for a real choice
        Here those keys do nothing until the filter shows something again.
        Choices already selected with tab still count for enter, even if the
        current filter hides them.
    """
    def _no_visible_choices(self) -> bool:
        return self.content_control.choice_count == 0

    def _handle_up(self, event) -> bool:
        return False if self._no_visible_choices() else super()._handle_up(event)

    def _handle_down(self, event) -> bool:
        return False if self._no_visible_choices() else super()._handle_down(event)

    def _handle_toggle_choice(self, event) -> None:
        if not self._no_visible_choices():
            super()._handle_toggle_choice(event)

    def _handle_enter(self, event) -> None:
        if self._no_visible_choices() and not (self._multiselect and self.selected_choices):
            return
        super()._handle_enter(event)
#


def pick_fuzzy(
        message:str, 
        choices:Sequence[str],
        pick_first_if_one:bool = True,
        *, #rest are kwargs for FuzzyPrompt
        max_height:str|None = "70%", 
        match_exact:bool = False,
        multiselect:bool=False,
        **kwargs
    ) -> str:
    """ Displays a prompt where you can type in part of the name of the selection 
        you want, and it will do a fuzzy search and show you the subset that
        match to choose from.

        Even if you type in the name, you still need to select a valid entry from 
        the list!

        Args:
            message: prompt message
            choices: prompt choices
            pick_first_if_one:
                if True, if there is only one chioce, will auto return
                that choice
        
        Returns:
            the selected list entry
    """
    from rich import print

    if(pick_first_if_one and len(choices) == 1):
        value = choices[0]
        print(
            f"[orange2]?[/] [cyan]{message}[/] -- "
            f"Auto selecting only available value: [bold bright_yellow]{value}[/]"
        )
        return value

    #from fxt.term import Colors
    #Colors.ORANGE4


    message += f" (#: {len(choices)})"
    if multiselect:
        kwargs.setdefault("long_instruction", MULTISELECT_HELP)
    #return inquirer.fuzzy(
    return SafeFuzzyPrompt(
        message=message, 
        choices=list(choices),
        max_height=max_height,
        match_exact=match_exact,
        multiselect=multiselect,
        **kwargs
    ).execute()
#




#!================================================================================(80)
#! gogogogog
#!--------------------------------------------------------------------------------(80)
if(__name__ == "__main__"):
    import sys
    from datetime import datetime
    from rich import print

    #! test fuzzy prompt
    month = pick_fuzzy("Pick a month", [
        "January",# "February", "March", "April"
    ])

    source = pick_fuzzy("Pick a source", ["dukascopy"])
    #sys.exit()

    #! test datetime prompt
    values = {
        "month": month,
        "source": source,
        # "dt_normal": pick_datetime(
        #     message="Choose a DATETIME (w/ no default):"
        # ),

        # "dt_datetime": pick_datetime(
        #     message="Choose a DATETIME (w/ default datetime):\n",
        #     default=datetime(2010,1,1)
        # ),

        # "date_today": pick_datetime(
        #     message="Choose a DATETIME (with default='today'):",
        #     default="today"
        # ),

        # "date_now": pick_datetime(
        #     message="Choose a DATETIME (with default='now'):",
        #     default="now"
        # ),
        "date_str": pick_datetime(
            message="Choose a DATETIME (with default str):",
            default="2027-12-01"
        ),
    }





    from pprint import pprint
    print("[bold cyan]chosen values[/]")
    pprint(values, indent=4)