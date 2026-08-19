"""Value objects for one outbound webhook delivery attempt.

Pure: no IO, no clock, no framework. The whole point of this module is
that an attempt's OUTCOME is data a consumer can persist, compare and
retry against — not an exception that unwinds a call stack and takes the
payload with it.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

#: Response bodies are stored, and a subscriber that returns a 10 MB HTML
#: error page must not become a 10 MB database row. Matches the limit
#: `products/core`'s deliverer has used since it was written.
RESPONSE_BODY_LIMIT = 2000


class DeliveryFailureKind(str, Enum):
    """Why an attempt did not succeed.

    Kept distinct from the HTTP status because the three failure modes
    warrant different operator responses: an `HTTP_ERROR` means the
    subscriber answered and rejected us, a `TIMEOUT` means they may have
    processed it anyway (so a retry can duplicate), and a
    `TRANSPORT_ERROR` means we never reached them at all.

    That middle case is the one worth naming: retrying a timeout is the
    right default, but it is the reason a consumer needs the receiver to
    be idempotent, and the reason "did it arrive?" is not answerable from
    our side alone.
    """

    HTTP_ERROR = "http_error"
    TIMEOUT = "timeout"
    TRANSPORT_ERROR = "transport_error"


@dataclass(frozen=True)
class DeliveryAttempt:
    """The result of exactly one POST. Never a retry sequence.

    `succeeded` is the only field a caller must branch on; the rest is
    for the delivery log and for a human reading it later.
    """

    succeeded: bool
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    failure_kind: Optional[DeliveryFailureKind] = None
    error: Optional[str] = None

    @property
    def is_retryable(self) -> bool:
        """Whether retrying this attempt could plausibly succeed.

        A 4xx is NOT retryable: the subscriber understood us and said no,
        and re-sending the identical body will be refused identically
        while consuming the retry budget a transient failure needed.
        `408` and `429` are the documented exceptions — both mean "try
        again", not "never".

        Deliberately a property on the outcome rather than a policy knob:
        every consumer that retries needs this exact judgement, and two
        copies of it would eventually disagree about 429.
        """
        if self.succeeded:
            return False
        if self.failure_kind in (
            DeliveryFailureKind.TIMEOUT,
            DeliveryFailureKind.TRANSPORT_ERROR,
        ):
            return True
        if self.status_code is None:
            return True
        if self.status_code in (408, 429):
            return True
        return self.status_code >= 500


def truncate_body(text: Optional[str], limit: int = RESPONSE_BODY_LIMIT) -> Optional[str]:
    """Clip a response body to a storable size, preserving `None`."""
    if text is None:
        return None
    return text[:limit]


__all__ = [
    "RESPONSE_BODY_LIMIT",
    "DeliveryAttempt",
    "DeliveryFailureKind",
    "truncate_body",
]
