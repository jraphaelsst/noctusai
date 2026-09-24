"""Certidões Negativas — the issuance pipeline.

Orchestrates certificate emission via the InfoSimples API, AI-powered document
analysis, and result persistence. Each certificate type is declared in
`registry.CERTIDOES_CONFIG`; the pipeline (fetch → download → convert → store →
analyze) is shared across all of them.

Ported from `products/erp-imobiliario/backend/app/services/certidoes_service.py`
as the ERP product is retired. Four things changed, and only these four:

1. **Storage goes through the seed seam.** ERP uploaded through its
   product-local `StorageService` into an `erp-certidoes` bucket and got a
   PUBLIC url back. This product owns no such service: it consumes
   `noctusai_lib.integrations.storage.StorageBackend` and writes into the
   existing `social-wiring-documentos` bucket under a `certidoes/` prefix.
   See `_persist_pdf` for what `arquivo_url` now holds and why.

2. **The delete workaround is gone, not ported.** ERP's `_delete_storage_files`
   reached past its own StorageService into `db.storage.from_(bucket).remove()`
   because that service silently fell back to a dry-run under a non-admin
   client — i.e. it worked around a defect in its own abstraction. The seed
   seam has no such fallback, so the delete is expressed through it.

3. **Credentials resolve through `credentials.resolve_key`.** One indirection,
   for the reason its module docstring gives.

4. **`log_action` is dropped.** This product has no audit-log helper, and
   inventing a shim for one feature would be a fork of an audit surface rather
   than an audit surface. Surfaced as `drift-found:`.

Everything else — the retry ladder, the 612/"nada consta" branch, the
content-type detection, the TJSP cooldown queue, the two recovery sweeps, the
cancel path, the manual-upload pipeline — is the ERP behaviour, because it is
the behaviour a live user depends on.
"""
from __future__ import annotations

import asyncio
import html
import io
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import httpx
from noctusai_lib.integrations.documents.abnt import (
    paragraphs_from_text,
    render_abnt_pdf,
    render_word_html,
)
from noctusai_lib.integrations.documents.cpf import only_digits
from noctusai_lib.integrations.documents.formatting import (
    FormatRange,
    FormattedDocument,
    Paragraph,
    ParagraphKind,
    Run,
    ranges_from_json,
    ranges_to_json,
)
from noctusai_lib.integrations.documents.providers import (
    DEFAULT_DOCUMENT_PROVIDER,
    DOCUMENT_ANALYSIS_MODELS,
)
from noctusai_lib.integrations.llm import chat_completion
from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.storage import StorageBackend
from noctusai_lib.primitives.tasks import schedule_coro
from xhtml2pdf import pisa
from xhtml2pdf.config.resources import ResourceAccessPolicy

from app.modules.certidoes import cost_ledger
from app.modules.certidoes.credentials import (
    INFOSIMPLES_TOKEN,
    provider_api_key,
    resolve_key,
)
from app.modules.certidoes.deps import BUCKET, PREFIXO
from app.modules.certidoes.registry import (
    CERTIDOES_CONFIG,
    INFOSIMPLES_BASE_URL,
    PARAM_BUILDERS,
    RESULTADO_VALUES,
    TJSP_COOLDOWN_SECONDS,
    TJSP_TIPO,
    config_for,
    parse_resultado,
)

logger = logging.getLogger(__name__)

CONSULTAS = "certidao_consultas"
RESULTADOS = "certidao_resultados"

#: Every `certidao_resultados` column EXCEPT `texto_extraido` / `formatacao`
#: (migration 113) — the two columns a polling response must never carry,
#: PLUS `tem_transcricao` (the GENERATED flag the frontend gates its
#: transcript buttons on, safe to poll precisely because it never carries
#: the text itself). Used everywhere a resultado is returned to the
#: frontend as part of a LIST (a consulta's `resultados[]`, the per-parte
#: panel) — the two dedicated `.../transcricao` routes are the only place
#: the full text travels, and each of those LGPD-logs the read.
#: `estrutura_erro`/`estrutura_tentativas` (migration 155) are the
#: manual-upload structured/vision-extraction leg's own status — a UI can
#: show a PT-BR reason (or a "tentativa 2 de 3") next to a `sucesso` resultado
#: whose structured fields never landed, instead of that looking identical to
#: one nothing was ever asked to read. See `process_manual_extraction`.
RESULTADO_COLUNAS_SEM_TEXTO = (
    "id,consulta_id,org_id,tipo,nome_display,ordem,status,analise_ia,"
    "arquivo_url,arquivo_nome,api_response,erro_mensagem,api_requested_at,"
    "created_at,updated_at,numero,emitida_em,validade_ate,resultado,"
    "resultado_origem,confirmado_por,confirmado_em,tem_transcricao,"
    "estrutura_erro,estrutura_tentativas"
)

MAX_RETRIES = 3
DEFAULT_TIMEOUT = 240.0

#: Maximum time a resultado can stay "processando" before being considered
#: stuck. InfoSimples API calls time out at 240s with 3 retries = ~12 min worst
#: case, so this threshold is deliberately LONGER than the slowest legitimate
#: run — that is what makes the sweep safe to fire at any moment rather than
#: only at boot.
STALE_PROCESSANDO_SECONDS = 15 * 60


# --------------- Paging (PostgREST's 1 000-row cap) ---------------


def _all_rows(fetch_page, label: str) -> list[dict]:
    """Every row of an UNBOUNDED read, paged past PostgREST's row cap.

    `app.services.table_reads.paged_rows` is the canonical helper and is what
    the org-scoped reads here use indirectly — but it requires an `org_id`, and
    the two recovery sweeps below are deliberately cross-org (they run from a
    scheduler that has no caller and no org). This is that same pager with the
    org filter left to the caller's `fetch_page`.
    """
    return list(iter_paged_rows(fetch_page, id_key="id", label=label))


def in_batches(items: list[str], size: int = 200):
    """Yield `items` in chunks — PostgREST rides `.in_()` values in the URL
    query string, so an unbatched ~1 000-item list comes back as a bare 400
    with no hint that length was the problem.
    """
    for i in range(0, len(items), size):
        yield items[i : i + size]


# --------------- Core Processing ---------------


async def _fetch_certidao(
    config: dict,
    consulta: dict,
    token: str,
    client: httpx.AsyncClient,
) -> dict:
    """Call InfoSimples API for a single certificate type, with retry logic.

    Retries up to MAX_RETRIES times on transient failures (timeouts, network
    errors, server errors). Returns dict with keys: success, file_url,
    raw_response, error.
    """
    builder = PARAM_BUILDERS[config["params_fn"]]
    params = builder(consulta, token)
    url = f"{INFOSIMPLES_BASE_URL}/{config['endpoint']}"
    timeout = config.get("timeout", DEFAULT_TIMEOUT)

    last_error = "Erro desconhecido"
    last_raw = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.get(url, params=params, timeout=timeout)
            data = resp.json()

            api_code = data.get("code")

            if api_code == 200 and data.get("data"):
                # Most endpoints: file URL is in data[0].site_receipt
                # CENPROT: file URL is in root-level site_receipts[0]
                site_receipt = data["data"][0].get("site_receipt", "")
                if not site_receipt:
                    site_receipts = data.get("site_receipts") or []
                    site_receipt = site_receipts[0] if site_receipts else ""
                return {
                    "success": True,
                    "file_url": site_receipt,
                    "raw_response": data,
                    "error": None,
                }

            # Code 612 = "no data at source" — for certidões this means
            # nada consta (no debts/protests/issues found), which is a valid result.
            if api_code == 612:
                detail = (data.get("errors", []) or ["Nada consta"])[0]
                # The source still hands back a receipt for a "nada consta" —
                # CENPROT's is a synthesized one at the ROOT `site_receipts`,
                # and it is the ONLY document of the lookup. Dropping it left
                # a successful row with nothing to view or download.
                site_receipts = data.get("site_receipts") or []
                return {
                    "success": True,
                    "file_url": site_receipts[0] if site_receipts else None,
                    "raw_response": data,
                    "error": None,
                    "nada_consta": detail,
                }

            # Extract error — prefer specific fields (errors[], code_message)
            # over the generic message field which is often uninformative.
            last_raw = data
            errors_list = data.get("errors") or []
            specific_error = (
                (errors_list[0] if errors_list else None)
                or data.get("code_message")
            )
            generic_error = data.get("message")
            # Combine: show specific error first, append generic if different
            if specific_error and generic_error and specific_error != generic_error:
                last_error = f"{specific_error} ({generic_error})"
            else:
                last_error = (
                    specific_error
                    or generic_error
                    or f"Erro na consulta (code: {data.get('code', 'unknown')})"
                )

            # Don't retry on definitive API errors (bad params, auth, etc.)
            if isinstance(api_code, int) and 400 <= api_code < 500:
                break

            logger.warning(
                "InfoSimples %s attempt %d/%d failed: %s",
                config["tipo"], attempt, MAX_RETRIES, last_error,
            )

        except Exception as e:
            last_error = str(e)
            last_raw = None
            logger.warning(
                "InfoSimples %s attempt %d/%d exception: %s",
                config["tipo"], attempt, MAX_RETRIES, e,
            )

        # Wait before retrying (exponential: 2s, 4s)
        if attempt < MAX_RETRIES:
            await asyncio.sleep(2 ** attempt)

    logger.error(
        "InfoSimples %s failed after %d attempts: %s",
        config["tipo"], MAX_RETRIES, last_error,
    )
    return {
        "success": False,
        "file_url": None,
        "raw_response": last_raw,
        "error": last_error,
    }


async def _download_file(
    url: str, client: httpx.AsyncClient
) -> Optional[tuple[bytes, str]]:
    """Download a file from a URL. Returns (content_bytes, content_type) or None."""
    try:
        resp = await client.get(url, timeout=60.0, follow_redirects=True)
        if resp.status_code == 200:
            ct = resp.headers.get("content-type", "application/octet-stream")
            logger.info(
                "Downloaded %s: content-type=%s, size=%d, first_bytes=%r",
                url[:80], ct, len(resp.content), resp.content[:20],
            )
            return resp.content, ct
        logger.warning("File download failed with status %d for %s", resp.status_code, url)
        return None
    except Exception as e:
        logger.error("File download error: %s", e)
        return None


def _cenprot_protocolo_consulta(raw_response: Optional[dict]) -> Optional[str]:
    """`data[0].protocolo_consulta` from a CENPROT 200 ("protests found")
    response, when present.

    Per InfoSimples docs for `cenprot-sp/protestos` (read 2026-09-14): a code
    612 ("nada consta") response has `data: []` and no protocol anywhere,
    including in its synthesized `site_receipts[0]` receipt — so this
    naturally returns `None` for a 612, without checking `code` directly.
    """
    if not raw_response:
        return None
    data = raw_response.get("data") or []
    if not data or not isinstance(data[0], dict):
        return None
    protocolo = data[0].get("protocolo_consulta")
    return protocolo if isinstance(protocolo, str) and protocolo else None


def _with_protocolo_stamp(html_bytes: bytes, protocolo: str) -> bytes:
    """Insert an HTML-escaped `Protocolo da consulta` line right after the
    opening `<body>` tag (or prepend one, if the receipt has none) — a
    CENPROT receipt never prints its own consulta protocol."""
    stamp = (
        f"<p><b>Protocolo da consulta:</b> {html.escape(protocolo)}</p>"
    ).encode("utf-8")
    lower = html_bytes.lower()
    body_start = lower.find(b"<body")
    if body_start == -1:
        return stamp + b"\n" + html_bytes
    tag_end = html_bytes.find(b">", body_start)
    if tag_end == -1:
        return stamp + b"\n" + html_bytes
    insert_at = tag_end + 1
    return html_bytes[:insert_at] + stamp + html_bytes[insert_at:]


#: The receipt is converted from its own bytes only. xhtml2pdf would otherwise
#: fetch every stylesheet and image the page references, synchronously and
#: without a deadline: on 2026-09-15 a TRF3 receipt pulled bootstrap.min.css,
#: three site stylesheets, two images and an anti-bot script served as CSS
#: from web.trf3.jus.br, one conversion took 92 s locally (0.6 s without the
#: fetches), and in prod it pinned the event loop at 95% CPU — the whole
#: social-wiring app stopped answering. `data:` URIs still render (they are
#: not a remote scheme); `base_dir=None` also refuses local file reads.
_NO_FETCH_POLICY = ResourceAccessPolicy(allow_remote=False, base_dir=None)

#: Upper bound for one HTML→PDF conversion. The conversion runs in a worker
#: thread (`asyncio.to_thread`), so a slow document can no longer block other
#: requests; past this deadline the certidão keeps the provider's original URL.
HTML_TO_PDF_TIMEOUT_SECONDS = 60


def _convert_html_to_pdf(html_bytes: bytes) -> Optional[bytes]:
    """Convert HTML content to PDF using xhtml2pdf, from the given bytes only.

    Nothing referenced by the page is fetched — see `_NO_FETCH_POLICY`. A
    receipt that relies on external CSS or images (TRF3's logo) renders
    without them.
    """
    try:
        pdf_buffer = io.BytesIO()
        pisa_status = pisa.CreatePDF(
            io.BytesIO(html_bytes),
            dest=pdf_buffer,
            resource_policy=_NO_FETCH_POLICY,
        )
        if pisa_status.err:
            logger.error("xhtml2pdf conversion error count: %d", pisa_status.err)
            return None
        return pdf_buffer.getvalue()
    except Exception as e:
        logger.error("HTML→PDF conversion failed: %s", e)
        return None


# --------------- Storage ---------------


def storage_key(org_id: str, consulta_id: str, tipo: str) -> str:
    """The bucket key for one stored certidão PDF.

    🔴 The `org_id` MUST be the FIRST path segment — this bucket's object-RLS
    policies (migration 057) match on it, so a key shaped any other way is
    readable across orgs.

    Keyed on `consulta_id` rather than on the person's NAME (which is what the
    ERP used as its subfolder). A name is not unique, contains spaces and
    accents, and can be edited after the fact — none of which a storage key
    survives well. The consulta id is stable and is what every read already
    has in hand.

    The random suffix keeps a re-issue (reprocess, manual upload) from
    overwriting the previous file: `put` overwrites, and a certidão that was
    superseded still has to be produceable, because it is what an earlier step
    of the deal was decided against.
    """
    return f"{org_id}/{PREFIXO}/{consulta_id}/{tipo}_{uuid.uuid4().hex[:8]}.pdf"


def is_storage_key(value: Optional[str]) -> bool:
    """Is `value` one of our bucket keys rather than an external URL?

    `arquivo_url` holds EITHER — see `_persist_pdf`. Everything we write is a
    key; anything with a scheme came from the source system.
    """
    return bool(value) and "://" not in value


