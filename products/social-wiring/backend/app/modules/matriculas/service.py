"""Matrícula Text Extractor Service — the product's half of transcription.

Ported from `erp-imobiliario`'s `app/services/matricula_service.py`
(2026-09-02) as ERP is retired. The behaviour is intentionally identical;
what changed is the schema (`social_wiring`), the org source, and the fact
that this product has no `log_action` audit shim — see `router.py`.

The ladder itself lives in the seed:
`noctusai_lib.integrations.documents.make_document_transcriber` decides,
per page, whether the PDF's own text layer is real content or a scan's
signature stamp, and rasterizes → vision only for the pages it cannot
read. That module carries the history this file used to carry alone.

WHAT STAYS HERE
---------------
The `matricula_extracoes` row and its status lifecycle, and the mapping
from a machine error code to a sentence this product's users can act on.
That mapping is the reason the seed returns codes rather than prose: a
chatbot surfacing the same failure over WhatsApp needs different words
than a settings screen does.

🔴 EVERY WRITE CARRIES AN EXPLICIT `org_id` PREDICATE
------------------------------------------------------
The detached half of this workflow writes through the SERVICE-ROLE client
(a background task outlives the token that spawned it), and service-role
bypasses RLS. So the org scoping RLS performs on the request path has to be
performed by hand here. `_marcar` takes `org_id` and refuses to write
without one — a `None` that silently widened an UPDATE to every org is the
exact shape this file must not have.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from noctusai_lib.config.credentials import resolve_credential
from noctusai_lib.integrations.documents.formatting import ranges_to_json

from app.modules.imovel_hub.deps import BUCKET as IMOVEL_BUCKET
from app.modules.matriculas import estrutura_service
from app.services import documento_retencao

logger = logging.getLogger(__name__)

TABLE = "matricula_extracoes"

#: A row stuck in a non-terminal state longer than this was orphaned by a
#: process that died mid-extraction. Generous enough that a slow vision pass
#: over a long matrícula is never mistaken for a dead one — the same 20
#: minutes `imovel_hub.matricula_extracao_service.STALE_APOS` uses, for the
#: same reason.
STALE_APOS = timedelta(minutes=20)

_ESTADOS_NAO_TERMINAIS = ("pendente", "processando")

#: What a stranded row says once the sweep finds it. It cannot say "retrying"
#: because there is nothing to retry FROM: this workflow keeps no copy of the
#: uploaded PDF (see `varrer_pendentes`), so re-uploading is genuinely the
#: only way forward and the message says so rather than implying otherwise.
MENSAGEM_ORFA = (
    "A extração foi interrompida (o servidor reiniciou durante o "
    "processamento). Envie o PDF novamente."
)

#: The same situation for an extraction LINKED to an imóvel (migration 109):
#: its PDF is kept as the imóvel's document, so "send the file again" would
#: be false — the operator re-requests the transcription from that document
#: (`POST /api/matriculas/extracoes/de-documento`; an `erro` row never blocks
#: the retry).
MENSAGEM_ORFA_VINCULADA = (
    "A extração foi interrompida (o servidor reiniciou durante o "
    "processamento). O PDF continua guardado nos documentos do imóvel — "
    "solicite a transcrição novamente a partir dele."
)

#: Machine error code → what this product's users should read.
#:
#: Anything not listed here is a bug rather than a condition the user can
#: act on, so it falls through to `_MENSAGEM_PADRAO` WITH the developer
#: message attached — a generic apology that hides the cause is how a
#: silent error survives to production.
_MENSAGENS: dict[str, str] = {
    "no_pages": "PDF sem páginas — verifique se o arquivo não está corrompido.",
    "empty_document": "Arquivo vazio — envie o PDF da matrícula novamente.",
    # Deliberately does NOT name a vendor: with the manual switch in
    # Settings, which key is missing depends on which provider this org
    # selected, and a message hard-coded to "OpenAI" would send the
    # operator to fix a key that was never going to be used. The seed's
    # `error_message` names the provider for the log; the operator is sent
    # to the one screen that shows both the keys and the switch.
    "missing_credentials": (
        "A chave do provedor de IA selecionado não está configurada. "
        "Verifique em Configurações → Chaves de API qual provedor está "
        "escolhido e se a chave dele foi salva."
    ),
    "too_many_vision_pages": (
        "Documento muito longo para transcrição automática. "
        "Envie a matrícula em partes menores."
    ),
    # Names both billing pages rather than guessing: the switch means the
    # empty account could be either one, and sending the operator to the
    # wrong console is the same dead end as saying nothing.
    "insufficient_quota": (
        "Sem créditos na conta do provedor de IA selecionado — a transcrição "
        "de matrículas digitalizadas fica suspensa até que créditos sejam "
        "adicionados (OpenAI: platform.openai.com/settings/organization/"
        "billing · Anthropic: console.anthropic.com/settings/billing). Você "
        "também pode trocar de provedor em Configurações → Chaves de API. "
        "PDFs com camada de texto continuam funcionando normalmente."
    ),
    # These two named OpenAI as well, for the same reason and with the same
    # cost: an org running on Anthropic would be told to check a key it does
    # not use.
    "rate_limited": (
        "Limite de requisições do provedor de IA atingido. Aguarde alguns "
        "minutos e envie novamente — nada foi perdido."
    ),
    "invalid_credentials": (
        "A chave do provedor de IA selecionado foi recusada. Verifique-a em "
        "Configurações → Chaves de API."
    ),
    "rasterize_failed": (
        "Não foi possível ler todas as páginas do PDF. "
        "Verifique se o arquivo não está corrompido."
    ),
}

_MENSAGEM_PADRAO = "Erro inesperado: {detalhe}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mensagem_de_erro(resultado) -> str:
    """Render a transcription failure for this product's users."""
    conhecida = _MENSAGENS.get(resultado.error or "")
    if conhecida:
        return conhecida
    return _MENSAGEM_PADRAO.format(
        detalhe=resultado.error_message or resultado.error or "desconhecido"
    )


