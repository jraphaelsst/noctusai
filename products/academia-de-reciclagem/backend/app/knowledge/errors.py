"""KnowledgeStore error taxonomy — contract §A.11 / §B.0.

`FakeKnowledgeStore` and `PgKnowledgeStore` both raise these, never a raw
`KeyError`/`ValueError`/postgrest `APIError` — the store boundary is where
"unknown slug" or "already superseded" becomes a *named* condition, so a
future B-routes slice can map each one onto the exact HTTP status the
contract's status taxonomy (§B.0) requires without re-deriving intent from
a generic exception's message string.

    404 <- NotFound         409 `conflict`      <- Conflict
    422 <- Invalid           409 `assertion_used` <- AssertionUsed
"""
from __future__ import annotations


class KnowledgeStoreError(Exception):
    """Base class for every error a KnowledgeStore implementation raises.

    Never raised directly — always one of the four subclasses below.
    """


class NotFound(KnowledgeStoreError):
    """The requested slug/codigo/entity does not exist for this org.

    Contract §B.0: maps to HTTP 404. Deliberately org-scoped at the raise
    site — "exists in another org" and "does not exist at all" are BOTH
    NotFound (never a 403), so a store call can never be used to probe
    whether a code exists in a sibling tenant.
    """


class Conflict(KnowledgeStoreError):
    """A write collided with existing state.

    Contract §B.0 `409 conflict`: a slug/codigo already taken, a decision
    already `superseded`, or a question already `respondida`.
    """


class Invalid(KnowledgeStoreError):
    """A write referenced another entity that does not resolve.

    Contract §B.0 `422`: e.g. `create_task` with an unknown `fase`.
    Distinct from `NotFound` — the *target* of the write exists (or is
    about to be created); it is a *reference inside the payload* that
    doesn't resolve.
    """


class AssertionUsed(KnowledgeStoreError):
    """The `X-Approval-Assertion`'s `jti` was already consumed.

    Contract §A.10 / §D: `approval_consumptions` is a single-use replay
    guard — its INSERT happens first, in the same transaction as the
    write(s) it authorizes. A duplicate `jti` means the assertion has
    already paid for a write once; maps to HTTP 409 `assertion_used`.
    """