def _is_certidoes_storage_key(value: str) -> bool:
    """🔴 REQUIRED SAFETY FIX (P0c contract §C5). `BUCKET` is shared across
    `card_hub` (`{org_id}/clientes/...`), `imovel_hub` (`{org_id}/imoveis/
    ...`), `empresas` (`{org_id}/empresas/...`) and this module
    (`{org_id}/certidoes/...` — `storage_key`, `PREFIXO`). Since migration
    167, `certidao_resultados.arquivo_url` can ALSO hold a `cliente_
    documentos.storage_path` verbatim (the Crednet -> certidão 9 provenance
    — `registrar_serasa_de_crednet` deliberately reuses the SAME stored
    file rather than copying it). Without this check, purging (or soft-
    deleting) one CPF consulta would delete the cliente's Crednet upload out
    from under `cliente_documentos` — a document this consulta does not
    own and did not create. Only a key whose SECOND path segment is this
    module's own `PREFIXO` is ever eligible for deletion here.
    """
    parts = value.split("/", 2)
    return len(parts) >= 2 and parts[1] == PREFIXO


async def _persist_pdf(
    pdf_bytes: bytes,
    storage: StorageBackend,
    org_id: Optional[str],
    consulta_id: str,
    tipo: str,
) -> Optional[str]:
    """Put the PDF in the bucket. Returns the KEY, or None when it could not.

    🔴 THE KEY, NOT A URL — and that is the one deliberate contract change from
    the ERP.

    ERP stored a permanent PUBLIC url. This product's bucket is private and its
    reads are minted as short-TTL signed URLs (`documento_store.
    SIGNED_URL_TTL_SECONDS` is 300 seconds). Storing a signed URL in a column
    that outlives it by months would mean every certidão silently becomes an
    un-downloadable dead link a few minutes after it is issued — and re-minting
    one per resultado on every read is 10 storage round-trips on a detail
    endpoint the frontend polls every 3 seconds.

    So the column holds the key, and the two routes that actually need bytes
    (`/download`, `/download-zip`) read them straight through this seam. No URL
    to expire, no per-poll minting, and the delete path gets the key for free
    instead of parsing it back out of a URL the way ERP had to.

    `None` on failure is a REPORTED outcome, not a swallowed one: the caller
    keeps the upstream `file_url` in `arquivo_url` so the certidão is still
    reachable while InfoSimples keeps it alive, and the failure is logged at
    error.
    """
    if not org_id:
        logger.warning(
            "certidoes: no org_id for consulta %s — skipping storage upload; "
            "arquivo_url will keep the upstream URL",
            consulta_id,
        )
        return None
    key = storage_key(org_id, consulta_id, tipo)
    try:
        await storage.put(
            bucket=BUCKET,
            key=key,
            data=pdf_bytes,
            content_type="application/pdf",
            metadata={"tipo": tipo, "consulta_id": consulta_id},
        )
        return key
    except Exception as e:
        logger.error("certidoes: storage upload failed for %s: %s", key, e)
        return None


async def read_certidao_bytes(
    arquivo_url: str,
    storage: StorageBackend,
    http_client: httpx.AsyncClient,
) -> Optional[bytes]:
    """The bytes behind one `arquivo_url`, whichever kind it is.

    A bucket key is read through the storage seam; an `https://` URL is fetched
    over HTTP (the source system still hosts it — this is the fallback path for
    a certidão whose upload failed). `None` when neither produced bytes; every
    caller treats that as "skip this file" and says so.
    """
    if is_storage_key(arquivo_url):
        try:
            blob = await storage.get(bucket=BUCKET, key=arquivo_url)
        except Exception as e:
            logger.warning("certidoes: storage read failed for %s: %s", arquivo_url, e)
            return None
        if blob is None:
            logger.warning("certidoes: no blob at key %s", arquivo_url)
            return None
        return blob.data
    downloaded = await _download_file(arquivo_url, http_client)
    return downloaded[0] if downloaded else None


async def delete_storage_files(
    resultados: list[dict], storage: StorageBackend
) -> int:
    """Delete every stored file behind a list of resultados. Returns the count.

    Replaces ERP's `_delete_storage_files`, which parsed the bucket path back
    out of a public URL and then bypassed its own StorageService to dodge a
    dry-run fallback. Neither half is needed here: the column already holds the
    key, and the seam deletes for real.
    """
    keys = [
        r["arquivo_url"]
        for r in resultados
        if is_storage_key(r.get("arquivo_url"))
        and _is_certidoes_storage_key(r["arquivo_url"])
    ]
    estrangeiras = [
        r["arquivo_url"]
        for r in resultados
        if is_storage_key(r.get("arquivo_url"))
        and not _is_certidoes_storage_key(r["arquivo_url"])
    ]
    if estrangeiras:
        # Never silently skipped — a foreign key here means a resultado
        # points at a document this module does not own (the Crednet ->
        # certidão 9 case). It is left alone on purpose; logged so the skip
        # is visible, not mysterious.
        logger.info(
            "certidoes: skipping %d non-certidões storage key(s) — owned by "
            "another surface (e.g. a Crednet cliente_documentos upload): %s",
            len(estrangeiras), estrangeiras,
        )
    if not keys:
        logger.info("certidoes: no stored files to delete for this consulta")
        return 0

    deleted = 0
    for key in keys:
        try:
            # `delete` returns False for an already-absent key and never raises
            # 404 — an already-gone file is not an error, it is the goal.
            await storage.delete(bucket=BUCKET, key=key)
            deleted += 1
        except Exception as e:
            # Logged, not raised: the DB rows must still go. A blob we failed
            # to remove is an orphan in the bucket; a row we failed to remove
            # is a certidão the user asked us to forget and still sees.
            logger.error("certidoes: failed to delete storage key %s: %s", key, e)
    logger.info("certidoes: deleted %d/%d storage files", deleted, len(keys))
    return deleted


# --------------- Soft-delete, restore, purge (S3 — audit-trail slice) ---------------
#
# 🔴 WHY SOFT-DELETE REPLACED THE HARD DELETE — see migration 161's header for
# the prod incident: a manual consulta of 12 results + blobs was hard-deleted
# and nobody could tell WHO did it. `soft_delete_consulta` stamps
# `excluida_em`/`excluida_por` on the consulta AND every one of its
# resultados (an UPDATE, not a DELETE — the FK CASCADE only fires on DELETE,
# so the resultados need their own explicit write, in the same call). Blobs
# are NEVER touched here: `restaurar_consulta` needs them intact, and
# `purge_excluidas` is the only place that removes them, 30 days later.


def soft_delete_consulta(db, org_id, consulta_id: str, usuario_id) -> Optional[int]:
    """Mark one consulta AND its resultados excluded. Returns the number of
    resultados stamped, or `None` when the consulta does not exist (or is
    already excluded) in this org — the router turns that into the 404.

    Re-checks existence even though the router already ran `_get_consulta_
    or_404` first: a service function's contract should not depend on what
    its one caller happened to check.
    """
    existing = (
        db.table(CONSULTAS)
        .select("id")
        .eq("id", consulta_id)
        .eq("org_id", str(org_id))
        .is_("excluida_em", "null")
        .execute()
    ).data or []
    if not existing:
        return None

    agora = datetime.now(timezone.utc).isoformat()
    quem = str(usuario_id) if usuario_id else None

    db.table(CONSULTAS).update({
        "excluida_em": agora,
        "excluida_por": quem,
    }).eq("id", consulta_id).eq("org_id", str(org_id)).execute()

    resultados_atualizados = (
        db.table(RESULTADOS)
        .update({"excluida_em": agora, "excluida_por": quem})
        .eq("consulta_id", consulta_id)
        .eq("org_id", str(org_id))
        .execute()
    ).data or []
    return len(resultados_atualizados)


def restaurar_consulta(db, org_id, consulta_id: str) -> Optional[dict]:
    """The inverse of `soft_delete_consulta`: clears `excluida_em`/
    `excluida_por` on the consulta AND every one of its resultados. Blobs
    were never touched by the soft-delete, so a restore needs no storage
    work at all.

    Deliberately does NOT filter `excluida_em` on the lookup — restoring is
    the one operation that MUST be able to find an excluded row. Returns
    `None` for a consulta absent from this org, OR one that was never
    excluded in the first place (nothing to restore — silently "succeeding"
    on that would hide a caller's mistaken id from itself); either shape is
    a 404 to the router, same contract as `atualizar_situacao_cadastral`'s.
    """
    existing = (
        db.table(CONSULTAS)
        .select("id, excluida_em")
        .eq("id", consulta_id)
        .eq("org_id", str(org_id))
        .execute()
    ).data or []
    if not existing or existing[0].get("excluida_em") is None:
        return None

    updated = (
        db.table(CONSULTAS)
        .update({"excluida_em": None, "excluida_por": None})
        .eq("id", consulta_id)
        .eq("org_id", str(org_id))
        .execute()
    ).data or []

    db.table(RESULTADOS).update({
        "excluida_em": None,
        "excluida_por": None,
    }).eq("consulta_id", consulta_id).eq("org_id", str(org_id)).execute()

    return updated[0] if updated else None


async def purge_excluidas(
    db, storage: StorageBackend, *, older_than_days: int = 30
) -> dict:
    """Hard-delete blobs + rows for every consulta excluded more than
    `older_than_days` ago. Cross-org, like `recover_stale_processando` above
    — the scheduler's `db` is the RAW admin client (`scheduler._clients`),
    same shape `meta_ads.services.leadgen_webhook_service.
    LeadgenWebhookService.purge_processed` uses for its own LGPD-retention
    cutoff delete.

    Runs the SAME "blobs before rows" ordering `routers/certidoes.py::
    excluir_consulta` always has: a row deleted first is a bucket key
    nobody can find again.
    """
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=older_than_days)
    ).isoformat()

    def _page(start: int, end: int):
        # `.lt("excluida_em", cutoff)` alone already excludes NULL rows (SQL
        # `col < value` is never true for NULL) — every active consulta is
        # simply not a candidate, no separate `IS NOT NULL` needed.
        return (
            db.table(CONSULTAS)
            .select("id")
            .lt("excluida_em", cutoff)
            .order("excluida_em")
            .range(start, end)
            .execute()
            .data
        )

    stale = _all_rows(_page, "certidao_consultas past purge cutoff")
    if not stale:
        return {"consultas": 0, "resultados": 0, "arquivos": 0}

    consultas_purgadas = 0
    resultados_purgados = 0
    arquivos_purgados = 0
    for consulta in stale:
        consulta_id = consulta["id"]
        # postgrest-unbounded-ok: at most ~13 resultados per consulta, the
        # same fan-out bound every other read against this table relies on.
        resultados = (
            db.table(RESULTADOS)
            .select("arquivo_url")
            .eq("consulta_id", consulta_id)
            .execute()
        ).data or []
        arquivos_purgados += await delete_storage_files(resultados, storage)

        deleted_resultados = (
            db.table(RESULTADOS).delete().eq("consulta_id", consulta_id).execute()
        ).data or []
        resultados_purgados += len(deleted_resultados)

        # CASCADE removes any resultado this pass did not already delete
        # (migration 091's FK) — belt-and-braces with the explicit delete
        # above, which is what lets `resultados_purgados` count accurately.
        db.table(CONSULTAS).delete().eq("id", consulta_id).execute()
        consultas_purgadas += 1

    logger.info(
        "certidoes purge: %d consulta(s), %d resultado(s), %d arquivo(s) "
        "hard-deleted past the %d-day retention window",
        consultas_purgadas, resultados_purgados, arquivos_purgados, older_than_days,
    )
    return {
        "consultas": consultas_purgadas,
        "resultados": resultados_purgados,
        "arquivos": arquivos_purgados,
    }


# --------------- AI analysis ---------------

#: Which model writes the analysis, PER PROVIDER.
#:
#: 🔴 A MAP, NOT A STRING — for the same reason
#: `documents/transcription.py::OCR_MODELS` is one: the model id is not
#: portable across vendors. `gpt-4.1-mini` sent to Anthropic is a 404, and the
#: operator who flipped the provider would read that as a broken key rather
#: than a mismatched pin. Selecting a provider selects its model.
#:
#: These are analysis models, deliberately separate from the OCR pins: this
#: call reasons about a legal document and writes the summary a human acts on,
#: where the transcription rung only has to copy characters faithfully. Tune
#: here, not at the call site.
#:
#: The pins live in the seed (`noctusai_lib.integrations.documents.providers`
#: — ONE place per rung, with the measurement that chose them); this is the
#: same object under the name this module's callers already import.
ANALYSIS_MODELS: dict[str, str] = DOCUMENT_ANALYSIS_MODELS

#: The provider assumed when the org never chose — the SAME seed constant the
#: `llm_chat_provider` spec defaults to, so an org that never opened Settings
#: is analysed by, and pre-flight-checked against, one vendor.
DEFAULT_ANALYSIS_PROVIDER = DEFAULT_DOCUMENT_PROVIDER


async def _analyze_with_ai(
    text: str,
    org_id: Optional[str] = None,
    *,
    resolve_provider: Optional[Callable[[Optional[str]], str]] = None,
) -> Optional[str]:
    """Send document text/summary to the seed `chat_completion` wrapper.

    Returns a user-facing marker string if the OpenAI key is not configured —
    AI analysis is optional, the certificate itself is still valid without it,
    and a Portuguese sentence in the column is what tells the operator WHY the
    analysis box is empty. The pre-flight credential check exists for exactly
    that: without it the call raises `LLMNotConfigured` and the operator sees a
    stack-trace-shaped error on a certidão that actually succeeded.

    Returns `None` — never the vendor's raw exception text — if the
    configured call itself fails (rate limit, bad kwarg, timeout, ...); the
    failure is logged instead. `analise_ia` is a due-diligence read surface,
    not an error channel.
    """
    from app.services.api_keys_store import get_spec, resolve_chat_provider

    # `resolve_provider` is the Class-B DI seam (KB § PATTERNS/backend/
    # di-test-seam.md), the same shape `_process_single_certidao` already
    # exposes for `analyze`. It exists because the alternative a test would
    # otherwise reach for — patching
    # `api_keys_store.resolve_chat_provider` — is monkeypatching OUR OWN
    # code: the test would then assert against the patch instead of the
    # seam, and the compliance keeper flags it high, correctly.
    resolver = resolve_provider or resolve_chat_provider

    # Checks the SELECTED provider's key, never OpenAI's unconditionally —
    # same reasoning as `matriculas.check_required_credentials`: an org
    # running on Anthropic that is told forever about a missing OpenAI key
    # learns to ignore this message, and the one time it means something it
    # is invisible.
    # 🔴 AN UNREADABLE SETTING MUST NOT PICK A VENDOR, AND MUST NOT CRASH.
    #
    # This runs detached from the request that triggered it, so an exception
    # here surfaces NOWHERE and leaves the certidão with no analysis and no
    # reason — the failure this module's header forbids ("every path ends in
    # a recorded status"). `resolve_api_key_detail` catches only
    # `EncryptionNotConfigured`; an unconfigured Supabase raises
    # `SupabaseException: supabase_url is required` straight through it.
    #
    # And the recovery is deliberately NOT "assume OpenAI". Defaulting here
    # would run an org that chose Anthropic on the other vendor, with nothing
    # said — the exact silent switch the manual-switch design exists to
    # prevent. Refusing with a stated reason is the only honest answer: the
    # certificate itself is already issued and valid, only the summary is
    # missing, and the operator can retry once the setting reads.
    try:
        provider = resolver(org_id)
    except Exception as exc:  # noqa: BLE001 — background job must not die
        logger.error(
            "AI analysis skipped — could not read the analysis-provider "
            "setting for org=%s: %s",
            org_id, exc,
        )
        return (
            "[Análise IA não disponível — não foi possível ler a configuração "
            "de provedor de análise. A certidão em si é válida; tente "
            "novamente ou verifique Configurações → Chaves de API]"
        )

    modelo = ANALYSIS_MODELS.get(provider, ANALYSIS_MODELS[DEFAULT_ANALYSIS_PROVIDER])
    api_key = resolve_key(provider_api_key(provider), org_id)
    if not api_key:
        logger.warning(
            "AI analysis skipped — %s not configured (selected provider)",
            provider_api_key(provider),
        )
        spec = get_spec(provider_api_key(provider))
        rotulo = spec.label if spec else provider_api_key(provider)
        return (
            f"[Análise IA não disponível — {rotulo} não configurada. "
            "É o provedor selecionado para análise de documentos. "
            "Configure em Configurações → Chaves de API]"
        )

    try:
        return await chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você é um analista jurídico. Analise o conteúdo desta certidão "
                        "e forneça um resumo claro da situação da pessoa/empresa mencionada. "
                        "Foque em: existência de débitos, pendências, restrições ou se está tudo regular. "
                        "Responda em português."
                    ),
                },
                {"role": "user", "content": text},
            ],
            model=modelo,
            provider=provider,
            org_id=org_id,
            max_tokens=1000,
        )
    except Exception as e:
        # The vendor's raw exception (often English, sometimes JSON-shaped —
        # e.g. `AsyncMessages.create() got an unexpected keyword argument
        # 'temperature'`, seen in prod on every non-612 certidão since
        # 2026-09-10) must never land in `analise_ia`: a due-diligence
        # operator reads that column as the document's content, not as an
        # error channel. NULL + a logged error is the honest answer — the
        # certificate itself is unaffected, only the summary is missing, and
        # the log line (not the column) is where an operator/on-call looks
        # for WHY.
        logger.error(
            "AI analysis failed for org=%s, provider=%s: %s",
            org_id, provider, e,
        )
        return None


