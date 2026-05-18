"""Autouse snapshot/restore guard for the seed process-global surface.

**Why this module exists (the leak class it formalizes).**

The seed framework keeps a handful of *process-global* singletons that a
product test can mutate (directly, or via an interleaved session-wide
``purge_shadowing_editable_finders`` re-run that swaps the module object
out from under cached ``app.*`` imports). With no per-test restoration the
mutation leaks forward and a later, unrelated test fails — green in
isolation, red in a full directory run, often only under
``pytest-randomly``. This class was re-discovered and bandaged
product-side **three times** during the social-wiring absorption
(N≥3 → MUST formalize per the recurrence rule):

1. ``noctusai_seed`` ``exec_module`` shadow under cached ``app.*``
   (structurally root-fixed by the per-package-root
   ``purge_shadowing_editable_finders`` change, DEP-A);
2. module conftests re-running the purge *after* the canonical purge +
   seed-singleton population swapped ``sys.modules`` identities (TEST-ISO);
3. module ``client`` fixtures mutating process-globals (consent registry,
   consent module bound deps, the seed APScheduler jobstore, the
   consent/scheduler ``sys.modules`` identities) with no per-test
   restoration → ~55-failure cascade under ``pytest-randomly``.

Instances (2) and (3) shipped an ad-hoc autouse fixture in
``products/social-wiring/backend/tests/modules/conftest.py``. This module
is that pattern lifted to the seed so **every** product test suite
inherits the isolation by a single re-export line — the leak class can no
longer recur per-product.

**Design — declarative, generic, zero per-product code.**

The guarded surface is expressed as a list of :class:`SingletonSpec`
value objects, each describing *one* leak-prone global by:

* the ``sys.modules`` key it lives in (snapshot is lazy + a no-op if the
  module is not imported — seed-lib's own tests and the mcp suite never
  import the product app, so the guard is inert there);
* an optional ``attr`` (the attribute on that module) — when omitted the
  spec guards the **module object identity** itself (pin it back into
  ``sys.modules`` so cached ``app.*`` references stay coherent);
* a ``kind`` describing how to copy/restore the value
  (``"dict"`` → shallow-copy then ``clear()`` + ``update()`` in place so
  references held elsewhere stay valid; ``"attr"`` → rebind the
  attribute; ``"module_identity"`` → re-pin ``sys.modules[name]``;
  ``"scheduler_jobs"`` → snapshot/replace APScheduler jobs).

:data:`DEFAULT_SPECS` encodes exactly the diagnosed seed surface. A
consumer with an extra product-global may pass ``extra_specs=[...]`` to
:func:`make_seed_singleton_guard` — the seed surface is always covered;
the product surface is purely additive and stays in the product's own
conftest (no per-product code lands in the seed).

Usage in a product conftest (autouse via re-export — pytest discovers
autouse fixtures in the conftest namespace, so the bare import line is
sufficient; ``# noqa: F401`` suppresses the unused-import lint)::

    from noctusai_lib.testing import seed_singleton_guard  # noqa: F401

Or, to add a product-specific global to the guarded set::

    from noctusai_lib.testing import (
        SingletonSpec,
        make_seed_singleton_guard,
    )

    seed_singleton_guard = make_seed_singleton_guard(extra_specs=[
        SingletonSpec("app.some_module", attr="_CACHE", kind="dict"),
    ])

Non-fixture callers (e.g. a manual block in a script) can use the
context manager :func:`guarded_seed_singletons`.
"""
from __future__ import annotations

import contextlib
import sys
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Sequence

import pytest

__all__ = [
    "SingletonSpec",
    "DEFAULT_SPECS",
    "snapshot_seed_singletons",
    "restore_seed_singletons",
    "guarded_seed_singletons",
    "make_seed_singleton_guard",
    "seed_singleton_guard",
]


