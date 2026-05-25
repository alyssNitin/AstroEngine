"""
systems/
========
Registry of all available Dasha systems.
New systems are auto-discovered if they subclass AbstractDashaSystem
and are imported here.
"""
from .base import AbstractDashaSystem
from .vimshottari import VimshottariDasha
from .yogini import YoginiDasha
from .chara import CharaDasha
from .kalachakra import KalachakraDasha
from .narayana import NarayanaDasha
from .moola import MoolaDasha

# Registry: system name → class
DASHA_SYSTEMS: dict[str, type[AbstractDashaSystem]] = {
    "vimshottari": VimshottariDasha,
    "yogini":      YoginiDasha,
    "chara":       CharaDasha,
    "kalachakra":  KalachakraDasha,
    "narayana":    NarayanaDasha,
    "moola":       MoolaDasha,
}

__all__ = [
    "AbstractDashaSystem",
    "VimshottariDasha", "YoginiDasha", "CharaDasha",
    "KalachakraDasha", "NarayanaDasha", "MoolaDasha",
    "DASHA_SYSTEMS",
]