def _is_iso_date(value: str) -> bool:
    """Is `value` a well-formed `YYYY-MM-DD`? Used to sanitize an LLM's JSON
    answer before it reaches a `DATE` column — a model that ignores the
    format instruction and answers `"15 de março de 2026"` must not reach
    Postgres as a date, silently or otherwise."""
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _parse_json_resultado(raw: Optional[str], nome_display: str) -> Optional[dict]:
    """Defensive JSON parse of `_analyze_estrutura_with_ai`'s own response.

    LLMs fence JSON in ``` even when told not to; this strips a fence before
    parsing rather than failing on it. Any field outside the CHECK-
    constrained `resultado` vocabulary, or an unparseable payload, or a
    non-dict payload is DROPPED rather than written — a malformed AI answer
    must never reach the database as a confident-looking value. This module's
    own `_analyze_with_ai` header names exactly that failure class for the
    free-text column; the structured one has more surface for it, not less,
    because here a malformed answer could otherwise land in a real column
    instead of a text blob a human reads skeptically.
    """
    if not raw:
        return None
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned[:4].lower() == "json":
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        parsed = json.loads(cleaned)
    except (ValueError, TypeError):
        logger.warning(
            "Structured AI extraction for %s returned unparseable JSON: %r",
            nome_display, raw[:200],
        )
        return None
    if not isinstance(parsed, dict):
        return None

    out: dict = {}
    numero = parsed.get("numero")
    if isinstance(numero, str) and numero.strip():
        out["numero"] = numero.strip()
    for key in ("emitida_em", "validade_ate"):
        value = parsed.get(key)
        if isinstance(value, str) and _is_iso_date(value):
            out[key] = value
    resultado = parsed.get("resultado")
    if resultado in RESULTADO_VALUES:
        out["resultado"] = resultado
    return out or None


async def _analyze_estrutura_with_ai(
    text: str,
    nome_display: str,
    org_id: Optional[str] = None,
    *,
    resolve_provider: Optional[Callable[[Optional[str]], str]] = None,
) -> Optional[dict]:
    """Ask the same seed `chat_completion` wrapper for the STRUCTURED
    determination (`numero`/`emitida_em`/`validade_ate`/`resultado`) instead
    of `_analyze_with_ai`'s free-text summary — the fallback `_derive_
    estrutura` reaches for when neither the raw API response
    (`registry.parse_resultado`) nor a human already say what `resultado` is.

    Returns `None` on ANY failure — unconfigured provider, unresolvable key,
    a raised exception, or unparseable JSON. Unlike `_analyze_with_ai`, whose
    PT-BR marker string is meant to be READ by a human in the free-text
    analysis column, a failure here has nowhere honest to go in a `numero`/
    `resultado` column, so the caller's own fields simply stay whatever they
    already were (never downgraded to a guess, never a stack trace surfacing
    on a background job — same posture `_analyze_with_ai` documents for the
    identical class of failure, applied to a return shape that cannot carry
    a PT-BR sentence).
    """
    from app.services.api_keys_store import resolve_chat_provider

    resolver = resolve_provider or resolve_chat_provider
    try:
        provider = resolver(org_id)
    except Exception as exc:  # noqa: BLE001 — background job must not die
        logger.error(
            "Structured AI extraction skipped for %s — could not read the "
            "analysis-provider setting for org=%s: %s",
            nome_display, org_id, exc,
        )
        return None

    modelo = ANALYSIS_MODELS.get(provider, ANALYSIS_MODELS[DEFAULT_ANALYSIS_PROVIDER])
    api_key = resolve_key(provider_api_key(provider), org_id)
    if not api_key:
        logger.warning(
            "Structured AI extraction skipped for %s — %s not configured "
            "(selected provider)",
            nome_display, provider_api_key(provider),
        )
        return None

    try:
        raw = await chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você é um analista jurídico. Leia esta certidão e "
                        "responda APENAS com um JSON (sem markdown, sem texto "
                        "adicional) com estas chaves: numero (string ou null), "
                        "emitida_em (data de emissão do documento, formato "
                        "YYYY-MM-DD ou null — se o documento não tiver uma "
                        "data de emissão explícita, use a data da consulta/"
                        "pesquisa quando o documento indicar uma, por exemplo "
                        "um relatório Serasa), validade_ate (formato "
                        "YYYY-MM-DD ou null), resultado (um destes valores "
                        "exatos: negativa, positiva, "
                        "positiva_com_efeito_de_negativa, nao_emitida, "
                        "negativa_com_homonimos — este último quando o "
                        "documento é negativo mas menciona homônimos ou "
                        "multiplicidade de registros sob o mesmo nome/CPF que "
                        "impedem confirmar a identidade com plena certeza — "
                        "ou null se não for possível determinar com confiança)."
                    ),
                },
                {"role": "user", "content": text},
            ],
            model=modelo,
            provider=provider,
            org_id=org_id,
            max_tokens=300,
        )
    except Exception as e:
        logger.error("Structured AI extraction failed for %s: %s", nome_display, e)
        return None

    return _parse_json_resultado(raw, nome_display)


async def _derive_estrutura(
    *,
    config: Optional[dict],
    result: Optional[dict],
    texto_para_ia: Optional[str],
    nome_display: str,
    org_id: Optional[str],
    travado: bool,
    analyze_estrutura: Callable[..., Any],
) -> dict:
    """The structured-field patch (`numero`/`emitida_em`/`validade_ate`/
    `resultado`, plus `resultado_origem`) for one resultado: the raw API
    response first, an AI structured read only for what that left
    undetermined, and NOTHING AT ALL when a human already owns this
    resultado's fields.

    🔴 `travado` IS THE ENFORCEMENT SIDE OF MIGRATION 107'S HEADER. A
    resultado with `resultado_origem='manual'` or a non-null `confirmado_por`
    was reviewed by a human — a reprocess, a retry, or a later manual upload
    on the SAME resultado must never silently overwrite that, including with
    a MORE confident-looking automated read. The caller (`_process_single_
    certidao` / `process_manual_upload`) computes `travado` off the row it
    already fetched; this function never reads the database itself.

    🔴 `resultado_origem` TRACKS THE VERDICT, NOT "DID ANY FIELD COME FROM
    THE API". `registry.parse_resultado` can legitimately fill `numero`/
    dates while leaving `resultado` itself undetermined (see its own
    docstring); when the AI leg THEN supplies the verdict, the row's origin
    is "ia" even though a `numero` also landed from the API — a due-
    diligence reader asking "who decided this was negativa" needs THAT
    answer, not "something here came from InfoSimples".
    """
    if travado:
        return {}
    patch: dict = {}
    origem: Optional[str] = None
    if config and result:
        parsed = parse_resultado(config, result)
        if parsed:
            patch.update(parsed)
            origem = "api"
    if "resultado" not in patch and texto_para_ia:
        via_ia = await analyze_estrutura(texto_para_ia, nome_display, org_id)
        if via_ia:
            for k, v in via_ia.items():
                patch.setdefault(k, v)
            origem = "ia"
    if patch:
        patch["resultado_origem"] = origem
    return patch


@dataclass(frozen=True)
class ExtractedPdfText:
    """`_extract_pdf_text`'s result, shaped for its TWO consumers.

    `para_ia` is the AI-analysis input — UNCHANGED by migration 113 (still
    `"Certidão: <nome>\\n\\n<text[:4000]>"`, still `None` when nothing
    trustworthy is there). `texto_extraido` / `formatacao` are the
    UNTRUNCATED transcript and its inline formatting, persisted onto
    `certidao_resultados` for the `.../transcricao` routes. A transcription
    that finds nothing, or that raises, is `ExtractedPdfText(para_ia=None)`
    — logged, never raised; see `_extract_pdf_text`.
    """

    para_ia: Optional[str]
    texto_extraido: Optional[str] = None
    formatacao: tuple[FormatRange, ...] = ()
    #: PT-BR sentence a UI can render when the transcription leg did NOT
    #: produce a trustworthy read — `None` on success (including the benign
    #: "nothing to extract" case an empty PDF page produces). Independent of
    #: `para_ia`/`texto_extraido` being `None`: those already mean "nothing
    #: usable came out"; this says WHY, for the one caller
    #: (`process_manual_extraction`) that persists it onto the row. See
    #: `_extract_pdf_text`.
    erro: Optional[str] = None


#: Vision pages a certidão transcription may bill. 0 = text layer only (the
#: free, exact rung). See `_extract_pdf_text` for why this is a cost decision,
#: and why the vision provider is only resolved when this is above 0.
CERTIDAO_MAX_VISION_PAGES = 0

#: The MANUAL-upload sibling of the constant above — a bounded, one-time,
#: human-triggered read, not a recurring scheduler bill. A human just
#: uploaded a PDF the automation could not obtain; keeping this at 0 (migration
#: 113's original choice, made for the SCHEDULER path) meant a scanned
#: certidão got no analysis, no structured fields, and nothing said about why
#: — indistinguishable from "nothing was ever asked to read it". 3 pages
#: covers every certificate this registry issues (`CERTIDOES_CONFIG` — none of
#: them is a multi-page bundle); `too_many_vision_pages` is the honest refusal
#: for the one that would exceed it, never a silent partial read. Only
#: `process_manual_extraction` uses this — the scheduler flow
#: (`_process_single_certidao`) keeps `CERTIDAO_MAX_VISION_PAGES` unchanged.
CERTIDAO_MANUAL_MAX_VISION_PAGES = 3

#: D3 (KB roadmap `sw-extraction-contract-gate-2026-09.md`). How many times
#: `process_manual_extraction` may be STARTED for one resultado, including the
#: first — same shape `card_hub.identidade_extracao_service.MAX_TENTATIVAS`
#: already established, and the same reasoning: a deterministically-broken
#: read (a corrupt PDF, an exhausted quota, a revoked key) must not be retried
#: forever by `recover_stale_processando`, paying for a vision call on every
#: pass. 3 = the first attempt plus 2 automatic retries.
MAX_ESTRUTURA_TENTATIVAS = 3

#: PT-BR sentences for `ExtractedPdfText.erro` / `certidao_resultados.
#: estrutura_erro` — a due-diligence operator reads this COLUMN, never a log
#: line, so the vendor's own error code (`_classify_failure`'s vocabulary,
#: `transcription.py`) is translated here rather than written raw. Falls back
#: to a generic-but-still-PT-BR sentence carrying the code for anything this
#: module has not named yet — never a bare English exception string (the same
#: rule `_analyze_with_ai`'s docstring states for `analise_ia`).
_ESTRUTURA_ERRO_MENSAGENS: dict[str, str] = {
    "no_pages": "Não foi possível abrir o PDF (arquivo corrompido ou inválido).",
    "too_many_vision_pages": (
        "Documento digitalizado tem mais páginas do que o limite permitido "
        "para leitura por IA."
    ),
    "missing_credentials": (
        "Provedor de IA de visão não configurado. Configure em "
        "Configurações → Chaves de API."
    ),
    "insufficient_quota": (
        "Cota do provedor de IA esgotada. Verifique o faturamento em "
        "Configurações → Chaves de API."
    ),
    "rate_limited": "Limite de requisições do provedor de IA atingido.",
    "invalid_credentials": (
        "Credencial do provedor de IA inválida. Verifique em "
        "Configurações → Chaves de API."
    ),
    "rasterize_failed": (
        "Falha ao converter o documento digitalizado em imagem para leitura."
    ),
    "transcription_failed": "Falha inesperada ao ler o documento digitalizado.",
    "vision_disabled": "Documento digitalizado — leitura por IA desabilitada.",
    "empty_document": "Arquivo vazio — nada para ler.",
}


def _estrutura_erro_mensagem(codigo: Optional[str]) -> Optional[str]:
    """`codigo` (a `Transcription.error` value) → the PT-BR sentence
    `estrutura_erro` stores, or `None` when there is nothing to report."""
    if not codigo:
        return None
    return _ESTRUTURA_ERRO_MENSAGENS.get(
        codigo, f"Falha na leitura automática do documento ({codigo})."
    )


