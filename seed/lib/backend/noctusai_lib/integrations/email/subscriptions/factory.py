"""``make_audience_store``: Fake or Supabase real, by flag."""
from __future__ import annotations

from typing import Any, Optional

from noctusai_lib.primitives.not_configured import IntegrationNotConfigured

from .store import AudienceStore, FakeAudienceStore
from .supabase_store import SupabaseAudienceStore
from .types import SubscriptionError


class AudienceStoreNotConfigured(SubscriptionError, IntegrationNotConfigured):
    """The real store needs a Supabase client pinned to the product schema."""


def make_audience_store(*, use_fake: bool = False, client: Optional[Any] = None) -> AudienceStore:
    if use_fake:
        return FakeAudienceStore()
    if client is None:
        raise AudienceStoreNotConfigured("make_audience_store: a Supabase client is required unless use_fake=True")
    return SupabaseAudienceStore(client)


__all__ = ["make_audience_store", "AudienceStoreNotConfigured"]
