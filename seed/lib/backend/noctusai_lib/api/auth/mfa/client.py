"""``MfaClient`` — TOTP factor operations against Supabase Auth (GoTrue).

Protocol + Fake + Real + factory (``KB § PATTERNS/backend/seed-fake-real-adapter.md``).
The Real adapter speaks the GoTrue REST API with ``httpx`` on a per-call
basis — it never builds or mutates a shared supabase-py client (SEC-1: a
user session set on a long-lived client poisons it). User-scoped calls
authenticate with the CALLER'S access token; ``delete_factor`` uses the
service-role key (admin recovery, audited by the caller).

``verify`` returns the NEW session tokens (aal2): a Bearer SPA swaps its
tokens; a cookie session rewrites its stored ones. Never log codes/tokens.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Literal, Optional, Protocol, runtime_checkable

import httpx

from noctusai_lib.api.auth.mfa.aal import read_aal_issued

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10.0


class MfaError(Exception):
    """A TOTP operation failed. ``code`` is machine-readable."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class MfaFactor:
    id: str
    factor_type: str
    status: Literal["verified", "unverified"] | str
    friendly_name: Optional[str] = None


@dataclass(frozen=True)
class MfaEnrollment:
    factor_id: str
    secret: str
    uri: str
    qr_svg: str


@dataclass(frozen=True)
class MfaChallenge:
    id: str
    expires_at: Optional[int] = None


@dataclass(frozen=True)
class MfaSession:
    access_token: str
    refresh_token: str
    expires_at: int
    aal: Optional[str]


@runtime_checkable
class MfaClient(Protocol):
    async def list_factors(self, access_token: str) -> list[MfaFactor]: ...
    async def enroll_totp(self, access_token: str, *, friendly_name: str) -> MfaEnrollment: ...
    async def challenge(self, access_token: str, factor_id: str) -> MfaChallenge: ...
    async def verify(self, access_token: str, factor_id: str, challenge_id: str, code: str) -> MfaSession: ...
    async def delete_factor(self, user_id: str, factor_id: str) -> None: ...


class FakeMfaClient:
    """In-memory, deterministic. Tokens are opaque ``fake-*`` strings; the
    only valid code is ``valid_code``. State is keyed by ``access_token``
    (user) so tests can run several users; ``admin_deleted`` records resets."""

    def __init__(self, *, valid_code: str = "123456") -> None:
        self.valid_code = valid_code
        self.factors: dict[str, list[MfaFactor]] = {}
        self.admin_deleted: list[tuple[str, str]] = []
        self._challenges: dict[str, str] = {}
        self._n = 0

    def _next(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}-{self._n}"

    async def list_factors(self, access_token: str) -> list[MfaFactor]:
        return list(self.factors.get(access_token, []))

    async def enroll_totp(self, access_token: str, *, friendly_name: str) -> MfaEnrollment:
        fid = self._next("factor")
        self.factors.setdefault(access_token, []).append(
            MfaFactor(fid, "totp", "unverified", friendly_name)
        )
        return MfaEnrollment(fid, "FAKESECRET", f"otpauth://totp/fake?secret=FAKESECRET&f={fid}", "<svg/>")

    async def challenge(self, access_token: str, factor_id: str) -> MfaChallenge:
        if not any(f.id == factor_id for f in self.factors.get(access_token, [])):
            raise MfaError("factor_not_found")
        cid = self._next("challenge")
        self._challenges[cid] = factor_id
        return MfaChallenge(cid, int(time.time()) + 300)

    async def verify(self, access_token: str, factor_id: str, challenge_id: str, code: str) -> MfaSession:
        if self._challenges.get(challenge_id) != factor_id:
            raise MfaError("challenge_invalid")
        if code != self.valid_code:
            raise MfaError("invalid_code")
        del self._challenges[challenge_id]
        self.factors[access_token] = [
            MfaFactor(f.id, f.factor_type, "verified", f.friendly_name) if f.id == factor_id else f
            for f in self.factors.get(access_token, [])
        ]
        return MfaSession(
            access_token=f"fake-aal2-{factor_id}", refresh_token=f"fake-refresh-{factor_id}",
            expires_at=int(time.time()) + 3600, aal="aal2",
        )

    async def delete_factor(self, user_id: str, factor_id: str) -> None:
        self.admin_deleted.append((user_id, factor_id))
        for tok, fs in self.factors.items():
            self.factors[tok] = [f for f in fs if f.id != factor_id]


