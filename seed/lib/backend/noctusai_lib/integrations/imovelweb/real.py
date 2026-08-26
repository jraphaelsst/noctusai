"""Live OpenNavent client.

Construction is LENIENT (the dep-factory contract every seed integration
follows): building this with no credentials never raises, so a host app
starts whether or not the tenant configured ImovelWeb. The first *call*
raises `ImovelWebConfigError` instead.

**No model calls, no LLM imports, ever.** This module sits on the path a
lead takes into the CRM, and the vendor allows 1.5 seconds to answer. A
provider outage must never become a lost enquiry.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional
# defusedxml, NOT xml.etree — this parses the VENDOR's error body, which is
# remote input we do not control: a hostile or compromised endpoint can answer
# a billion-laughs / XXE payload and take the worker down while it expands.
# Same call shape (`fromstring`, `ParseError`), same house answer adconnect
# already uses for untrusted NF-e XML. Bandit B314.
from defusedxml import ElementTree

from noctusai_lib.integrations.rate_limit import acquire_async

from .auth import ImovelWebAuth
from .endpoints import (
    IMOVELWEB_SANDBOX_WINDOW,
    base_url as resolve_base_url,
    is_sandbox_host,
    preferred_path,
)
from .errors import ImovelWebConfigError, ImovelWebUpstreamError, redact_secrets
from .types import CallbackConfig

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 20.0

#: Rate-limit bucket. The vendor publishes NO limit — Gate 2.5 records
#: whatever 429s appear in practice. Pacing an undocumented API
#: conservatively is cheaper than discovering its limit by being blocked.
RATE_LIMIT_BUCKET = "imovelweb"

_XML_ERROR_FIELDS = ("error_description", "error", "message")


def describe_error_body(response: Any) -> str:
    """Best-effort human description of a failed response.

    Gate 0 observed that this vendor answers errors in **XML**, not JSON,
    despite its spec declaring `produces: */*`: a 401 returns
    `<UnauthorizedException><error>unauthorized</error>
    <error_description>…</error_description></UnauthorizedException>`.

    Assuming a JSON envelope here would turn every upstream failure into a
    decode error and bury the vendor's actual message — so this tries XML,
    then JSON, then falls back to raw text, and never raises.
    """
    status = getattr(response, "status_code", "?")
    text = ""
    try:
        text = getattr(response, "text", "") or ""
    except Exception:  # a mock or a stream that cannot be re-read
        text = ""

    stripped = text.strip()
    if stripped.startswith("<"):
        try:
            root = ElementTree.fromstring(stripped)
            parts = []
            for field in _XML_ERROR_FIELDS:
                node = root.find(field)
                if node is not None and node.text:
                    parts.append(node.text.strip())
            if root.text and root.text.strip():
                parts.insert(0, root.text.strip())
            if parts:
                return f"HTTP {status}: {' — '.join(dict.fromkeys(parts))}"
            return f"HTTP {status}: {root.tag}"
        except ElementTree.ParseError:
            pass

    try:
        payload = response.json()
        if isinstance(payload, dict):
            for field in ("error_description", "error", "message", "detail"):
                value = payload.get(field)
                if isinstance(value, str) and value.strip():
                    return f"HTTP {status}: {value.strip()}"
        return f"HTTP {status}: {payload!r}"[:500]
    except Exception:
        pass

    return f"HTTP {status}: {stripped[:500]}" if stripped else f"HTTP {status}"


def _is_retryable(status: Optional[int]) -> bool:
    """429 and 5xx only.

    Never a 4xx: a 400 or 422 will be identical on every retry, and
    hammering the vendor with it wastes our quota and their patience. A
    401 is likewise not retryable at this layer — the token refresh path
    handles that explicitly, once.
    """
    if status is None:
        return True  # transport-level: worth one more try
    return status == 429 or 500 <= status < 600


class ImovelWebClient:
    """Real `ImovelWebAdapter`."""

    def __init__(
        self,
        *,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        region: str = "br",
        sandbox: bool = False,
        base_url: Optional[str] = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        http_client: Any = None,
        callback_header_value: Optional[str] = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._region = region
        self._sandbox = sandbox
        self._timeout = timeout_seconds
        self._http_client = http_client
        # Held only so it can be redacted out of anything we surface.
        self._callback_header_value = callback_header_value

        if base_url:
            self._base_url = base_url.rstrip("/")
        else:
            try:
                self._base_url = resolve_base_url(region, sandbox=sandbox)
            except ValueError:
                # Lenient construction: an unknown region must not stop the
                # host app from starting. The first call raises instead.
                self._base_url = ""

        self._auth = ImovelWebAuth(
            base_url=self._base_url,
            client_id=client_id,
            client_secret=client_secret,
            http_client=http_client,
        )

    # -- introspection -----------------------------------------------------

    @property
    def configured(self) -> bool:
        return bool(self._base_url and self._client_id and self._client_secret)

    @property
    def base_url(self) -> str:
        return self._base_url

    def redact(self, text: Optional[str]) -> Optional[str]:
        """All THREE secrets — client secret, bearer token, callback header."""
        cached = self._auth._cache.get(self._auth.cache_key)  # noqa: SLF001
        return redact_secrets(
            text,
            self._client_secret,
            cached.value if cached else None,
            self._callback_header_value,
        )

    def connection_status(self) -> dict[str, Any]:
        """Readiness, with **zero API calls**."""
        return {
            "vendor": "imovelweb",
            "configured": self.configured,
            "base_url": self._base_url or None,
            "region": self._region,
            "sandbox": self._sandbox,
            "sandbox_window": IMOVELWEB_SANDBOX_WINDOW if self._sandbox else None,
            "missing": [
                name
                for name, value in (
                    ("base_url", self._base_url),
                    ("client_id", self._client_id),
                    ("client_secret", self._client_secret),
                )
                if not value
            ],
            "verified_against_live_traffic": False,
            "how_to_configure": (
                "Request Sandbox credentials from integracao@imovelweb.com.br, "
                "then set IMOVELWEB_CLIENT_ID / IMOVELWEB_CLIENT_SECRET."
            ),
        }

    # -- plumbing ----------------------------------------------------------

    def _require_config(self) -> None:
        if not self.configured:
            raise ImovelWebConfigError(
                "ImovelWeb is not configured — "
                f"missing {', '.join(self.connection_status()['missing'])}"
            )
        if self._http_client is None:
            raise ImovelWebConfigError(
                "no http_client supplied to ImovelWebClient — the seed does "
                "not construct one for you; pass httpx.AsyncClient or a Fake"
            )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> Any:
        self._require_config()
        token = await self._auth.token()
        await acquire_async(RATE_LIMIT_BUCKET)

        headers = {"Authorization": f"Bearer {token.value}"}
        url = f"{self._base_url}{path}"
        try:
            response = await self._http_client.request(
                method, url, params=params, json=json_body, headers=headers
            )
        except Exception as exc:
            raise ImovelWebUpstreamError(
                f"{method} {path} transport failure: {self.redact(str(exc))}"
            ) from exc

        status = getattr(response, "status_code", None)
        if status is not None and 200 <= status < 300:
            return response
        raise ImovelWebUpstreamError(
            f"{method} {path} failed: {self.redact(describe_error_body(response))}",
            status=status,
        )

    @staticmethod
    def _json(response: Any) -> Any:
        try:
            return response.json()
        except Exception as exc:
            raise ImovelWebUpstreamError(
                f"response body was not JSON: {exc}"
            ) from exc

    # -- auth ---------------------------------------------------------------

    async def login(self) -> dict[str, Any]:
        token = await self._auth.token(force=True)
        return {
            "token_type": token.token_type,
            "expires_at": token.expires_at.isoformat() if token.expires_at else None,
            "scope": list(token.scope),
            # The token value itself is deliberately absent.
        }

    async def logout(self) -> None:
        await self._auth.logout()

    # -- callback configuration --------------------------------------------

    async def get_callback_config(self) -> CallbackConfig:
        response = await self._request("GET", preferred_path("callback_config"))
        return CallbackConfig.from_wire(self._json(response) or {})

    async def put_callback_config(self, config: CallbackConfig) -> CallbackConfig:
        """⚠️ INTEGRATOR-WIDE. Validated here; confirmation is the caller's."""
        problems = config.validate()
        if problems:
            raise ImovelWebConfigError(
                "refusing to register an invalid callback config: "
                + "; ".join(problems)
            )
        await self._request(
            "PUT", preferred_path("callback_config"), json_body=config.to_wire()
        )
        # Read back rather than trusting the write: a PUT that silently
        # drops `subscriptions` is otherwise invisible, and the result is
        # a receiver that is perfectly configured and never delivered to.
        return await self.get_callback_config()

    async def subscribe_event(self, event: str) -> Any:
        path = preferred_path("callback_event").replace("{evento}", "")
        response = await self._request("PUT", path, params={"evento": event})
        return getattr(response, "text", None)

    async def unsubscribe_event(self, event: str) -> Any:
        path = preferred_path("callback_event").replace("{evento}", "")
        response = await self._request("DELETE", path, params={"evento": event})
        return getattr(response, "text", None)

    # -- reconciliation -----------------------------------------------------

    async def list_agency_messages(
        self,
        codigo_imobiliaria: str,
        *,
        from_date: str,
        to_date: Optional[str] = None,
        page: int = 0,
        size: int = 100,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "fromDate": from_date,
            "pageable.page": page,
            "pageable.size": size,
        }
        if to_date:
            params["toDate"] = to_date
        response = await self._request(
            "GET", f"/v2/imobiliarias/{codigo_imobiliaria}/mensagens", params=params
        )
        # 204 No Content is a documented, normal "nothing in this window".
        if getattr(response, "status_code", None) == 204:
            return {"content": [], "number": page, "size": size, "total": 0}
        return self._json(response) or {}

    async def get_message(self, id_mensaje: int) -> dict[str, Any]:
        response = await self._request("GET", f"/v1/mensagens/{id_mensaje}")
        return self._json(response) or {}

    async def list_listing_messages(
        self, codigo_imobiliaria: str, codigo_anuncio: str
    ) -> dict[str, Any]:
        response = await self._request(
            "GET",
            f"/v1/imobiliarias/{codigo_imobiliaria}/anuncios/{codigo_anuncio}/mensagens",
        )
        return self._json(response) or {}

    # -- enrichment ---------------------------------------------------------

    async def get_contact(
        self, codigo_imobiliaria: str, id_contato: int
    ) -> dict[str, Any]:
        response = await self._request(
            "GET", f"/v1/imobiliarias/{codigo_imobiliaria}/contatos/{id_contato}"
        )
        return self._json(response) or {}

    async def get_smartlead(self, id_mensagem: int) -> dict[str, Any]:
        # Note the vendor's own typo: `mensagen`, singular-with-n, unlike
        # every sibling path. Not ours to fix.
        response = await self._request("GET", f"/v1/mensagen/{id_mensagem}/smartLead")
        return self._json(response) or {}

    async def get_seeker_profile(self, user_id_navplat: str) -> dict[str, Any]:
        response = await self._request(
            "GET", f"/v1/seekers/br/{user_id_navplat}/profile"
        )
        return self._json(response) or {}

    async def list_contact_actions(self) -> list[dict[str, Any]]:
        response = await self._request("GET", "/v1/contatos/acoes")
        payload = self._json(response)
        return payload if isinstance(payload, list) else []

    # -- agencies -----------------------------------------------------------

    async def list_agencies(self, *, page: int = 0, size: int = 100) -> dict[str, Any]:
        response = await self._request(
            "GET", "/v1/imobiliarias",
            params={"pageable.page": page, "pageable.size": size},
        )
        if getattr(response, "status_code", None) == 204:
            return {"content": [], "number": page, "size": size, "total": 0}
        return self._json(response) or {}

    async def unlink_agency(self, codigo_imobiliaria: str) -> Any:
        response = await self._request(
            "DELETE", f"/v1/imobiliarias/{codigo_imobiliaria}/"
        )
        return getattr(response, "text", None)

    # -- sandbox only -------------------------------------------------------

    async def emit_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Ask the SANDBOX to push a synthetic event at our receiver.

        Hard-refuses a non-sandbox host. This is not defensive politeness:
        pointed at production it would inject fabricated leads into a live
        CRM, and the failure would look exactly like real traffic.
        """
        if not is_sandbox_host(self._base_url):
            raise ImovelWebConfigError(
                f"emit_event refuses a non-sandbox host ({self._base_url!r}). "
                "It fabricates lead events; against production those would be "
                "indistinguishable from real customers."
            )
        response = await self._request(
            "POST", preferred_path("sandbox_emit"), json_body=payload
        )
        return self._json(response) or {}


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "RATE_LIMIT_BUCKET",
    "ImovelWebClient",
    "describe_error_body",
]
