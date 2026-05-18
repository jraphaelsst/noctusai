"""Tests for `noctusai_lib.testing.seed_singleton_guard`.

The contract under test: a test that mutates a guarded seed singleton
must NOT leak that mutation into the next test — the autouse guard
snapshots before and restores after every test.

Coverage:

(a) ``SingletonSpec`` validation — ``attr=None`` forces
    ``module_identity``; unknown ``kind`` raises;
(b) ``snapshot``/``restore`` round-trip for each ``kind``
    (``dict`` in-place, ``attr`` rebind, ``attr`` absent→deleted,
    ``module_identity`` re-pin, ``scheduler_jobs``);
(c) ``guarded_seed_singletons`` context manager restores on exit even
    when the body raises;
(d) lazy snapshot — a spec whose module is not imported is a no-op and
    the snapshot is only ``taken`` once something was captured;
(e) **leak containment (the headline test)** — an autouse guard built
    over a fake seed module; a deliberately-leaking test mutates the
    fake singletons; an ordered follow-up test asserts the leak was
    contained (state restored to the snapshot). Reproduces the exact
    social-wiring leak shape (dict registry + bound dep + module
    identity swap) against a synthetic module so it needs no product
    app on the import path.

Each test that creates fake modules cleans ``sys.modules`` so the seed
guard surface (real ``noctusai_lib.*``) is never touched.
"""
from __future__ import annotations

import sys
import types

import pytest

from noctusai_lib.testing import (
    DEFAULT_SPECS,
    SingletonSpec,
    guarded_seed_singletons,
    restore_seed_singletons,
    snapshot_seed_singletons,
)

_FAKE = "noctusai_lib._fake_singleton_module_for_tests"


@pytest.fixture
def fake_module():
    """A synthetic stand-in for the leak-prone seed module surface.

    Mirrors the diagnosed shape: a ``_CATALOG`` dict, a ``_bound_dep``
    attribute, and the module object identity itself. Cleaned from
    ``sys.modules`` after the test so the real seed guard surface is
    never perturbed.
    """
    mod = types.ModuleType(_FAKE)
    mod._CATALOG = {"baseline": 1}
    mod._bound_dep = "baseline_dep"
    sys.modules[_FAKE] = mod
    try:
        yield mod
    finally:
        for k in list(sys.modules):
            if k == _FAKE or k.startswith(_FAKE + "."):
                del sys.modules[k]


def _fake_specs() -> tuple[SingletonSpec, ...]:
    return (
        SingletonSpec(_FAKE),  # module identity
        SingletonSpec(_FAKE, attr="_CATALOG", kind="dict"),
        SingletonSpec(_FAKE, attr="_bound_dep", kind="attr"),
        SingletonSpec(_FAKE, attr="_created_by_test", kind="attr"),
    )


# ─── (a) SingletonSpec validation ───────────────────────────────────────────


class TestSingletonSpecValidation:
    def test_attr_none_forces_module_identity(self):
        spec = SingletonSpec("some.mod", attr=None, kind="dict")
        assert spec.kind == "module_identity"
        assert spec.key == "some.mod:<module>:module_identity"

    def test_unknown_kind_raises(self):
        with pytest.raises(ValueError, match="unknown SingletonSpec.kind"):
            SingletonSpec("some.mod", attr="x", kind="bogus")

    def test_default_specs_cover_diagnosed_surface(self):
        keys = {s.key for s in DEFAULT_SPECS}
        assert "noctusai_lib.domain.ai.consent:_CATALOG:dict" in keys
        assert (
            "noctusai_lib.api.scheduler:scheduler:scheduler_jobs" in keys
        )
        # module-identity pins present for both leak-prone modules
        assert "noctusai_lib.domain.ai.consent:<module>:module_identity" in keys
        assert "noctusai_lib.api.scheduler:<module>:module_identity" in keys


# ─── (b) snapshot/restore round-trip ────────────────────────────────────────


