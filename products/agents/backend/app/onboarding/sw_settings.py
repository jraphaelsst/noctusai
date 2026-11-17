"""Port to social-wiring's operational settings (reengage, CRM send, address/IPTU policy, recess, sector contacts).

Seed IO shape: ``SwSettingsPort`` Protocol + ``FakeSwSettings`` + the Real ``SwSettingsStaffClient`` + factory
(``KB § PATTERNS/backend/seed-fake-real-adapter.md``). Never raises: a refusal is a result the apply report carries.

NOC-REMEDIATE[onboarding-sw-staff-channel]: social-wiring's settings routes take an ORG ADMIN session
(``require_org_admin_for``); agents has no platform-staff credential that SW accepts for them. Until SW mints one (a
channel token scope, like ``agents:channel-specs`` in the other direction) the Real client answers
``canal_sw_nao_configurado`` and the report hands the operator the exact route + body to apply in SW. Destination:
the social-wiring slice that adds the staff scope -- then this one class changes, nothing else.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

__all__ = ["CANAL_NAO_CONFIGURADO", "FakeSwSettings", "SwResultado", "SwSettingsPort", "SwSettingsStaffClient", "get_sw_settings"]

CANAL_NAO_CONFIGURADO = "canal_sw_nao_configurado"


@dataclass(frozen=True)
class SwResultado:
    ok: bool
    codigo: str | None = None
    mensagem: str | None = None


class SwSettingsPort(Protocol):
    def aplicar(self, org_id: UUID, setting: str, rota: str | None, corpo: dict[str, Any]) -> SwResultado:
        """Apply ``corpo`` to the SW setting ``setting`` (``rota`` = the route that takes it, when one exists)."""
        ...


@dataclass
class FakeSwSettings:
    """In-memory port: records calls; ``falhar`` maps a setting id to a refusal code."""

    chamadas: list[tuple[UUID, str, dict[str, Any]]] = field(default_factory=list)
    falhar: dict[str, str] = field(default_factory=dict)

    def aplicar(self, org_id: UUID, setting: str, rota: str | None, corpo: dict[str, Any]) -> SwResultado:
        self.chamadas.append((org_id, setting, dict(corpo)))
        if setting in self.falhar:
            return SwResultado(False, self.falhar[setting], "recusado pelo social-wiring")
        return SwResultado(True)


class SwSettingsStaffClient:
    """Real port. See the module NOC-REMEDIATE: no staff channel exists yet, so it refuses, loudly and typed."""

    def aplicar(self, org_id: UUID, setting: str, rota: str | None, corpo: dict[str, Any]) -> SwResultado:
        return SwResultado(
            False, CANAL_NAO_CONFIGURADO,
            "Ainda não há canal da equipe para gravar esta configuração no social-wiring; aplique-a lá com a rota indicada.",
        )


def get_sw_settings() -> SwSettingsPort:
    return SwSettingsStaffClient()
