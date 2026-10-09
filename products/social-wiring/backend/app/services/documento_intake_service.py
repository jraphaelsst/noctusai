"""Inbound WhatsApp media -> `cliente_documentos` (CONTRACT §2.3).

    download -> store like a card upload (HEIC -> JPEG happens THERE) -> classify ->
    insert (`origem_entrada='whatsapp'`) -> extract through the registry.

CLASSIFIER. `identidade_extracao_service.classificar_tipo_provavel` works on the
TEXT of a document; the generic identity extractor produces that text and runs
it (`IdentityFields.tipo_provavel`). So classification = one type-agnostic read
of the file. A recognised, extractable type with a clean read => `alta`
confidence => the document is typed and extracted. Anything else =>
`a_classificar`: the document waits in the card's triage list for the operator,
who picks the type (`reclassificar`), and extraction then runs.
COST NOTE: a confidently classified document is read twice (classify + extract);
a dedicated classifier / the next-phase parsers remove the duplicate.

MEDIA IS NEVER DROPPED SILENTLY. Whatever cannot become a document (a type the
store refuses, an unconvertible HEIC, a failed download) is recorded on the
message's `anexo` with a `motivo` and logged -- the bubble tells the operator.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import ValidationError_

from app.modules.card_hub import conversa_service
from app.modules.card_hub import documentos_service as docs_svc
from app.modules.card_hub.extracao import registry
from app.services import documento_retencao

logger = logging.getLogger(__name__)

TIPO_A_CLASSIFICAR = "a_classificar"
ORIGEM_WHATSAPP = "whatsapp"

Downloader = Callable[[str], Awaitable[bytes]]


# ─── Classification ──────────────────────────────────────────────────────


async def classificar(
    conteudo: bytes, mime: str, nome: str, extractor: Any
) -> tuple[Optional[str], str, Optional[str]]:
    """`(tipo|None, confianca, tipo_provavel_bruto)`.

    `alta`: the content classifier named an extractable type on a clean read.
    `baixa`: the read failed. `nenhuma`: read fine, no marker recognised.
    """
    try:
        fields = await extractor.extract(
            conteudo, mimetype=mime, filename=nome, titular=None, tipo_documento=None
        )
    except Exception:  # noqa: BLE001 - an extractor must not raise, but never lose the file
        logger.warning("intake: classification read raised", exc_info=True)
        return None, "baixa", None
    provavel = getattr(fields, "tipo_provavel", None)
    if getattr(fields, "error", None):
        return None, "baixa", provavel
    if provavel and registry.deve_extrair(provavel):
        return provavel, "alta", provavel
    return None, "nenhuma", provavel


# ─── Typing a stored document ────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def tipar_documento(
    client: Any, org_id: UUID, cliente_id: UUID, documento_id: UUID, tipo: str
) -> dict:
    """Give a stored document its real type: LGPD category, retention and a
    queued extraction follow the type. Used by the intake (confident class) and
    by the operator's triage. Refuses a type that is not enabled/extractable."""
    tipos = (
        client.table("cliente_documento_tipos").select("*").eq("tipo_documento", tipo).execute()
    ).data or []
    if not tipos or not tipos[0].get("ativo") or tipo == TIPO_A_CLASSIFICAR:
        raise ValidationError_(
            f"tipo_documento {tipo!r} não está habilitado", field="tipo_documento"
        )
    if not registry.deve_extrair(tipo):
        raise ValidationError_(
            f"tipo_documento {tipo!r} não tem leitura definida", field="tipo_documento"
        )
    dias = documento_retencao.dias_para(client, org_id, "cliente", tipo)
    retencao_ate = None
    if dias:
        from datetime import date, timedelta  # noqa: PLC0415

        retencao_ate = (date.today() + timedelta(days=dias)).isoformat()
    patch = {
        "tipo_documento": tipo,
        "categoria_lgpd": tipos[0]["categoria_lgpd"],
        "retencao_ate": retencao_ate,
        "extracao_status": "pendente",
        "extracao_erro": None,
        "extracao_em": _now(),
    }
    client.table("cliente_documentos").update(patch).eq("org_id", str(org_id)).eq(
        "cliente_id", str(cliente_id)
    ).eq("id", str(documento_id)).execute()
    return patch


def a_classificar(client: Any, org_id: UUID, cliente_id: UUID) -> list[dict]:
    """The card's triage list: live documents still waiting for a type."""
    rows = (
        client.table("cliente_documentos")
        .select("id,nome_original,mime_type,tamanho_bytes,created_at,origem_entrada,"
                "classificacao_tipo_provavel,classificacao_confianca")
        .eq("org_id", str(org_id)).eq("cliente_id", str(cliente_id))
        .eq("tipo_documento", TIPO_A_CLASSIFICAR).is_("deleted_at", "null")
        .order("created_at", desc=True).execute()
    ).data or []
    return rows


def classificar_manualmente(
    client: Any, org_id: UUID, cliente_id: UUID, documento_id: UUID, tipo: str
) -> dict:
    """Operator picks the type of a triage document. Returns the document row
    summary; the caller schedules the extraction (`registry.extrair`)."""
    docs_svc._require_documento(client, org_id, cliente_id, documento_id)  # noqa: SLF001
    atual = (
        client.table("cliente_documentos").select("tipo_documento")
        .eq("id", str(documento_id)).execute()
    ).data or []
    if not atual or atual[0].get("tipo_documento") != TIPO_A_CLASSIFICAR:
        raise ValidationError_(
            "documento não está aguardando classificação", field="tipo_documento"
        )
    tipar_documento(client, org_id, cliente_id, documento_id, tipo)
    client.table("cliente_documentos").update(
        {"classificacao_confianca": "alta", "classificado_em": _now()}
    ).eq("id", str(documento_id)).execute()
    return {"id": str(documento_id), "tipo_documento": tipo, "extracao_status": "pendente"}


