"""NoctusAI's own sales funnel (`/api/admin/funnel`) -- core's consumer of the seed funnel organ.

ONE seed organ (`noctusai_lib.domain.pipeline.funnel`), consumed here with core's declared
card table (`website_leads`), stages, lost reasons, gates and the `ganhar` action. Nothing in
this file re-implements board, move, loss or history logic.

CARDS ARE THE LEADS THEMSELVES (not a projection): `website_leads` IS the funnel's card table,
so every lead is a card by construction and there is no sync to drift. A lead inserted by ANY
writer (the public form's `create_or_merge_lead`, a future WhatsApp intake, the admin's
"novo contato") lands in the first active stage through the BEFORE INSERT trigger in
migration 107, plus its `entrada` movimento -- `website_public.py` is untouched.

TIER: platform data (PII + commercial pipeline). The router is `platform` (`get_current_admin`:
401 unauthenticated, 403 non-admin); every table is service-role only (migration 107).

TENANCY: the funnel's own rows (stages, movimentos) carry ONE declared scope id,
`NOC_FUNNEL_ORG_ID`. It is a stable scope key (uuid5 of "funil.noctusai.com"), not a join to
`organizations`: nothing references it, and a request never resolves "all tenants".

CARD HUB (notes/tags/checklists/documents): not wired yet.
NOC-REMEDIATE[core-funnel-card-hub]: set `FunnelConfig.card_hub` (+ `card_hub_migration`, a
storage bucket and the `geral` spine renderer) once the seed's `funnel-geral-spine` adapter ships
-- 2026-11-07.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI

from noctusai_lib.api.audit.sink import log_overflow_or_failure
from noctusai_lib.domain.pipeline import PipelineConfig, PipelineContext, pipeline_migration
from noctusai_lib.domain.pipeline.funnel import (
    FunnelAction,
    FunnelConfig,
    FunnelContext,
    FunnelGate,
    LostReason,
    Pendencia,
    mount_funnel,
)
from noctusai_lib.integrations.persistence.table_reads import actor_resolver
from noctusai_lib.primitives.responses import success_response

from app import database
from app.database import _db
from app.dependencies import get_current_admin

logger = logging.getLogger(__name__)

PREFIX = "/api/admin/funnel"
#: uuid5(NAMESPACE_DNS, "funil.noctusai.com") -- pinned by tests against migration 107.
NOC_FUNNEL_ORG_ID = "68230bf3-1323-5ad3-96ad-a87b8c1c844d"
PIPELINE_KEY = "funil_noc"

#: The roles a stage may carry (gates key on them, so renaming/reordering a column cannot dodge a rule).
STAGE_ROLES = ("novo", "contatado", "qualificado", "proposta")

PIPELINE = PipelineConfig(
    pipeline=PIPELINE_KEY,
    card_table="website_leads",
    value_field="valor_unico",
    entity_label="contato",
    entity_kind="website_lead",
    cliente_field=None,
    stage_roles=STAGE_ROLES,
    status_field="status",
    count_excludes=("ganho", "perdido", "arquivado"),
)

LOST_REASONS = (
    LostReason("preco", "Achou caro"),
    LostReason("sem_orcamento", "Sem orçamento agora"),
    LostReason("outra_solucao", "Escolheu outra solução"),
    LostReason("sem_resposta", "Parou de responder"),
    LostReason("fora_do_perfil", "Não é o nosso cliente (fora do perfil)"),
    LostReason("produto_indisponivel", "O produto ainda não está disponível"),
    LostReason("outro", "Outro motivo", exige_texto=True),
)

_ORIGENS = {
    "waitlist": "Lista de espera",
    "brief": "Briefing",
    "contact": "Contato",
    "signup_intent": "Intenção de cadastro",
}
_OFERTA_TIPOS = {"plano": "Plano do catálogo", "projeto": "Projeto sob medida", "avulso": "Serviço avulso"}


# -- gates ---------------------------------------------------------------


def _gate_contatado(db: Any, ctx: FunnelContext, card: dict) -> list[Pendencia]:
    if card.get("email") or card.get("phone_e164"):
        return []
    return [Pendencia("sem_contato", "Informe um WhatsApp ou e-mail antes de marcar como contatado.")]


def _gate_qualificado(db: Any, ctx: FunnelContext, card: dict) -> list[Pendencia]:
    if card.get("owner_user_id"):
        return []
    return [Pendencia("sem_responsavel", "Defina um responsável antes de qualificar.")]


def _gate_proposta(db: Any, ctx: FunnelContext, card: dict) -> list[Pendencia]:
    has_value = any(float(card.get(k) or 0) > 0 for k in ("valor_unico", "valor_mensal"))
    if card.get("oferta_tipo") and has_value:
        return []
    return [Pendencia("sem_oferta", "Registre a oferta (tipo e valor) antes da proposta.")]


GATES = {
    "contatado": FunnelGate("entrar_contatado", _gate_contatado, mensagem="Precisa de um WhatsApp ou e-mail."),
    "qualificado": FunnelGate("entrar_qualificado", _gate_qualificado, mensagem="Precisa de um responsável."),
    "proposta": FunnelGate("entrar_proposta", _gate_proposta, mensagem="Precisa de uma oferta com valor."),
}


# -- ganho ----------------------------------------------------------------


def _on_ganho(db: Any, ctx: FunnelContext, card: dict) -> dict:
    """Effects of winning a card: plan -> Stripe subscription link, project -> receivables.

    NOC-REMEDIATE[core-funnel-ganho-bridge]: send the Stripe link (oferta_tipo='plano') / create the
    receivables in the finance organ (oferta_tipo='projeto'); the dates and taxes of the installments
    wait on the accountant -- 2026-11-07. Until then a win only changes the status, and says so.
    """
    return {"ponte_financeira": "nao_implementada"}


def _ganhar(db: Any, ctx: FunnelContext, card: dict, payload: dict) -> dict:
    db.table("website_leads").update({"status": "ganho"}).eq("id", card["id"]).execute()
    db.table(PIPELINE.history_table).insert(
        {
            "org_id": ctx.org_id,
            "pipeline": PIPELINE_KEY,
            "entidade_id": str(card["id"]),
            "de_etapa_id": card.get("etapa_id"),
            "para_etapa_id": card.get("etapa_id"),
            "kind": "ganho",
            "responsavel_id": str(ctx.user_id) if ctx.user_id else None,
            "motivo": "Ganho",
        }
    ).execute()
    return _on_ganho(db, ctx, card)


ACTIONS = {"ganhar": FunnelAction("ganhar", "Marcar como ganho", _ganhar)}


# -- card DTO ---------------------------------------------------------------


def _projection(row: dict) -> dict:
    """Pure over the row. The Contato tab reads these read-only `campos` (never editable)."""
    produtos = list(row.get("product_interest") or [])
    badges = [{"label": _ORIGENS.get(row.get("source"), str(row.get("source") or "")), "variant": "secondary"}]
    badges += [{"label": p, "variant": "outline"} for p in produtos[:2]]
    consent = row.get("consent") or {}
    return {
        "subtitulo": row.get("company") or None,
        "badges": badges,
        "campos": {
            "origem": _ORIGENS.get(row.get("source"), row.get("source")),
            "produtos": ", ".join(produtos) if produtos else None,
            "mensagem": row.get("message"),
            "consentimento_marketing": "Sim" if consent.get("marketing") else "Não",
            "oferta_tipo_label": _OFERTA_TIPOS.get(row.get("oferta_tipo")),
        },
    }


def _prepare_create(db: Any, ctx: FunnelContext, row: dict) -> dict:
    """A card typed in by the operator ("novo contato"): fills the NOT NULL intake columns."""
    return {
        **row,
        "source": "contact",
        "consent": {
            "marketing": False,
            "text_version": "manual",
            "at": datetime.now(timezone.utc).isoformat(),
            "ip_hash": "manual",
        },
        "dedupe_key": f"manual:{uuid.uuid4()}",
    }


# NOC-REMEDIATE[funnel-campo-validators]: `email`/`whatsapp` are written as typed (no per-field
# validator seam in FunnelConfig.editable_fields yet) -- add the seam in the seed, then normalise
# the phone to E.164 here -- 2026-11-07.
EDITABLE_FIELDS = {
    "empresa": "company",
    "email": "email",
    "whatsapp": "phone_e164",
    "proxima_acao": "next_action",
    "proxima_acao_em": "next_action_at",
    "oferta_tipo": "oferta_tipo",
    "oferta_descricao": "oferta_descricao",
    "valor_unico": "valor_unico",
    "valor_mensal": "valor_mensal",
}


def build_config() -> FunnelConfig:
    return FunnelConfig(
        pipeline=PIPELINE,
        tenancy="platform",
        platform_org_id=NOC_FUNNEL_ORG_ID,
        card_projection=_projection,
        editable_fields=EDITABLE_FIELDS,
        lost_reasons=LOST_REASONS,
        gates=GATES,
        actions=ACTIONS,
        status_field="status",
        title_field="name",
        responsavel_field="owner_user_id",
        actor_resolver=actor_resolver(lambda: _db.get_core_client()),
        prepare_create=_prepare_create,
        # The AFTER INSERT trigger on website_leads (migration 107) owns the `entrada` row, so the
        # public lead form and an admin-typed card each get exactly one; the history is append-only.
        record_entry_on_create=False,
    )


FUNNEL = build_config()


def render_migration() -> str:
    """The pipeline DDL core's migration 107 embeds verbatim (never hand-written)."""
    return pipeline_migration(PIPELINE, "public", tier="platform")


# -- wiring -----------------------------------------------------------------


def _resolve_context(auth: Any) -> PipelineContext:
    user, _token = auth
    return PipelineContext(db=database.get_admin_client(), org_id=None, user_id=getattr(user, "id", None))


def _log_action(user_id: Any, action: str, entity_kind: str, entity_id: str, text: str, meta: dict | None = None) -> None:
    """Platform audit trail (`audit_logs`, ids/enums only -- the organ's free text is not stored)."""
    row = {
        "user_id": str(user_id) if user_id else None,
        "org_id": None,
        "action": action,
        "resource_type": entity_kind,
        "resource_id": entity_id,
        "details": dict(meta or {}),
        "product_slug": "core",
    }
    try:
        database.get_admin_client().table("audit_logs").insert(row).execute()
    except Exception as exc:
        log_overflow_or_failure(kind="noc_funnel_audit_write_failed", entry=row, exc=exc)


def mount_noc_funnel(app: FastAPI) -> None:
    mount_funnel(
        app,
        FUNNEL,
        prefix=PREFIX,
        auth_dependency=get_current_admin,
        resolve_context=_resolve_context,
        success_response=success_response,
        log_action=_log_action,
    )