def _marcar(db, extracao_id: str, org_id: str, **updates: Any) -> None:
    """Write `updates` onto one row, scoped to its org.

    Raises rather than widening: `db` here is service-role, so an UPDATE
    without the org predicate would reach every tenant's rows.
    """
    if not org_id:
        raise ValueError(
            "matricula_extracoes update requires an org_id — a service-role "
            "write without one is not scoped to any tenant"
        )
    (
        db.table(TABLE)
        .update(updates)
        .eq("id", extracao_id)
        .eq("org_id", org_id)
        .execute()
    )


async def processar_extracao(
    extracao_id: str,
    pdf_bytes: bytes,
    org_id: str,
    db,
    transcriber=None,
    transcriber_factory=None,
) -> None:
    """Full extraction pipeline — runs as a background task. NEVER raises.

    An exception escaping here surfaces NOWHERE: no user sees it, no
    response carries it, and the row sits in `processando` forever. So every
    outcome, including the ugly ones, is written to the row.

    `transcriber` is the direct test seam. `transcriber_factory` is the
    production seam (`app.modules.matriculas.deps.get_transcriber_factory`)
    — a factory rather than an instance so the org's credential is resolved
    at extraction time rather than at import time.
    """
    try:
        _marcar(db, extracao_id, org_id, status="processando")

        if transcriber is None:
            if transcriber_factory is None:
                raise ValueError(
                    "processar_extracao needs a transcriber or a "
                    "transcriber_factory — it must never build its own"
                )
            transcriber = transcriber_factory(org_id)

        resultado = await transcriber.transcribe(
            pdf_bytes, mimetype="application/pdf"
        )

        if not resultado.ok:
            logger.warning(
                "Matrícula %s: transcription failed (%s) %s",
                extracao_id, resultado.error, resultado.error_message or "",
            )
            _marcar(
                db, extracao_id, org_id,
                status="erro",
                erro_mensagem=_mensagem_de_erro(resultado),
            )
            return

        logger.info(
            "Matrícula %s: %d pages — %d from text layer, %d via vision",
            extracao_id,
            resultado.num_paginas,
            len(resultado.paginas_por_camada),
            len(resultado.paginas_por_visao),
        )

        # 🔴 Stamped on the SAME write that lands the text (migration 111) —
        # `documento_retencao.dias_para` reads the two-tier policy under
        # `superficie="imovel"`, `tipo_documento="texto_extraido"`. `None`
        # when there is no policy row or the policy says keep indefinitely;
        # both read as "does not expire" to `estrutura_service.
        # purgar_texto_expirado`.
        dias = documento_retencao.dias_para(db, org_id, "imovel", "texto_extraido")
        retencao_ate = (
            (datetime.now(timezone.utc).date() + timedelta(days=dias)).isoformat()
            if dias
            else None
        )
        # 🔴 NOC-REMEDIATE[transcricao-formatacao-backfill]: 5 rows in prod
        # already hold `texto_extraido` with literal `**bold**`/`<u>…</u>`
        # markers baked into the PLAIN TEXT (the OLD vision prompt, before
        # the seed learned to parse markup into ranges). Migration 111's
        # write-once trigger refuses to let `texto_extraido` be REWRITTEN
        # once `status = 'concluida'`, and this write never touches an
        # existing row either — so those five stay unformatted (`formatacao`
        # keeps its `'[]'` column default) until someone re-transcribes
        # them. Every row landing HERE, from this write onward, is correct.
        # — 2026-09-14
        _marcar(
            db, extracao_id, org_id,
            status="concluida",
            texto_extraido=resultado.text,
            formatacao=ranges_to_json(resultado.formatting),
            num_paginas=resultado.num_paginas,
            retencao_ate=retencao_ate,
        )

        # The acts (migration 109), as offsets into the text that just landed.
        # Deliberately AFTER the text write and in its own try: the text is
        # the product of a paid vision pass and must not be rolled back to
        # `erro` because a second insert failed. The failure is logged at
        # ERROR and self-heals — `estrutura_service.listar_atos` re-segments
        # a concluded extraction that has no acts on its first read.
        try:
            escritos = estrutura_service.persistir_atos(
                db, extracao_id, org_id, resultado.text
            )
            logger.info("Matrícula %s: %d acts persisted", extracao_id, escritos)
        except Exception as falha_atos:  # noqa: BLE001 - text landed; acts heal on read
            logger.error(
                "Matrícula %s: text saved but its acts were not persisted (%s) — "
                "they are re-segmented on the first GET .../atos",
                extracao_id, falha_atos, exc_info=True,
            )

    except Exception as e:  # noqa: BLE001 - detached task; record, never raise
        logger.error(
            "Matrícula %s extraction failed: %s", extracao_id, e, exc_info=True
        )
        _registrar_erro(db, extracao_id, org_id, f"Erro inesperado: {e}", e)


