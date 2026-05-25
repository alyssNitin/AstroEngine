"""
services/dasha_engine/__init__.py
Thin alias for services/dasha-engine (hyphen → underscore Python compat shim).
Imports from the real dasha-engine package via sys.path injection.
"""
import sys, os
_ENGINE_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dasha-engine", "src")
if _ENGINE_SRC not in sys.path:
    sys.path.insert(0, _ENGINE_SRC)
