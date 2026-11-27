#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
`fxt.research.paths`

Where research data lives. Code and data use the same two slugs:

    code:  src/fxtapps/research/<group>/<project>/      (and <group>/common/)
    data:  runs/<group>/<project>/                      (and <group>/common/)

    runs/
    ├── lockbox.db                      global: every look at held-out data, all projects
    ╰── <group>/
        ├── common/                     group scope (`common` is a reserved slug)
        │   ╰── data/
        │       ├── lake/derived/...    same partitions as data/lake (fxt.data.paths.Lake)
        │       ╰── <declared>/         custom dirs, declared in <group>/common/__init__.py
        ╰── <project>/                  project scope
            ├── experiments.db
            ├── data/
            │   ├── lake/derived/...
            │   ╰── <declared>/         custom dirs, declared in <project>/__init__.py
            ╰── artifacts/<run-id>/     outputs of one run

Both scopes have the same shape (`<scope>/data/{lake,<declared>}`), so code that
builds data doesn't care which one it writes to. A dataset in a scope's lake has
the main lake's layout, so promoting it to data/lake is a move.

Declarations:

    # fxtapps/research/<group>/common/__init__.py
    GROUP = group_from_module(__name__, data_dirs={
        "features": DataDir("shared feature tables", key=FeatureKey),   # partitioned
    })

    # fxtapps/research/<group>/<project>/__init__.py
    from ..common import GROUP
    PROJECT = project_from_module(__name__, group=GROUP, data_dirs={
        "scratch": DataDir("notebook scratch; nothing depends on it"),   # free-form
    })

    scope.dir("scratch")          -> Path            (any declared dir)
    scope.partitioned("features") -> PartitionedDir  (declared with a key)
    scope.lake                    -> Lake            (main lake layout)

NOTE: placement only. The tracking schema, run manifests and the lockbox get
their own formal definitions later.
"""


#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar

from fxt.core.io.partitioned import PartitionedDir, PartitionKey
from fxt.data.paths import Lake, LakeKey

__all__ = [
    "APPS_PACKAGE",
    "SLUG_RE",
    "DataDir",
    "DataScope",
    "FeatureKey",
    "Group",
    "Project",
    "ProjectPaths",
    "group_from_module",
    "lockbox_db",
    "project_from_module",
    "runs_root",
]

#: package that holds project code: fxtapps.research.<group>.<project>
APPS_PACKAGE = "fxtapps.research"

#: a slug is used as a python package name AND a directory name
SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")

COMMON = "common"
#: names a group may not use (they're dirs/modules at the same level)
RESERVED_GROUPS = frozenset({COMMON, "cli"})
#: names a project may not use inside a group
RESERVED_PROJECTS = frozenset({COMMON, "cli"})
#: names a declared data dir may not use (fixed members of every scope's data/)
RESERVED_DATA_DIRS = frozenset({"lake"})

LOCKBOX_DB = "lockbox.db"
EXPERIMENTS_DB = "experiments.db"
DATA_DIR = "data"
LAKE_DIR = "lake"
ARTIFACTS_DIR = "artifacts"


#!================================================================================(80)
#! roots
#!--------------------------------------------------------------------------------(80)
def runs_root() -> Path:
    """ `runs/` from the project settings (fxt.toml [paths] can override it). """
    from fxt.settings import get_settings   # lazy: keeps this module import-light
    return get_settings().paths.runs


def lockbox_db(root: Path | None = None) -> Path:
    """ The one lockbox shared by every group and project. """
    return (root if root is not None else runs_root()) / LOCKBOX_DB


def _check_slug(kind: str, value: str, reserved: frozenset[str]) -> None:
    if not isinstance(value, str) or not SLUG_RE.match(value):
        raise ValueError(
            f"{kind} {value!r} must match {SLUG_RE.pattern} "
            "(lowercase, digits, underscores; starts with a letter)"
        )
    if value in reserved:
        raise ValueError(f"{kind} {value!r} is reserved")


#!================================================================================(80)
#! declared data dirs
#!--------------------------------------------------------------------------------(80)
@dataclass(frozen=True, slots=True)
class DataDir:
    """ A custom data dir a scope declares. With `key`, the dir is laid out by
        that PartitionKey (`scope.partitioned(name)`); without one it's free-form. """
    description: str = ""
    key: type[PartitionKey] | None = None

    def __post_init__(self) -> None:
        if self.key is not None and not (isinstance(self.key, type) and issubclass(self.key, PartitionKey)):
            raise TypeError(f"DataDir key must be a PartitionKey subclass, got {self.key!r}")


