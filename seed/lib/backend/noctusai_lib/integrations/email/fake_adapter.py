"""`FakeEmailSender` — deterministic in-memory double."""
from __future__ import annotations

from dataclasses import dataclass, field

from .types import OutgoingEmail, SentEmail


@dataclass
class FakeEmailSender:
    """Records every send on `.sent`; never touches a socket. Message
    ids are monotonic (`<fake-1@...>`, `<fake-2@...>`, ...) so tests can
    assert on stable ids across a multi-send scenario without needing
    real network I/O — mirrors `FakeWahaClient`/`FakeGmailClient`'s
    shape (bi-directional would mean "accepts injected inbound replies"
    too, but that's R8's reply-watcher concern, not the sender's)."""

    sent: list[OutgoingEmail] = field(default_factory=list)
    domain: str = "fake.noctus.test"
    _counter: int = field(default=0, repr=False)

    async def send(self, email: OutgoingEmail) -> SentEmail:
        self._counter += 1
        message_id = email.message_id or f"<fake-{self._counter}@{self.domain}>"
        self.sent.append(email)
        references_header = email.headers.get("References")
        return SentEmail(
            message_id=message_id,
            in_reply_to=email.headers.get("In-Reply-To"),
            references=tuple(references_header.split()) if references_header else (),
        )


__all__ = ["FakeEmailSender"]
