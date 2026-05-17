"""Shared seed-singleton hygiene for the ``tests/modules/`` subtree.

**Why this file exists (the defect it fixes).**

Each module suite (`email_marketing`, `scheduling`) ships its own
`client` fixture. Both, plus the product-level `tests/conftest.py`,
historically called `purge_shadowing_editable_finders(_LIB)` at *their
own conftest import (collection) time*.

`purge_shadowing_editable_finders` deletes every `noctusai_lib.*` /
`noctusai_seed.*` entry from `sys.modules` so they re-resolve through the
local source tree. That helper is "idempotent" only when called
back-to-back with no state established between calls. During a full
directory run that invariant is violated:

  1. `tests/conftest.py` (parent) purges + the seed pytest11 plugin
     imports `app.main`, which runs `create_product_app(...)` and
     populates the **process-global** seed singletons —
     `noctusai_lib.domain.ai.consent._CATALOG`, the consent module's
     bound `get_current_user` / `admin_client_factory`, and the seed
     `noctusai_lib.api.scheduler.scheduler` jobstore.
  2. pytest then imports the *child* module conftests. Their
     collection-time `purge_shadowing_editable_finders(_LIB)` re-runs
     **after** step 1 and **re-deletes** `noctusai_lib.*` /
     `noctusai_seed.*` from `sys.modules` — swapping those singleton
     module objects out from under the already-cached `app.*` modules
     (which are NOT guarded packages and stay cached pointing at the now
     orphaned, pre-purge objects).
  3. Net effect: the consent catalog the plugin populated is gone, the
     consent module's bound deps are gone (→ `401 UNAUTHORIZED`), and
     the seed scheduler the modules registered jobs on is a stale object
     (→ `email_marketing_*` jobs "missing"). Each module suite is GREEN
     in isolation; the full directory run leaks ~55 cascade failures
     spanning W2.1 + W2.2, order-independent (reproduces under
     `-p no:randomly` in default order and under explicit
     `pytest-randomly` seeds).

**The root fix (DRY, N=2, at the shared layer — no per-test bandaids).**

Single purge site: the parent `tests/conftest.py` already runs the
canonical `purge_shadowing_editable_finders` once for the whole `tests/`
tree, before any test or child conftest. The defect was the two child
module conftests *re-running* that purge at their own collection time
(after step 1 had populated the singletons). The fix removes those
redundant re-purges (delegation edits in the two module conftests; this
subtree conftest itself deliberately does NOT re-purge either), so the
seed singleton module identities established by the parent conftest +
seed pytest11 plugin stay stable through the entire run — the swap in
step 2 never happens.

Belt-and-suspenders: the autouse fixture below snapshots the leak-prone
process-globals once (after collection has settled) and restores them
before/after every `tests/modules/` test, so an *unrelated* session-wide
re-purge (e.g. some other conftest a future change adds) cannot leak
state into a `tests/modules/` test either.
"""
from __future__ import annotations

import sys as _sys

# NOTE — deliberately NO `purge_shadowing_editable_finders` call here.
#
# The parent `tests/conftest.py` already runs the canonical seed
# path-bootstrap + shadow-finder purge ONCE for the whole `tests/` tree,
# before any test or child conftest. The defect this file fixes is a
# *redundant re-purge* at child-conftest collection time: any second
# `purge_shadowing_editable_finders` that fires AFTER the parent purge +
# the seed pytest11 plugin populated the process-global seed singletons
# deletes `noctusai_lib.*` / `noctusai_seed.*` from `sys.modules`,
# swapping those singletons out from under the already-cached `app.*`
# modules → the ~55-failure cascade. So this subtree conftest must NOT
# re-purge, and (via the delegation edits) neither must the two child
# module conftests. Single purge site = `tests/conftest.py`.

import pytest  # noqa: E402

_SNAP: dict = {}


def _consent_mod():
    return _sys.modules.get("noctusai_lib.domain.ai.consent")


def _scheduler_mod():
    return _sys.modules.get("noctusai_lib.api.scheduler")


@pytest.fixture(autouse=True)
def _restore_seed_singletons():
    """Snapshot-once / restore-per-test the leak-prone seed globals.

    Snapshots are taken lazily on first test (collection-time purges have
    settled by then, and the parent conftest + seed pytest11 plugin have
    populated the singletons). Restored both before yielding (so a test
    that runs after an interleaved re-purge starts clean) and after (so a
    test that mutates a singleton does not leak forward).

    Globals covered (the diagnosed set):
      (a) consent feature registry — `consent._CATALOG` dict + the
          consent module object identity in `sys.modules`;
      (b) consent module bound deps — `_get_current_user` /
          `_admin_client_factory` (set by `bind_consent_module_to_mock`);
      (c) the `noctusai_lib.domain.ai.consent` / `.api.scheduler`
          `sys.modules` entries (pin identity so cached `app.*` refs stay
          valid);
      (d) the seed APScheduler jobstore (`scheduler.scheduler` jobs).
    """

    def _capture():
        c = _consent_mod()
        s = _scheduler_mod()
        if c is None:
            return
        _SNAP.setdefault("consent_mod", c)
        _SNAP["catalog"] = dict(getattr(c, "_CATALOG", {}))
        _SNAP["consent_bound"] = (
            getattr(c, "_get_current_user_dep", None),
            getattr(c, "_admin_client_factory", None),
        )
        if s is not None:
            _SNAP.setdefault("scheduler_mod", s)
            sched = getattr(s, "scheduler", None)
            if sched is not None:
                try:
                    _SNAP["jobs"] = list(sched.get_jobs())
                except Exception:  # pragma: no cover - scheduler not started
                    _SNAP["jobs"] = []

    def _restore():
        if "consent_mod" not in _SNAP:
            return
        # (c) pin module identity so app.* cached imports stay coherent.
        if _consent_mod() is not _SNAP["consent_mod"]:
            _sys.modules["noctusai_lib.domain.ai.consent"] = _SNAP["consent_mod"]
        if "scheduler_mod" in _SNAP and _scheduler_mod() is not _SNAP["scheduler_mod"]:
            _sys.modules["noctusai_lib.api.scheduler"] = _SNAP["scheduler_mod"]
        c = _SNAP["consent_mod"]
        # (a) consent registry.
        if hasattr(c, "_CATALOG") and "catalog" in _SNAP:
            c._CATALOG.clear()
            c._CATALOG.update(_SNAP["catalog"])
        # (b) consent bound deps.
        bound = _SNAP.get("consent_bound")
        if bound is not None:
            gcu, acf = bound
            if gcu is not None:
                c._get_current_user_dep = gcu
            if acf is not None:
                c._admin_client_factory = acf

    if "catalog" not in _SNAP:
        _capture()
    _restore()
    yield
    _restore()