# ─── The intake ──────────────────────────────────────────────────────────


async def processar_midia(
    client: Any,
    storage: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    mensagem_id: Optional[Any],
    media_url: Optional[str],
    mimetype: Optional[str],
    filename: Optional[str],
    downloader: Downloader,
    extractor_factory: Callable[[Optional[str], Optional[str]], Any],
    notification_service: Optional[Any] = None,
    cep_lookup: Optional[Any] = None,
) -> dict:
    """Run the whole intake for ONE inbound media. Never raises.

    Returns `{status, documento_id|None, tipo_documento|None, motivo|None}`;
    `status` in `extraido | a_classificar | recusado | erro`.
    """
    mime = (mimetype or "").split(";")[0].strip().lower()
    nome = filename or "anexo"
    resultado: dict[str, Any] = {
        "status": "erro", "documento_id": None, "tipo_documento": None, "motivo": None,
    }

    async def _anexo(documento_id: Optional[str], motivo: Optional[str]) -> None:
        if mensagem_id is None:
            return
        try:
            conversa_service.patch_payload_da_mensagem(
                client, org_id, mensagem_id,
                {"anexo": {"mime": mime or None, "nome": nome,
                           "documento_id": documento_id, "motivo": motivo}},
            )
        except Exception:  # noqa: BLE001
            logger.warning("intake: could not annotate message %s", mensagem_id, exc_info=True)

    try:
        if not media_url:
            resultado.update(status="recusado", motivo="sem_url")
            logger.warning("intake: media without url (cliente=%s)", cliente_id)
            await _anexo(None, "sem_url")
            return resultado
        try:
            dados = await downloader(media_url)
        except Exception:  # noqa: BLE001
            logger.warning("intake: media download failed (cliente=%s)", cliente_id, exc_info=True)
            resultado.update(status="erro", motivo="download_falhou")
            await _anexo(None, "download_falhou")
            return resultado

        try:
            documento = await docs_svc.upload_documento(
                client, storage, org_id, cliente_id,
                filename=nome, content_type=mime, data=dados,
                tipo_documento=TIPO_A_CLASSIFICAR, enviado_por=None,
                permitir_a_classificar=True,
            )
        except ValidationError_ as exc:
            # A type/size the card store refuses (audio, video, huge file). The
            # message keeps its text; the bubble says why there is no document.
            logger.info("intake: media refused by the document store: %s", exc)
            resultado.update(status="recusado", motivo="tipo_ou_tamanho_nao_aceito")
            await _anexo(None, "tipo_ou_tamanho_nao_aceito")
            return resultado

        documento_id = UUID(documento["id"])
        resultado["documento_id"] = str(documento_id)
        client.table("cliente_documentos").update(
            {"origem_entrada": ORIGEM_WHATSAPP}
        ).eq("id", str(documento_id)).execute()
        await _anexo(str(documento_id), None)

        tipo, confianca, provavel = await classificar(
            dados, mime, nome, extractor_factory(str(org_id), None)
        )
        client.table("cliente_documentos").update(
            {
                "classificacao_tipo_provavel": provavel,
                "classificacao_confianca": confianca,
                "classificado_em": _now(),
            }
        ).eq("id", str(documento_id)).execute()

        if tipo is None:
            resultado.update(status="a_classificar", tipo_documento=TIPO_A_CLASSIFICAR)
            return resultado

        tipar_documento(client, org_id, cliente_id, documento_id, tipo)
        resultado.update(status="extraido", tipo_documento=tipo)
        await registry.extrair(
            tipo, client, storage, org_id, cliente_id, documento_id,
            extractor_factory=extractor_factory,
            notification_service=notification_service,
            cep_lookup=cep_lookup,
        )
        return resultado
    except Exception:  # noqa: BLE001 - runs detached from the webhook
        logger.exception("intake: unexpected failure (cliente=%s)", cliente_id)
        resultado.update(status="erro", motivo="falha_inesperada")
        return resultado


async def processar_midia_do_webhook(
    org_id: UUID,
    cliente_id: UUID,
    *,
    mensagem_id: Optional[Any],
    media_url: Optional[str],
    mimetype: Optional[str],
    filename: Optional[str],
) -> dict:
    """Webhook entry: wires the production collaborators and runs the intake.
    Detached from the request (fire-and-forget) -- never raises."""
    try:
        from app.modules.card_hub import deps
        from app.services.media_service import make_media_service

        return await processar_midia(
            deps.get_card_hub_client(), deps.get_storage_backend(), org_id, cliente_id,
            mensagem_id=mensagem_id, media_url=media_url, mimetype=mimetype,
            filename=filename,
            downloader=make_media_service().download,
            extractor_factory=deps.get_identity_extractor_factory(),
            notification_service=deps.get_conflict_notification_service(),
            cep_lookup=deps.get_cep_lookup_adapter(),
        )
    except Exception:  # noqa: BLE001
        logger.exception("intake: could not start (cliente=%s)", cliente_id)
        return {"status": "erro", "documento_id": None, "tipo_documento": None,
                "motivo": "falha_ao_iniciar"}
