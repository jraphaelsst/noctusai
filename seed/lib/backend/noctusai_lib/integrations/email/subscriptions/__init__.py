"""E-mail audience mechanism: double opt-in, one-click unsubscribe, hashed suppression, lifecycle events.

Lifted from social-wiring's product-local ``email_marketing`` (2nd consumer: the newsletters
products). Store = Protocol + Fake + Supabase real + ``make_audience_store``; storage lives in each
product's own schema (``ddl.email_audience_tables_sql``). Router: ``router.make_subscription_router``
(import it explicitly; it pulls FastAPI).
"""
from .ddl import email_audience_tables_sql
from .factory import AudienceStoreNotConfigured, make_audience_store
from .guard import SuppressionGuardedSender, ensure_not_suppressed
from .hashing import hash_email, normalize_email
from .service import AudienceService, SubscribeResult
from .store import AudienceStore, FakeAudienceStore
from .supabase_store import SupabaseAudienceStore
from .tokens import (
    issue_confirm_token,
    issue_unsubscribe_token,
    one_click_headers,
    verify_confirm_token,
    verify_unsubscribe_token,
)
from .types import (
    InvalidEmailAddress,
    InvalidSubscriptionToken,
    RecipientSuppressed,
    Subscriber,
    SubscriberEvent,
    SubscriptionError,
)

__all__ = [
    "email_audience_tables_sql", "AudienceStoreNotConfigured", "make_audience_store",
    "SuppressionGuardedSender", "ensure_not_suppressed", "hash_email", "normalize_email",
    "AudienceService", "SubscribeResult", "AudienceStore", "FakeAudienceStore", "SupabaseAudienceStore",
    "issue_confirm_token", "issue_unsubscribe_token", "one_click_headers",
    "verify_confirm_token", "verify_unsubscribe_token",
    "InvalidEmailAddress", "InvalidSubscriptionToken", "RecipientSuppressed",
    "Subscriber", "SubscriberEvent", "SubscriptionError",
]
