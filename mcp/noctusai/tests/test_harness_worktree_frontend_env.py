"""A harness-created worktree gets the seed frontends' node_modules (and a hand-made product symlink is converted to
the per-entry overlay) so `vite build` resolves `@vitejs/plugin-react-swc` / tailwind. 2026-11-17 incident."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_task_branch import _seed_primary, _seed_worktree_tree  # noqa: E402
from tools.noctus.dev import task_branch as T  # noqa: E402


def test_seed_links_and_stale_product_symlink_is_converted(tmp_path):
    primary = tmp_path / "primary"
    wt = primary / ".claude" / "worktrees" / "agent-x"
    _seed_primary(primary, slugs=("alpha",))
    _seed_worktree_tree(wt)
    pnm = wt / "products" / "alpha" / "frontend" / "node_modules"
    pnm.parent.mkdir(parents=True, exist_ok=True)
    if pnm.exists() or pnm.is_symlink():
        pnm.unlink() if pnm.is_symlink() else None
    os.symlink(primary / "products" / "alpha" / "frontend" / "node_modules", pnm)

    res = T.wire_harness_worktree_frontend_env(str(primary), str(wt))

    assert res["products"] == ["alpha"] and not res["failed"]
    assert not pnm.is_symlink() and pnm.is_dir()  # real dir: nothing writes through into the primary
    assert (wt / "seed" / "lib" / "frontend" / "node_modules").is_symlink()
    # idempotent, and a product with no hand-made link stays unwired
    assert T.wire_harness_worktree_frontend_env(str(primary), str(wt))["failed"] == []
