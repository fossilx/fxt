#=================================================================================(80)
#
#   fxt ;D
#
#=================================================================================(80)
"""
fxt.lake.models.derived

Metadata models for derived lake files (bars now; other derived types later).

    base.py   InputRef, Transform, DerivedMeta (unregistered base)
    bars.py   BarsMeta

New derived model modules must be imported here (models register on import).
"""

#!================================================================================(80)
#! imports/exports
#!--------------------------------------------------------------------------------(80)
from .base import DerivedMeta, InputRef, Transform
from ..bars import BarsMeta

__all__ = [
    "DerivedMeta", "InputRef", "Transform",
    "BarsMeta",
]
