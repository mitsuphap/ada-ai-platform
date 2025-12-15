# Implementation/scraper/verticals/__init__.py

from __future__ import annotations
import importlib
import pkgutil
from typing import List, Optional, Tuple

from .base import DetectionResult, VerticalIntelligenceModule
from .education import EducationVertical

# You can either:
# A) Explicitly register modules (simple & reliable)
# B) Auto-discover via pkgutil (more dynamic)
#
# We'll do BOTH: explicit baseline + auto-discovery for future modules.

_VERTICALS: List[VerticalIntelligenceModule] = []


def _register_defaults() -> None:
    global _VERTICALS
    if _VERTICALS:
        return
    _VERTICALS = [EducationVertical()]


def autodiscover() -> None:
    """
    Optional: auto-import sibling modules to trigger any custom registration patterns.
    In our simple pattern, modules are instantiated in _register_defaults(),
    so autodiscover is mostly for future expansion.
    """
    pkg_name = __name__
    for _, mod_name, is_pkg in pkgutil.iter_modules(__path__):  # type: ignore[name-defined]
        if is_pkg:
            continue
        if mod_name in {"base", "__init__"}:
            continue
        importlib.import_module(f"{pkg_name}.{mod_name}")


def list_verticals() -> List[str]:
    _register_defaults()
    return [v.name for v in sorted(_VERTICALS, key=lambda x: x.priority, reverse=True)]


def get_vertical_for_request(user_request: str, min_conf: float = 0.6) -> Tuple[Optional[VerticalIntelligenceModule], Optional[DetectionResult]]:
    _register_defaults()
    # autodiscover()  # enable later if you add many modules dynamically

    best_v: Optional[VerticalIntelligenceModule] = None
    best_r: Optional[DetectionResult] = None

    for v in sorted(_VERTICALS, key=lambda x: x.priority, reverse=True):
        r = v.detect_vertical(user_request)
        if not r.matched:
            continue
        if r.confidence >= min_conf and (best_r is None or r.confidence > best_r.confidence):
            best_v = v
            best_r = r

    return best_v, best_r
