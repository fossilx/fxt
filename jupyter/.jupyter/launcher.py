#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
jupyter lab launcher

launches jupyter via pixi env
"""


#!================================================================================(80)
#! imports
#!--------------------------------------------------------------------------------(80)
import os
import subprocess
import sys
from pathlib import Path

from fxt.settings import get_settings
import logging
logging.basicConfig(level=logging.DEBUG)

def get_project_root() -> Path:
    # root = os.environ.get("PIXI_PROJECT_ROOT")
    # if not root:
    #     sys.exit(
    #         "This launcher must be run inside a pixi environment.\n"
    #         "Try: pixi run python <this_script>.py  (or run it from `pixi shell`)"
    #     )
    # return Path(root)
    return get_settings().paths.root


#!================================================================================(80)
#! gogogogog
#!--------------------------------------------------------------------------------(80)
if __name__ == "__main__":
    from fxt.term import pause
    from rich import print
    from rich.panel import Panel
    from rich.pretty import Pretty, pprint


    cmd: list[str] = [
        "jupyter", "lab",
        "--no-browser",
        "--custom-css",
        #f"--notebook-dir={jupyter_root}",
        #f"--config={config}",
    ]

    print(Panel(
        " ".join(cmd),
        title="[bold green]jupyter command[/]", title_align="left"
    ))

    #! send a modified env
    project_root: Path = get_project_root()
    env:dict[str,str] = os.environ.copy()
    #this forces it to only usd the config file we specify, and not any other config files that may exist in the environment
    #env["JUPYTER_NO_CONFIG"] = "1"

    #pass a str
    env["JUPYTER_CONFIG_DIR"] = str(project_root / "jupyter" / ".jupyter")
    print(Panel(
        f"[cyan]JUPYTER_CONFIG_DIR[/]: {env["JUPYTER_CONFIG_DIR"]}",
        title="[bold green]adjusting env with[/]", title_align="left"
    ))
    pause()


    try:
        sys.exit(subprocess.run(
            cmd, 
            cwd=project_root,
            env=env
        ).returncode)
    except KeyboardInterrupt:
        sys.exit(0)