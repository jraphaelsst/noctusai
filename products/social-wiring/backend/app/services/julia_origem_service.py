"""Where did this Julia contact come from? ONE resolver, written once when the contato is created.

`julia_contatos` carries `origem_slug` (a `lead_sources.slug`), `campanha_origem`, `anuncio_origem`,
`codigo_imovel_campanha` and `lead_id`; the leads filters, the CSV export and the agents contexto
(`estado.origem.canal_origem`) read them. Precedence (first hit wins, nothing is invented):

  a. an explicit Meta lead-form row (the first-contact path) -> its CRM lead's source slug, its own campaign/ad;
  b. a click-to-WhatsApp ad referral on the inbound message  -> slug `meta-ctwa`, the ad id, the campaign when
     the ad is registered (`campanha_veiculacoes`) or already seen on a lead form;
  c. a CRM lead with this phone (same org, most recent)       -> its source (+ its Meta campaign/ad when it has them);
  d. otherwise                                                -> `whatsapp` (the person wrote to us directly).

The source slug always comes from the CRM lead's own `lead_sources` row, so a new lead pipe (ImovelWeb, OLX, ...)
needs no change here. A column no source records stays NULL.

Nothing in here may log a phone, a name or a message: ids and slugs only.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from app.modules.leads.services import dimensions_service
from app.modules.leads.services.meta_ingest_service import META_LEAD_ADS_SLUG
from app.modules.meta_ads.services.campanha_resolucao import resolver_campanha

logger = logging.getLogger(__name__)

SLUG_DIRETO = "whatsapp"
SLUG_CTWA = "meta-ctwa"

_CAMPOS = ("origem_slug", "campanha_origem", "anuncio_origem", "codigo_imovel_campanha", "lead_id")
_MAX = 200


def _txt(value: Any, limit: int = _MAX) -> Optional[str]:
    if value is None or isinstance(value, (dict, list, bool)):
        return None
    s = str(value).strip()
    return s[:limit] or None


def _origem(slug: str, *, campanha: Any = None, anuncio: Any = None, codigo: Any = None, lead_id: Any = None) -> dict[str, Any]:
    return {
        "origem_slug": slug, "campanha_origem": _txt(campanha), "anuncio_origem": _txt(anuncio),
        "codigo_imovel_campanha": _txt(codigo, 40), "lead_id": str(lead_id) if lead_id else None,
    }


# ── (b) the click-to-WhatsApp referral ──────────────────────────────────────
def _ad_reply_de_mensagem(message: Any) -> Optional[dict[str, Any]]:
    """`externalAdReply` of a Baileys/NOWEB `message` object: it lives in the `contextInfo` of whichever message type
    carries it (extendedTextMessage, imageMessage, videoMessage, ...)."""
    if not isinstance(message, dict):
        return None
    for conteudo in message.values():
        ctx = conteudo.get("contextInfo") if isinstance(conteudo, dict) else None
        reply = ctx.get("externalAdReply") if isinstance(ctx, dict) else None
        if isinstance(reply, dict):
            return reply
    return None


def extrair_referral_ctwa(body: Any) -> Optional[dict[str, Any]]:
    """The ad a WAHA message webhook says the lead clicked, or None. Defensive by contract: any absent or odd shape
    is "no referral", never an exception. Understands the NOWEB raw shape (`payload._data.message.*.contextInfo.
    externalAdReply`) and the Cloud-API-style normalized `payload.referral`. Only an AD counts (`sourceType == "ad"` or a
    `ctwaClid`): link previews also use `externalAdReply` and are not an origin.

    Returns `{source_id, source_type, source_url, title}` (ids/urls/ad title only, no PII)."""
    try:
        payload = body.get("payload") if isinstance(body, dict) else None
        if not isinstance(payload, dict):
            return None
        data = payload.get("_data")
        reply = _ad_reply_de_mensagem(data.get("message")) if isinstance(data, dict) else None
        if reply is not None:
            bruto = {"source_id": reply.get("sourceId"), "source_type": reply.get("sourceType"),
                     "source_url": reply.get("sourceUrl"), "title": reply.get("title"), "clid": reply.get("ctwaClid")}
        else:
            ref = payload.get("referral")
            if not isinstance(ref, dict):
                return None
            bruto = {"source_id": ref.get("source_id") or ref.get("sourceId"),
                     "source_type": ref.get("source_type") or ref.get("sourceType"),
                     "source_url": ref.get("source_url") or ref.get("sourceUrl"),
                     "title": ref.get("headline") or ref.get("title"),
                     "clid": ref.get("ctwa_clid") or ref.get("ctwaClid")}
        tipo = (_txt(bruto["source_type"]) or "").lower()
        if tipo != "ad" and not _txt(bruto["clid"]):
            return None
        source_id = _txt(bruto["source_id"], 64)
        if not source_id:
            return None
        return {"source_id": source_id, "source_type": tipo or "ad", "source_url": _txt(bruto["source_url"]),
                "title": _txt(bruto["title"], 120)}
    except Exception as exc:  # a malformed webhook must never break message intake
        logger.debug("julia: ctwa referral not parsed (%s)", type(exc).__name__)
        return None


def referral_do_lote(run: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The first ad referral among the buffered inbounds of a batch (the click arrives on the lead's first message)."""
    for item in run:
        referral = (item.get("metadata") or {}).get("referral")
        if isinstance(referral, dict) and referral.get("source_id"):
            return referral
    return None


