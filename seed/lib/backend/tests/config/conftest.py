"""Config-test-scoped fix: restore the *legitimate* ``noctusai_seed`` install.

The parent ``seed/lib/backend/tests/conftest.py`` calls
``purge_shadowing_editable_finders(_LIB)`` where ``_LIB`` is
``seed/lib/backend`` and the default ``package_names`` includes BOTH
``noctusai_lib`` *and* ``noctusai_seed``. That single-root check is correct
for ``noctusai_lib`` (which genuinely lives at ``seed/lib/backend``) but
*wrong* for ``noctusai_seed`` — the framework package lives at
``seed/framework/backend``, so its editable finder's mapping resolves
*outside* ``seed/lib/backend`` and the helper drops it as if it were a
sibling-worktree shadow. It is not: it is the legitimate in-repo install.

Net effect: any config test that (directly or via ``exec_module`` of a
``products/<slug>/backend/app/config.py``) does ``from noctusai_seed
import ProductSettings`` fails collection with ``ModuleNotFoundError: No
module named 'noctusai_seed'``. That is the root cause of the 12
``test_per_product_cors_sentinel`` failures and the parallel core-backend
collection errors.

This conftest re-registers the *correct* local ``noctusai_seed`` source
tree (``<repo>/seed/framework/backend``) on ``sys.path`` after the parent
purge runs, and drops any stale cached ``noctusai_seed*`` modules so the
next import binds to the local tree. Sibling-worktree shadow defense for
``noctusai_lib`` is left intact (the parent purge still applies to it).

Scoped to the ``config`` test package — does not touch product code and
does not weaken the ``noctusai_lib`` shadow defense.
"""
from __future__ import annotations

import sys
from pathlib import Path

# parents[0]=config, [1]=tests, [2]=backend, [3]=lib, [4]=seed, [5]=repo-root
_FRAMEWORK_BACKEND = Path(__file__).resolve().parents[5] / "seed" / "framework" / "backend"

if _FRAMEWORK_BACKEND.is_dir():
    _fw = str(_FRAMEWORK_BACKEND)
    if _fw not in sys.path:
        sys.path.insert(0, _fw)
    # Drop stale cached entries the parent purge left behind so the next
    # ``import noctusai_seed`` resolves through the local framework tree.
    for _name in [
        _n
        for _n in list(sys.modules)
        if _n == "noctusai_seed" or _n.startswith("noctusai_seed.")
    ]:
        del sys.modules[_name]
