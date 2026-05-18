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
_SEED_BACKEND = _HERE.parents[1] / "seed" / "lib" / "backend"


def _pin_in_tree_noctusai_lib() -> None:
    """Resolve `noctusai_lib` from the seed IN THIS TREE.

    A repo-wide editable install (`pip install -e`) registers a
    `_EditableFinder` MetaPathFinder that hard-pins `noctusai_lib` to
    whatever worktree it was last installed from — which may be a
    *different* (now stale) `.claude/worktrees/agent-*` tree missing a
    freshly-added seed symbol. `sys.meta_path` is consulted BEFORE
    `sys.path`, so a plain `sys.path.insert` cannot override it. We
    evict any editable finder whose pinned `noctusai_lib` path is
    OUTSIDE this tree and drop stale cached modules, then prepend the
    in-tree seed. Pure path/import wiring — same category as the
    `google`-namespace-collision workaround below; touches no product
    code."""
    target = str(_SEED_BACKEND)
    for finder in list(sys.meta_path):
        mapping = getattr(finder, "_mapping", None) or getattr(
            finder, "MAPPING", None
        )
        if not isinstance(mapping, dict):
            continue
        pinned = mapping.get("noctusai_lib")
        pinned_str = pinned if isinstance(pinned, str) else (
            pinned[0] if isinstance(pinned, (list, tuple)) and pinned else None
        )
        if pinned_str and target not in str(pinned_str):
            sys.meta_path.remove(finder)
    for name in list(sys.modules):
        if name == "noctusai_lib" or name.startswith("noctusai_lib."):
            del sys.modules[name]
    sys.path.insert(0, target)


_pin_in_tree_noctusai_lib()
sys.path.insert(0, str(_HERE.parent))  # mcp/   → _kit
sys.path.insert(0, str(_HERE))          # mcp/google/ → tools/settings/schemas
