#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
research group `examples`: shared code + the group declaration

Code used by more than one project in this group. If another group starts
needing it, promote it to `fxt.research`.

`GROUP` declares the custom data dirs of the group's shared data scope,
runs/examples/common/data/ (its `lake/` always exists and needs no declaring).
"""
from __future__ import annotations

from fxt.research.paths import DataDir, FeatureKey, group_from_module

__all__ = ["GROUP", "banner"]

GROUP = group_from_module(__name__, data_dirs={
    "features": DataDir("feature tables shared by the group's projects", key=FeatureKey),
})


def banner(text: str) -> str:
    """ Trivial stand-in for group-shared code. """
    return f"examples · {text}"
