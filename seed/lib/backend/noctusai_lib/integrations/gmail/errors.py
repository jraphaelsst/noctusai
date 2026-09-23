"""Typed errors for the Gmail push-watch surface.

Every failure mode a caller must BRANCH on gets its own type — never a
bare `ValueError` the caller has to string-match, and never a silent
accept (a push webhook that swallows a bad token is an open door; a
history loop that swallows a 404 silently stops seeing replies forever).

- `GmailHistoryExpiredError` — `users.history.list` returned 404: the
  stored `startHistoryId` is older than Gmail's retained history
  (typically ~1 week, can be shorter). The ONLY correct recovery is a
  full resync (re-`watch()` to get a fresh history id, then reconcile
  recent mail via `list_messages`), so it is its own type.
- `GmailPushError` — base for the Pub/Sub push-receiver helpers.
  - `GmailPushEnvelopeError` — body is not a Pub/Sub push envelope
    carrying a Gmail notification. Respond 400 (Pub/Sub will retry, then
    dead-letter — a malformed body never becomes valid on retry, so ack
    semantics are the caller's call; see `push.py`).
  - `GmailPushAuthError` — the OIDC bearer token is missing, malformed,
    unverifiable, for the wrong audience, or from the wrong service
    account. Respond 401/403 and DO NOT process the body.
- `PubSubProvisioningError` — `ensure_push_subscription` found a state it
  must not silently overwrite (a same-named subscription bound to a
  DIFFERENT topic) or the Pub/Sub API refused.
"""

from __future__ import annotations


class GmailHistoryExpiredError(Exception):
    """`startHistoryId` is too old (Gmail answered 404) — resync required."""

    def __init__(self, start_history_id: str) -> None:
        self.start_history_id = start_history_id
        super().__init__(
            f"gmail history id {start_history_id!r} is no longer available "
            "(404) — re-watch() for a fresh history id and resync recent mail"
        )


class GmailPushError(Exception):
    """Base for Pub/Sub push-receiver failures."""


class GmailPushEnvelopeError(GmailPushError):
    """The request body is not a valid Gmail Pub/Sub push envelope."""


class GmailPushAuthError(GmailPushError):
    """The push request's OIDC token failed verification."""


class PubSubProvisioningError(Exception):
    """Pub/Sub topic/subscription provisioning could not converge."""


__all__ = [
    "GmailHistoryExpiredError",
    "GmailPushAuthError",
    "GmailPushEnvelopeError",
    "GmailPushError",
    "PubSubProvisioningError",
]
