"""``AcademiaApi`` — the thin HTTP transport the §C tool proxies (tools.py)
call. Protocol + Fake + Http + factory (seed IO shape,
``KB § PATTERNS/backend/seed-fake-real-adapter.md``), product-local (only
``agents`` calls academia's HTTP API today).

**Deliberately generic**, not one named method per §C tool. Each tool
handler in ``tools.py`` already knows its own method/path/body shape (it
has to, to mint the §D assertion over that exact triple) — a second
30-method surface here mirroring §C 1:1 would duplicate that mapping and
drift from it. ``get``/``request`` are the two primitives every §C route
reduces to; error translation (401/403/404/409/422/5xx) lives ONCE, here.

Auth: every call carries ``Authorization: Bearer <ACADEMIA_API_TOKEN>``.
Writes ALSO carry ``X-Approval-Assertion`` (contract §D) — minted by the
caller (``tools.py``, which holds the approval id and the agent/org
identity), never by this module.
"""
from __future__ import annotations

from typing import Any, Protocol

import httpx

__all__ = [
    "AcademiaApiError",
    "AcademiaAuthError",
    "AcademiaNotFoundError",
    "AcademiaConflictError",
    "AcademiaValidationError",
    "AcademiaUnreachableError",
    "AcademiaApi",
    "FakeAcademiaApi",
    "HttpAcademiaApi",
    "make_academia_api",
]


class AcademiaApiError(Exception):
    """Base class. Carries the raw ``status`` + parsed ``detail``/``code``
    (academia's error shape, contract §0: ``{"detail": ..., "code": ...}``)
    so a tool handler can surface something useful in its ``error`` field
    without re-deriving it from a caught ``httpx`` exception."""

    def __init__(self, status: int, detail: str, code: str | None = None) -> None:
        self.status = status
        self.detail = detail
        self.code = code
        super().__init__(f"academia {status} {code or ''}: {detail}")


class AcademiaAuthError(AcademiaApiError):
    """401 or 403 — includes ``assertion_invalid`` / ``assertion_used`` /
    ``scope_missing`` (contract §B.0 status taxonomy)."""


class AcademiaNotFoundError(AcademiaApiError):
    """404."""


class AcademiaConflictError(AcademiaApiError):
    """409."""


class AcademiaValidationError(AcademiaApiError):
    """422."""


class AcademiaUnreachableError(AcademiaApiError):
    """5xx, network error, or timeout."""


class AcademiaApi(Protocol):
    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """A read (contract §B GET route). ``path`` is the API-relative
        path, e.g. ``"/api/kb"`` — never includes the base URL."""
        ...

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        assertion: str | None = None,
    ) -> dict[str, Any]:
        """A write (contract §B POST/PUT/PATCH route). ``assertion`` is the
        compact JWS from :func:`app.runtime.assertion.mint_assertion`,
        sent as ``X-Approval-Assertion`` when set."""
        ...


def _translate_error(status: int, payload: dict[str, Any]) -> AcademiaApiError:
    detail = str(payload.get("detail", "")) if isinstance(payload, dict) else ""
    code = payload.get("code") if isinstance(payload, dict) else None
    if status in (401, 403):
        return AcademiaAuthError(status, detail, code)
    if status == 404:
        return AcademiaNotFoundError(status, detail, code)
    if status == 409:
        return AcademiaConflictError(status, detail, code)
    if status == 422:
        return AcademiaValidationError(status, detail, code)
    return AcademiaUnreachableError(status, detail, code)


class HttpAcademiaApi:
    """Real :class:`AcademiaApi` — httpx over academia's HTTP API."""

    def __init__(self, *, base_url: str, token: str, timeout_seconds: float = 15.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout_seconds

    def _headers(self, *, assertion: str | None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._token}"}
        if assertion:
            headers["X-Approval-Assertion"] = assertion
        return headers

    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout
        ) as client:
            try:
                resp = await client.get(
                    path, params=params, headers=self._headers(assertion=None)
                )
            except httpx.HTTPError as exc:
                raise AcademiaUnreachableError(0, str(exc)) from exc
        return self._unwrap(resp)

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        assertion: str | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout
        ) as client:
            try:
                resp = await client.request(
                    method,
                    path,
                    json=body if body is not None else {},
                    headers=self._headers(assertion=assertion),
                )
            except httpx.HTTPError as exc:
                raise AcademiaUnreachableError(0, str(exc)) from exc
        return self._unwrap(resp)

    @staticmethod
    def _unwrap(resp: httpx.Response) -> dict[str, Any]:
        try:
            payload = resp.json() if resp.content else {}
        except ValueError:
            payload = {}
        if resp.status_code >= 400:
            raise _translate_error(resp.status_code, payload)
        return payload


class FakeAcademiaApi:
    """Deterministic in-memory :class:`AcademiaApi` — dev/test default.
    Records every call on ``self.calls`` for assertion in tests; returns
    whatever ``self.responses`` scripts for the (method, path) pair, or an
    empty dict when nothing was scripted (a permissive default so tests
    that only care about the CALL, not the response, don't need to script
    one)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        # (method, path) -> response dict. GET uses method "GET".
        self.responses: dict[tuple[str, str], dict[str, Any]] = {}
        # (method, path) -> exception instance to raise instead of returning.
        self.errors: dict[tuple[str, str], AcademiaApiError] = {}

    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append({"method": "GET", "path": path, "params": params, "body": None, "assertion": None})
        key = ("GET", path)
        if key in self.errors:
            raise self.errors[key]
        return self.responses.get(key, {})

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        assertion: str | None = None,
    ) -> dict[str, Any]:
        method = method.upper()
        self.calls.append(
            {"method": method, "path": path, "params": None, "body": body, "assertion": assertion}
        )
        key = (method, path)
        if key in self.errors:
            raise self.errors[key]
        return self.responses.get(key, {})


def make_academia_api(*, base_url: str = "", token: str = "", use_fake: bool = False) -> AcademiaApi:
    """Fake unless BOTH ``base_url`` and ``token`` are set — mirrors the
    seed adapter convention (no credentials/target => Fake)."""
    if use_fake or not base_url or not token:
        return FakeAcademiaApi()
    return HttpAcademiaApi(base_url=base_url, token=token)
