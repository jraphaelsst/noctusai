"""Port to social-wiring's operational settings (reengage, CRM send, address/IPTU policy, recess, review link, ...).

Seed IO shape: ``SwSettingsPort`` Protocol + ``FakeSwSettings`` + the Real ``SwSettingsStaffClient`` + factory
(``KB § PATTERNS/backend/seed-fake-real-adapter.md``). Never raises: a refusal is a result the apply report carries.

The Real client calls social-wiring's onboarding staff channel (``PUT /api/julia/onboarding/orgs/{org}/configuracoes/{setting}``,
service tier): a PLATFORM-issued service token (scope ``social-wiring:onboarding-settings``, held as the platform
setting ``sw_onboarding_service_token``) plus the acting staff user and the grant as ``ator`` / ``grant_id``. The caller
(the platform-admin onboarding route) has ALREADY verified the admin and the live ``plataforma`` grant; this port never
decides authority, it only carries the attested actor. Social-wiring allow-lists the settings and records the event.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, Callable, Protocol
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

SW_TOKEN_KEY = "sw_onboarding_service_token"
SW_TIMEOUT_SECONDS = 10.0
SW_INDISPONIVEL = "sw_indisponivel"

__all__ = ["CANAL_NAO_CONFIGURADO", "SW_INDISPONIVEL", "SW_TOKEN_KEY", "FakeSwSettings", "SwResultado", "SwSettingsPort", "SwSettingsStaffClient", "get_sw_settings"]

CANAL_NAO_CONFIGURADO = "canal_sw_nao_configurado"


@dataclass(frozen=True)
class SwResultado:
    ok: bool
    codigo: str | None = None
    mensagem: str | None = None


class SwSettingsPort(Protocol):
    def aplicar(
        self, org_id: UUID, setting: str, rota: str | None, corpo: dict[str, Any], *, ator: UUID, grant_id: UUID | None = None,
    ) -> SwResultado:
        """Apply ``corpo`` to the SW setting ``setting`` (``rota`` = the manual route, when one exists) for ``org_id``, as
        the platform user ``ator`` acting under ``grant_id`` (both verified by the caller)."""
        ...


@dataclass
class FakeSwSettings:
    """In-memory port: records calls; ``falhar`` maps a setting id to a refusal code."""

    chamadas: list[tuple[UUID, str, dict[str, Any]]] = field(default_factory=list)
    #: ``(org, setting, ator, grant_id)`` per call -- who the port was told is acting.
    atores: list[tuple[UUID, str, UUID, UUID | None]] = field(default_factory=list)
    falhar: dict[str, str] = field(default_factory=dict)

    def aplicar(
        self, org_id: UUID, setting: str, rota: str | None, corpo: dict[str, Any], *, ator: UUID, grant_id: UUID | None = None,
    ) -> SwResultado:
        self.chamadas.append((org_id, setting, dict(corpo)))
        self.atores.append((org_id, setting, ator, grant_id))
        if setting in self.falhar:
            return SwResultado(False, self.falhar[setting], "recusado pelo social-wiring")
        return SwResultado(True)


class SwSettingsStaffClient:
    """Real port: ``httpx`` over the staff channel. ``transport`` is the DI seam (``httpx.MockTransport`` in tests)."""

    def __init__(
        self, base_url: str | None, token_resolver: Callable[[], str | None], *, transport: httpx.BaseTransport | None = None,
        timeout: float = SW_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = (base_url or "").rstrip("/")
        self._token_resolver = token_resolver
        self._transport = transport
        self._timeout = timeout

    def aplicar(
        self, org_id: UUID, setting: str, rota: str | None, corpo: dict[str, Any], *, ator: UUID, grant_id: UUID | None = None,
    ) -> SwResultado:
        token = self._token_resolver() if self._base_url else None
        if not token:
            return SwResultado(
                False, CANAL_NAO_CONFIGURADO,
                "O canal da equipe com o social-wiring não está configurado; aplique esta configuração lá com a rota indicada.",
            )
        body: dict[str, Any] = {"corpo": corpo, "ator": {"user_id": str(ator)}}
        if grant_id:
            body["grant_id"] = str(grant_id)
        url = f"{self._base_url}/api/julia/onboarding/orgs/{org_id}/configuracoes/{setting}"
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as http:
                resp = http.put(url, json=body, headers={"Authorization": f"Bearer {token}"})
        except httpx.HTTPError as exc:
            logger.warning("agents.onboarding.sw_unavailable org=%s setting=%s error=%s", org_id, setting, type(exc).__name__)
            return SwResultado(False, SW_INDISPONIVEL, "O social-wiring não respondeu; tente de novo.")
        if resp.status_code == 200:
            return SwResultado(True)
        codigo, msg = f"sw_http_{resp.status_code}", "O social-wiring recusou a configuração."
        try:
            j = resp.json()
            e = j.get("error") if isinstance(j.get("error"), dict) else j
            codigo = str(e.get("code") or codigo)
            msg = str(e.get("message") or e.get("detail") or msg)[:300]
        except (ValueError, AttributeError):
            pass
        logger.warning("agents.onboarding.sw_refused org=%s setting=%s status=%s code=%s", org_id, setting, resp.status_code, codigo)
        return SwResultado(False, codigo, msg)


def get_sw_settings() -> SwSettingsPort:
    from noctusai_lib.config.credentials import resolve_credential
    from noctusai_lib.config.product_urls import resolve_product_url

    try:
        base = resolve_product_url("social-wiring")
    except ValueError:
        base = None
    return SwSettingsStaffClient(base, lambda: resolve_credential(SW_TOKEN_KEY))
