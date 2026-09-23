"""Lead sources v1 — WhatsApp (WAHA) and Meta Lead Ads put leads on the funnel
(roadmap decision log "Lead sources v1", contract §E2).

Both land the same way: a `lead` (origem `whatsapp` / `meta_ads`) + a `negocio`
in the funnel's entry stage (`comercial_funil.abrir_negocio` — the same service
the "Novo lead" button uses), then the entry-stage automations run exactly as
they do for a hand-made negócio.

DEDUPE IS THE DATABASE'S JOB
----------------------------
`(org_id, waha_chat_id)` and `(org_id, meta_lead_id)` are unique (018). A
second delivery — WAHA's double webhook, Meta's retry — first finds the
existing lead by that key; if two deliveries race past the read, the loser's
insert raises 23505 and is read as "already exists", never as an error and
never as a second lead.

Runs on the igig SERVICE-ROLE client (the callers are vendors with no noc
session); `org_id` comes from the verified webhook and is filtered on every
query.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from noctusai_lib.integrations.whatsapp import WhatsAppInboundMessage, is_phone_jid
from noctusai_lib.primitives.phone import normalize_phone

from app.services import automacoes, comercial_funil
from app.services.automacoes import PortasAutomacao

logger = logging.getLogger(__name__)

__all__ = ["lead_da_meta", "lead_do_whatsapp", "lead_existente", "mapear_lead_meta"]

#: Meta Lead-Ads standard question keys promoted to typed `lead` columns.
_META_NOME = ("full_name",)
_META_PRIMEIRO, _META_ULTIMO = "first_name", "last_name"
_META_EMAIL = ("email", "work_email")
_META_TELEFONE = ("phone_number", "work_phone_number")
_META_EMPRESA = ("company_name",)


def _violacao_unica(exc: Exception) -> bool:
    code = str(getattr(exc, "code", "") or "")
    return code == "23505" or "duplicate key" in str(exc).lower()


def lead_existente(db: Any, org_id: str, coluna: str, valor: str) -> Optional[dict]:
    """The org's lead already carrying this dedupe key, or `None`."""
    return _lead_por(db, org_id, coluna, valor)


def _lead_por(db: Any, org_id: str, coluna: str, valor: str) -> Optional[dict]:
    linhas = (
        db.table("lead").select("*").eq("org_id", org_id).eq(coluna, valor).execute().data or []
    )
    return linhas[0] if linhas else None


async def _criar_lead_e_negocio(
    portas: PortasAutomacao, org_id: str, *, chave: str, valor: str, lead: dict, titulo: Optional[str]
) -> dict:
    """Find-or-create by the dedupe key; a NEW lead gets its negócio + the
    entry-stage automations. Returns `{status, lead_id, negocio_id?}`."""
    existente = _lead_por(portas.db, org_id, chave, valor)
    if existente is not None:
        return {"status": "existente", "lead_id": str(existente["id"])}
    try:
        criado = (
            portas.db.table("lead").insert({"org_id": org_id, chave: valor, **lead}).execute().data
            or []
        )
    except Exception as exc:  # noqa: BLE001 — only a unique violation is a duplicate
        if _violacao_unica(exc):
            corrida = _lead_por(portas.db, org_id, chave, valor)
            logger.info("lead duplicado por corrida org=%s %s=%s", org_id, chave, valor)
            return {"status": "existente", "lead_id": str(corrida["id"]) if corrida else None}
        raise
    if not criado:
        raise RuntimeError("insert de lead não retornou a linha criada")
    novo = criado[0]
    negocio = comercial_funil.abrir_negocio(
        portas.db, org_id, lead_id=str(novo["id"]), titulo=titulo, user_id=None
    )
    await automacoes.ao_entrar_etapa(portas, org_id, pipeline="comercial", card_id=str(negocio["id"]))
    logger.info("lead %s criado org=%s lead=%s negocio=%s", lead.get("origem"), org_id,
                novo["id"], negocio["id"])
    return {"status": "criado", "lead_id": str(novo["id"]), "negocio_id": str(negocio["id"])}


# ── WhatsApp ─────────────────────────────────────────────────────────
async def lead_do_whatsapp(
    portas: PortasAutomacao, org_id: str, mensagem: WhatsAppInboundMessage
) -> dict:
    """The FIRST inbound message of an unknown chat becomes a lead + negócio.

    Group chats are not leads (a group is not a person). A `@lid` chat has no
    phone in its id — the lead is still created (the chat id is the dedupe
    key and the reply address), with `telefone` left empty rather than a
    made-up number.
    """
    if mensagem.group_id:
        return {"status": "ignorado", "motivo": "grupo"}
    telefone = normalize_phone(mensagem.from_phone) if is_phone_jid(mensagem.chat_id) else None
    nome = (mensagem.from_name or "").strip() or telefone or "Contato do WhatsApp"
    return await _criar_lead_e_negocio(
        portas, org_id,
        chave="waha_chat_id", valor=mensagem.chat_id,
        lead={
            "nome": nome[:200],
            "telefone": telefone,
            "origem": "whatsapp",
            "observacoes": f"Primeira mensagem: {mensagem.text}"[:4000] if mensagem.text else None,
        },
        titulo=nome[:200],
    )


# ── Meta Lead Ads ────────────────────────────────────────────────────
def mapear_lead_meta(lead_meta: Any) -> dict:
    """Seed `Lead.field_data` → igig `lead` columns. Answers that are not a
    typed column are kept, lossless, in `especificacoes` (+ a readable copy in
    `observacoes`), never dropped."""
    respostas: dict[str, str] = {}
    for campo in getattr(lead_meta, "field_data", None) or []:
        nome_campo = (getattr(campo, "name", None) or "").strip()
        valores = [str(v) for v in (getattr(campo, "values", None) or []) if str(v).strip()]
        if nome_campo and valores:
            respostas[nome_campo] = ", ".join(valores)

    def primeiro(chaves: tuple[str, ...]) -> Optional[str]:
        return next((respostas[c] for c in chaves if respostas.get(c)), None)

    nome = primeiro(_META_NOME) or " ".join(
        p for p in (respostas.get(_META_PRIMEIRO), respostas.get(_META_ULTIMO)) if p
    ).strip()
    usados = set(_META_NOME + _META_EMAIL + _META_TELEFONE + _META_EMPRESA + (_META_PRIMEIRO, _META_ULTIMO))
    extras = {k: v for k, v in respostas.items() if k not in usados}
    atribuicao = {
        k: getattr(lead_meta, k, None)
        for k in ("form_id", "ad_id", "ad_name", "campaign_id", "campaign_name", "platform")
        if getattr(lead_meta, k, None)
    }
    return {
        "nome": (nome or primeiro(_META_EMAIL) or "Lead do Meta")[:200],
        "email": primeiro(_META_EMAIL),
        "telefone": normalize_phone(primeiro(_META_TELEFONE)) or primeiro(_META_TELEFONE),
        "empresa": primeiro(_META_EMPRESA),
        "origem": "meta_ads",
        "especificacoes": {"respostas": extras, "meta": atribuicao},
        "observacoes": "\n".join(f"{k}: {v}" for k, v in extras.items()) or None,
    }


async def lead_da_meta(portas: PortasAutomacao, org_id: str, leadgen_id: str, lead_meta: Any) -> dict:
    valores = mapear_lead_meta(lead_meta)
    return await _criar_lead_e_negocio(
        portas, org_id,
        chave="meta_lead_id", valor=leadgen_id,
        lead=valores,
        titulo=valores.get("empresa") or valores["nome"],
    )
