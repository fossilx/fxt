#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
research project: examples/p00_smoke

Template project. Proves the wiring: code location -> data location, the
dispatcher, group-shared code and data, and a notebook that imports the project.

    p00_smoke/
    ├── __init__.py         PROJECT declaration (this file)
    ├── cli.py              `pixi run research examples p00_smoke ...`
    ├── README.md           question, hypothesis, status (kept current)
    ╰── notebooks/          jupytext percent-format .py files (versioned)

Data:  runs/examples/p00_smoke/        this project (PROJECT.paths().data)
       runs/examples/common/           shared by the group (PROJECT.paths().common)
"""
from __future__ import annotations

from fxt.research.paths import DataDir, project_from_module

from ..common import GROUP

__all__ = ["PROJECT"]

PROJECT = project_from_module(__name__, group=GROUP, data_dirs={
    "scratch": DataDir("notebook scratch; nothing depends on it"),
})