def _origem_do_referral(client: Any, org_id: UUID | str, referral: dict[str, Any]) -> dict[str, Any]:
    ad_id = referral["source_id"]
    campanha = codigo = None
    try:
        registrada = resolver_campanha(client, UUID(str(org_id)), {"ad_id": ad_id})
        if registrada:
            campanha = registrada.get("nome")
            if len(registrada.get("codigos") or []) == 1:  # a campaign that advertises several listings names none
                codigo = registrada["codigos"][0]
        if not campanha:
            vista = (
                client.table("meta_ads_leads").select("campaign_name,campaign_id")
                .eq("org_id", str(org_id)).eq("ad_id", ad_id).limit(1).execute().data or []
            )
            if vista:
                campanha = vista[0].get("campaign_name") or vista[0].get("campaign_id")
    except Exception as exc:
        logger.warning("julia: ctwa campaign lookup failed org=%s (%s)", org_id, type(exc).__name__)
    _garantir_fonte(client, org_id, SLUG_CTWA)
    return _origem(SLUG_CTWA, campanha=campanha, anuncio=ad_id, codigo=codigo)


# ── CRM-lead based origins (a, c) ───────────────────────────────────────────
def _garantir_fonte(client: Any, org_id: UUID | str, slug: str) -> None:
    """The slug exists as a `lead_sources` row (so reports and the CRM can group by it). Best-effort: the contato keeps
    its slug even when the catalog write fails."""
    try:
        dimensions_service.get_or_create_canonical_source(client, UUID(str(org_id)), slug)
    except Exception as exc:
        logger.warning("julia: could not ensure lead_source %s org=%s (%s)", slug, org_id, type(exc).__name__)


def _slug_da_fonte(client: Any, org_id: UUID | str, origem_id: Any) -> Optional[str]:
    if not origem_id:
        return None
    rows = (
        client.table("lead_sources").select("slug").eq("org_id", str(org_id)).eq("id", str(origem_id))
        .limit(1).execute().data or []
    )
    return rows[0].get("slug") if rows else None


def _origem_de_lead_crm(client: Any, org_id: UUID | str, lead: dict[str, Any]) -> Optional[dict[str, Any]]:
    slug = _slug_da_fonte(client, org_id, lead.get("origem_id"))
    if not slug:
        return None
    campanha = anuncio = None
    if lead.get("meta_lead_id"):  # only a Meta lead has campaign/ad data; portals store none
        rows = (
            client.table("meta_ads_leads").select("campaign_name,campaign_id,ad_id")
            .eq("org_id", str(org_id)).eq("id", str(lead["meta_lead_id"])).limit(1).execute().data or []
        )
        if rows:
            campanha = rows[0].get("campaign_name") or rows[0].get("campaign_id")
            anuncio = rows[0].get("ad_id")
    return _origem(slug, campanha=campanha, anuncio=anuncio, lead_id=lead.get("id"))


def _lead_por(client: Any, org_id: UUID | str, coluna: str, valor: str) -> Optional[dict[str, Any]]:
    rows = (
        client.table("leads").select("id,origem_id,meta_lead_id")
        .eq("org_id", str(org_id)).eq(coluna, valor)
        .order("data_entrada", desc=True).limit(1).execute().data or []
    )
    return rows[0] if rows else None


def _origem_de_meta_lead(client: Any, org_id: UUID | str, meta_lead: dict[str, Any]) -> dict[str, Any]:
    """(a) The Meta lead-form row Julia was handed: its campaign/ad are on the row; the source slug is the one of the
    CRM lead the ingest created from it (same `lead_sources` row the CRM shows), else the ingest's own slug."""
    crm = _lead_por(client, org_id, "meta_lead_id", str(meta_lead.get("id"))) if meta_lead.get("id") else None
    slug = _slug_da_fonte(client, org_id, (crm or {}).get("origem_id")) or META_LEAD_ADS_SLUG
    return _origem(
        slug, campanha=meta_lead.get("campaign_name") or meta_lead.get("campaign_id"),
        anuncio=meta_lead.get("ad_id"), lead_id=(crm or {}).get("id"),
    )


def resolver_origem(
    client: Any, org_id: UUID | str, *, meta_lead: Optional[dict[str, Any]] = None,
    referral: Optional[dict[str, Any]] = None, telefone: Optional[str] = None,
) -> dict[str, Any]:
    """`{origem_slug, campanha_origem, anuncio_origem, codigo_imovel_campanha, lead_id}` for a NEW contato (precedence
    in the module docstring). Never raises: a lookup that fails degrades to the next rule."""
    passos = []
    if meta_lead:
        passos.append(lambda: _origem_de_meta_lead(client, org_id, meta_lead))
    if referral and referral.get("source_id"):
        passos.append(lambda: _origem_do_referral(client, org_id, referral))
    if telefone:
        def por_telefone() -> Optional[dict[str, Any]]:
            lead = _lead_por(client, org_id, "contato_norm", telefone)
            return _origem_de_lead_crm(client, org_id, lead) if lead else None
        passos.append(por_telefone)
    for passo in passos:
        try:
            achado = passo()
        except Exception as exc:
            logger.warning("julia: origin lookup failed org=%s (%s)", org_id, type(exc).__name__)
            continue
        if achado:
            return achado
    return _origem(SLUG_DIRETO)


__all__ = ["SLUG_CTWA", "SLUG_DIRETO", "extrair_referral_ctwa", "referral_do_lote", "resolver_origem"]
