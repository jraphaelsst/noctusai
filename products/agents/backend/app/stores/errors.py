"""Store-layer error types for the agents product (contract §E).

Every store method that hits a not-found / conflict / already-decided /
turn-in-progress condition raises one of these instead of returning ``None``
or a bare ``bool`` — the router layer (wave 1b) maps each to its own HTTP
status without re-deriving the reason from a falsy value. Mirrors the
seed's "no silent errors" rule (CLAUDE.md §1): a swallowed ``None`` return
here would look like "not found" and "transient bug" identically.
"""
from __future__ import annotations


class StoreError(Exception):
    """Base class for every agents-store error."""


class NotFound(StoreError):
    """The requested row does not exist, or belongs to another org.

    Deliberately the SAME error for both cases (unknown id vs. cross-org
    id) — the store must never let a caller distinguish "exists but isn't
    yours" from "doesn't exist" (that distinction itself leaks existence
    across orgs).
    """


class Conflict(StoreError):
    """The write would violate a uniqueness/ordering invariant the store enforces."""


class AlreadyDecided(StoreError):
    """An approval's decision was already settled; a second decision is refused."""


class TurnInProgress(StoreError):
    """A conversation turn is already running; the caller must wait or reject."""


class Orphaned(StoreError):
    """G1b addition (contract §E.9 ``ApprovalBroker.resolve``: "raises
    ``runtime.errors.Orphaned`` -> 409 ``orphaned``"). Declared HERE
    (``app.stores.errors``), not in the not-yet-built ``app/runtime/``,
    so ``app/routers/approvals_router.py`` has a stable, always-importable
    exception type to catch regardless of whether G2 has landed —
    ``app/routers/agents_router.py``'s lazy-import discipline only covers
    obtaining the runtime/broker INSTANCES (contract §E.9), not naming an
    exception TYPE the router's own ``except`` clause needs at every call,
    including in this slice's own tests (which inject the E.9 stand-in
    broker, never a real ``app.runtime``). **Contract note for G2**: the
    real ``ApprovalBroker.resolve`` must raise THIS class (or a subclass)
    for "no live turn is waiting" — flagged to the tech-lead as a
    contract coordination point, not a silent assumption."""