class TestSnapshotRestoreRoundTrip:
    def test_dict_restored_in_place(self, fake_module):
        specs = _fake_specs()
        snap = snapshot_seed_singletons(specs)
        assert snap.taken is True
        original_dict = fake_module._CATALOG
        original_dict["leaked"] = 999
        restore_seed_singletons(snap, specs)
        # same dict object (in-place restore), content reverted
        assert fake_module._CATALOG is original_dict
        assert fake_module._CATALOG == {"baseline": 1}

    def test_attr_rebind_restored(self, fake_module):
        specs = _fake_specs()
        snap = snapshot_seed_singletons(specs)
        fake_module._bound_dep = "MUTATED"
        restore_seed_singletons(snap, specs)
        assert fake_module._bound_dep == "baseline_dep"

    def test_attr_absent_at_snapshot_is_deleted_on_restore(self, fake_module):
        specs = _fake_specs()
        snap = snapshot_seed_singletons(specs)
        assert not hasattr(fake_module, "_created_by_test")
        fake_module._created_by_test = "leak"
        restore_seed_singletons(snap, specs)
        assert not hasattr(fake_module, "_created_by_test")

    def test_module_identity_repinned(self, fake_module):
        specs = _fake_specs()
        snap = snapshot_seed_singletons(specs)
        # simulate a session-wide re-purge swapping the module object
        swapped = types.ModuleType(_FAKE)
        swapped._CATALOG = {}
        sys.modules[_FAKE] = swapped
        restore_seed_singletons(snap, specs)
        assert sys.modules[_FAKE] is fake_module

    def test_scheduler_jobs_snapshot_tolerates_missing_scheduler(
        self, fake_module
    ):
        # fake module has no `scheduler` attr → scheduler_jobs spec must
        # be a tolerant no-op, not an error.
        specs = (SingletonSpec(_FAKE, attr="scheduler", kind="scheduler_jobs"),)
        snap = snapshot_seed_singletons(specs)
        restore_seed_singletons(snap, specs)  # must not raise


# ─── (c) context manager ────────────────────────────────────────────────────


class TestGuardedContextManager:
    def test_restores_on_normal_exit(self, fake_module):
        specs = _fake_specs()
        with guarded_seed_singletons(specs):
            fake_module._bound_dep = "X"
        assert fake_module._bound_dep == "baseline_dep"

    def test_restores_even_when_body_raises(self, fake_module):
        specs = _fake_specs()
        with pytest.raises(RuntimeError):
            with guarded_seed_singletons(specs):
                fake_module._CATALOG["boom"] = 1
                raise RuntimeError("boom")
        assert fake_module._CATALOG == {"baseline": 1}


# ─── (d) lazy snapshot ──────────────────────────────────────────────────────


class TestLazySnapshot:
    def test_unimported_module_is_noop(self):
        specs = (SingletonSpec("noctusai_lib._definitely_not_imported_xyz"),)
        snap = snapshot_seed_singletons(specs)
        assert snap.taken is False
        # restore is a no-op when nothing was taken
        restore_seed_singletons(snap, specs)  # must not raise


# ─── (e) leak containment — the headline contract ───────────────────────────
#
# An autouse guard built over the fake module. ``test_b_*`` deliberately
# leaks; ``test_c_*`` (alphabetically after) asserts the leak was
# contained. ``test_a_*`` establishes the snapshot baseline. Ordering is
# alphabetical within the class (pytest default collection order); the
# guard restores BEFORE and AFTER each test, so order-independence holds
# regardless — but the explicit ordering makes the intent legible.


@pytest.fixture(scope="class")
def _install_fake(request):
    mod = types.ModuleType(_FAKE)
    mod._CATALOG = {"baseline": 1}
    mod._bound_dep = "baseline_dep"
    sys.modules[_FAKE] = mod
    request.cls._fake = mod
    yield
    for k in list(sys.modules):
        if k == _FAKE or k.startswith(_FAKE + "."):
            del sys.modules[k]


@pytest.mark.usefixtures("_install_fake")
class TestLeakContainment:
    """A deliberately-leaking test is contained by the autouse guard.

    The autouse ``_seed_guard`` fixture exercises the *exact* contract
    ``make_seed_singleton_guard`` implements (snapshot once, restore
    before-yield + after-yield) over the fake spec surface — proving
    containment without needing a product app on the import path.
    """

    @pytest.fixture(autouse=True)
    def _seed_guard(self):
        specs = _fake_specs()
        snap = snapshot_seed_singletons(specs)
        restore_seed_singletons(snap, specs)
        yield
        restore_seed_singletons(snap, specs)

    def test_a_baseline_intact(self):
        assert self._fake._CATALOG == {"baseline": 1}
        assert self._fake._bound_dep == "baseline_dep"

    def test_b_deliberately_leaks(self):
        # Mutate every guarded surface, as the historical product
        # fixtures did (registry dict, bound dep, a new attr, and swap
        # the module object identity).
        self._fake._CATALOG["leaked"] = 42
        self._fake._bound_dep = "LEAKED_DEP"
        self._fake._created_by_test = "leak-marker"
        swapped = types.ModuleType(_FAKE)
        swapped._CATALOG = {"only": "garbage"}
        sys.modules[_FAKE] = swapped
        # Within this test the mutation is visible (the leak is real)…
        assert sys.modules[_FAKE] is swapped

    def test_c_leak_was_contained(self):
        # …but the guard restored everything before this test ran.
        assert sys.modules[_FAKE] is self._fake, "module identity not re-pinned"
        assert self._fake._CATALOG == {"baseline": 1}, "registry leaked"
        assert self._fake._bound_dep == "baseline_dep", "bound dep leaked"
        assert not hasattr(
            self._fake, "_created_by_test"
        ), "test-created attr leaked"