def _registrar_erro(db, extracao_id: str, org_id: str, mensagem: str, causa) -> None:
    """Write `erro` onto the row — the last thing a detached task can do.

    If even that fails (bad org_id, DB down) there is nowhere else to report
    to, so the log IS the report — it must not be swallowed, and it must not
    mask the original failure.
    """
    try:
        _marcar(db, extracao_id, org_id, status="erro", erro_mensagem=mensagem)
    except Exception as falha:  # noqa: BLE001 - last resort; say so
        logger.error(
            "Matrícula %s: could not even record the failure: %s "
            "(original error: %s)",
            extracao_id, falha, causa,
        )


async def processar_extracao_de_documento(
    extracao_id: str,
    storage_path: str,
    org_id: str,
    db,
    storage,
    *,
    transcriber=None,
    transcriber_factory=None,
) -> None:
    """Read an imóvel's KEPT matrícula PDF back out of storage, then run the
    one transcription pipeline (`processar_extracao`). NEVER raises.
    """
    try:
        blob = await storage.get(bucket=IMOVEL_BUCKET, key=storage_path)
    except Exception as e:  # noqa: BLE001 - detached task; record, never raise
        logger.warning("Matrícula %s: storage read failed: %s", extracao_id, e)
        _registrar_erro(
            db, extracao_id, org_id,
            "Não foi possível ler o PDF guardado no imóvel. Tente novamente.", e,
        )
        return
    if blob is None:
        logger.warning(
            "Matrícula %s: stored object %s is missing", extracao_id, storage_path
        )
        _registrar_erro(
            db, extracao_id, org_id,
            "O PDF da matrícula não foi encontrado no armazenamento do imóvel.",
            "objeto ausente",
        )
        return
    await processar_extracao(
        extracao_id,
        blob.data,
        org_id,
        db,
        transcriber=transcriber,
        transcriber_factory=transcriber_factory,
    )


