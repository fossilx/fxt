#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
jupyter lab configuration 

If a password is set in fxt.env, it will use it here.
"""


#!================================================================================(80)
#! imports
#!--------------------------------------------------------------------------------(80)
import os
from pathlib import Path
from typing import TYPE_CHECKING

from fxt.settings import get_settings, get_secrets


#!================================================================================(80)
#! error checking
#!--------------------------------------------------------------------------------(80)
project_root = get_settings().paths.root
#Path(os.environ["PIXI_PROJECT_ROOT"])

if(not project_root.exists()):
    raise RuntimeError(
        "This launcher must be run inside a pixi environment.\n"
        "PIXI_PROJECT_ROOT does not exist"
    )
else:
    print(f"[jupyter-launcher] found project root: {project_root}")

if TYPE_CHECKING:
    from traitlets.config import Config #type: ignore

    # Inform the type checker of get_config's signature
    def get_config() -> Config: ...

    # Declare the type for `c`
    c: Config


#!================================================================================(80)
#! modify config
#!--------------------------------------------------------------------------------(80)
#self._token.get_secret_value()
c = get_config()


#! set the root to /jupyter
c.ServerApp.root_dir = str(project_root / "jupyter")

#! set password if one is set
pw = get_secrets().JUPYTER_PASSWORD_HASH
if(pw is not None):
    print("[jupyter-launcher] password hash set! using it")
    c.PasswordIdentityProvider.hashed_password = pw.get_secret_value()

#example password: tonytony
#c.PasswordIdentityProvider.hashed_password = "argon2:$argon2id$v=19$m=10240,t=10,p=8$CbP7qssosP2zgFZ1KngZPw$Xbv5/n8RxOEeriNJ+1WKK2JLoIKZ7Wwktt4qHcaKoXo"



