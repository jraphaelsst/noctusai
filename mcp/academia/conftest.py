"""pytest path setup for the academia connector MCP.

Puts `mcp/` on `sys.path` so `from academia.X import ...` and `from
_kit.X import ...` resolve as top-level modules — the same
self-dir-on-path strategy every connector MCP test suite uses
(mcp/vista, mcp/waha, ...). Centralized once here (a `conftest.py`
alongside the package, picked up automatically for every test under
`tests/`) instead of duplicated inline in each `test_*.py` file — this
connector has no `noctusai_lib` dependency, so there is no editable-
install seed-pin dance to repeat (contrast `mcp/vista/tests/*.py`,
which does need it).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_MCP_DIR = Path(__file__).resolve().parent.parent
if str(_MCP_DIR) not in sys.path:
    sys.path.insert(0, str(_MCP_DIR))


@pytest.fixture
def fake_client():
    """`FakeAcademiaApi` wired through the `configure_client` DI seam for
    the duration of one test — every `academia.*` tool's `get_client()`
    call returns THIS instance. Torn down (restored to the production
    path) even on failure."""
    from academia.client import FakeAcademiaApi, configure_client

    fake = FakeAcademiaApi()
    configure_client(fake)
    try:
        yield fake
    finally:
        configure_client(None)
