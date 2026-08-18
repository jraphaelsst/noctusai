"""Live Gestor de Leads client — `POST /v1/addLeads`.

Construction is LENIENT (the dep-factory contract every seed integration
follows): building this with no key never raises, so a host app starts
whether or not the tenant configured OLX. The first *call* raises
`OlxConfigError` instead.
"""

from __future__ import annotations

from typing import Any, Optional

from noctusai_lib.integrations.rate_limit import acquire_async, retry_with_backoff_async

from .endpoints import OLX_LEAD_MANAGER_BASE_URL
from .errors import OlxConfigError, OlxError, OlxUpstreamError, redact_secret

DEFAULT_TIMEOUT_SECONDS = 20.0

#: Rate-limit bucket. OLX publishes no limit for addLeads, so this is a
#: politeness default, not a documented one — pacing an undocumented API
#: conservatively is cheaper than discovering its limit by being blocked.
RATE_LIMIT_BUCKET = "olx"


class OlxLeadManagerClient:
    """Real `OlxLeadManagerAdapter`."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        agent_name: Optional[str] = None,
        *,
        base_url: str = OLX_LEAD_MANAGER_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        http_client: Any = None,
    ) -> None:
        self._api_key = api_key
        self._agent_name = agent_name
        self._base_url = (base_url or OLX_LEAD_MANAGER_BASE_URL).rstrip("/")
        self._timeout = timeout_seconds
        self._http_client = http_client

    @property
    def configured(self) -> bool:
        return bool(self._api_key and self._agent_name)

    async def connection_status(self) -> dict[str, Any]:
        """Zero API calls — see the Protocol docstring for why."""
        return {
            "ok": self.configured,
            "configured": self.configured,
            "base_url": self._base_url,
            "has_api_key": bool(self._api_key),
            "has_agent_name": bool(self._agent_name),
            "next_step": (
                None if self.configured
                else "Set OLX_API_KEY and OLX_AGENT_NAME. Both come from the "
                     "Gestor de Leads setup — request them at "
                     "integracaoleads@grupozap.com."
            ),
        }

    async def push_lead(
        self,
        *,
        lead_name: str,
        lead_email: Optional[str] = None,
        lead_telephone: Optional[str] = None,
        message: Optional[str] = None,
        external_id: Optional[str] = None,
        business_type: Optional[str] = None,
        broker_email: Optional[str] = None,
        lead_origin: Optional[str] = None,
    ) -> dict[str, Any]:
        if not self.configured:
            raise OlxConfigError(
                "OLX Gestor de Leads is not configured — OLX_API_KEY and "
                "OLX_AGENT_NAME are both required."
            )
        if business_type is not None and business_type not in ("SALE", "RENTAL"):
            # Loud, not coerced: SELL/RENT is the INBOUND webhook's
            # vocabulary and silently accepting it here would post a lead
            # OLX rejects, with the cause two layers away.
            raise ValueError(
                f"business_type must be 'SALE' or 'RENTAL' (got {business_type!r}). "
                "The inbound webhook's SELL/RENT is a DIFFERENT vocabulary — "
                "translate, do not pass through."
            )

        body = {
            k: v for k, v in {
                "LeadName": lead_name,
                "LeadEmail": lead_email,
                "LeadTelephone": lead_telephone,
                "Message": message,
                "ExternalId": external_id,
                "BusinessType": business_type,
                "BrokerEmail": broker_email,
                "LeadOrigin": lead_origin,
            }.items() if v is not None
        }
        return await self._post("/v1/addLeads", body)

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        import httpx

        url = f"{self._base_url}{path}"
        headers = {
            "X-API-KEY": self._api_key or "",
            "X-Agent-Name": self._agent_name or "",
            "Content-Type": "application/json",
            "accept": "application/json",
        }

        async def _attempt() -> dict[str, Any]:
            await acquire_async(RATE_LIMIT_BUCKET)
            client = self._http_client
            if client is not None:
                response = await client.post(url, json=body, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as owned:
                    response = await owned.post(url, json=body, headers=headers)
            return self._decode(response, path)

        return await retry_with_backoff_async(
            _attempt,
            bucket=RATE_LIMIT_BUCKET,
            is_retryable=_is_retryable,
        )

    def _decode(self, response: Any, path: str) -> dict[str, Any]:
        status = getattr(response, "status_code", None)
        text = getattr(response, "text", "") or ""
        if status is None or not (200 <= int(status) < 300):
            raise OlxUpstreamError(
                redact_secret(
                    f"OLX POST {path} failed with {status}: {text[:500]}",
                    self._api_key,
                ),
                status=int(status) if status is not None else 502,
            )
        if not text.strip():
            # A 2xx with an empty body is a success with nothing to say.
            return {}
        try:
            return response.json()
        except Exception:  # noqa: BLE001 — any decoder, one meaning
            raise OlxUpstreamError(
                redact_secret(
                    f"OLX POST {path} returned {status} with a non-JSON body: "
                    f"{text[:500]}",
                    self._api_key,
                ),
                status=502,
            ) from None


def _is_retryable(exc: BaseException) -> bool:
    """Retry transport failures and OLX's own 429/5xx; never a 4xx.

    A 4xx means the request is wrong — retrying it just sends the same
    wrong request three more times.
    """
    if isinstance(exc, OlxConfigError):
        return False
    if isinstance(exc, OlxUpstreamError):
        return exc.status == 429 or (exc.status or 0) >= 500
    return not isinstance(exc, (OlxError, ValueError))


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "RATE_LIMIT_BUCKET",
    "OlxLeadManagerClient",
]
