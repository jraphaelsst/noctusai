"""Port to social-wiring's operational settings (reengage, CRM send, address/IPTU policy, recess, review link, ...).

Seed IO shape: ``SwSettingsPort`` Protocol + ``FakeSwSettings`` + the Real ``SwSettingsStaffClient`` + factory
(``KB § PATTERNS/backend/seed-fake-real-adapter.md``). Never raises: a refusal is a result the apply report carries.

The Real client calls social-wiring's onboarding staff channel (``PUT /api/julia/onboarding/orgs/{org}/configuracoes/{setting}``,
service tier): a PLATFORM-issued service token (scope ``social-wiring:onboarding-settings``) that the channel
(:mod:`app.onboarding.sw_canal`) provisions and rotates by itself -- nobody creates or pastes it -- plus the acting staff
user and the grant as ``ator`` / ``grant_id``. A channel failure is a refusal result with a named code. The caller
(the platform-admin onboarding route) has ALREADY verified the admin and the live ``plataforma`` grant; this port never
decides authority, it only carries the attested actor. Social-wiring allow-lists the settings and records the event.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, Protocol
from uuid import UUID

import httpx

from app.onboarding.sw_canal import CanalErro, SwCanalPort

logger = logging.getLogger(__name__)

SW_TIMEOUT_SECONDS = 10.0
SW_INDISPONIVEL = "sw_indisponivel"

__all__ = ["SW_INDISPONIVEL", "FakeSwSettings", "SwResultado", "SwSettingsPort", "SwSettingsStaffClient", "get_sw_settings"]


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
        self, base_url: str | None, canal: SwCanalPort, *, transport: httpx.BaseTransport | None = None,
        timeout: float = SW_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = (base_url or "").rstrip("/")
        self._canal = canal
        self._transport = transport
        self._timeout = timeout

    def aplicar(
        self, org_id: UUID, setting: str, rota: str | None, corpo: dict[str, Any], *, ator: UUID, grant_id: UUID | None = None,
    ) -> SwResultado:
        if not self._base_url:
            return self._resultado(SwResultado(False, "sw_url_ausente", "O endereço do social-wiring não está configurado."))
        try:
            token = self._canal.token_para_uso()
        except CanalErro as exc:
            return self._resultado(SwResultado(False, exc.codigo, exc.mensagem))
        body: dict[str, Any] = {"corpo": corpo, "ator": {"user_id": str(ator)}}
        if grant_id:
            body["grant_id"] = str(grant_id)
        url = f"{self._base_url}/api/julia/onboarding/orgs/{org_id}/configuracoes/{setting}"
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as http:
                resp = http.put(url, json=body, headers={"Authorization": f"Bearer {token}"})
        except httpx.HTTPError as exc:
            logger.warning("agents.onboarding.sw_unavailable org=%s setting=%s error=%s", org_id, setting, type(exc).__name__)
            return self._resultado(SwResultado(False, SW_INDISPONIVEL, "O social-wiring não respondeu; tente de novo."))
        if resp.status_code == 200:
            return self._resultado(SwResultado(True))
        codigo, msg = f"sw_http_{resp.status_code}", "O social-wiring recusou a configuração."
        try:
            j = resp.json()
            e = j.get("error") if isinstance(j.get("error"), dict) else j
            codigo = str(e.get("code") or codigo)
            msg = str(e.get("message") or e.get("detail") or msg)[:300]
        except (ValueError, AttributeError):
            pass
        logger.warning("agents.onboarding.sw_refused org=%s setting=%s status=%s code=%s", org_id, setting, resp.status_code, codigo)
        return self._resultado(SwResultado(False, codigo, msg))

    def _resultado(self, r: SwResultado) -> SwResultado:
        """Report the outcome to the channel (its ``sw_canal_chamada_concluida`` event), then hand it back unchanged."""
        self._canal.registrar_chamada(ok=r.ok, codigo=r.codigo, mensagem=r.mensagem)
        return r


def get_sw_settings(canal: SwCanalPort) -> SwSettingsPort:
    """The Real port over the staff channel, using the already-bound ``canal`` (``SwCanal.como(org, ator)``)."""
    from noctusai_lib.config.product_urls import resolve_product_url

    try:
        base = resolve_product_url("social-wiring")
    except ValueError:
        base = None
    return SwSettingsStaffClient(base, canal)