@dataclass(frozen=True)
class SingletonSpec:
    """One leak-prone process-global the guard snapshots/restores.

    Args:
        module: the ``sys.modules`` key the global lives in. If the module
            is not imported when the snapshot is taken the spec is a
            silent no-op (the guard is inert outside product test runs).
        attr: the attribute name on ``module``. ``None`` → the spec
            guards the **module object identity** (pin it back into
            ``sys.modules`` so cached ``app.*`` references stay coherent);
            ``kind`` is forced to ``"module_identity"`` in that case.
        kind: how to snapshot/restore the value:

            * ``"dict"`` — value is a dict; snapshot a shallow copy and
              restore by ``clear()`` + ``update()`` *in place* so other
              holders of the dict reference see the restored content;
            * ``"attr"`` — value is any object; snapshot the reference,
              restore by rebinding the attribute;
            * ``"module_identity"`` — re-pin ``sys.modules[module]`` to
              the snapshotted module object (used when ``attr is None``);
            * ``"scheduler_jobs"`` — value is an APScheduler instance at
              ``getattr(module, attr)``; snapshot its jobs and restore by
              removing all + re-adding the snapshotted ones.
    """

    module: str
    attr: str | None = None
    kind: str = "attr"

    def __post_init__(self) -> None:
        if self.attr is None:
            # module-identity spec — normalize kind regardless of caller.
            object.__setattr__(self, "kind", "module_identity")
        if self.kind not in {"dict", "attr", "module_identity", "scheduler_jobs"}:
            raise ValueError(f"unknown SingletonSpec.kind: {self.kind!r}")

    @property
    def key(self) -> str:
        return f"{self.module}:{self.attr or '<module>'}:{self.kind}"


# The diagnosed seed process-global surface (the three social-wiring
# absorption instances). Ordered module-identity-first so a later attr
# spec restores onto the re-pinned module object.
DEFAULT_SPECS: tuple[SingletonSpec, ...] = (
    # (c) pin module identity so cached app.* imports stay coherent.
    SingletonSpec("noctusai_lib.domain.ai.consent"),
    SingletonSpec("noctusai_lib.api.scheduler"),
    # (a) consent feature registry.
    SingletonSpec("noctusai_lib.domain.ai.consent", attr="_CATALOG", kind="dict"),
    # (b) consent module bound deps (set by bind_consent_module_to_mock).
    SingletonSpec(
        "noctusai_lib.domain.ai.consent", attr="_get_current_user_dep", kind="attr"
    ),
    SingletonSpec(
        "noctusai_lib.domain.ai.consent", attr="_admin_client_factory", kind="attr"
    ),
    # (d) the seed APScheduler jobstore.
    SingletonSpec("noctusai_lib.api.scheduler", attr="scheduler", kind="scheduler_jobs"),
)

# Sentinel for "attribute was absent at snapshot time" so restore can
# delete an attr a test created (distinct from a real ``None`` value,
# which is the legitimate unconfigured state of e.g. the consent deps).
_ABSENT = object()


@dataclass
class _Snapshot:
    """Captured state for one guard cycle.

    Keyed by ``SingletonSpec.key``; ``taken`` flips True once a non-empty
    capture has happened (snapshots are lazy — the product app may not be
    imported on the first test).
    """

    values: dict[str, Any] = field(default_factory=dict)
    modules: dict[str, Any] = field(default_factory=dict)
    taken: bool = False


def _module(name: str) -> Any | None:
    return sys.modules.get(name)


def snapshot_seed_singletons(specs: Sequence[SingletonSpec]) -> _Snapshot:
    """Capture current state for *specs*.

    Lazy + tolerant: a spec whose module is not imported is skipped. The
    snapshot is only marked ``taken`` once at least one spec captured
    something — so a fixture can re-attempt the snapshot on each early
    test until the product app has been imported and the singletons
    populated (matching the lifted ad-hoc fixture's behaviour).
    """
    snap = _Snapshot()
    for spec in specs:
        mod = _module(spec.module)
        if mod is None:
            continue
        if spec.kind == "module_identity":
            snap.modules[spec.module] = mod
            snap.taken = True
            continue
        cur = getattr(mod, spec.attr, _ABSENT)
        if spec.kind == "dict":
            snap.values[spec.key] = (
                dict(cur) if isinstance(cur, dict) else _ABSENT
            )
        elif spec.kind == "scheduler_jobs":
            if cur is _ABSENT or cur is None:
                snap.values[spec.key] = _ABSENT
            else:
                try:
                    snap.values[spec.key] = list(cur.get_jobs())
                except Exception:  # pragma: no cover - scheduler not started
                    snap.values[spec.key] = []
        else:  # "attr"
            snap.values[spec.key] = cur
        snap.taken = True
    return snap