async def _extract_pdf_text(
    pdf_bytes: bytes,
    nome_display: str,
    org_id: Optional[str] = None,
    *,
    max_vision_pages: int = CERTIDAO_MAX_VISION_PAGES,
) -> ExtractedPdfText:
    """Extract text (and its formatting) from a certidão PDF.

    Goes through the seed transcriber (`documents.make_document_transcriber`)
    rather than a bare `get_text()` sweep, so a scanned certidão — whose text
    layer is a digital-signature stamp, not content — is not handed to
    `_analyze_with_ai` (nor persisted) as if it were the document.

    `max_vision_pages` defaults to `CERTIDAO_MAX_VISION_PAGES` (0 — text layer
    only), UNCHANGED by migration 113 for the scheduler flow
    (`_process_single_certidao`), which never passes this argument.
    `process_manual_extraction` passes `CERTIDAO_MANUAL_MAX_VISION_PAGES`
    instead — see that constant's own docstring for why the two paths differ.

    Never raises: a failed or empty transcription is
    `ExtractedPdfText(para_ia=None, erro=...)` (contract §4 — "never fails the
    certidão"). `erro` carries the PT-BR reason (`None` on success, including
    the benign case where nothing was there to read) — the automated flow
    ignores it entirely (unchanged behaviour); `process_manual_extraction` is
    the one caller that persists it onto `certidao_resultados.estrutura_erro`.
    The `vision_disabled` case is ALSO logged (never silently dropped) rather
    than just carried in `erro`: a scanned certidão getting no AI analysis
    should be visible in the logs too, not inferred from an empty column.
    """
    try:
        from noctusai_lib.integrations.documents import make_document_transcriber

        from app.services.api_keys_store import resolve_vision_provider

        # The provider is resolved ONLY when the cap lets a page reach a vision
        # model. At 0 no vendor can ever be called, and resolving it anyway
        # made a text-layer-only transcription depend on a credential lookup:
        # without Supabase config it raised, the broad `except` below turned
        # that into "no transcript", and every certidão silently lost its AI
        # analysis. Tying both to ONE parameter keeps the original intent — a
        # caller that raises the cap gets the vendor the operator picked, not
        # the seed default.
        provider = (
            resolve_vision_provider(org_id) if max_vision_pages > 0 else None
        )
        transcriber = make_document_transcriber(
            real=True,
            org_id=org_id,
            max_vision_pages=max_vision_pages,
            provider=provider,
        )
        resultado = await transcriber.transcribe(
            pdf_bytes, mimetype="application/pdf"
        )
        erro: Optional[str] = None
        if resultado.error == "vision_disabled":
            logger.info(
                "Certidão %s: %s — analysing the %d page(s) with a real text layer",
                nome_display, resultado.error_message, len(resultado.pages),
            )
            erro = _estrutura_erro_mensagem(resultado.error)
        elif not resultado.ok:
            logger.warning(
                "Certidão %s: transcription failed (%s) %s",
                nome_display, resultado.error, resultado.error_message or "",
            )
            erro = _estrutura_erro_mensagem(resultado.error)

        extracted = resultado.text
        if not extracted:
            return ExtractedPdfText(para_ia=None, erro=erro)
        # Prefix with certificate type for context (mirrors how the automated
        # flow sends structured API response data). Truncate to avoid exceeding
        # token limits. UNCHANGED shape — see `ExtractedPdfText.para_ia`.
        para_ia = f"Certidão: {nome_display}\n\n{extracted[:4000]}"
        return ExtractedPdfText(
            para_ia=para_ia,
            texto_extraido=extracted,
            formatacao=resultado.formatting,
            erro=erro,
        )
    except Exception as e:
        logger.warning("PDF text extraction failed: %s", e)
        return ExtractedPdfText(
            para_ia=None, erro=_estrutura_erro_mensagem("transcription_failed")
        )


# --------------- One certificate ---------------