async def varrer_pendentes(client, _storage=None, *, limite: int = 50) -> dict:
    """Close out extractions that were started and never finished.

    🔴 WHY THIS EXISTS. `status` moves to `processando` before the work and
    to a terminal value after it. If the process dies in between — a deploy,
    an OOM kill, a container restart — nothing ever moves it again. The row
    sits there, the text never fills in, and NOTHING SURFACES. The same is
    true of `pendente` when the background task was never scheduled at all.

    🔴 WHY THIS MARKS `erro` INSTEAD OF RETRYING, unlike `card_hub` /
    `imovel_hub`. Those two read their bytes back out of Storage, so a
    stranded document can genuinely be re-read. A legacy UNLINKED upload
    keeps NO copy of the PDF — the bytes live only in the `BackgroundTask`'s
    closure (ERP's shape, ported unchanged). When the process dies the bytes
    die with it. So the honest recovery is to tell the user the truth and
    ask for the file again; pretending a retry is possible would leave the
    row cycling through `processando` forever, which is the silent error
    this sweep exists to remove, wearing a different hat.

    A LINKED extraction (migration 109) does keep its PDF, as the imóvel's
    document, and the message says so (`MENSAGEM_ORFA_VINCULADA`): the
    operator re-requests it from that document. It is still marked rather
    than retried here because a retry needs the org's transcriber, which is
    a per-request DI seam this scheduler does not hold.

    `_storage` is accepted and ignored: `app.services.extraction_sweep`'s
    `SweepFn` contract is `(admin_client, storage_backend)`, shared with the
    two sweeps that DO need storage.
    """
    cutoff = (_now() - STALE_APOS).isoformat()

    # Both halves below are provably bounded, not assumed to be. The `in_`
    # list is the 2-element module constant `_ESTADOS_NAO_TERMINAIS` — it
    # cannot grow at runtime, so it can never overflow the URL query string.
    # The select carries `.limit(limite)` (default 50), far under PostgREST's
    # 1 000-row cap, and deliberately does NOT page: a sweep that walked every
    # stranded row in one pass would rewrite an unbounded slice of the table
    # in a single scheduled run. It runs hourly and closes out `limite` rows a
    # run, which is the right shape for a recovery job.
    #
    # postgrest-unbounded-ok: fixed 2-element `in_` constant, `.limit(limite)`.
    presos = (
        client.table(TABLE)
        .select("id,org_id,nome_arquivo,status,imovel_documento_id")
        .in_("status", list(_ESTADOS_NAO_TERMINAIS))
        .lt("updated_at", cutoff)
        .limit(limite)
        .execute()
    ).data or []

    marcados = 0
    for row in presos:
        org_id = row.get("org_id")
        if not org_id:
            # An org-less row cannot exist (NOT NULL + DEFAULT
            # current_org_id()), so one here means the schema drifted.
            # Say so; do not widen the UPDATE to reach it.
            logger.error(
                "matricula sweep: row %s has no org_id — skipping (schema drift?)",
                row.get("id"),
            )
            continue
        _marcar(
            client, row["id"], str(org_id),
            status="erro",
            erro_mensagem=(
                MENSAGEM_ORFA_VINCULADA
                if row.get("imovel_documento_id")
                else MENSAGEM_ORFA
            ),
        )
        marcados += 1

    return {"encontrados": len(presos), "marcados": marcados}