def _restore_scheduler_jobs(scheduler: Any, jobs: list[Any]) -> None:
    """Restore an APScheduler instance to *jobs* (remove-all + re-add)."""
    try:
        for job in list(scheduler.get_jobs()):
            with contextlib.suppress(Exception):
                scheduler.remove_job(job.id)
        existing = {j.id for j in scheduler.get_jobs()}
        for job in jobs:
            if job.id in existing:
                continue
            with contextlib.suppress(Exception):
                scheduler.add_job(
                    job.func,
                    trigger=job.trigger,
                    id=job.id,
                    name=job.name,
                    args=job.args,
                    kwargs=job.kwargs,
                    replace_existing=True,
                )
    except Exception:  # pragma: no cover - scheduler not started
        return


def restore_seed_singletons(
    snap: _Snapshot, specs: Sequence[SingletonSpec]
) -> None:
    """Restore state captured in *snap* for *specs*.

    No-op if the snapshot was never taken (the guard never saw the
    populated singletons — nothing to restore, nothing to corrupt).
    Module-identity specs are restored first so attr specs rebind onto
    the re-pinned module object.
    """
    if not snap.taken:
        return
    # Module identities first.
    for spec in specs:
        if spec.kind != "module_identity":
            continue
        saved = snap.modules.get(spec.module)
        if saved is not None and _module(spec.module) is not saved:
            sys.modules[spec.module] = saved
    # Then attribute-level specs.
    for spec in specs:
        if spec.kind == "module_identity":
            continue
        mod = _module(spec.module)
        if mod is None:
            continue
        if spec.key not in snap.values:
            continue
        saved = snap.values[spec.key]
        if spec.kind == "dict":
            if saved is _ABSENT:
                continue
            cur = getattr(mod, spec.attr, _ABSENT)
            if isinstance(cur, dict):
                cur.clear()
                cur.update(saved)
            else:
                setattr(mod, spec.attr, dict(saved))
        elif spec.kind == "scheduler_jobs":
            if saved is _ABSENT:
                continue
            sched = getattr(mod, spec.attr, None)
            if sched is not None:
                _restore_scheduler_jobs(sched, saved)
        else:  # "attr"
            if saved is _ABSENT:
                if hasattr(mod, spec.attr):
                    with contextlib.suppress(AttributeError):
                        delattr(mod, spec.attr)
            else:
                setattr(mod, spec.attr, saved)


@contextlib.contextmanager
def guarded_seed_singletons(
    specs: Sequence[SingletonSpec] = DEFAULT_SPECS,
) -> Iterator[_Snapshot]:
    """Context manager: snapshot on enter, restore on exit.

    For non-fixture callers (a manual block in a script / a one-off test
    that wraps state-mutating setup). The autouse :data:`seed_singleton_guard`
    fixture is the normal entry point for product test suites.
    """
    snap = snapshot_seed_singletons(specs)
    try:
        yield snap
    finally:
        restore_seed_singletons(snap, specs)


def make_seed_singleton_guard(
    *,
    extra_specs: Iterable[SingletonSpec] = (),
):
    """Build an autouse ``seed_singleton_guard`` fixture.

    The seed surface (:data:`DEFAULT_SPECS`) is always guarded; *extra_specs*
    is purely additive for a product-specific process-global (the product
    spec stays in the product's own conftest — no per-product code lands
    in the seed). The returned fixture is module-scoped state-wise (the
    snapshot persists across the session via a closure dict) but per-test
    in effect: it restores before yielding (so a test after an interleaved
    re-purge starts clean) and after (so a mutating test cannot leak
    forward).

    Snapshots are lazy: re-attempted on each early test until the product
    app has been imported and the singletons populated — so a suite whose
    very first test runs before ``client`` is exercised still ends up
    guarded once the app is up.
    """
    specs: tuple[SingletonSpec, ...] = (*DEFAULT_SPECS, *extra_specs)
    state: dict[str, _Snapshot] = {}

    @pytest.fixture(autouse=True)
    def seed_singleton_guard():
        snap = state.get("snap")
        if snap is None or not snap.taken:
            snap = snapshot_seed_singletons(specs)
            state["snap"] = snap
        restore_seed_singletons(snap, specs)
        yield
        restore_seed_singletons(snap, specs)

    return seed_singleton_guard


# The canonical autouse fixture. A product conftest activates it with a
# single re-export line (autouse → pytest discovers it in the conftest
# namespace):
#
#     from noctusai_lib.testing import seed_singleton_guard  # noqa: F401
#
seed_singleton_guard = make_seed_singleton_guard()
