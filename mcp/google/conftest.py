"""pytest path setup for the Google connector MCP.

The package directory is named `google`, which collides with the PyPI
`google.*` namespace package (google-api-python-client / google-auth).
Under pytest's default prepend import-mode the test module would be
imported as `google.tests.test_smoke`, resolving `google` to the
site-packages namespace and failing. This conftest puts the two needed
dirs on sys.path so the connector's modules (`tools` / `settings` /
`schemas`) and the shared `_kit` resolve as TOP-LEVEL modules — the same
self-dir-on-path strategy mcp/noctusai uses. Pair with
`--import-mode=importlib` (see pytest.ini in this dir) so pytest does
not synthesize the colliding `google.` package path for the test file.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))  # mcp/   → _kit
sys.path.insert(0, str(_HERE))          # mcp/google/ → tools/settings/schemas