def _freeze_dirs(kind: str, dirs: Mapping[str, DataDir] | None) -> Mapping[str, DataDir]:
    dirs = dict(dirs or {})
    for name, d in dirs.items():
        _check_slug(f"{kind} data dir", name, RESERVED_DATA_DIRS)
        if not isinstance(d, DataDir):
            raise TypeError(f"data dir {name!r} must be a DataDir, got {type(d).__name__}")
    return MappingProxyType(dirs)


#!================================================================================(80)
#! common partition keys
#!--------------------------------------------------------------------------------(80)
class FeatureKey(PartitionKey):
    """ Lake layout with a leading config level, for parameterised datasets
        (features, events, labels, ...): config/source/market/symbol/interval/year.
        `config` is the config hash of whatever built the file. """
    FILE_GLOB: ClassVar[str] = "*.parquet"

    config:   str
    source:   str
    market:   str
    symbol:   str
    interval: str
    year:     int

    @property
    def filename(self) -> str:
        return f"{self.symbol}-{self.year}.parquet"

    @classmethod
    def for_lake(cls, config: str, key: LakeKey) -> FeatureKey:
        """ The feature file built from one lake file under one config. """
        return cls(config=config, **key.model_dump())

    def lake_key(self) -> LakeKey:
        """ The lake partition this feature file lines up with. """
        return LakeKey(**self.model_dump(exclude={"config"}))


#!================================================================================(80)
#! identities
#!--------------------------------------------------------------------------------(80)
@dataclass(frozen=True, slots=True)
class Group:
    """ A research group and the data dirs its `common` scope declares. """
    name: str
    data_dirs: Mapping[str, DataDir] = field(default_factory=dict, compare=False, hash=False, repr=False)

    def __post_init__(self) -> None:
        _check_slug("group", self.name, RESERVED_GROUPS)
        object.__setattr__(self, "data_dirs", _freeze_dirs(f"group {self.name!r}", self.data_dirs))

    @property
    def module(self) -> str:
        return f"{APPS_PACKAGE}.{self.name}"

    def common(self, root: Path | None = None) -> DataScope:
        """ The group's shared data scope: runs/<group>/common/. """
        runs = root if root is not None else runs_root()
        return DataScope(label=f"{self.name}/{COMMON}", root=runs / self.name / COMMON,
                         declared=self.data_dirs)

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True, slots=True)
class Project:
    """ Identity of a research project: `(group, id)`. `group` may be a name or a
        declared Group (which carries the group's data dir declarations). """
    group: Group
    id: str
    data_dirs: Mapping[str, DataDir] = field(default_factory=dict, compare=False, hash=False, repr=False)

    def __init__(self, group: Group | str, id: str, data_dirs: Mapping[str, DataDir] | None = None):
        g = group if isinstance(group, Group) else Group(group)
        _check_slug("project id", id, RESERVED_PROJECTS)
        object.__setattr__(self, "group", g)
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "data_dirs", _freeze_dirs(f"project {g.name}/{id}", data_dirs))

    @property
    def key(self) -> str:
        """ `group/id`, for logs and registry rows. """
        return f"{self.group.name}/{self.id}"

    @property
    def module(self) -> str:
        """ Where the project's code lives. """
        return f"{APPS_PACKAGE}.{self.group.name}.{self.id}"

    def paths(self, root: Path | None = None) -> ProjectPaths:
        """ Data paths under `root` (default: `runs/` from settings). """
        return ProjectPaths(project=self, runs=root if root is not None else runs_root())

    def __str__(self) -> str:
        return self.key


def _module_parts(name: str, need: int) -> list[str]:
    prefix = APPS_PACKAGE + "."
    if not name.startswith(prefix):
        raise ValueError(f"{name!r} is not under {APPS_PACKAGE}")
    parts = name[len(prefix):].split(".")
    if len(parts) < need:
        raise ValueError(f"{name!r} is too short: expected {APPS_PACKAGE}.<group>.<project|common>")
    return parts


