"""Shared builders for the onboarding-channel tests: the real ``SwCanal`` over Fakes (token admin, encrypted-config store,
event store) and a stub social-wiring that judges the bearer the way the real guard does (401 unknown / revoked / expired,
403 wrong scope or issuer, 200 ``whoami`` otherwise), so a wrong token is refused by the stub, not by the test."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx

from noctusai_lib.api.auth.session import FakeProductTokenAdmin, hash_token
from noctusai_lib.security.app_config import CachedAppConfigStore, FakeAppConfigStore

from app.credentials.registry import SW_ONBOARDING_TOKEN
from app.credentials.resolver import ConfigStoreHandle
from app.onboarding.sw_canal import SwCanal
from app.stores.sw_canal_eventos import FakeSwCanalEventStore

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
ORG = UUID("11111111-1111-1111-1111-111111111111")
STAFF = UUID("33333333-3333-3333-3333-333333333333")
SCHEMA = SW_ONBOARDING_TOKEN.target_schema
SCOPE = SW_ONBOARDING_TOKEN.scopes[0]
SW_URL = "http://sw.test"


@dataclass
class Kit:
    canal: SwCanal
    store: FakeAppConfigStore
    admin: FakeProductTokenAdmin
    eventos: FakeSwCanalEventStore
    clock: list
    seen: list = field(default_factory=list)  # (method, path, bearer) per request the stub received
    #: forced answer (status) for a path; the stub otherwise judges the bearer
    forcar: dict = field(default_factory=dict)

    def guardado(self) -> str | None:
        return self.store.get(SW_ONBOARDING_TOKEN.store_key)

    def linhas(self):
        return self.admin.rows.get(SCHEMA, [])


def _stub(kit: "Kit"):
    def handler(req: httpx.Request) -> httpx.Response:
        auth = req.headers.get("authorization", "")
        bearer = auth.removeprefix("Bearer ")
        kit.seen.append((req.method, req.url.path, bearer))
        if req.url.path in kit.forcar:
            return httpx.Response(kit.forcar[req.url.path], json={"code": "forcado"})
        row = next((r for r in kit.linhas() if r["token_hash"] == hash_token(bearer)), None)
        agora = kit.clock[0]
        if row is None or row["revoked_at"] or (row["expires_at"] and datetime.fromisoformat(row["expires_at"]) <= agora):
            return httpx.Response(401, json={"code": "invalid_token"})
        if SCOPE not in row["scopes"]:
            return httpx.Response(403, json={"code": "scope_missing"})
        if row.get("issuer") != "noctus-platform":
            return httpx.Response(403, json={"code": "issuer_not_allowed"})
        return httpx.Response(200, json={"data": {"ok": True, "escopo": SCOPE}})

    return handler


def build_kit(*, persistent: bool = True) -> Kit:
    store, admin, eventos = FakeAppConfigStore(), FakeProductTokenAdmin(), FakeSwCanalEventStore()
    clock = [NOW]
    kit = Kit(canal=None, store=store, admin=admin, eventos=eventos, clock=clock)  # type: ignore[arg-type]
    kit.canal = SwCanal(
        handle=ConfigStoreHandle(
            store=CachedAppConfigStore(store, ttl_seconds=0), persistent=persistent,
            reason=None if persistent else "ENCRYPTION_KEY ausente"),
        token_admin=admin, eventos=eventos, base_url=lambda: SW_URL, clock=lambda: clock[0],
        transport=httpx.MockTransport(_stub(kit)),
    )
    return kit


def avancar(kit: Kit, **delta) -> None:
    kit.clock[0] = kit.clock[0] + timedelta(**delta)