async def _process_single_certidao(
    config: dict,
    consulta: dict,
    infosimples_token: str,
    db,
    resultado_id: str,
    http_client: httpx.AsyncClient,
    storage: StorageBackend,
    *,
    analyze: Optional[Callable[..., Any]] = None,
    analyze_estrutura: Optional[Callable[..., Any]] = None,
    extract_text: Optional[Callable[..., Any]] = None,
    core_db: Any = None,
) -> None:
    """Process a single certificate: fetch → download → store → analyze → update.

    Updates the parent consulta's progress (concluidas count) after each
    certificate finishes so the frontend progress bar updates in real-time.

    `analyze` is the AI-analysis seam, defaulting to `_analyze_with_ai`. It is
    a parameter so a test can inject a stub INSTEAD of patching our own
    `_analyze_with_ai` out of the module — the InfoSimples call itself needs no
    such seam, because `http_client` already is one (drive the fake client and
    the real retry / 612 / error-extraction logic runs, which is the point).
    `analyze_estrutura` is the same seam for `_derive_estrutura`'s AI leg,
    defaulting to `_analyze_estrutura_with_ai`. `extract_text` is the same
    shape for the transcription leg (migration 113), defaulting to
    `_extract_pdf_text` — separate from `analyze`: THIS flow's AI analysis
    reads the API's own response summary, never the PDF text, so
    `extract_text`'s only job here is persisting `texto_extraido` /
    `formatacao` for the `.../transcricao` routes.
    `core_db` is the Custos-page cost-booking seam (`cost_ledger.
    book_infosimples_cost`) — the `public.cost_ledger` client, DIFFERENT
    from `db` above (social_wiring schema). Same DI-seam shape: `None`
    (every existing caller) lazily resolves `app.database.get_core_client()`
    at call time, matching production; a test injects a fake instead of
    patching our own `get_core_client` out of the module.
    → KB § PATTERNS/backend/di-test-seam.md
    """
    analyze = analyze or _analyze_with_ai
    analyze_estrutura = analyze_estrutura or _analyze_estrutura_with_ai
    extract_text = extract_text or _extract_pdf_text
    consulta_id = consulta["id"]
    org_id = consulta.get("org_id")
    nome_display = config.get("nome", config["tipo"])

    # Read BEFORE touching status — a resultado a human already confirmed or
    # manually corrected must keep its structured fields untouched by this
    # run, including on a reprocess. See `_derive_estrutura`'s docstring.
    atual_rows = (
        db.table(RESULTADOS)
        .select("resultado_origem, confirmado_por")
        .eq("id", resultado_id)
        .execute()
    ).data or []
    travado = bool(atual_rows) and (
        atual_rows[0].get("resultado_origem") == "manual"
        or bool(atual_rows[0].get("confirmado_por"))
    )

    # Update status to processando and record when the API call is about to
    # happen. api_requested_at survives status resets (reprocessing) so the
    # TJSP cooldown is always enforced — even after a resultado is reset from
    # "erro" to "na_fila".
    db.table(RESULTADOS).update({
        "status": "processando",
        "api_requested_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", resultado_id).execute()

    # Fetch from InfoSimples
    result = await _fetch_certidao(config, consulta, infosimples_token, http_client)

    # Book the InfoSimples spend regardless of success/erro — a "nada
    # consta" (612) or a definitive 4xx API error still consumed a billed
    # call at the source; only a call that never got a parseable response
    # (raw_response=None — network/timeout on every retry) has nothing to
    # bill. Never breaks certidão issuance: `book_infosimples_cost` never
    # raises and every skip path is a WARNING log, not a silent no-op.
    if result.get("raw_response") is not None:
        _core_db = core_db
        if _core_db is None:
            # 🔴 Resolved INSIDE the never-break boundary. Outside it, a
            # ledger client that cannot be built (no SUPABASE_URL — CI) raised
            # straight through and failed the certidão itself: 17 red tests on
            # 922c6831, green locally only because a worktree's .env symlink
            # supplied the URL. Booking a cost must never cost the certidão.
            try:
                from app.database import get_core_client
                _core_db = get_core_client()
            except Exception as exc:  # noqa: BLE001 - booking is best-effort
                logger.warning(
                    "infosimples cost_ledger: core client unavailable, consulta %s "
                    "not booked: %s", resultado_id, exc,
                )
    if result.get("raw_response") is not None and _core_db is not None:
        cost_ledger.book_infosimples_cost(
            _core_db,
            org_id=org_id,
            tipo=config["tipo"],
            raw_response=result["raw_response"],
            reference_id=resultado_id,
        )

    if not result["success"]:
        db.table(RESULTADOS).update({
            "status": "erro",
            "erro_mensagem": result["error"],
            "api_response": result["raw_response"],
        }).eq("id", resultado_id).execute()
        _atualizar_status_consulta(consulta_id, org_id, db)
        return

    file_url = result["file_url"]
    arquivo_url = file_url
    is_html = config["response_format"] == "html"
    # Migration 113: every PDF this pipeline STORES is also transcribed, so
    # the `.../transcricao` routes have something to serve. Stays
    # `ExtractedPdfText(None)` (never persisted — see the two `update_data`
    # sites below) when nothing gets stored, e.g. an unrecognised
    # content-type or a download failure.
    extracted_doc = ExtractedPdfText(para_ia=None)

    # Download the document and persist it to our own bucket so we don't depend
    # on InfoSimples keeping the site_receipt URL alive.
    if file_url:
        download_result = await _download_file(file_url, http_client)
        if download_result:
            raw_bytes, content_type = download_result
            already_pdf = raw_bytes[:5] == b"%PDF-"

            if already_pdf:
                # Content is already a valid PDF — use as-is
                pdf_bytes = raw_bytes
            elif is_html or "text/html" in content_type:
                # HTML content (either from config or detected via content-type)
                # → convert to PDF
                html_to_convert = raw_bytes
                if config["tipo"] == "cenprot":
                    protocolo = _cenprot_protocolo_consulta(result.get("raw_response"))
                    if protocolo:
                        html_to_convert = _with_protocolo_stamp(raw_bytes, protocolo)
                try:
                    pdf_bytes = await asyncio.wait_for(
                        asyncio.to_thread(_convert_html_to_pdf, html_to_convert),
                        timeout=HTML_TO_PDF_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    logger.error(
                        "HTML→PDF conversion for %s exceeded %ds",
                        config["tipo"], HTML_TO_PDF_TIMEOUT_SECONDS,
                    )
                    pdf_bytes = None
                if not pdf_bytes:
                    logger.warning(
                        "HTML→PDF conversion failed for %s, keeping original URL",
                        config["tipo"],
                    )
            elif "application/pdf" in content_type:
                # Server says it's a PDF but missing magic bytes — trust the server
                pdf_bytes = raw_bytes
            else:
                # Unknown content type — not a PDF, not HTML. Skip storage.
                logger.warning(
                    "Unexpected content-type %s for %s (first bytes: %r), keeping original URL",
                    content_type, config["tipo"], raw_bytes[:20],
                )
                pdf_bytes = None

            if pdf_bytes:
                stored_key = await _persist_pdf(
                    pdf_bytes, storage, org_id, consulta_id, config["tipo"]
                )
                if stored_key:
                    arquivo_url = stored_key
                    extracted_doc = await extract_text(
                        pdf_bytes, nome_display, org_id
                    )
        else:
            logger.warning(
                "Failed to download file for %s from %s, keeping original URL",
                config["tipo"], file_url,
            )

    # "Nada consta" (e.g., no protests found) — success with NO AI call: the
    # verdict is the source's own. Deliberately AFTER the download block: the
    # source's receipt, when it sent one (CENPROT always does), is stored like
    # any other document so the row can be viewed and downloaded.
    if result.get("nada_consta"):
        update_data = {
            "status": "sucesso",
            "analise_ia": result["nada_consta"],
            "api_response": result["raw_response"],
            "erro_mensagem": None,
            "texto_extraido": extracted_doc.texto_extraido,
            "formatacao": ranges_to_json(extracted_doc.formatacao),
        }
        if arquivo_url:
            update_data["arquivo_url"] = arquivo_url
            update_data["arquivo_nome"] = f"{config['tipo']}.pdf"
        update_data.update(await _derive_estrutura(
            config=config, result=result, texto_para_ia=None,
            nome_display=nome_display, org_id=org_id, travado=travado,
            analyze_estrutura=analyze_estrutura,
        ))
        db.table(RESULTADOS).update(update_data).eq("id", resultado_id).execute()
        _atualizar_status_consulta(consulta_id, org_id, db)
        return

    # AI analysis (use raw response summary as text input)
    analise = None
    text_for_analysis = None
    raw = result["raw_response"]
    if raw and raw.get("data"):
        summary_parts = []
        for item in raw["data"]:
            if isinstance(item, dict):
                for k, v in item.items():
                    if k != "site_receipt" and v:
                        summary_parts.append(f"{k}: {v}")
        if summary_parts:
            text_for_analysis = "\n".join(summary_parts)
            analise = await analyze(text_for_analysis, org_id)

    # Update resultado — always store as .pdf
    update_data = {
        "status": "sucesso",
        "arquivo_url": arquivo_url,
        "arquivo_nome": f"{config['tipo']}.pdf",
        "analise_ia": analise,
        "api_response": result["raw_response"],
        "erro_mensagem": None,
        "texto_extraido": extracted_doc.texto_extraido,
        "formatacao": ranges_to_json(extracted_doc.formatacao),
    }
    update_data.update(await _derive_estrutura(
        config=config, result=result, texto_para_ia=text_for_analysis,
        nome_display=nome_display, org_id=org_id, travado=travado,
        analyze_estrutura=analyze_estrutura,
    ))
    db.table(RESULTADOS).update(update_data).eq("id", resultado_id).execute()
    _atualizar_status_consulta(consulta_id, org_id, db)


def _atualizar_status_consulta(consulta_id: str, org_id: Optional[str], db) -> None:
    """Recalculate and update the consulta's progress and status.

    Called after each certificate finishes (success or error) so the frontend
    progress bar updates in real-time. Also called by the TJSP queue worker
    after processing queued items.

    Status logic:
    - Any resultado still pending/processing/queued → "processando"
    - All done, at least one success → "concluida"
    - All done, zero successes → "erro"
    """
    query = db.table(RESULTADOS).select("status").eq("consulta_id", consulta_id)
    if org_id:
        query = query.eq("org_id", str(org_id))
    rows = query.execute().data or []

    sucessos = sum(1 for r in rows if r["status"] == "sucesso")
    erros = sum(1 for r in rows if r["status"] == "erro")
    still_pending = sum(
        1 for r in rows if r["status"] in ("pendente", "processando", "na_fila")
    )

    if still_pending > 0:
        final_status = "processando"
    elif sucessos == 0 and erros > 0:
        final_status = "erro"
    else:
        final_status = "concluida"

    db.table(CONSULTAS).update({
        "status": final_status,
        "concluidas": sucessos,
    }).eq("id", consulta_id).execute()


# --------------- One consulta ---------------


async def processar_consulta(
    consulta_id: str,
    db,
    storage: StorageBackend,
    *,
    process_one: Optional[Callable[..., Any]] = None,
    schedule_tjsp: Optional[Callable[..., Any]] = None,
) -> None:
    """Process all certificates for a consulta (runs in background).

    All certificates are processed in parallel. TJSP is included if the
    cooldown has passed; otherwise it's queued ("na_fila") for the on-demand
    scheduler. A premature TJSP request RESETS the API counter, so we never
    fire before the cooldown expires.

    `process_one` / `schedule_tjsp` are DI seams (default: the real
    `_process_single_certidao` / `schedule_tjsp_for_org`) so a test can assert
    the FAN-OUT decisions this function makes — which resultados run now, which
    are queued — without each one firing a real pipeline.
    → KB § PATTERNS/backend/di-test-seam.md
    """
    process_one = process_one or _process_single_certidao
    schedule_tjsp = schedule_tjsp or schedule_tjsp_for_org
    consulta_result = db.table(CONSULTAS).select("*").eq(
        "id", consulta_id
    ).single().execute()
    consulta = consulta_result.data
    if not consulta:
        logger.error("certidoes: consulta %s not found — nothing to process", consulta_id)
        return
    org_id = consulta.get("org_id")

    db.table(CONSULTAS).update({
        "status": "processando",
    }).eq("id", consulta_id).execute()

    # postgrest-unbounded-ok: one resultado per registry type per consulta
    # (exactly `len(CERTIDOES_CONFIG)`, 10 today) — 10 rows, not 1 000.
    resultados_result = db.table(RESULTADOS).select("*").eq(
        "consulta_id", consulta_id
    ).order("ordem").execute()
    resultados = resultados_result.data or []

    # Validate InfoSimples token — required for certificate issuance
    infosimples_token = _get_infosimples_token(org_id)
    if not infosimples_token:
        error_msg = (
            "Token InfoSimples não configurado. "
            "Configure em Configurações → Chaves de API."
        )
        logger.error("InfoSimples token missing for consulta %s", consulta_id)
        resultado_ids = [r["id"] for r in resultados]
        for batch in in_batches(resultado_ids):
            db.table(RESULTADOS).update({
                "status": "erro",
                "erro_mensagem": error_msg,
            }).in_("id", batch).execute()
        db.table(CONSULTAS).update({
            "status": "erro",
            "concluidas": 0,
        }).eq("id", consulta_id).execute()
        return

    # Only process resultados that are pending (skip already succeeded ones)
    pending = [r for r in resultados if r["status"] == "pendente"]

    tjsp_pending = [r for r in pending if r["tipo"] == TJSP_TIPO]
    non_tjsp_pending = [r for r in pending if r["tipo"] != TJSP_TIPO]

    # Check TJSP cooldown — if clear, process in parallel; otherwise queue
    tjsp_can_run = False
    if tjsp_pending:
        last_at = _get_tjsp_last_request_at(org_id, db) if org_id else None
        if last_at:
            elapsed = (datetime.now(timezone.utc) - last_at).total_seconds()
            tjsp_can_run = elapsed >= TJSP_COOLDOWN_SECONDS
            if not tjsp_can_run:
                remaining = TJSP_COOLDOWN_SECONDS - elapsed
                logger.info(
                    "TJSP cooldown active for org %s, %.0fs remaining — queuing",
                    org_id, remaining,
                )
        else:
            # No previous TJSP request — safe to run immediately
            tjsp_can_run = True

    async with httpx.AsyncClient() as http_client:
        tasks = []
        for r in non_tjsp_pending:
            config = config_for(r["tipo"])
            if not config:
                logger.warning(
                    "certidoes: resultado %s has tipo %r which is not in the "
                    "registry — skipping (the row stays 'pendente')",
                    r["id"], r["tipo"],
                )
                continue
            tasks.append(
                process_one(
                    config, consulta, infosimples_token, db, r["id"],
                    http_client, storage,
                )
            )
        if tjsp_can_run:
            for r in tjsp_pending:
                config = config_for(r["tipo"])
                if config:
                    tasks.append(
                        process_one(
                            config, consulta, infosimples_token, db, r["id"],
                            http_client, storage,
                        )
                    )
                    logger.info(
                        "TJSP resultado %s processing immediately (cooldown clear)",
                        r["id"],
                    )
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            logger.error("Certificate processing failed: %s", result)

    # Queue TJSP items that couldn't run due to cooldown, and schedule the
    # deferred processing
    if not tjsp_can_run and tjsp_pending:
        tjsp_ids = [r["id"] for r in tjsp_pending]
        for batch in in_batches(tjsp_ids):
            db.table(RESULTADOS).update({
                "status": "na_fila",
            }).in_("id", batch).execute()
        for r in tjsp_pending:
            logger.info("TJSP resultado %s queued (na_fila) — cooldown active", r["id"])
        if org_id:
            schedule_tjsp(org_id, db, storage)

    _atualizar_status_consulta(consulta_id, org_id, db)


# --------------- Recovery ---------------


def recover_stale_processando(
    db,
    storage: Optional[StorageBackend] = None,
    *,
    http_client_factory: Optional[Callable[[], httpx.AsyncClient]] = None,
    schedule: Optional[Callable[..., Any]] = None,
) -> int:
    """Detect and recover resultados stuck in 'processando' for too long.

    Called on every list fetch (throttled) so the frontend never loops forever
    on stuck items. Uses `api_requested_at` to determine staleness — NOT
    `updated_at`, which may reflect the original creation time. Set right
    before the API call in `_process_single_certidao` for the automated flow,
    and right before scheduling the background extraction in
    `process_manual_upload` for a manual one — both mean the same thing here:
    "background work this row is waiting on started at this time".

    Only recovers items whose `api_requested_at` is older than the threshold.
    Items in 'processando' WITHOUT an `api_requested_at` are waiting to start
    and are handled by `recover_stuck_processando`.

    D3 (KB roadmap `sw-extraction-contract-gate-2026-09.md`). When `storage`
    is given, a stale row that already has a file in the bucket (`arquivo_url`
    — only true for a manual upload whose extraction leg stalled; the
    automated flow never writes `arquivo_url` before reaching `sucesso`) and
    has not exhausted `MAX_ESTRUTURA_TENTATIVAS` gets its structured/AI read
    RETRIED instead of closed out — `_retomar_extracao_manual`, scheduled
    fire-and-forget via `schedule` (default `schedule_coro`, the same
    primitive `schedule_tjsp_for_org` already uses in this module). Every
    other stale row — the automated InfoSimples flow, or a manual row that
    exhausted its retries or never actually made it to storage — keeps the
    original, unconditional "mark erro" behaviour; a human already has a
    reprocess button for those. `storage=None` (the default) is the pre-D3
    behaviour unchanged, so an existing caller (or a test with no storage
    backend to inject) is unaffected.

    Returns the total number of items this call acted on — retried plus
    closed out.
    """
    cutoff = (
        datetime.now(timezone.utc) - timedelta(seconds=STALE_PROCESSANDO_SECONDS)
    ).isoformat()

    # Fetch all "processando" items, then filter in Python for stale ones. We
    # can't use `.lt("api_requested_at", cutoff)` directly because items
    # without api_requested_at (NULL) would be silently included or excluded
    # depending on the PostgREST version.
    def _page(start: int, end: int):
        return (
            db.table(RESULTADOS)
            .select(
                "id, tipo, nome_display, consulta_id, org_id, api_requested_at, "
                "arquivo_url, estrutura_tentativas"
            )
            .eq("status", "processando")
            .order("id")
            .range(start, end)
            .execute()
            .data
        )

    stuck = _all_rows(_page, "certidao_resultados processando")

    stale = [
        item for item in stuck
        if item.get("api_requested_at") and item["api_requested_at"] < cutoff
    ]

    if not stale:
        return 0

    retry_candidates: list[dict] = []
    terminal = stale
    if storage is not None:
        retry_candidates = [
            item for item in stale
            if item.get("arquivo_url")
            and int(item.get("estrutura_tentativas") or 0) < MAX_ESTRUTURA_TENTATIVAS
        ]
        retry_ids = {item["id"] for item in retry_candidates}
        terminal = [item for item in stale if item["id"] not in retry_ids]

    if retry_candidates:
        _agendar_retomada_extracao_manual(
            db, retry_candidates, storage,
            http_client_factory=http_client_factory, schedule=schedule,
        )

    if not terminal:
        return len(retry_candidates)

    logger.warning(
        "Auto-recovering %d stale 'processando' items (>%ds old)",
        len(terminal), STALE_PROCESSANDO_SECONDS,
    )

    stale_ids = [item["id"] for item in terminal]
    for batch in in_batches(stale_ids):
        db.table(RESULTADOS).update({
            "status": "erro",
            "erro_mensagem": (
                "Processamento expirou — a automação foi interrompida. "
                "Tente reprocessar ou faça upload manual."
            ),
        }).in_("id", batch).execute()

    consultas: dict[str, Optional[str]] = {}
    for item in terminal:
        consultas[item["consulta_id"]] = item.get("org_id")
        logger.info(
            "Auto-recovered stale resultado %s (api_requested_at=%s) → erro",
            item["id"], item["api_requested_at"],
        )

    for cid, oid in consultas.items():
        _atualizar_status_consulta(cid, oid, db)

    return len(retry_candidates) + len(terminal)


def _agendar_retomada_extracao_manual(
    db,
    candidates: list[dict],
    storage: StorageBackend,
    *,
    http_client_factory: Optional[Callable[[], httpx.AsyncClient]],
    schedule: Optional[Callable[..., Any]],
) -> None:
    """Fire-and-forget one `_retomar_extracao_manual` per stale manual-upload
    candidate. Split out of `recover_stale_processando` (a SYNC function — the
    retry itself is async) so each row's own `schedule_coro` call is
    independent: one row's task failing to schedule must not stop the others
    from being retried, or the delete-storage-files-on-error class of bug this
    module's other sweeps avoid would apply here too.
    """
    schedule_fn = schedule or schedule_coro
    client_factory = http_client_factory or httpx.AsyncClient

    async def _retry(item: dict, tentativa: int) -> None:
        async with client_factory() as http_client:
            await _retomar_extracao_manual(
                db=db,
                storage=storage,
                http_client=http_client,
                resultado_id=item["id"],
                consulta_id=item["consulta_id"],
                org_id=item.get("org_id"),
                nome_display=item.get("nome_display") or item.get("tipo") or "certidão",
                arquivo_url=item["arquivo_url"],
                tentativa=tentativa,
            )

    for item in candidates:
        tentativa = int(item.get("estrutura_tentativas") or 0) + 1
        logger.info(
            "Certidão %s (resultado %s): retomando extração manual — "
            "tentativa %d/%d",
            item.get("nome_display"), item["id"], tentativa,
            MAX_ESTRUTURA_TENTATIVAS,
        )
        schedule_fn(
            _retry(item, tentativa),
            logger=logger,
            name=f"certidao_extracao_manual_retry_{item['id']}",
        )


def recover_stuck_processando(db) -> None:
    """Reset orphaned "processando" items left by killed background tasks.

    Non-TJSP items go back to "pendente", TJSP items go back to "na_fila" so
    they are picked up by `schedule_all_pending_tjsp`.

    🔴 UNCONDITIONAL — it resets EVERY 'processando' row, including one a live
    task in this very process is working on. That is correct exactly once, at
    process START, when by definition no task of ours is running yet, and it is
    why the periodic sweep in `scheduler.py` calls `recover_stale_processando`
    (which has a 15-minute floor) instead of this one. See that module for the
    boot-time wiring.
    """
    def _page(start: int, end: int):
        return (
            db.table(RESULTADOS)
            .select("id, tipo, consulta_id, org_id")
            .eq("status", "processando")
            .order("id")
            .range(start, end)
            .execute()
            .data
        )

    items = _all_rows(_page, "certidao_resultados processando (startup)")
    if not items:
        return

    logger.warning("Recovering %d stuck 'processando' items on startup", len(items))

    tjsp_ids = [item["id"] for item in items if item["tipo"] == TJSP_TIPO]
    non_tjsp_ids = [item["id"] for item in items if item["tipo"] != TJSP_TIPO]

    for batch in in_batches(non_tjsp_ids):
        db.table(RESULTADOS).update({
            "status": "pendente",
            "erro_mensagem": None,
        }).in_("id", batch).execute()

    for batch in in_batches(tjsp_ids):
        db.table(RESULTADOS).update({
            "status": "na_fila",
            "erro_mensagem": None,
        }).in_("id", batch).execute()

    consultas: dict[str, Optional[str]] = {
        item["consulta_id"]: item.get("org_id") for item in items
    }
    for cid, oid in consultas.items():
        _atualizar_status_consulta(cid, oid, db)


def cancelar_processamento(consulta_id: str, org_id: Optional[str], db) -> dict:
    """Cancel in-progress certificate processing for one consulta.

    Resets every resultado of the consulta that is pendente/processando/na_fila
    to 'erro' with a cancellation message, and cancels any scheduled TJSP task
    for the affected orgs.

    Returns counts of cancelled items.
    """
    query = db.table(RESULTADOS).select("id, tipo, org_id").eq(
        "consulta_id", consulta_id
    ).in_("status", ["pendente", "processando", "na_fila"])
    if org_id:
        query = query.eq("org_id", str(org_id))
    items = query.execute().data or []
    if not items:
        return {"cancelados": 0}

    item_ids = [item["id"] for item in items]
    for batch in in_batches(item_ids):
        db.table(RESULTADOS).update({
            "status": "erro",
            "erro_mensagem": "Cancelado manualmente pelo usuário.",
        }).in_("id", batch).execute()

    org_ids = set(item.get("org_id") for item in items if item.get("org_id"))
    for oid in org_ids:
        task = _tjsp_scheduled_tasks.pop(oid, None)
        if task and not task.done():
            task.cancel()
            logger.info("Cancelled scheduled TJSP task for org %s", oid)

    _atualizar_status_consulta(consulta_id, org_id, db)

    logger.info(
        "Cancelled %d in-progress resultados for consulta %s", len(items), consulta_id
    )
    return {"cancelados": len(items)}


# --------------- Credentials ---------------


def _get_infosimples_token(org_id: Optional[str] = None) -> Optional[str]:
    """Resolve the InfoSimples token via this module's credential seam."""
    return resolve_key(INFOSIMPLES_TOKEN, org_id)


def check_required_credentials(org_id: Optional[str] = None) -> list[str]:
    """Which required credentials are missing for certificate issuance.

    Returns a list of human-readable messages, one per missing credential; an
    empty list means everything is configured.
    """
    missing = []
    if not resolve_key(INFOSIMPLES_TOKEN, org_id):
        missing.append(
            "Token InfoSimples não configurado — necessário para emissão de certidões."
        )
    return missing


# --------------- Manual upload ---------------


async def process_manual_upload(
    pdf_bytes: bytes,
    resultado_id: str,
    consulta: dict,
    tipo: str,
    nome_display: str,
    org_id: Optional[str],
    db,
    storage: StorageBackend,
) -> dict:
    """Persist a manually uploaded certificate PDF and mark the resultado
    `processando`. Returns fast — same reason `card_hub.router.
    upload_documento_route` and `imovel_hub`'s upload routes already split
    storage from extraction: storage is a single bucket `PUT`, but the
    structured/AI read that follows (`process_manual_extraction`) may need a
    vision call per page, and blocking the upload response on a per-page
    network round trip would make a routine upload feel broken.

    1. Put it in the bucket (same key shape `_process_single_certidao` uses)
    2. Mark the resultado `processando` with the file already attached, so
       `arquivo_url` (and therefore download/view) is available immediately
       even while the extraction leg is still running.

    The caller (`routers/certidoes.py::upload_certidao_manual`) schedules
    `process_manual_extraction` as a FastAPI `BackgroundTasks` job right
    after this returns — see that function's own docstring for the rest of
    the pipeline (AI analysis, structured-field determination, retry).
    """
    consulta_id = consulta["id"]
    arquivo_url = await _persist_pdf(pdf_bytes, storage, org_id, consulta_id, tipo)
    update_data: dict = {
        "status": "processando",
        # Reused, not a new column: `recover_stale_processando` already keys
        # staleness off this timestamp for the automated flow, and "the
        # background work this row is waiting on started at this time" is
        # exactly as true for the extraction leg about to be scheduled.
        "api_requested_at": datetime.now(timezone.utc).isoformat(),
        "arquivo_url": arquivo_url,
        "arquivo_nome": f"{tipo}.pdf",
        "api_response": None,
        "erro_mensagem": None,
        "estrutura_erro": None,
    }
    db.table(RESULTADOS).update(update_data).eq("id", resultado_id).execute()
    return update_data


async def process_manual_extraction(
    pdf_bytes: bytes,
    resultado_id: str,
    consulta_id: str,
    nome_display: str,
    org_id: Optional[str],
    db,
    *,
    resultado_origem_atual: Optional[str] = None,
    confirmado_por_atual: Optional[str] = None,
    tentativa: int = 1,
    extract_text: Optional[Callable[..., Any]] = None,
    analyze: Optional[Callable[..., Any]] = None,
    analyze_estrutura: Optional[Callable[..., Any]] = None,
) -> dict:
    """The AI/vision leg of a manual certidão upload — the post-storage steps
    of the pipeline `process_manual_upload` starts.

    1. Extract text (bounded vision, `CERTIDAO_MANUAL_MAX_VISION_PAGES`) for
       AI analysis
    2. Run AI analysis on the extracted text
    3. Derive the structured fields (numero/emitida_em/validade_ate/resultado)
       from the SAME extracted text, unless a human already owns them
    4. Update resultado → `sucesso`, recalculate consulta status

    Scheduled by `routers/certidoes.py::upload_certidao_manual` via FastAPI
    `BackgroundTasks` right after `process_manual_upload` persists the file
    (`tentativa=1`), and re-run by `recover_stale_processando` — with an
    incremented `tentativa` and the bytes re-read from storage — when a prior
    attempt was interrupted mid-flight (a deploy, an OOM kill). Never raises:
    a background job that dies here is, to the sweep, identical to one that
    never ran; see `recover_stale_processando`'s own header for why that must
    never happen silently.

    D3 (KB roadmap `sw-extraction-contract-gate-2026-09.md`). A failed
    extraction (`extracted.erro` set) below `MAX_ESTRUTURA_TENTATIVAS` leaves
    `status='processando'` UNTOUCHED and records only the attempt count + the
    reason — `recover_stale_processando` retries it once the row goes stale.
    Reaching the cap closes the resultado out as `sucesso` (the certidão
    itself IS valid; only the automated structured read gave up — same
    posture `_analyze_with_ai`'s own docstring states for its failure class)
    with `estrutura_erro` carrying the human-readable, terminal reason.

    Returns the update_data dict WRITTEN to the row — WITHOUT `texto_extraido`
    / `formatacao` (migration 113, `RESULTADO_COLUNAS_SEM_TEXTO`'s rule) — for
    tests to assert on; the router never echoes this into an HTTP response
    (it runs after the response was already sent).

    `resultado_origem_atual` / `confirmado_por_atual` mirror
    `process_manual_upload`'s original contract: the FIRST call passes the
    caller's already-fetched values (no redundant round trip); a
    sweep-triggered RETRY has none to pass (the caller is not a request
    handler) and leaves them `None`, so `_retomar_extracao_manual` re-reads
    the row fresh instead — a human confirmation that landed WHILE this row
    sat stale must still be respected.

    `extract_text` / `analyze` / `analyze_estrutura` are the same DI seams
    the pre-split function exposed. → KB § PATTERNS/backend/di-test-seam.md
    """
    extract_text = extract_text or _extract_pdf_text
    analyze = analyze or _analyze_with_ai
    analyze_estrutura = analyze_estrutura or _analyze_estrutura_with_ai
    travado = resultado_origem_atual == "manual" or bool(confirmado_por_atual)

    try:
        extracted = await extract_text(
            pdf_bytes, nome_display, org_id,
            max_vision_pages=CERTIDAO_MANUAL_MAX_VISION_PAGES,
        )
    except Exception as exc:  # noqa: BLE001 - background job must not die
        logger.error(
            "Certidão %s (resultado %s): extract_text raised inesperadamente "
            "na tentativa %d: %s",
            nome_display, resultado_id, tentativa, exc, exc_info=True,
        )
        return {}

    esgotado = tentativa >= MAX_ESTRUTURA_TENTATIVAS
    if extracted.erro and not esgotado:
        # Retry pending — status stays `processando`, untouched. `api_
        # requested_at` IS refreshed (unlike status): otherwise this row
        # would still read as stale on the VERY NEXT sweep tick — 5 minutes
        # later, and this attempt may still be in flight — and get a SECOND
        # concurrent retry scheduled on top of the first. Refreshing restarts
        # the 15-minute staleness window, which is what paces retries apart
        # instead of racing them.
        update_data = {
            "estrutura_tentativas": tentativa,
            "estrutura_erro": extracted.erro,
            "api_requested_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            db.table(RESULTADOS).update(update_data).eq(
                "id", resultado_id
            ).execute()
        except Exception as exc:  # noqa: BLE001 - background job must not die
            logger.error(
                "Certidão %s (resultado %s): falha ao registrar tentativa "
                "%d/%d: %s",
                nome_display, resultado_id, tentativa,
                MAX_ESTRUTURA_TENTATIVAS, exc, exc_info=True,
            )
            return {}
        logger.warning(
            "Certidão %s (resultado %s): extração falhou na tentativa %d/%d "
            "(%s) — nova tentativa via varredura de pendências",
            nome_display, resultado_id, tentativa, MAX_ESTRUTURA_TENTATIVAS,
            extracted.erro,
        )
        return update_data

    # Either a trustworthy read, or retries are exhausted — either way this
    # is the FINAL write for this resultado; `text_for_analysis` is `None` in
    # the exhausted-with-no-text case, so `analyze`/`analyze_estrutura` are
    # skipped naturally rather than run against a document we already know
    # failed to read.
    text_for_analysis = extracted.para_ia
    analise = None
    if text_for_analysis:
        analise = await analyze(text_for_analysis, org_id)

    update_data = {
        "status": "sucesso",
        "analise_ia": analise,
        "erro_mensagem": None,
        "estrutura_erro": extracted.erro,
        "estrutura_tentativas": tentativa,
    }
    if extracted.erro:
        logger.warning(
            "Certidão %s (resultado %s): extração automática esgotada após "
            "%d tentativa(s) (%s) — certidão válida, sem leitura estruturada",
            nome_display, resultado_id, tentativa, extracted.erro,
        )

    if not travado and text_for_analysis:
        via_ia = await analyze_estrutura(text_for_analysis, nome_display, org_id)
        if via_ia:
            update_data.update(via_ia)
            update_data["resultado_origem"] = "ia"

    # 🔴 `persist_data` is a SUPERSET of `update_data`, built for the DB write
    # ONLY — see this docstring's leak note. `update_data` itself never gains
    # these two keys.
    persist_data = {
        **update_data,
        "texto_extraido": extracted.texto_extraido,
        "formatacao": ranges_to_json(extracted.formatacao),
    }
    try:
        db.table(RESULTADOS).update(persist_data).eq("id", resultado_id).execute()
        _atualizar_status_consulta(consulta_id, org_id, db)
    except Exception as exc:  # noqa: BLE001 - background job must not die
        logger.error(
            "Certidão %s (resultado %s): falha ao persistir resultado da "
            "extração: %s",
            nome_display, resultado_id, exc, exc_info=True,
        )
        return {}

    return update_data


async def _retomar_extracao_manual(
    *,
    db,
    storage: StorageBackend,
    http_client: httpx.AsyncClient,
    resultado_id: str,
    consulta_id: str,
    org_id: Optional[str],
    nome_display: str,
    arquivo_url: str,
    tentativa: int,
) -> None:
    """`recover_stale_processando`'s retry half: re-read a manually uploaded
    certidão's already-stored bytes and re-run `process_manual_extraction`.

    Never raises past this point (`schedule_coro`'s done-callback would log
    it regardless, but every OTHER function in this family states its own
    "never raises" boundary explicitly, and this one is no different).
    Re-reads `resultado_origem`/`confirmado_por` FRESH rather than trusting a
    value the sweep captured earlier — a human confirmation that landed while
    this row sat stale must still lock the row against being overwritten.
    """
    try:
        pdf_bytes = await read_certidao_bytes(arquivo_url, storage, http_client)
    except Exception as exc:  # noqa: BLE001 - background job must not die
        logger.error(
            "Certidão %s (resultado %s): retomada da extração — leitura do "
            "arquivo armazenado falhou: %s",
            nome_display, resultado_id, exc, exc_info=True,
        )
        return
    if not pdf_bytes:
        logger.error(
            "Certidão %s (resultado %s): retomada da extração — arquivo %s "
            "não encontrado no armazenamento",
            nome_display, resultado_id, arquivo_url,
        )
        return

    try:
        atual = (
            db.table(RESULTADOS)
            .select("resultado_origem, confirmado_por")
            .eq("id", resultado_id)
            .execute()
        ).data or []
    except Exception as exc:  # noqa: BLE001 - background job must not die
        logger.error(
            "Certidão %s (resultado %s): retomada da extração — leitura do "
            "estado atual falhou: %s",
            nome_display, resultado_id, exc, exc_info=True,
        )
        return

    await process_manual_extraction(
        pdf_bytes=pdf_bytes,
        resultado_id=resultado_id,
        consulta_id=consulta_id,
        nome_display=nome_display,
        org_id=org_id,
        db=db,
        resultado_origem_atual=(atual[0].get("resultado_origem") if atual else None),
        confirmado_por_atual=(atual[0].get("confirmado_por") if atual else None),
        tentativa=tentativa,
    )


# --------------- TJSP On-Demand Scheduler ---------------
#
# Instead of polling every N seconds, TJSP items are scheduled to fire at the
# exact moment the cooldown expires. Each org has at most one scheduled task.
# After processing, the task chains the next queued item (if any) with a fresh
# cooldown delay.

#: One scheduled asyncio.Task per org — prevents double-scheduling and holds a
#: strong reference so the task isn't garbage-collected.
_tjsp_scheduled_tasks: dict[str, "asyncio.Task"] = {}


def _get_tjsp_last_request_at(org_id: str, db) -> Optional[datetime]:
    """When the last TJSP API request was made for an org.

    Uses the dedicated `api_requested_at` column, which is set right before
    calling the InfoSimples API and is NEVER cleared on reprocessing. That is
    what keeps the cooldown enforced even after a resultado is reset from
    "erro" to "na_fila" for retry.

    Fetches recent TJSP resultados and filters NULLs in Python rather than
    relying on supabase-py's `.not_.is_()` filter, which can silently return
    NULL rows depending on the client version.
    """
    result = db.table(RESULTADOS).select(
        "id, api_requested_at"
    ).eq("tipo", TJSP_TIPO).eq("org_id", str(org_id)).order(
        "created_at", desc=True
    ).limit(10).execute()

    for row in (result.data or []):
        ts_str = row.get("api_requested_at")
        if not ts_str:
            continue
        try:
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as exc:
            logger.warning(
                "certidoes: resultado id=%s has unparseable api_requested_at=%r (%s); "
                "skipping when computing TJSP cooldown",
                row.get("id"), ts_str, exc,
            )
            continue
    return None


def _get_tjsp_remaining_cooldown(org_id: str, db) -> float:
    """Seconds remaining on the TJSP cooldown for an org. 0.0 when clear."""
    last_at = _get_tjsp_last_request_at(org_id, db)
    if not last_at:
        logger.info(
            "TJSP cooldown: no previous api_requested_at found for org %s", org_id
        )
        return 0.0
    elapsed = (datetime.now(timezone.utc) - last_at).total_seconds()
    remaining = max(0.0, TJSP_COOLDOWN_SECONDS - elapsed)
    logger.info(
        "TJSP cooldown for org %s: last_at=%s, elapsed=%.0fs, remaining=%.0fs",
        org_id, last_at.isoformat(), elapsed, remaining,
    )
    return remaining


async def _process_single_tjsp_item(
    resultado: dict,
    db,
    storage: StorageBackend,
    *,
    process_one: Optional[Callable[..., Any]] = None,
) -> None:
    """Process one queued TJSP resultado: fetch its consulta, call InfoSimples.

    `process_one` is the DI seam (default `_process_single_certidao`) — the
    guard clauses ABOVE it (consulta missing, token missing) are what this
    function is really about, and a test must be able to reach them without
    the happy path making a network call.
    """
    process_one = process_one or _process_single_certidao
    consulta_id = resultado["consulta_id"]
    org_id = resultado.get("org_id")

    consulta_result = db.table(CONSULTAS).select("*").eq(
        "id", consulta_id
    ).single().execute()
    consulta = consulta_result.data
    if not consulta:
        logger.error(
            "TJSP queue: consulta %s not found for resultado %s",
            consulta_id, resultado["id"],
        )
        db.table(RESULTADOS).update({
            "status": "erro",
            "erro_mensagem": "Consulta não encontrada",
        }).eq("id", resultado["id"]).execute()
        _atualizar_status_consulta(consulta_id, org_id, db)
        return

    infosimples_token = _get_infosimples_token(org_id)
    if not infosimples_token:
        db.table(RESULTADOS).update({
            "status": "erro",
            "erro_mensagem": (
                "Token InfoSimples não configurado. "
                "Configure em Configurações → Chaves de API."
            ),
        }).eq("id", resultado["id"]).execute()
        _atualizar_status_consulta(consulta_id, org_id, db)
        return

    config = config_for(TJSP_TIPO)
    if not config:
        logger.error(
            "TJSP queue: %r is not in CERTIDOES_CONFIG — resultado %s left queued",
            TJSP_TIPO, resultado["id"],
        )
        return

    async with httpx.AsyncClient() as http_client:
        await process_one(
            config, consulta, infosimples_token, db, resultado["id"],
            http_client, storage,
        )

    _atualizar_status_consulta(consulta_id, org_id, db)


async def _delayed_tjsp_process(
    delay: float,
    resultado: dict,
    org_id: str,
    db,
    storage: StorageBackend,
    *,
    process_item: Optional[Callable[..., Any]] = None,
    reschedule: Optional[Callable[..., Any]] = None,
) -> None:
    """Sleep out the remaining cooldown, process one TJSP item, chain the next.

    Runs as a one-shot asyncio.Task in the main event loop. After completion
    (success or failure), checks for more queued items for the same org and
    schedules the next one with a fresh cooldown delay.

    On CancelledError (server shutdown / --reload) it does NOT reschedule — the
    new process's startup recovery handles that.

    `process_item` / `reschedule` are DI seams (defaults `_process_single_tjsp_item`
    / `schedule_tjsp_for_org`). What this function owns is the SEQUENCING — sleep,
    re-check the row is still queued, process, chain the next, and specifically
    do NOT chain on cancellation — and every one of those assertions needs the
    two collaborators to be observable rather than real.
    """
    process_item = process_item or _process_single_tjsp_item
    reschedule = reschedule or schedule_tjsp_for_org
    resultado_id = resultado["id"]
    cancelled = False
    sleep_start = datetime.now(timezone.utc)
    try:
        if delay > 0:
            logger.info(
                "TJSP sleep START: resultado %s, delay=%.0fs (org %s)",
                resultado_id, delay, org_id,
            )
            await asyncio.sleep(delay)
            actual = (datetime.now(timezone.utc) - sleep_start).total_seconds()
            logger.info(
                "TJSP sleep END: resultado %s, slept=%.0fs of %.0fs (org %s)",
                resultado_id, actual, delay, org_id,
            )

        # Verify the item is still queued (it may have been deleted, cancelled
        # or reprocessed while we slept)
        check = db.table(RESULTADOS).select("status").eq(
            "id", resultado_id
        ).execute()
        if not check.data or check.data[0]["status"] != "na_fila":
            logger.info("TJSP resultado %s no longer na_fila, skipping", resultado_id)
            return

        logger.info("TJSP processing: resultado %s (org %s)", resultado_id, org_id)
        await process_item(resultado, db, storage)

    except asyncio.CancelledError:
        cancelled = True
        actual = (datetime.now(timezone.utc) - sleep_start).total_seconds()
        logger.info(
            "TJSP task CANCELLED for resultado %s after %.0fs of %.0fs sleep (org %s)",
            resultado_id, actual, delay, org_id,
        )
        raise
    except Exception as e:
        logger.error("TJSP processing failed for %s: %s", resultado_id, e)
        db.table(RESULTADOS).update({
            "status": "erro",
            "erro_mensagem": f"Erro no processamento: {e}",
        }).eq("id", resultado_id).execute()
        _atualizar_status_consulta(
            resultado["consulta_id"], resultado.get("org_id"), db
        )
    finally:
        _tjsp_scheduled_tasks.pop(org_id, None)
        # Only reschedule on normal completion or handled errors — NOT on
        # CancelledError (server shutdown). The new process's startup recovery
        # calls schedule_all_pending_tjsp, which handles rescheduling.
        if not cancelled:
            reschedule(org_id, db, storage)


def schedule_tjsp_for_org(
    org_id: str,
    db,
    storage: StorageBackend,
    *,
    delayed: Optional[Callable[..., Any]] = None,
) -> None:
    """Schedule the next queued TJSP item for an org.

    Idempotent: if a task is already in flight for this org, does nothing.
    Calculates the exact delay from `api_requested_at` so the item fires
    precisely when the cooldown expires — no polling.

    `delayed` is the DI seam (default `_delayed_tjsp_process`): this function's
    job is the BOOKKEEPING — one task per org, the right delay, the right next
    item — and a test of that must not have to wait out a 45-minute sleep.
    """
    delayed = delayed or _delayed_tjsp_process
    existing = _tjsp_scheduled_tasks.get(org_id)
    if existing and not existing.done():
        return  # Already scheduled

    queued = db.table(RESULTADOS).select(
        "id, consulta_id, org_id"
    ).eq("tipo", TJSP_TIPO).eq("status", "na_fila").eq(
        "org_id", str(org_id)
    ).order("created_at").limit(1).execute()

    items = queued.data or []
    if not items:
        return

    remaining = _get_tjsp_remaining_cooldown(org_id, db)
    task = schedule_coro(
        delayed(remaining, items[0], org_id, db, storage),
        logger=logger,
        name=f"tjsp_{org_id}",
    )
    _tjsp_scheduled_tasks[org_id] = task
    logger.info(
        "TJSP task scheduled for org %s: resultado %s in %.0fs",
        org_id, items[0]["id"], remaining,
    )


def schedule_all_pending_tjsp(
    db,
    storage: StorageBackend,
    *,
    schedule_one: Optional[Callable[..., Any]] = None,
) -> None:
    """Scan for every queued TJSP item and schedule one task per org.

    Called after `recover_stuck_processando` to resume items that were waiting
    before the process restarted.

    `schedule_one` is the DI seam (default `schedule_tjsp_for_org`) — what this
    function decides is WHICH ORGS have queued work, and that is assertable
    without creating a live asyncio task per org.
    """
    schedule_one = schedule_one or schedule_tjsp_for_org
    def _page(start: int, end: int):
        return (
            db.table(RESULTADOS)
            .select("id, org_id")
            .eq("tipo", TJSP_TIPO)
            .eq("status", "na_fila")
            .order("id")
            .range(start, end)
            .execute()
            .data
        )

    queued = _all_rows(_page, "certidao_resultados na_fila (tjsp)")

    org_ids = set(item["org_id"] for item in queued if item.get("org_id"))
    if org_ids:
        logger.info("Scheduling pending TJSP items for %d org(s)", len(org_ids))
    for oid in org_ids:
        schedule_one(oid, db, storage)


def status_counts_por_consulta(
    consulta_ids: list[str], org_id: Any, db
) -> tuple[dict[str, int], dict[str, int]]:
    """`(sucessos, erros)` counts keyed by consulta_id, for a page of consultas.

    🔴 BATCHED **AND** PAGED — both hazards are live on this one read, and
    fixing only the famous one leaves the other silently wrong.

    - Batched, because PostgREST rides `.in_()` values in the URL query string,
      so a long id list comes back as a bare 400.
    - Paged, because a full page is 200 consultas and each fans out to one
      resultado per registry type (10 today) — 2 000 rows against PostgREST's
      1 000-row cap, which it applies SILENTLY and reports as success. An
      un-paged read here does not fail; it just returns counts that are wrong
      for the back half of the page, and "concluídas: 0" on a consulta that
      finished is indistinguishable from one that genuinely has not started.

    The batch size is deliberately smaller than `in_batches`' default: the id
    count is not the row count here, it is the row count divided by the
    fan-out. The pager underneath makes the read correct regardless; the
    smaller batch just keeps it to one round-trip per batch in the common case.
    """
    sucessos: dict[str, int] = {}
    erros: dict[str, int] = {}
    if not consulta_ids:
        return sucessos, erros

    for batch in in_batches(consulta_ids, size=50):

        def _page(start: int, end: int, _batch=batch):
            return (
                db.table(RESULTADOS)
                .select("id, consulta_id, status")
                .eq("org_id", str(org_id))
                .in_("consulta_id", _batch)
                .in_("status", ["sucesso", "erro"])
                .order("id")
                .range(start, end)
                .execute()
                .data
            )

        for row in _all_rows(_page, f"certidao_resultados counts for org_id={org_id}"):
            target = sucessos if row["status"] == "sucesso" else erros
            target[row["consulta_id"]] = target.get(row["consulta_id"], 0) + 1

    return sucessos, erros


def tjsp_cooldown_status(org_id: Any, db) -> dict:
    """The org's TJSP cooldown, shaped for the frontend's countdown.

    `{"ativo": False}` when this org has never made a TJSP request — which is
    a real state ("you can go now"), not a missing one, and is why it does not
    carry the other two keys.
    """
    last_at = _get_tjsp_last_request_at(str(org_id), db)
    if not last_at:
        return {"ativo": False}
    elapsed = (datetime.now(timezone.utc) - last_at).total_seconds()
    remaining = max(0.0, TJSP_COOLDOWN_SECONDS - elapsed)
    return {
        "ativo": remaining > 0,
        "ultimo_request_at": last_at.isoformat(),
        "segundos_restantes": int(remaining),
    }


def queued_tjsp_for_org(org_id: Any, db) -> list[dict]:
    """Every `na_fila` TJSP resultado for an org, oldest first (queue order)."""
    def _page(start: int, end: int):
        return (
            db.table(RESULTADOS)
            .select("id, consulta_id, created_at")
            .eq("tipo", TJSP_TIPO)
            .eq("status", "na_fila")
            .eq("org_id", str(org_id))
            .order("created_at")
            .range(start, end)
            .execute()
            .data
        )

    return _all_rows(_page, f"certidao_resultados na_fila for org_id={org_id}")


# --------------- Per-parte reads, confirmation, LGPD-logged URL ---------------
#
# The contract-automation slice's three additions on top of the existing
# consulta-centric surface — see migration 107's header for why they land
# together.

#: Mirrors migration 107's `certidao_resultado_acessos` table.
RESULTADO_ACESSOS = "certidao_resultado_acessos"


#: Every `certidao_consultas` column the per-person resultados readers below
#: need — the identifying fields `certidoes_por_parte`/`certidoes_por_
#: cliente` denormalize onto each resultado row, plus the migration 116
#: registration-status fields (a fact about the document being
#: investigated, worth showing alongside its certidões without a second
#: round-trip).
_CONSULTA_COLUNAS_RESUMO = (
    "id, nome, documento, tipo_documento, "
    "situacao_cadastral, data_situacao, situacao_origem"
)


def _resultados_das_consultas(db, org_id, consultas: list[dict]) -> list[dict]:
    """Every resultado across a set of already-fetched consultas,
    denormalized with each parent consulta's identifying fields.

    The shared body of `certidoes_por_parte` / `certidoes_por_cliente`,
    which differ only in HOW they select their consultas (by
    `atendimento_parte_id` vs. by `cliente_id`) — everything past that
    point is the same two-step read (a resultado carries no `atendimento_
    parte_id`/`cliente_id` of its own, only `consulta_id`) and the same
    bound: a person realistically has one or two consultas over the life of
    a deal, each with at most ~13 resultados (10 automated + 3 manual),
    well under PostgREST's row cap.
    """
    if not consultas:
        return []
    consulta_by_id = {c["id"]: c for c in consultas}

    resultados: list[dict] = []
    for batch in in_batches(list(consulta_by_id)):
        # postgrest-unbounded-ok: batched by `in_batches` (200/batch), and a
        # person's total resultado count across all their consultas stays in
        # the low tens in practice.
        # Migration 113: this panel polls like the consulta-detail screen
        # does — never `select("*")` here, or the certidão text rides along.
        rows = (
            db.table(RESULTADOS)
            .select(RESULTADO_COLUNAS_SEM_TEXTO)
            .eq("org_id", str(org_id))
            .in_("consulta_id", batch)
            .is_("excluida_em", "null")
            .order("ordem")
            .execute()
        ).data or []
        for r in rows:
            consulta = consulta_by_id.get(r["consulta_id"], {})
            r["consulta_nome"] = consulta.get("nome")
            r["consulta_documento"] = consulta.get("documento")
            # Already selected above; the contract generator groups a
            # person's PF (cpf) and company (cnpj) certidões by it — never
            # guessed from the document's digit count.
            r["consulta_tipo_documento"] = consulta.get("tipo_documento")
            r["consulta_situacao_cadastral"] = consulta.get("situacao_cadastral")
            r["consulta_data_situacao"] = consulta.get("data_situacao")
            r["consulta_situacao_origem"] = consulta.get("situacao_origem")
            resultados.append(r)
    return resultados


def certidoes_por_parte(db, org_id, atendimento_parte_id: str) -> list[dict]:
    """Every certidão result across every consulta linked to one party of an
    atendimento — the per-parte certidões panel the contract-automation
    slice reads.

    A consulta names a party via `atendimento_parte_id` (migration 107); see
    `_resultados_das_consultas` for the shared two-step read this and
    `certidoes_por_cliente` both run.
    """
    # postgrest-unbounded-ok: a handful of consultas per party, not 1 000.
    # `.is_("excluida_em", "null")`: a soft-deleted consulta's certidões must
    # not surface here — the contract generator's readiness read runs
    # straight through this function (see the module's `certidoes_svc.
    # certidoes_por_parte` callers).
    consultas = (
        db.table(CONSULTAS)
        .select(_CONSULTA_COLUNAS_RESUMO)
        .eq("org_id", str(org_id))
        .eq("atendimento_parte_id", str(atendimento_parte_id))
        .is_("excluida_em", "null")
        .execute()
    ).data or []
    return _resultados_das_consultas(db, org_id, consultas)


def certidoes_por_cliente(db, org_id, cliente_id: str) -> list[dict]:
    """Every certidão result across every consulta linked to a `clientes`
    row — `certidoes_por_parte`'s sibling for the one party it cannot reach:
    a card's TITULAR, named by `atendimentos.cliente_id`, has no
    `atendimento_parte_id` row to key off at all (migration 073's header).
    `routers/certidoes.py::vincular_cliente` (migration 116) is what links a
    consulta this way.

    Filters `certidao_consultas.cliente_id` directly rather than through
    `atendimento_partes` — and deliberately does NOT exclude a consulta that
    ALSO carries an `atendimento_parte_id` (set by `vincular_parte`, which
    denormalizes `cliente_id` too, per migration 107's header): the
    certidão still belongs to this person either way, and a caller asking
    "every certidão for this cliente" wants both.
    """
    # postgrest-unbounded-ok: a handful of consultas per cliente, not 1 000.
    consultas = (
        db.table(CONSULTAS)
        .select(_CONSULTA_COLUNAS_RESUMO)
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .is_("excluida_em", "null")
        .execute()
    ).data or []
    return _resultados_das_consultas(db, org_id, consultas)


def certidoes_por_empresa(db, org_id, empresa_id: str) -> list[dict]:
    """Every certidão result across every CNPJ consulta linked to an
    `empresas` row — `certidoes_por_cliente`'s sibling for an empresa
    (P0c contract §D5, mirroring `service.py:2651-2676`). `GET /api/
    certidoes/empresas/{empresa_id}/resultados`; `app.modules.card_hub.
    contrato_gerador.carregador` (S2b) calls this by this exact name to
    build `DadosContrato.empresas[].certidoes`.
    """
    # postgrest-unbounded-ok: a handful of consultas per empresa, not 1 000.
    consultas = (
        db.table(CONSULTAS)
        .select(_CONSULTA_COLUNAS_RESUMO)
        .eq("org_id", str(org_id))
        .eq("empresa_id", str(empresa_id))
        .is_("excluida_em", "null")
        .execute()
    ).data or []
    return _resultados_das_consultas(db, org_id, consultas)


def atualizar_situacao_cadastral(db, org_id, consulta_id: str, campos: dict) -> Optional[dict]:
    """A human's manual entry of the CNPJ/CPF's registration status
    (migration 116) — `situacao_cadastral` / `data_situacao` on the
    CONSULTA. Stamps `situacao_origem='manual'` alongside whatever subset of
    the two fields `campos` carries (`SituacaoCadastralPatch(...).model_dump
    (exclude_unset=True)` — the router refuses an empty `campos` with a 422
    before this is ever called, unlike `confirmar_resultado`'s deliberate
    empty-body-is-a-confirmation shape: there is no automated writer for
    this field today (see migration 116's header for what was checked and
    found absent in the API/IA payloads this module already receives), so an
    empty PATCH here has nothing to confirm.

    Returns `None` when the consulta does not exist in this org — the router
    turns that into the 404, same shape as `confirmar_resultado`.
    """
    existing = (
        db.table(CONSULTAS)
        .select("id")
        .eq("id", consulta_id)
        .eq("org_id", str(org_id))
        .is_("excluida_em", "null")
        .execute()
    ).data or []
    if not existing:
        return None
    patch = {**campos, "situacao_origem": "manual"}
    updated = (
        db.table(CONSULTAS)
        .update(patch)
        .eq("id", consulta_id)
        .eq("org_id", str(org_id))
        .execute()
    ).data or []
    return updated[0] if updated else None


def confirmar_resultado(
    db, org_id, resultado_id: str, campos: dict, usuario_id
) -> Optional[dict]:
    """Merge a human's structured-field correction/confirmation into a
    resultado, and LOCK it: `resultado_origem='manual'` plus who/when,
    unconditionally — even when `campos` is empty, because calling this AT
    ALL is the human's statement "I reviewed this". After this,
    `_derive_estrutura` refuses to touch the same resultado's structured
    fields again (its `travado` check).

    Returns `None` when the resultado does not exist in this org — the
    router turns that into the 404. `campos` is whatever subset of
    `numero`/`emitida_em`/`validade_ate`/`resultado` the caller sent
    (`schemas.ResultadoPatch(...).model_dump(exclude_unset=True)`); already
    validated against the CHECK-constrained vocabulary by that schema.

    🔴 Never carries `texto_extraido` / `formatacao` (migration 113): an
    UPDATE returns its full row by default (`postgrest-py` has no per-column
    `.select()` on that chain — see this module's history), and this
    dict rides straight into the router's HTTP response. Stripped below
    rather than avoided upstream, since there is nowhere upstream to avoid
    it FROM.
    """
    existing = (
        db.table(RESULTADOS)
        .select("id")
        .eq("id", resultado_id)
        .eq("org_id", str(org_id))
        .is_("excluida_em", "null")
        .execute()
    ).data or []
    if not existing:
        return None
    patch = {
        **campos,
        "resultado_origem": "manual",
        "confirmado_por": str(usuario_id) if usuario_id else None,
        "confirmado_em": datetime.now(timezone.utc).isoformat(),
    }
    updated = (
        db.table(RESULTADOS)
        .update(patch)
        .eq("id", resultado_id)
        .eq("org_id", str(org_id))
        .execute()
    ).data or []
    if not updated:
        return None
    row = dict(updated[0])
    row.pop("texto_extraido", None)
    row.pop("formatacao", None)
    return row


def _log_resultado_acesso(db, org_id, resultado_id: str, usuario_id, acao: str) -> None:
    """Append to `certidao_resultado_acessos` — the LGPD content-read log
    this module did not have before migration 107. Same shape
    `documento_store.DocumentoStore.log_acesso` uses on the other document
    surfaces, as a bespoke insert rather than reusing that class directly:
    `DocumentoStore` is configured against a table that owns its OWN
    document rows (`.guardar()` inserts one per upload), and a certidão's
    file lives on the SAME `certidao_resultados` row `criar_consulta`'s
    fan-out already created — see `mint_resultado_url`'s docstring.
    """
    db.table(RESULTADO_ACESSOS).insert({
        "id": str(uuid.uuid4()),
        "org_id": str(org_id),
        "documento_id": str(resultado_id),
        "usuario_id": str(usuario_id) if usuario_id else None,
        "acao": acao,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


async def mint_resultado_url(
    db,
    storage: StorageBackend,
    org_id,
    resultado_id: str,
    *,
    usuario_id,
    intent: str = "view",
) -> Optional[dict]:
    """A short-TTL signed URL for one resultado's stored file, LGPD-logging
    the access — the resultado_id-scoped sibling of `GET /download` for a
    caller that already holds the id (the per-parte panel) rather than the
    opaque `arquivo_url` handle `GET /consultas/{id}` hands back.

    Returns `None` for a resultado that does not exist in this org (→ 404 in
    the router), or `{"error": "sem_arquivo"}` when it exists but has no
    file yet (→ 404, distinct message).

    NOT built on `DocumentoStore.url()`: that method reads a `storage_path`
    column this table does not have (`arquivo_url` holds EITHER a bucket key
    OR — when persisting failed — an external `https://` URL; see
    `is_storage_key`). An external URL cannot be "signed" by our storage
    backend at all, so it is handed back as-is, exactly as `/download`
    already proxies it today.
    """
    rows = (
        db.table(RESULTADOS)
        .select("id, arquivo_url")
        .eq("id", resultado_id)
        .eq("org_id", str(org_id))
        .is_("excluida_em", "null")
        .execute()
    ).data or []
    if not rows:
        return None
    arquivo_url = rows[0].get("arquivo_url")
    if not arquivo_url:
        return {"error": "sem_arquivo"}

    if is_storage_key(arquivo_url):
        from app.services.documento_store import SIGNED_URL_TTL_SECONDS

        signed = await storage.signed_url(
            bucket=BUCKET, key=arquivo_url, expires_in_seconds=SIGNED_URL_TTL_SECONDS,
        )
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=SIGNED_URL_TTL_SECONDS)
        ).isoformat()
        url = signed
    else:
        url = arquivo_url
        expires_at = None

    _log_resultado_acesso(db, org_id, resultado_id, usuario_id, intent)
    return {"url": url, "expires_at": expires_at}


def obter_transcricao_resultado(
    db, org_id, resultado_id: str, *, usuario_id
) -> Optional[dict]:
    """The resultado's transcript row for the two `.../transcricao` routes
    (migration 113) — JSON and PDF both start here. LGPD-logs the read
    (`_log_resultado_acesso`, acao='view') BEFORE returning, exactly as
    `mint_resultado_url` logs a file read; a failed log fails the request,
    same existing contract.

    Returns `None` for a resultado absent from this org (-> 404 "Resultado
    não encontrado"). Returns `{"disponivel": False}` for one that exists
    but has no transcript yet (-> 404 "Transcrição indisponível para esta
    certidão") — no log fires for that case, there is no read to log.
    """
    rows = (
        db.table(RESULTADOS)
        .select("id, tipo, nome_display, texto_extraido, formatacao")
        .eq("id", resultado_id)
        .eq("org_id", str(org_id))
        .is_("excluida_em", "null")
        .execute()
    ).data or []
    if not rows:
        return None
    row = rows[0]
    texto = row.get("texto_extraido")
    if not texto:
        return {"disponivel": False}

    _log_resultado_acesso(db, org_id, resultado_id, usuario_id, "view")

    formatacao_json = row.get("formatacao") or []
    doc = FormattedDocument(
        paragraphs=paragraphs_from_text(texto, ranges_from_json(formatacao_json))
    )
    return {
        "disponivel": True,
        "tipo": row["tipo"],
        "nome_display": row["nome_display"],
        "texto": texto,
        "texto_html": render_word_html(doc),
        "formatacao": formatacao_json,
    }


def renderizar_transcricao_pdf(nome_display: str, texto: str, formatacao_json) -> bytes:
    """ABNT-formatted PDF of one certidão transcript, titled
    `"Transcrição — <nome_display>"` (contract §4).

    Raises `noctusai_lib.integrations.documents.abnt.UnsupportedGlyphError`
    straight through — the router turns it into a 422 naming the character,
    never a silent 500.
    """
    titulo = f"Transcrição — {nome_display}"
    ranges = ranges_from_json(formatacao_json)
    titulo_paragrafo = Paragraph(runs=(Run(text=titulo),), kind=ParagraphKind.TITLE)
    doc = FormattedDocument(
        paragraphs=(titulo_paragrafo, *paragraphs_from_text(texto, ranges)),
        title=titulo,
    )
    return render_abnt_pdf(doc)


# --------------- Serasa Crednet -> certidão 9 (P0c contract §C5/§E7) ---------------
#
# `registrar_serasa_de_crednet` is `card_hub.crednet_service.aplicar_leitura`'s
# step (d) — the SAME stored Crednet PDF that filled the cliente's identity
# fields ALSO fills the 'serasa' resultado of every matching CPF consulta,
# per owner decision D1/H5: manual or already-confirmed rows are never
# overwritten, and a Crednet upload with no consulta yet DEFERS rather than
# creating one — `aplicar_crednet_pendente` is that deferred half, called
# once a consulta links to this cliente (`vincular-parte`/`vincular-cliente`/
# `criar_consulta_manual`'s inline fan-out).
#
# 🔴 `leitura` IS DUCK-TYPED, NEVER IMPORTED. `noctusai_lib.integrations.
# documents.serasa_crednet.CrednetFields` is S1's deliverable (a sibling
# worktree/branch at the time this was written) — this module accepts
# anything with `.cpf` / `.protocolo` / `.consulta_em` / `.ocorrencias_
# constam()`, so it never depends on that import existing. The full reading
# ALSO travels stored (`cliente_documentos.extracao_crednet`, JSON) — that
# JSON is what `aplicar_crednet_pendente` reconstructs a minimal reader from
# (`_LeituraCrednetArmazenada`), independently of whichever dataclass wrote
# it.
#
# NOC-REMEDIATE[crednet-lgpd-delete-cascade] — 2026-09-24. An LGPD delete of
# the Crednet `cliente_documentos` row FK-nulls `certidao_resultados.
# fonte_cliente_documento_id` (migration 167's `ON DELETE SET NULL`), but
# `arquivo_url` — a verbatim copy of the SAME now-gone storage path (§C5:
# "same bucket") — is left dangling, pointing at an object that no longer
# exists. Owner decision H5: deferred, not fixed in this slice. Destination:
# `project-history/roadmaps/sw-drive-extraction-2026-09.md` P1.


@dataclass(frozen=True)
class _LeituraCrednetArmazenada:
    """The 4 facts `_aplicar_crednet_a_resultado` needs, reconstructed from
    `cliente_documentos.extracao_crednet`'s stored JSON — never re-derived
    from the nested ocorrências, which `crednet_service._serializar_crednet`
    already reduced to `ocorrencias_constam` at write time."""

    cpf: Optional[str]
    protocolo: Optional[str]
    consulta_em: Optional[datetime]
    _constam: Optional[bool]

    def ocorrencias_constam(self) -> Optional[bool]:
        return self._constam


def _crednet_leitura_de_jsonb(dados: dict) -> _LeituraCrednetArmazenada:
    consulta_em_raw = dados.get("consulta_em")
    consulta_em = datetime.fromisoformat(consulta_em_raw) if consulta_em_raw else None
    return _LeituraCrednetArmazenada(
        cpf=dados.get("cpf"),
        protocolo=dados.get("protocolo"),
        consulta_em=consulta_em,
        _constam=dados.get("ocorrencias_constam"),
    )


def _aplicar_crednet_a_resultado(
    db, org_id, consulta_id: str, doc: dict, leitura: Any
) -> bool:
    """Fill (or supersede) ONE consulta's `serasa` resultado from a Crednet
    reading. Returns whether it actually wrote anything.

    "Empty" (never touched): `status == 'pendente'` and `resultado_origem`
    is still NULL — the placeholder `_fan_out_tipos_manuais`/`criar_consulta
    _manual` created. Otherwise this only supersedes a PRIOR Crednet-derived
    reading (`resultado_origem == 'ia'` AND a non-null `fonte_cliente_
    documento_id`) that is OLDER than this one — never a manual row, never
    an already-confirmed row, per §H5.
    """
    rows = (
        db.table(RESULTADOS)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("consulta_id", consulta_id)
        .eq("tipo", "serasa")
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return False
    resultado = rows[0]
    novo_em = leitura.consulta_em.date().isoformat() if leitura.consulta_em else None

    vazio = resultado.get("status") == "pendente" and resultado.get("resultado_origem") is None
    if not vazio:
        if resultado.get("confirmado_em") or resultado.get("resultado_origem") == "manual":
            return False
        if (
            resultado.get("resultado_origem") != "ia"
            or not resultado.get("fonte_cliente_documento_id")
        ):
            return False
        anterior_em = resultado.get("emitida_em")
        if not novo_em or (anterior_em and anterior_em >= novo_em):
            return False

    constam = leitura.ocorrencias_constam()
    patch = {
        "arquivo_url": doc["storage_path"],
        "arquivo_nome": "serasa_crednet.pdf",
        "status": "sucesso",
        "numero": leitura.protocolo,
        "emitida_em": novo_em,
        "resultado": (
            "negativa" if constam is False else ("positiva" if constam is True else None)
        ),
        "resultado_origem": "ia",
        "fonte_cliente_documento_id": str(doc["id"]),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    db.table(RESULTADOS).update(patch).eq("id", resultado["id"]).execute()
    return True


def registrar_serasa_de_crednet(db, org_id, cliente_id: str, doc: dict, leitura: Any) -> int:
    """§C5 step (d): fill the `serasa` resultado of every CPF consulta this
    cliente's Crednet CPF matches. `doc` is the `cliente_documentos` row the
    reading came off (`storage_path`/`id` are what this needs of it).

    Targets: every non-excluded `tipo_documento='cpf'` consulta belonging to
    `cliente_id` whose normalized `documento` equals the Crednet's normalized
    CPF — the same person may be investigated under a slightly differently
    punctuated CPF, so comparison is digit-only, not string-equal.

    Returns the number of resultados this call actually filled/superseded.
    """
    cpf_norm = only_digits(leitura.cpf) if leitura.cpf else None
    if not cpf_norm:
        return 0
    consultas = (
        db.table(CONSULTAS)
        .select("id, documento")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .eq("tipo_documento", "cpf")
        .is_("excluida_em", "null")
        .execute()
    ).data or []
    alvo = [c for c in consultas if only_digits(c.get("documento") or "") == cpf_norm]
    if not alvo:
        return 0
    return sum(
        1
        for consulta in alvo
        if _aplicar_crednet_a_resultado(db, org_id, consulta["id"], doc, leitura)
    )


def aplicar_crednet_pendente(db, org_id, consulta: dict) -> bool:
    """§C5's deferred half: a CPF consulta was just LINKED (`vincular-parte`
    / `vincular-cliente` / `criar_consulta_manual`'s inline fan-out) and may
    already have a Crednet reading on file for the same person — apply it
    retroactively rather than leaving the placeholder `serasa` resultado
    waiting for a re-upload that already happened.

    `consulta` is the just-linked row (needs `id`, `tipo_documento`,
    `cliente_id`, `documento`). Never creates a consulta — see the module
    docstring's "no consulta yet ⇒ defer" contract; this is the OTHER side
    of that deferral, called once one exists.
    """
    if consulta.get("tipo_documento") != "cpf" or not consulta.get("cliente_id"):
        return False
    cpf_norm = only_digits(consulta.get("documento") or "")
    if not cpf_norm:
        return False
    docs = (
        db.table("cliente_documentos")
        .select("id, storage_path, extracao_crednet")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(consulta["cliente_id"]))
        .eq("tipo_documento", "serasa_crednet")
        .eq("extracao_status", "ok")
        .is_("deleted_at", "null")
        .execute()
    ).data or []
    candidatos = [
        d for d in docs
        if d.get("extracao_crednet")
        and only_digits((d["extracao_crednet"] or {}).get("cpf") or "") == cpf_norm
    ]
    if not candidatos:
        return False
    # The most recent Crednet reading for this CPF — same "newer supersedes
    # older" direction `_aplicar_crednet_a_resultado` enforces.
    candidatos.sort(
        key=lambda d: (d.get("extracao_crednet") or {}).get("consulta_em") or "",
        reverse=True,
    )
    doc = candidatos[0]
    leitura = _crednet_leitura_de_jsonb(doc["extracao_crednet"])
    return _aplicar_crednet_a_resultado(db, org_id, consulta["id"], doc, leitura)


__all__ = [
    "CERTIDOES_CONFIG",
    "CONSULTAS",
    "RESULTADOS",
    "RESULTADO_ACESSOS",
    "RESULTADO_COLUNAS_SEM_TEXTO",
    "STALE_PROCESSANDO_SECONDS",
    "TJSP_COOLDOWN_SECONDS",
    "TJSP_TIPO",
    "ExtractedPdfText",
    "atualizar_situacao_cadastral",
    "cancelar_processamento",
    "certidoes_por_cliente",
    "certidoes_por_parte",
    "check_required_credentials",
    "confirmar_resultado",
    "delete_storage_files",
    "is_storage_key",
    "mint_resultado_url",
    "obter_transcricao_resultado",
    "process_manual_upload",
    "process_manual_extraction",
    "processar_consulta",
    "in_batches",
    "queued_tjsp_for_org",
    "read_certidao_bytes",
    "recover_stale_processando",
    "recover_stuck_processando",
    "renderizar_transcricao_pdf",
    "schedule_all_pending_tjsp",
    "schedule_tjsp_for_org",
    "status_counts_por_consulta",
    "storage_key",
    "tjsp_cooldown_status",
]
