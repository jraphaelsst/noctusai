"""Shared builders for the credential tests — Fake store / token admin /
prober composed through the service's own constructor (DI, no patching)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from noctusai_lib.api.auth.session import FakeProductTokenAdmin
from noctusai_lib.security.app_config import CachedAppConfigStore, FakeAppConfigStore

from app.credentials.prober import FakeCredentialProber
from app.credentials.resolver import ConfigStoreHandle
from app.credentials.service import CredentialService

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
ORG_ID = UUID("11111111-1111-1111-1111-111111111111")
JULIA_ID = UUID("22222222-2222-2222-2222-222222222222")

#: Secrets every test plants and then asserts never leak.
OLD_ACADEMIA = "pk_" + "a" * 64
ENV_SOCIAL = "pk_" + "b" * 64
ANTHROPIC = "sk-ant-api03-" + "Z" * 80
RING_ENV = "ring-secret-one,ring-secret-two"
PLANTED = (OLD_ACADEMIA, ENV_SOCIAL, ANTHROPIC, "ring-secret-one", "ring-secret-two")


def make_settings(**overrides):
    base = dict(
        academia_api_token="",
        social_wiring_api_token="",
        anthropic_api_key="",
        approval_assertion_secrets="",
        julia_agent_id="",
        credential_expiry_warning_days=30,
        approval_key_activation_delay_seconds=120,
        approval_key_retire_after_seconds=86400,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@dataclass
class Kit:
    service: CredentialService
    store: FakeAppConfigStore
    admin: FakeProductTokenAdmin
    prober: FakeCredentialProber
    settings: SimpleNamespace
    clock: list = field(default_factory=lambda: [NOW])


def build_kit(*, persistent: bool = True, **settings_overrides) -> Kit:
    store = FakeAppConfigStore()
    admin = FakeProductTokenAdmin()
    prober = FakeCredentialProber()
    settings = make_settings(**settings_overrides)
    clock = [NOW]
    service = CredentialService(
        handle=ConfigStoreHandle(
            store=CachedAppConfigStore(store, ttl_seconds=0), persistent=persistent,
            reason=None if persistent else "ENCRYPTION_KEY ausente",
        ),
        settings=settings,
        token_admin=admin,
        prober=prober,
        clock=lambda: clock[0],
    )
    return Kit(service=service, store=store, admin=admin, prober=prober, settings=settings, clock=clock)


def seed_academia_token(kit: Kit, *, days_left: int = 60, principal: UUID | None = JULIA_ID, **fields):
    return kit.admin.seed(
        "academia_de_reciclagem",
        OLD_ACADEMIA,
        org_id=ORG_ID,
        expires_at=NOW + timedelta(days=days_left, hours=1),
        scopes=["academia:read"],
        principal_agent_id=principal,
        issuer="agents",
        token_id=uuid4(),
        **fields,
    )


@pytest.fixture
def kit() -> Kit:
    return build_kit(
        academia_api_token=OLD_ACADEMIA,
        social_wiring_api_token=ENV_SOCIAL,
        anthropic_api_key=ANTHROPIC,
        approval_assertion_secrets=RING_ENV,
        julia_agent_id=str(JULIA_ID),
    )


def assert_no_secret(text: str) -> None:
    for secret in PLANTED:
        assert secret not in text, "a planted secret leaked"
