"""Sender-domain verification over the Resend Domains API — Protocol + Fake +
Real + factory (KB § PATTERNS/backend/seed-fake-real-adapter.md).

`create(name)` registers a domain and returns the DNS records (SPF / DKIM /
DMARC / return-path) the owner must publish; `verify(id)` asks Resend to check
them; `get(id)` reads the current status. Any product sending from its own
domain needs this — added 2026-10-10 for social-wiring email marketing P1b(c),
whose "verify" endpoint was a TODO that only echoed the stored row.

Status vocabulary is Resend's (`not_started`, `pending`, `verified`, `failed`,
`temporary_failure`); callers map it to their own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol, runtime_checkable

import httpx

from noctusai_lib.primitives.not_configured import IntegrationNotConfigured

RESEND_DOMAINS_URL = "https://api.resend.com/domains"


class ResendDomainsError(Exception):
    """Resend answered with an error (or the transport failed)."""


class ResendNotConfigured(ResendDomainsError, IntegrationNotConfigured):
    """No Resend API key resolved — refuse; never pretend a domain verified."""


@dataclass
class DomainRecord:
    id: str
    name: str
    status: str
    records: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "DomainRecord":
        return cls(id=str(data.get("id", "")), name=str(data.get("name", "")),
                   status=str(data.get("status", "not_started")),
                   records=list(data.get("records") or []))


@runtime_checkable
class ResendDomains(Protocol):
    async def create(self, name: str) -> DomainRecord: ...
    async def get(self, domain_id: str) -> DomainRecord: ...
    async def verify(self, domain_id: str) -> DomainRecord: ...


@dataclass
class FakeResendDomains:
    """In-memory double. `verifiable` names domains whose DNS is "published":
    `verify` flips those to `verified`, every other domain to `failed`."""

    verifiable: set[str] = field(default_factory=set)
    domains: dict[str, DomainRecord] = field(default_factory=dict)

    async def create(self, name: str) -> DomainRecord:
        rec = DomainRecord(
            id=f"dom_{len(self.domains) + 1}", name=name, status="not_started",
            records=[
                {"record": "SPF", "type": "TXT", "name": f"send.{name}", "value": "v=spf1 include:amazonses.com ~all"},
                {"record": "DKIM", "type": "TXT", "name": f"resend._domainkey.{name}", "value": "p=FAKEKEY"},
                {"record": "DMARC", "type": "TXT", "name": f"_dmarc.{name}", "value": "v=DMARC1; p=none;"},
            ],
        )
        self.domains[rec.id] = rec
        return rec

    async def get(self, domain_id: str) -> DomainRecord:
        if domain_id not in self.domains:
            raise ResendDomainsError(f"unknown domain {domain_id}")
        return self.domains[domain_id]

    async def verify(self, domain_id: str) -> DomainRecord:
        rec = await self.get(domain_id)
        rec.status = "verified" if rec.name in self.verifiable else "failed"
        return rec


class HttpResendDomains:
    def __init__(self, api_key: str, *, http_client_factory: Callable[[], Any] = httpx.AsyncClient):
        if not api_key:
            raise ResendNotConfigured("resend_api_key is not configured")
        self._api_key = api_key
        self._http_client_factory = http_client_factory  # seam: the Resend HTTP boundary

    async def _call(self, method: str, path: str, json: Optional[dict] = None) -> dict[str, Any]:
        try:
            async with self._http_client_factory() as client:
                resp = await client.request(
                    method, f"{RESEND_DOMAINS_URL}{path}", json=json,
                    headers={"Authorization": f"Bearer {self._api_key}"}, timeout=30,
                )
        except Exception as exc:
            raise ResendDomainsError(f"resend transport error: {exc}") from exc
        if resp.status_code not in (200, 201):
            raise ResendDomainsError(f"resend HTTP {resp.status_code}: {str(getattr(resp, 'text', ''))[:200]}")
        return resp.json() or {}

    async def create(self, name: str) -> DomainRecord:
        return DomainRecord.from_api(await self._call("POST", "", {"name": name}))

    async def get(self, domain_id: str) -> DomainRecord:
        return DomainRecord.from_api(await self._call("GET", f"/{domain_id}"))

    async def verify(self, domain_id: str) -> DomainRecord:
        await self._call("POST", f"/{domain_id}/verify")
        return await self.get(domain_id)


def make_resend_domains(api_key: Optional[str], *, use_fake: bool = False) -> ResendDomains:
    """Real when a key is present; the Fake only on an explicit `use_fake=True`;
    otherwise `ResendNotConfigured` (callers answer 503). Never "no key → Fake"."""
    if use_fake:
        return FakeResendDomains()
    if not api_key:
        raise ResendNotConfigured("resend_api_key is not configured")
    return HttpResendDomains(api_key)


__all__ = [
    "RESEND_DOMAINS_URL", "DomainRecord", "FakeResendDomains", "HttpResendDomains",
    "ResendDomains", "ResendDomainsError", "ResendNotConfigured", "make_resend_domains",
]
