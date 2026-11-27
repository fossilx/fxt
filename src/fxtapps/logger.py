#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
`fxtapps.logger`

Simple logger wrapper meant to make my logging messages pretty/functional no matter
where they are executed, the options being:
- from within vscode/console (so at a terminal), or
- from within jupyter

"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
import logging
#import re
#from io import StringIO

from rich.console import Console
#from rich.text import Text
from rich.logging import RichHandler

from fxt.utils import is_notebook




#!================================================================================(80)
#! example of stripping all rich markup
#!--------------------------------------------------------------------------------(80)
def create_logger(
        id:str,
        level:int=logging.DEBUG,
        force_notebook=False
    ):
    """ For testing differnt loggers without using basicConfig

        If this is executed from within jupyter, or `force_notebook=True`:
        - turns off the paths (aligned to the right) when printing
          debug messages.
    """
    logger = logging.getLogger(id)
    logger.setLevel(level)
    logger.handlers.clear()
    logger.propagate = False

    in_nb = is_notebook() or force_notebook
    handler = RichHandler(
        console=Console(force_jupyter=False) if in_nb else None,
        show_path=not in_nb, #False if in_nb else True,
        show_time=True,
        rich_tracebacks=True, 
        markup=True
    )
    handler.setFormatter(logging.Formatter(
        fmt="[grey62][[/][underline][deep_sky_blue1]%(name)s[/][/][grey62]][/] | %(message)s",
        datefmt="[%X]"
    ))
    logger.addHandler(handler)
    return logger
#




#!================================================================================(80)
#! gogogogog
#!--------------------------------------------------------------------------------(80)
if(__name__ == "__main__"):
    from rich import print
    #from rich.logging import RichHandler

    # handler = RichHandler(rich_tracebacks=True, markup=True)
    # formatter = handler.formatter
    # format_str = formatter._fmt if(formatter) else "<empty>"
    
    # print(f"Current log handler:    {handler}")
    # print(f"Current log formatter:  {formatter}")
    # print(f"Current log format str: {format_str}")
    
    print("TESTING: [bold green]normal[/]")
    logger = create_logger(id="normal")
    logger.debug("Debugging [bold cyan]variable[/bold cyan] values...")
    logger.info("Processing complete! Everything looks [bold green]good[/bold green].")
    logger.warning("High memory usage: [yellow]85%[/yellow]")
    logger.error("Failed to connect to [red underline]database[/red underline].")
    logger.critical("System crash imminent!")

    print()
    print()
    print("TESTING: [bold cyan]jupyter[/]")
    logger = create_logger(id="jupyter", force_notebook=True)
    #logger.setLevel(logging.DEBUG)
    logger.debug("Debugging [bold cyan]variable[/bold cyan] values...")
    logger.info("Processing complete! Everything looks [bold green]good[/bold green].")
    logger.warning("High memory usage: [yellow]85%[/yellow]")
    logger.error("Failed to connect to [red underline]database[/red underline].")
    logger.critical("System crash imminent!")
