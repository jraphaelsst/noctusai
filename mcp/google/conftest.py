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

# Resolve `noctusai_lib` from the seed IN THIS TREE via the shared
# `_kit.seed_pin` primitive. A repo-wide editable install
# (`pip install -e`) registers a `_EditableFinder` MetaPathFinder that
# hard-pins `noctusai_lib` to whatever worktree it was last installed
# from — which may be a *different* (now stale) `agent-*` tree missing a
# freshly-added seed symbol. `sys.meta_path` is consulted BEFORE
# `sys.path`, so a plain `sys.path.insert` cannot override it.
# `pin_in_tree_seed` evicts any editable finder pinning `noctusai_lib`
# OUTSIDE this tree, drops stale cached modules, and prepends the
# in-tree seed. Formerly hand-rolled here (N=2 with server.py + meta) —
# now the deduped `_kit` helper. Pure path/import wiring — same category
# as the `google`-namespace-collision workaround below; touches no
# product code. The `_kit` import needs `mcp/` on sys.path first.
sys.path.insert(0, str(_HERE.parent))  # mcp/   → _kit
from _kit.seed_pin import pin_in_tree_seed

pin_in_tree_seed(_HERE)
sys.path.insert(0, str(_HERE))          # mcp/google/ → tools/settings/schemas
