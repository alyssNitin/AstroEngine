"""
services/dasha_engine/src/systems/vimshottari.py
Shim — loads the real dasha-engine vimshottari module as a proper package
so relative imports (from .base import ...) work correctly.
"""
import importlib.util, os, sys, types

_ENGINE_SRC = os.path.abspath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..", "..",              # project root
    "services", "dasha-engine", "src"
))

def _load_real_pkg():
    # Register 'systems' package pointing to the real directory
    _sys_dir = os.path.join(_ENGINE_SRC, "systems")

    pkg_name = "_dashaengine_systems"

    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [_sys_dir]
        pkg.__package__ = pkg_name
        pkg.__spec__ = importlib.util.spec_from_file_location(
            pkg_name, os.path.join(_sys_dir, "__init__.py"),
            submodule_search_locations=[_sys_dir]
        )
        sys.modules[pkg_name] = pkg

    # Now load base module inside the package
    for sub in ("base", "vimshottari"):
        full_name = f"{pkg_name}.{sub}"
        if full_name not in sys.modules:
            fpath = os.path.join(_sys_dir, f"{sub}.py")
            spec = importlib.util.spec_from_file_location(
                full_name, fpath,
                submodule_search_locations=[_sys_dir]
            )
            mod = importlib.util.module_from_spec(spec)
            mod.__package__ = pkg_name
            sys.modules[full_name] = mod
            spec.loader.exec_module(mod)

    return sys.modules[f"{pkg_name}.vimshottari"]

_real = _load_real_pkg()

# Re-export what tests need
VIMSHOTTARI_SEQUENCE = _real.VIMSHOTTARI_SEQUENCE
TOTAL_YEARS          = _real.TOTAL_YEARS
VimshottariDasha     = _real.VimshottariDasha
