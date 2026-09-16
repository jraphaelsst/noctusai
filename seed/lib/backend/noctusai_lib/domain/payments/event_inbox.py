"""Webhook idempotency — Protocol + Fake + RealSupabase + factory.

Both Stripe and Asaas retry webhook deliveries; a duplicate `(gateway,
event_id)` MUST be a proven no-op, not "probably fine because we
checked a dict that happened to still be warm." `EventInbox.claim`
answers exactly one question — "have I already processed this?" — and
answers it durably (the Real implementation), not just for the lifetime
of one process (that would be `noctusai_lib.integrations.whatsapp.
dedup`'s SETNX pre-filter, a different tool for a different race: WAHA's
near-simultaneous double-delivery within milliseconds vs. a gateway's
retry policy that can resend hours later after a timeout).

Mirrors `noctusai_lib.domain.jobs.repo`'s canonical Protocol + Fake +
RealSupabase + factory shape exactly. The Real implementation is
**shape-only at this phase**, per that same module's convention: it
exercises the canonical Supabase Python-client `insert` call and the
PostgREST `23505` unique-violation code, but the consumer ships the
migration that creates the table.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EventInbox(Protocol):
    """First-seen check for one `(gateway, event_id)` webhook delivery.

    `claim` returns `True` the FIRST time a given pair is seen and
    `False` for every subsequent delivery — including a delivery that
    arrives after a process restart, which is exactly the case
    `noctusai_lib.integrations.whatsapp.dedup`'s in-memory SETNX
    pre-filter does NOT cover and this module exists to.
    """

    def claim(self, *, gateway: str, event_id: str) -> bool:
        """True iff this is the first time `(gateway, event_id)` has been
        claimed. MUST NOT raise for a duplicate — a duplicate is an
        ordinary, expected outcome the caller checks and skips on,
        never an error condition."""
        ...


class FakeEventInbox:
    """In-memory `EventInbox` for dev + tests. Single-process only —
    restart-survival is the Real implementation's entire reason to
    exist, and this Fake makes no attempt to simulate it."""

    def __init__(self) -> None:
        self._seen: set[tuple[str, str]] = set()
        # Recorded calls, so a test can assert on intent (e.g. "claim was
        # called exactly twice for this event_id") and not just outcome.
        self.claims: list[tuple[str, str]] = []

    def claim(self, *, gateway: str, event_id: str) -> bool:
        self.claims.append((gateway, event_id))
        key = (gateway, event_id)
        if key in self._seen:
            return False
        self._seen.add(key)
        return True

    def clear(self) -> None:
        """Reset between test cases."""
        self._seen.clear()
        self.claims.clear()


class RealSupabaseEventInbox:
    """Supabase-client backed `EventInbox`.

    **Shape-only at this phase**, matching
    `noctusai_lib.domain.jobs.repo.RealSupabaseJobRepository`'s own
    documented convention: it exercises the canonical Supabase
    query-builder `insert` call, but the consumer ships the migration:

        create table payment_gateway_events (
            gateway text not null,
            event_id text not null,
            claimed_at timestamptz not null default now(),
            primary key (gateway, event_id)
        );

    The unique `(gateway, event_id)` constraint IS the idempotency
    guarantee — `claim` attempts an INSERT and treats a `23505` (unique
    violation) as "already claimed" rather than an error. This is the
    exact backstop shape `noctusai_lib.integrations.whatsapp.dedup`'s
    own docstring describes as "owned by the consumer's message_store" —
    here it is the seed's own table instead of a per-consumer one,
    because webhook events (unlike chat messages) have no other natural
    home.
    """

    def __init__(
        self,
        client: Any,
        *,
        schema_name: str = "public",
        table_name: str = "payment_gateway_events",
    ) -> None:
        self._client = client
        self._schema = schema_name
        self._table = table_name

    def _table_builder(self) -> Any:
        if self._schema == "public":
            return self._client.table(self._table)
        return self._client.schema(self._schema).from_(self._table)

    def claim(self, *, gateway: str, event_id: str) -> bool:
        builder = self._table_builder().insert(
            {
                "gateway": gateway,
                "event_id": event_id,
                "claimed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        try:
            builder.execute()
        except Exception as exc:  # noqa: BLE001 - narrowed below
            if _is_unique_violation(exc):
                return False
            raise
        return True


def _is_unique_violation(exc: Exception) -> bool:
    """True iff `exc` is a PostgREST `23505` (unique constraint
    violation). Matches `noctusai_lib.primitives.exceptions.
    postgrest_exception_handler`'s own `pg_code == "23505"` check —
    duplicated here (not imported) because that module raises an HTTP
    response, and this one must never raise HTTP from inside a webhook
    or job-worker call path (same rationale as `noctusai_lib.
    integrations.payments.errors.PaymentGatewayError`).
    """
    return getattr(exc, "code", None) == "23505"


def make_event_inbox(
    *,
    use_fake: bool = False,
    supabase_client: Any | None = None,
    schema_name: str = "public",
    table_name: str = "payment_gateway_events",
) -> EventInbox:
    """Construct an `EventInbox`.

    Args:
        use_fake: when True, return `FakeEventInbox` regardless of other
            arguments.
        supabase_client: live Supabase Python client. Required when
            `use_fake=False`.
        schema_name: Postgres schema hosting the events table.
        table_name: table name (default `payment_gateway_events`).

    Raises:
        RuntimeError: `use_fake=False` and no `supabase_client` given.
    """
    if use_fake:
        return FakeEventInbox()
    if supabase_client is None:
        raise RuntimeError(
            "make_event_inbox: supabase_client is required when use_fake=False"
        )
    return RealSupabaseEventInbox(
        supabase_client, schema_name=schema_name, table_name=table_name
    )


__all__ = [
    "EventInbox",
    "FakeEventInbox",
    "RealSupabaseEventInbox",
    "make_event_inbox",
]
