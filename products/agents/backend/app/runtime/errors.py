"""Runtime-layer error types (contract §E.9).

Sibling of ``app.stores.errors`` — that module owns store-shaped failures
(``NotFound``, ``Conflict``, ``AlreadyDecided``, ``TurnInProgress``); this
module owns the one failure that is a RUNTIME concept, not a store one:
an approval decision arriving for a request no live process is waiting on.
"""
from __future__ import annotations


class Orphaned(Exception):
    """``ApprovalBroker.resolve`` raises this when the approval row is still
    ``pendente`` in the store, but no live in-process future is waiting on
    it in THIS process — the process that requested it died or restarted
    before a human decided (contract §E.2: 409 ``orphaned``).

    Distinct from :class:`app.stores.errors.NotFound` (the row doesn't
    exist / wrong org) and :class:`app.stores.errors.AlreadyDecided` (the
    row is already settled) — this is "the row is real and still pending,
    but nothing is listening for the answer any more."
    """
