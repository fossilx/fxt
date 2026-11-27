#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
`fxt.settings`

Project settings loaders for two settings files, both project wide, currently
stored at the pixi root as:
- fxt.env : for secrets
- fxt.toml : for library/project settings/overrides

I don't have to use this often, but meh.

I didn't use .env cuz I wanted them to stay listed next to each other.

"""

#!================================================================================(80)
#! imports
#!--------------------------------------------------------------------------------(80)
import os
import logging
from pathlib import Path
from functools import lru_cache

from pydantic import BaseModel, SecretStr, Field
from pydantic_settings import (
    BaseSettings, PydanticBaseSettingsSource,
    SettingsConfigDict, TomlConfigSettingsSource,
)

from fxt.core.env import ENVSettings
from fxt.core.io.parquet_store import ParquetStoreSettings
from fxt.paths import PathSettings



#!================================================================================(80)
#! setup
#!--------------------------------------------------------------------------------(80)
logger = logging.getLogger(__name__)

PATHS:PathSettings = PathSettings()

ENV_FILE = PATHS.root / "fxt.env"
CONFIG_FILE = PATHS.root / 'fxt.toml'
CONFIG_ENV_VAR = "FXT_CONFIG"

#print(f"ENV_FILE: {ENV_FILE}")
#print(f"CONFIG_FILE: {CONFIG_FILE}")


#!================================================================================(80)
#! env file
#!--------------------------------------------------------------------------------(80)
class Secrets(ENVSettings):  
    #.env only
    #model_config = SettingsConfigDict(env_prefix="FXT_", env_file=".env")
    #model_config = SettingsConfigDict(env_file="fxt.env")
    TELEGRAM_TOKEN: SecretStr
    TELEGRAM_USERID: int

    #! jupyter-specific
    JUPYTER_PASSWORD_HASH: SecretStr|None = None
#

@lru_cache
def get_secrets() -> Secrets:
    """ 
    """
    #return Secrets.from_path_tree(__file__)
    return Secrets.from_env_files(
        [ENV_FILE]
    )
#

#! to test the env var setting...
#os.environ.setdefault(CONFIG_ENV_VAR, str(Path(__file__).parent / "xfxt.toml"))


#!================================================================================(80)
#! toml setup
#!--------------------------------------------------------------------------------(80)
def _toml_config() -> Path:
    """ toml file should be at the root of this PIXI PROJECT
        
        this is a change !
    """
    config:Path
    src:str

    if(override := os.environ.get(CONFIG_ENV_VAR)): #"FXT_CONFIG"):
        src = f"env-var('{CONFIG_ENV_VAR}')"
        config = Path(override)
    else:
        src = f"config-file('{CONFIG_FILE}')"
        config = Path(__file__).parent / CONFIG_FILE

    if(not config.is_file()):
        raise FileNotFoundError(
            f"Failed to load fxt library settings using method: {src}, file: {config}"
        )
    return config
#

class Settings(BaseSettings):
    """
    """
    model_config = SettingsConfigDict(
        toml_file=_toml_config(),
        env_prefix="FXT_",
        env_nested_delimiter="__"
    )

    #name of field corrersponds to name of key (i think)
    parquet_store: ParquetStoreSettings
    paths: PathSettings = Field(default_factory=PathSettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings, TomlConfigSettingsSource(settings_cls))
    #
#-

@lru_cache
def get_settings() -> Settings:
    """ Switching to this (rather than get_env)
    """
    #return #FXTSettings.from_path_tree(__file__)
    return Settings() #type: ignore[call-arg]
#



#!================================================================================(80)
#! previewing/output
#!--------------------------------------------------------------------------------(80)
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.tree import Tree

def _fmt_value(value: object) -> str:
    """ Format a single leaf value; secrets are never revealed. 
    """
    if isinstance(value, SecretStr):
        n = len(value.get_secret_value())
        return f"[yellow]{'•' * 8}[/] [dim](secret, len {n})[/]"
    
    if isinstance(value, Path):
        status = "[green]✓[/]" if value.exists() else "[red]✗[/]"
        return f"{status} {escape(str(value))}"
    
    return f"{escape(repr(value))} [dim]({type(value).__name__})[/]"
#
 
def _build_tree(model: BaseModel, tree: Tree, mask_extra: bool) -> Tree:
    """ Recursively add a model's fields (and any extras) to a rich Tree. 
    """
    for name in type(model).model_fields:
        value = getattr(model, name)
        if isinstance(value, BaseModel):
            _build_tree(value, tree.add(f"[bold cyan]{name}[/]"), mask_extra)
        else:
            tree.add(f"[cyan]{name}[/]: {_fmt_value(value)}")
 
    # undeclared values (extra="allow") are plain strings, so mask them if asked
    for name, value in (model.model_extra or {}).items():
        shown = SecretStr(str(value)) if mask_extra else value
        tree.add(f"[magenta]{escape(name)}[/] [dim](extra)[/]: {_fmt_value(shown)}")
    return tree
#

_SECRET_COLORS = ['orchid1', 'orchid2', 'pale_violet_red1']
_SETTING_COLORS = ['cyan1', 'steel_blue1', 'aquamarine3']

def show_settings(
    settings: BaseModel | None = None,
    secrets: BaseModel | None = None,
    console: Console | None = None,
) -> None:
    """ Print the Settings and Secrets models as trees.
 
        - SecretStr values are always hidden (only their length is shown)
        - extra (undeclared) keys on Secrets are masked too, since they're plain strings
        - Paths show ✓/✗ for whether they exist
    """
    console = console or Console()
    settings = settings if settings is not None else get_settings()
    secrets = secrets if secrets is not None else get_secrets()
    
    console.print(Panel(
        "Settings are currently loaded from the following files @ the pixi root:"
        f"\n- as [bold {_SETTING_COLORS[0]}]settings[/] -- from: [{_SETTING_COLORS[1]}]{CONFIG_FILE.name}[/]"
        f"\n- as [bold {_SECRET_COLORS[0]}]secrets[/] -- from: [{_SECRET_COLORS[1]}]{ENV_FILE.name}[/]",
        #title=f"[bold orchid2]{title}[/]"
    ))

    for model, title, mask_extra in (
        (settings, "settings", False),
        (secrets, "secrets", True),
    ):
        title_color:str = ""
        tree_top:str = ""

        if(str(title).lower() == "settings"):
            title_color = _SETTING_COLORS[0]
            tree_top = _SETTING_COLORS[1]
        elif(str(title).lower() == "secrets"):
            title_color = _SECRET_COLORS[0]
            tree_top = _SECRET_COLORS[1]
        
        tree = _build_tree(model, Tree(f"[bold {tree_top}]{type(model).__name__}[/]"), mask_extra)
        console.print(Panel(tree, title=f"[{title_color}]{title}[/]"))
#





#!================================================================================(80)
#! gogogogog
#!--------------------------------------------------------------------------------(80)
if(__name__ == "__main__"):
    import sys
    from rich import print

    #print(Panel(get_secrets()))
    #print(_toml_config())
    #print("NEEDS UPDATED")
    show_settings()