def group_from_module(name: str, data_dirs: Mapping[str, DataDir] | None = None) -> Group:
    """ Call from `fxtapps.research.<group>.common` -> Group(<group>). """
    parts = _module_parts(name, 2)
    if parts[1] != COMMON:
        raise ValueError(f"declare a group in {APPS_PACKAGE}.{parts[0]}.{COMMON}, not {name!r}")
    return Group(parts[0], data_dirs)


def project_from_module(
    name: str,
    *,
    group: Group | None = None,
    data_dirs: Mapping[str, DataDir] | None = None,
) -> Project:
    """ `fxtapps.research.<group>.<project>[.anything]` -> Project. Pass the
        group's declared `GROUP` to get its common data dirs too. """
    parts = _module_parts(name, 2)
    if group is not None and group.name != parts[0]:
        raise ValueError(f"group {group.name!r} doesn't match module {name!r}")
    return Project(group if group is not None else parts[0], parts[1], data_dirs)


#!================================================================================(80)
#! scopes + paths
#!--------------------------------------------------------------------------------(80)
@dataclass(frozen=True, slots=True)
class DataScope:
    """ `<scope>/data/`: a lake with the main lake's layout plus declared dirs.
        Same shape for a group's common scope and for a project. """
    label: str
    root: Path
    declared: Mapping[str, DataDir] = field(repr=False)

    @property
    def data(self) -> Path:
        return self.root / DATA_DIR

    @property
    def lake(self) -> Lake:
        """ Lake rooted in this scope: lake.derived.path(source=..., ...) etc. """
        return Lake(root=self.data / LAKE_DIR)

    def _declared(self, name: str) -> DataDir:
        if name not in self.declared:
            known = ", ".join(sorted(self.declared)) or "(none)"
            raise KeyError(f"{self.label}: data dir {name!r} isn't declared (declared: {known})")
        return self.declared[name]

    def dir(self, name: str) -> Path:
        """ A declared custom data dir. Undeclared names are an error, so every
            dir a scope uses is listed in its __init__.py. """
        self._declared(name)
        return self.data / name

    def partitioned(self, name: str) -> PartitionedDir:
        """ A declared dir that has a partition key. """
        key = self._declared(name).key
        if key is None:
            raise TypeError(f"{self.label}: data dir {name!r} was declared without a key")
        return PartitionedDir(self.data / name, key)

    def ensure(self) -> DataScope:
        """ Create data/, data/lake/ and every declared dir (idempotent). """
        (self.data / LAKE_DIR).mkdir(parents=True, exist_ok=True)
        for name in self.declared:
            (self.data / name).mkdir(exist_ok=True)
        return self


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    """ Path builders only; nothing is created until `ensure()` is called. """
    project: Project
    runs: Path = field(repr=False)

    @property
    def root(self) -> Path:
        return self.runs / self.project.group.name / self.project.id

    @property
    def data(self) -> DataScope:
        """ This project's own data scope. """
        return DataScope(label=self.project.key, root=self.root, declared=self.project.data_dirs)

    @property
    def common(self) -> DataScope:
        """ The group's shared data scope. """
        return self.project.group.common(self.runs)

    @property
    def experiments_db(self) -> Path:
        return self.root / EXPERIMENTS_DB

    @property
    def artifacts(self) -> Path:
        return self.root / ARTIFACTS_DIR

    @property
    def lockbox_db(self) -> Path:
        return lockbox_db(self.runs)

    def run_dir(self, run_id: str) -> Path:
        """ Outputs of one run. `run_id` is a single path component. """
        if not run_id or "/" in run_id or "\\" in run_id or run_id in {".", ".."}:
            raise ValueError(f"bad run id: {run_id!r}")
        return self.artifacts / run_id

    def ensure(self) -> ProjectPaths:
        """ Create the project skeleton and the group's common scope (idempotent). """
        self.data.ensure()
        self.common.ensure()
        self.artifacts.mkdir(parents=True, exist_ok=True)
        return self


#!================================================================================(80)
#! gogogogog
#!--------------------------------------------------------------------------------(80)
if __name__ == "__main__":
    from rich.pretty import pprint

    p = Project("examples", "p00_smoke").paths()
    pprint({"project": p.project.key, "root": p.root, "data": p.data.data,
            "lake": p.data.lake.root, "common": p.common.data,
            "experiments": p.experiments_db, "lockbox": p.lockbox_db,
            "run": p.run_dir("example-run")})