class SupabaseMfaClient:
    """Real GoTrue REST adapter. ``transport`` is the test seam (``httpx.MockTransport``)."""

    def __init__(self, *, supabase_url: str, anon_key: str, service_role_key: Optional[str] = None,
                 timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
                 transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self._base = supabase_url.rstrip("/") + "/auth/v1"
        self._anon = anon_key
        self._service = service_role_key
        self._timeout = timeout_seconds
        self._transport = transport

    async def _call(self, method: str, path: str, *, bearer: str, apikey: str,
                    json: Optional[dict] = None) -> Any:
        headers = {"Authorization": f"Bearer {bearer}", "apikey": apikey}
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as c:
                resp = await c.request(method, self._base + path, headers=headers, json=json)
        except httpx.HTTPError as exc:
            logger.error("mfa.client: %s %s transport error: %s", method, path, type(exc).__name__)
            raise MfaError("provider_unavailable") from exc
        if resp.status_code >= 400:
            logger.warning("mfa.client: %s %s -> %s", method, path, resp.status_code)
            code = "invalid_code" if resp.status_code in (400, 422) and path.endswith("/verify") else (
                "unauthorized" if resp.status_code in (401, 403) else (
                    "factor_not_found" if resp.status_code == 404 else "provider_error"))
            raise MfaError(code, f"auth provider answered {resp.status_code}")
        return resp.json() if resp.content else None

    async def list_factors(self, access_token: str) -> list[MfaFactor]:
        user = await self._call("GET", "/user", bearer=access_token, apikey=self._anon)
        return [
            MfaFactor(f["id"], f.get("factor_type", ""), f.get("status", ""), f.get("friendly_name"))
            for f in (user or {}).get("factors") or []
        ]

    async def enroll_totp(self, access_token: str, *, friendly_name: str) -> MfaEnrollment:
        data = await self._call("POST", "/factors", bearer=access_token, apikey=self._anon,
                                json={"factor_type": "totp", "friendly_name": friendly_name})
        totp = data.get("totp") or {}
        return MfaEnrollment(data["id"], totp.get("secret", ""), totp.get("uri", ""), totp.get("qr_code", ""))

    async def challenge(self, access_token: str, factor_id: str) -> MfaChallenge:
        data = await self._call("POST", f"/factors/{factor_id}/challenge", bearer=access_token, apikey=self._anon)
        return MfaChallenge(data["id"], data.get("expires_at"))

    async def verify(self, access_token: str, factor_id: str, challenge_id: str, code: str) -> MfaSession:
        data = await self._call("POST", f"/factors/{factor_id}/verify", bearer=access_token, apikey=self._anon,
                                json={"challenge_id": challenge_id, "code": code})
        new_access = data["access_token"]
        expires_at = data.get("expires_at") or int(time.time()) + int(data.get("expires_in", 3600))
        # The token came straight from the provider's verify response → issued-to-us.
        return MfaSession(new_access, data["refresh_token"], int(expires_at), read_aal_issued(new_access))

    async def delete_factor(self, user_id: str, factor_id: str) -> None:
        if not self._service:
            raise MfaError("service_role_required")
        await self._call("DELETE", f"/admin/users/{user_id}/factors/{factor_id}",
                         bearer=self._service, apikey=self._service)


def make_mfa_client(*, use_fake: bool = False, supabase_url: Optional[str] = None,
                    anon_key: Optional[str] = None, service_role_key: Optional[str] = None,
                    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
                    transport: Optional[httpx.AsyncBaseTransport] = None) -> MfaClient:
    """Fake when ``use_fake``; else the Real adapter (needs ``supabase_url`` + ``anon_key``)."""
    if use_fake:
        return FakeMfaClient()
    if not supabase_url or not anon_key:
        raise ValueError("make_mfa_client: supabase_url and anon_key are required unless use_fake=True")
    return SupabaseMfaClient(supabase_url=supabase_url, anon_key=anon_key,
                             service_role_key=service_role_key,
                             timeout_seconds=timeout_seconds, transport=transport)


__all__ = [
    "FakeMfaClient", "MfaChallenge", "MfaClient", "MfaEnrollment", "MfaError",
    "MfaFactor", "MfaSession", "SupabaseMfaClient", "make_mfa_client",
]
