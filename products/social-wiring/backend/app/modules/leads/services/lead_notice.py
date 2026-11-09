"""OPERATIONAL in-app notices for leads (KB § PATTERNS/backend/notifications.md).

`avisar_lead_novo` is called from `leads_service.create_lead` — the ONE seam
every single-lead path stacks on (manual/API, Meta webhook + sync, OLX,
Imovelweb), so a path can never notify twice or forget to. The bulk workbook
importer inserts rows itself and emits ONE summary (`avisar_importacao`).

Both NEVER raise (the lead is already saved): failures log and continue.
Recipients = org owners + admins (seed helper, owner decision 2026-11-04).

NOC-REMEDIATE[lead-novo-whatsapp-intake]: a lead created by WhatsApp inbox
intake (whatsapp_intake_service / message_store, owned by the Julia/WhatsApp
workstream) does not go through `create_lead`; once that module settles, call
`avisar_lead_novo(client, row)` right after its lead insert — 2026-11-04.
"""
from __future__ import annotations

import logging
from typing import Any

from noctusai_lib.domain.notifications import notify_org_admins

logger = logging.getLogger(__name__)

PRODUTO = "social-wiring"
LINK_LEADS = "/leads"


def _core():
    from app.database import get_core_client  # lazy: keeps this module import-cycle free

    return get_core_client()


JULIA_SLUG = "julia"  # = julia_envio_service.ORIGEM_SLUG (not imported: julia_* is owned elsewhere)


def _origem(client: Any, lead: dict) -> dict:
    """`{slug, label}` of the lead's source (best effort; cosmetic except the Julia skip)."""
    sid = lead.get("origem_id")
    if not sid:
        return {}
    try:
        rows = client.table("lead_sources").select("slug,label").eq("id", str(sid)).limit(1).execute().data or []
    except Exception:  # noqa: BLE001
        logger.warning("lead_notice: could not resolve origem for %s", sid, exc_info=True)
        return {}
    return rows[0] if rows else {}


def _origem_label(origem: dict, lead: dict) -> str | None:
    return str(lead["origem_raw"]) if lead.get("origem_raw") else origem.get("label")


def avisar_lead_novo(client: Any, lead: dict) -> int:
    """`lead_novo` to the org's owners + admins. Returns rows written (0 on any problem).

    Skips a lead whose source is Julia's (slug `julia`, created by `julia_envio_service`):
    Julia's own hand-off already notifies with richer routing (responsible/attendant, then
    admins), so a `lead_novo` would double-notify the admins."""
    try:
        origem = _origem(client, lead)
        if origem.get("slug") == JULIA_SLUG:
            return 0
        nome = (lead.get("cliente_nome") or "").strip() or "sem nome"
        partes = [p for p in (_origem_label(origem, lead),
                              f"Interesse: {lead['codigo_imovel']}" if lead.get("codigo_imovel") else None) if p]
        return notify_org_admins(
            _core(), org_id=lead["org_id"], kind="lead_novo",
            title=f"Novo lead: {nome}", message=" · ".join(partes) or "Novo lead recebido",
            produto=PRODUTO, link=LINK_LEADS, entidade={"tipo": "lead", "id": str(lead.get("id"))},
        )
    except Exception:  # noqa: BLE001 — never fail lead creation
        logger.exception("lead_notice: lead_novo failed for lead %s", lead.get("id"))
        return 0


def avisar_importacao(org_id: Any, inseridos: int) -> int:
    """ONE summary notice for a bulk import ("N leads importados"); silent when N == 0."""
    if inseridos <= 0:
        return 0
    try:
        return notify_org_admins(
            _core(), org_id=org_id, kind="leads_importados",
            title=f"{inseridos} leads importados", message="Importação de planilha concluída",
            produto=PRODUTO, link=LINK_LEADS, entidade=None,
        )
    except Exception:  # noqa: BLE001
        logger.exception("lead_notice: leads_importados failed for org %s", org_id)
        return 0


def avisar_corretor_divergente(
    org_id: Any, *, lead_id: Any, codigo: str, tipo: str, lead_corretor: str | None, imovel_corretores: list[str],
    principal: str | None = None,
) -> int:
    """ONE in-app warning to the org's owners + admins per corretor-divergence TIPO (ad-lead intake, CONTRACT ad-lead-intake § 2.3):
    `fora_dos_corretores` | `nao_e_principal` | `lead_sem_corretor`, each its own `kind` (`lead_corretor_<tipo>`). The durable record is
    `lead_corretor_divergencias`; this is only the "check it" nudge. Never raises; returns rows written (0 on any problem)."""
    try:
        quem = lead_corretor or "sem nome"
        no_imovel = ", ".join(imovel_corretores) or "sem corretor"
        if tipo == "lead_sem_corretor":
            titulo, msg = f"Lead sem corretor ({codigo})", f"O lead do imóvel {codigo} não tem corretor. O imóvel está com {no_imovel}. Confira."
        elif tipo == "nao_e_principal":
            titulo, msg = f"Corretor não é o principal ({codigo})", f"Lead com {quem}; o corretor principal do imóvel é {principal or 'não informado'}. Confira."
        else:
            titulo, msg = f"Corretor diverge no imóvel {codigo}", f"Lead com {quem}; o imóvel está com {no_imovel}. Confira."
        return notify_org_admins(
            _core(), org_id=org_id, kind=f"lead_corretor_{tipo}", title=titulo, message=msg,
            produto=PRODUTO, link=LINK_LEADS, entidade={"tipo": "lead", "id": str(lead_id)},
        )
    except Exception:  # noqa: BLE001
        logger.exception("lead_notice: lead_corretor_%s failed for lead %s", tipo, lead_id)
        return 0
