#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
`fxt.paths`

Creates a `PathSettings` model that provides, if nothing else, direct access
to the root of the pixi project.

It will probably include other important paths as well.

"""

#!================================================================================(80)
#! imports
#!--------------------------------------------------------------------------------(80)
import os
import logging
from pathlib import Path
import tomllib

from pydantic import model_validator, BaseModel, ConfigDict, Field


#!================================================================================(80)
#! setup
#!--------------------------------------------------------------------------------(80)
logger = logging.getLogger(__name__)


#!================================================================================(80)
#! original
#!--------------------------------------------------------------------------------(80)
def pyproject_has_pixi_section(filepath: str | Path) -> bool:
    """ Check's if the provided filepath contains a section that identifies
        it as a pixi config using the `toml` format.
    """
    path = Path(filepath)
    if not path.exists():
        return False

    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
        
        tool_table = data.get("tool")
        if not isinstance(tool_table, dict):
            return False

        # Checks if 'pixi' exists as a sub-table under [tool]
        pixi_table = tool_table.get("pixi")
        return isinstance(pixi_table, dict) and bool(pixi_table)

    except Exception:
        return False
#
def get_pixi_root(start_path:Path = Path(__file__)) -> Path|None:
    """ Returns path of nearest pixi env, or None.
        
        Attempts to determine the path for the parent pixi env starting
        from the specified location (`start_path`) using the following
        methods..

        1. check env var: PIXI_PROJECT_ROOT 
           this is set when you run something with pixi
        
        2. looks for the nearest config file, which can be:
           
           a. pixi.toml, or

           b. pyproject.toml with the toml section:
              [tool.pixi.workspace]
    """
    if(not start_path.exists()):
        raise ValueError(
            "the provided path doesn't exist; how can it be a pixi project; "
            f"provided path: \n    {start_path}"
        )

    #----------------------------------------(40)

    for parent in start_path.resolve().parents:

        if (parent / "pixi.toml").exists():
            return parent
        
        pyproj = parent / "pyproject.toml"
        if pyproj.exists() and pyproject_has_pixi_section(pyproj):
            return parent
    
    env = os.environ.get("PIXI_PROJECT_ROOT")
    return Path(env) if env else None
#


#!================================================================================(80)
#! new
#!--------------------------------------------------------------------------------(80)
def find_project_root() -> Path:
    if env := os.environ.get("PIXI_PROJECT_ROOT"):   # set by `pixi run` / `pixi shell`
        return Path(env)
    for d in (Path.cwd(), *Path.cwd().parents):
        if (d / "pixi.toml").exists():
            return d
    raise RuntimeError("Couldn't find the project root (no pixi.toml found)")
#

class PathSettings(BaseModel):
    """ I don't really use this much other than for root, but keeping for now
        
        Current setup: (2026-11-22)

        root/
        ├── data                        main data lake, prob a symlink
        │   ├── ingest
        │   │   ╰── downloads
        │   ╰── lake
        │       ├── raw
        │       ╰── derived
        │
        ├── jupyter/
        │   > currently a placeholder should I wish to add jupyter later
        │
        ├── runs/                       research data, see fxt.research.paths
        │   ├── <group>/                same slugs as fxtapps/research/<group>/...
        │   │   ├── common/data/        group scope: lake/ (data/lake layout) + declared dirs
        │   │   ╰── <project>/
        │   │       ├── experiments.db
        │   │       ├── data/           project scope: lake/ + declared dirs
        │   │       ╰── artifacts/<run-id>/
        │   ╰── lockbox.db              global, shared by all projects
        │
        ├── scripts/
        │
        ├── src/
        │   ├── fxt
        │   │   ├── __init__.py
        │   │   ╰── ...
        │   │
        │   ╰── fxtapps
        │       ├── __init__.py
        │       ╰── ...
        │
        ├── test/                       unit tests, should mirror `src`
        │   ├── fxt
        │   ╰── fxtapps
        │
        ├── fxt.env                     project-wide secrets (not in git)
        ├── fxt.toml                    project-wide config (in git)
        ├── pixi.toml                   deps + tasks
        ├── pyproject.toml              package settings + tool settings
        ╰── ...


    """
    model_config = ConfigDict(extra="forbid")

    root:Path = Field(default_factory=find_project_root)
    #jupyter:Path = Path("jupyter")
    #dataprep:Path = Path("data/dataprep")
    #top level
    data:Path = Path("data")
    ingest:Path = Path("data/ingest")
    lake:Path = Path("data/lake")

    jupyter:Path = Path("jupyter")
    runs:Path = Path("runs")
    scripts:Path = Path("scripts")

    
    @model_validator(mode="after")
    def _resolve(self):
        self.root = self.root.expanduser().resolve()

        attrs = sorted([
            attr for attr in type(self).model_fields
            if not attr.startswith("_") and attr != "root"
        ])
        for name in attrs: #("jupyter", "dataprep", "datalake", "research", "experiments"):
            p = getattr(self, name).expanduser()
            setattr(self, name, p if p.is_absolute() else self.root / p)
        return self
#



#!================================================================================(80)
#! gogogogog
#!--------------------------------------------------------------------------------(80)
if(__name__ == "__main__"):
    from rich.pretty import pprint
    
    pprint(PathSettings())