def check_required_credentials(org_id: Optional[str] = None) -> list[str]:
    """Check which required credentials are missing for matrícula extraction.

    Still reports the key as required: it is needed for any SCANNED matrícula,
    and the caller cannot know in advance which kind will be uploaded. Since
    rung 1 landed, a digitally-issued PDF will extract without it — so this is
    a warning about what may fail, not a hard precondition for every document.
    """
    # Checks the SELECTED provider's key, not OpenAI's unconditionally —
    # otherwise an org running on Anthropic would be warned forever about a
    # key it deliberately does not use, which trains operators to ignore
    # this panel.
    #
    # `resolve_credential` (not `api_keys_store.resolve_api_key`) is correct
    # here: `main.py` registers the product's encrypted store as tier 0 of
    # that same chain, so a key saved in the UI is already visible through
    # it. That closes NOC-REMEDIATE[matriculas-api-key-store] — the marker's
    # concern was that the store was invisible, and it no longer is.
    from app.services.api_keys_store import get_spec, resolve_vision_provider

    missing = []
    provider = resolve_vision_provider(org_id)
    spec = get_spec(f"{provider}_api_key")
    rotulo = spec.label if spec else f"{provider}_api_key"
    if not resolve_credential(f"{provider}_api_key", org_id):
        missing.append(
            f"{rotulo} não configurada — é o provedor selecionado para "
            "extração de matrículas digitalizadas (PDFs com camada de texto "
            "não precisam)."
        )
    return missing


def texto_html_da_extracao(texto: Optional[str], formatacao_json) -> Optional[str]:
    """Word-pasteable HTML of a transcript — `GET .../extracoes/{id}`'s
    `texto_html` field. `None` when there is no text yet (an in-progress or
    failed extraction), never an HTML fragment of an empty string.
    `formatacao_json` is the raw `jsonb` column value (possibly `None` for a
    row written before migration 113).
    """
    if not texto:
        return None
    from noctusai_lib.integrations.documents.abnt import (
        paragraphs_from_text,
        render_word_html,
    )
    from noctusai_lib.integrations.documents.formatting import (
        FormattedDocument,
        ranges_from_json,
    )

    doc = FormattedDocument(
        paragraphs=paragraphs_from_text(texto, ranges_from_json(formatacao_json))
    )
    return render_word_html(doc)


def renderizar_extracao_pdf(nome_arquivo: str, texto: str, formatacao_json) -> bytes:
    """ABNT-formatted PDF of one matrícula transcript, titled
    `"Transcrição da matrícula — <nome_arquivo>"` (contract §4).

    Raises `noctusai_lib.integrations.documents.abnt.UnsupportedGlyphError`
    straight through — the router turns it into a 422 naming the character,
    never a silent 500.
    """
    from noctusai_lib.integrations.documents.abnt import (
        paragraphs_from_text,
        render_abnt_pdf,
    )
    from noctusai_lib.integrations.documents.formatting import (
        FormattedDocument,
        Paragraph,
        ParagraphKind,
        Run,
        ranges_from_json,
    )

    titulo = f"Transcrição da matrícula — {nome_arquivo}"
    corpo = paragraphs_from_text(texto, ranges_from_json(formatacao_json))
    titulo_paragrafo = Paragraph(runs=(Run(text=titulo),), kind=ParagraphKind.TITLE)
    doc = FormattedDocument(paragraphs=(titulo_paragrafo, *corpo), title=titulo)
    return render_abnt_pdf(doc)


__all__ = [
    "MENSAGEM_ORFA",
    "MENSAGEM_ORFA_VINCULADA",
    "STALE_APOS",
    "TABLE",
    "check_required_credentials",
    "processar_extracao",
    "processar_extracao_de_documento",
    "renderizar_extracao_pdf",
    "texto_html_da_extracao",
    "varrer_pendentes",
]
