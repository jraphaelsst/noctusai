"""Shared fixtures for seed library unit tests.

The library layer (`noctusai_lib.*`) is pure Python — no FastAPI, no DB
wrapper — so tests target functions directly. This conftest only makes
the sibling lib importable regardless of cwd.
"""
from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1]
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
