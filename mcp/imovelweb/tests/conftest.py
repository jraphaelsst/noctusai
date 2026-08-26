"""Import bootstrap for the ImovelWeb connector tests.

Two steps, in this order and no other:

1. put `mcp/` on `sys.path` so `imovelweb.*` and `_kit.*` resolve as
   top-level packages (the PyPI `mcp` package shadows our `mcp/`
   directory);
2. `_kit.seed_pin.pin_in_tree_seed` — point `noctusai_lib` at THIS
   worktree's seed. An editable install registers a meta-path finder that
   hard-pins `noctusai_lib` to whichever worktree `pip install -e` last
   ran in, and meta-path finders are consulted BEFORE `sys.path`, so a
   plain path insert cannot override it. In a multi-worktree setup that
   pinned tree is frequently a stale one without
   `noctusai_lib.integrations.imovelweb` at all.

The kit owns this logic (`mcp/_kit/README.md` § in-tree seed pin) — do not
hand-roll a local copy.
"""
from __future__ import annotations

import sys
from pathlib import Path

_MCP_DIR = Path(__file__).resolve().parents[2]
if str(_MCP_DIR) not in sys.path:
    sys.path.insert(0, str(_MCP_DIR))

from _kit.seed_pin import pin_in_tree_seed  # noqa: E402

pin_in_tree_seed(Path(__file__).resolve())
