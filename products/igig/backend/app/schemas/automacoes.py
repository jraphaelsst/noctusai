"""Wire contracts for Automações v1, the lead-source setup and the assistant
(contract `cardhub-igig-crm-2026-09.wave-2-contract.md` §E2).

`stage_id` on the wire ↔ `etapa_id` in the table (018) — the contract's name.
`acao.params` is validated PER TIPO at the boundary (`StrictHttpModel`, extra
fields refused), so a rule that could never run is a 422 at save time, not an
`erro` row at 3 a.m.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from noctusai_lib.api.schemas import StrictHttpModel

__all__ = [
    "AcaoIn",
    "AssistenteIn",
    "AutomacaoCreate",
    "AutomacaoUpdate",
    "LeadsMetaIn",
    "LeadsWhatsappIn",
    "PARAMS_POR_TIPO",
    "TipoAcao",
    "automacao_out",
]

TipoAcao = Literal[
    "criar_checklist", "definir_responsavel", "criar_tarefa",
    "notificar", "enviar_email", "enviar_whatsapp",
]


class _ChecklistParams(StrictHttpModel):
    titulo: str = Field(min_length=1, max_length=200)
    itens: list[str] = Field(default_factory=list, max_length=50)


class _ResponsavelParams(StrictHttpModel):
    profissional_id: str = Field(min_length=1)


class _TarefaParams(StrictHttpModel):
    titulo: str = Field(min_length=1, max_length=200)
    prazo_dias: int | None = Field(default=None, ge=0, le=365)
    responsavel_id: str | None = None


class _NotificarParams(StrictHttpModel):
    titulo: str | None = Field(default=None, max_length=200)
    mensagem: str | None = Field(default=None, max_length=2000)
    usuario_ids: list[str] = Field(default_factory=list, max_length=50)


class _EmailParams(StrictHttpModel):
    assunto: str = Field(min_length=1, max_length=300)
    mensagem: str = Field(min_length=1, max_length=20000)
    para: str | None = Field(default=None, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class _WhatsappParams(StrictHttpModel):
    mensagem: str = Field(min_length=1, max_length=4000)
    para: str | None = Field(default=None, max_length=40)


PARAMS_POR_TIPO: dict[str, type[StrictHttpModel]] = {
    "criar_checklist": _ChecklistParams,
    "definir_responsavel": _ResponsavelParams,
    "criar_tarefa": _TarefaParams,
    "notificar": _NotificarParams,
    "enviar_email": _EmailParams,
    "enviar_whatsapp": _WhatsappParams,
}


class AcaoIn(StrictHttpModel):
    tipo: TipoAcao
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _params_do_tipo(self) -> "AcaoIn":
        # Normalised through the tipo's own model: unknown keys refused,
        # defaults filled, so the stored JSON is exactly what the engine reads.
        self.params = PARAMS_POR_TIPO[self.tipo].model_validate(self.params).model_dump()
        return self


class AutomacaoCreate(StrictHttpModel):
    pipeline: Literal["comercial", "esteira"]
    stage_id: str = Field(min_length=1)
    gatilho: Literal["entrada_etapa", "sla"]
    sla_horas: int | None = Field(default=None, gt=0, le=24 * 365)
    acao: AcaoIn
    ativo: bool = True

    @model_validator(mode="after")
    def _regras(self) -> "AutomacaoCreate":
        if self.gatilho == "sla" and self.sla_horas is None:
            raise ValueError("Uma automação de SLA precisa de `sla_horas`.")
        if self.gatilho == "entrada_etapa":
            self.sla_horas = None
        return self


class AutomacaoUpdate(StrictHttpModel):
    """Partial. `pipeline` is fixed at creation — a rule moved to the other
    board would point at a stage of the wrong pipeline."""

    stage_id: str | None = Field(default=None, min_length=1)
    gatilho: Literal["entrada_etapa", "sla"] | None = None
    sla_horas: int | None = Field(default=None, gt=0, le=24 * 365)
    acao: AcaoIn | None = None
    ativo: bool | None = None


def automacao_out(row: dict) -> dict:
    """Table row → wire shape (`etapa_id` → `stage_id`)."""
    acao = row.get("acao") or {}
    return {
        "id": row["id"],
        "pipeline": row.get("pipeline"),
        "stage_id": row.get("etapa_id"),
        "gatilho": row.get("gatilho"),
        "sla_horas": row.get("sla_horas"),
        "acao": {"tipo": acao.get("tipo"), "params": acao.get("params") or {}},
        "ativo": bool(row.get("ativo")),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


# ── lead sources ────────────────────────────────────────────────────
class LeadsWhatsappIn(StrictHttpModel):
    """WAHA connection, configured like social-wiring's (base url + api key +
    session). `api_key` omitted ⇒ keep the stored one."""

    base_url: str = Field(min_length=1, max_length=500, pattern=r"^https?://")
    api_key: str | None = Field(default=None, min_length=1, max_length=500)
    session: str = Field(default="default", min_length=1, max_length=100)


class LeadsMetaIn(StrictHttpModel):
    """Meta Lead Ads. Secrets omitted ⇒ keep the stored ones. `app_secret` is
    optional: without it the platform's `IGIG_META_APP_SECRET` verifies the
    delivery signatures (reported as `app_secret_origem`)."""

    page_id: str = Field(min_length=1, max_length=64, pattern=r"^\d+$")
    verify_token: str | None = Field(default=None, min_length=8, max_length=200)
    page_access_token: str | None = Field(default=None, min_length=1, max_length=2000)
    app_secret: str | None = Field(default=None, min_length=1, max_length=200)


# ── assistant ───────────────────────────────────────────────────────
class AssistenteIn(StrictHttpModel):
    acao: Literal["resumo", "proxima_acao", "rascunho_mensagem"]
    canal: Literal["email", "whatsapp"] | None = None
