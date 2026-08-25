"""
Certidões Negativas Service — Orchestrates certificate issuance via InfoSimples API,
AI-powered document analysis, and result persistence.

Each certificate type is defined declaratively in CERTIDOES_CONFIG. The processing
pipeline (fetch → download → analyze → store) is shared across all types.
"""
from __future__ import annotations

import asyncio
import io
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from xhtml2pdf import pisa

from noctusai_lib.config.credentials import resolve_credential
from noctusai_lib.integrations.llm import chat_completion
from noctusai_lib.primitives.tasks import schedule_coro

logger = logging.getLogger(__name__)


# --------------- Certificate Registry ---------------

CERTIDOES_CONFIG = [
    {
        "tipo": "cnd_federal",
        "nome": "CND Federal (Receita)",
        "endpoint": "receita-federal/pgfn",
        "ordem": 1,
        "params_fn": "cnd_federal",
        "response_format": "pdf",
    },
    {
        "tipo": "trf3_sp",
        "nome": "Certidão TRF3 (São Paulo)",
        "endpoint": "tribunal/trf3/certidao-distr",
        "ordem": 2,
        "params_fn": "trf3_sp",
        "response_format": "html",
    },
    {
        "tipo": "trf3",
        "nome": "Certidão TRF3 (Regional)",
        "endpoint": "tribunal/trf3/certidao-distr",
        "ordem": 3,
        "params_fn": "trf3",
        "response_format": "html",
    },
    {
        "tipo": "trt2_digital",
        "nome": "TRT2 (Trabalhista SP) Digital",
        "endpoint": "tribunal/trt2/ceat-digital",
        "ordem": 4,
        "params_fn": "trt2_digital",
        "response_format": "html",
    },
    {
        "tipo": "trt2_fisico",
        "nome": "TRT2 (Trabalhista SP) Físico",
        "endpoint": "tribunal/trt2/ceat",
        "ordem": 5,
        "params_fn": "trt2_fisico",
        "response_format": "pdf",
    },
    {
        "tipo": "cnd_trabalhista_tst",
        "nome": "CND Trabalhistas (TST)",
        "endpoint": "tst/cndt",
        "ordem": 6,
        "params_fn": "simples",
        "response_format": "pdf",
    },
    {
        "tipo": "tjsp",
        "nome": "Certidão TJSP",
        "endpoint": "tribunal/tjsp/pedido-certidao",
        "ordem": 7,
        "params_fn": "tjsp",
        "response_format": "pdf",
    },
    {
        "tipo": "cenprot",
        "nome": "CENPROT (Protestos)",
        "endpoint": "cenprot-sp/protestos",
        "ordem": 8,
        "params_fn": "simples",
        "response_format": "html",
    },
    {
        "tipo": "cnd_fazenda_sp",
        "nome": "CND Fazenda SP",
        "endpoint": "sefaz/sp/certidao-debitos",
        "ordem": 9,
        "params_fn": "simples",
        "response_format": "pdf",
    },
    {
        "tipo": "divida_ativa_sp",
        "nome": "Dívida Ativa SP",
        "endpoint": "pge/sp/cndt",
        "ordem": 10,
        "params_fn": "simples",
        "response_format": "pdf",
    },
]

INFOSIMPLES_BASE_URL = "https://api.infosimples.com/api/v2/consultas"

# TJSP has a rate limit of 1 request per 30 minutes per email.
# We use 45 minutes to add a safety margin.
TJSP_COOLDOWN_SECONDS = 45 * 60
TJSP_TIPO = "tjsp"


# --------------- Parameter Builders ---------------
# Each builder matches the exact params from the working n8n workflow.
# Endpoints reject unknown params, so only send what each one expects.


def _token_and_doc(consulta: dict, token: str) -> dict:
    """Shared base: token + CPF/CNPJ key."""
    doc_key = "cpf" if consulta["tipo_documento"] == "cpf" else "cnpj"
    return {"token": token, doc_key: consulta["documento"]}


def _build_params_cnd_federal(consulta: dict, token: str) -> dict:
    """CND Federal (Receita): token + cpf/cnpj + birthdate + preferencia_emissao."""
    params = _token_and_doc(consulta, token)
    if consulta.get("data_nascimento"):
        params["birthdate"] = consulta["data_nascimento"]
    params["preferencia_emissao"] = "2via"
    return params


def _build_params_trf3_sp(consulta: dict, token: str) -> dict:
    """TRF3 São Paulo: same endpoint as Regional but tipo=2."""
    params = _token_and_doc(consulta, token)
    params["tipo"] = "2"
    params["tipo_documento"] = "1" if consulta["tipo_documento"] == "cpf" else "2"
    if consulta.get("nome"):
        params["nome_social"] = consulta["nome"]
    params["abrangencia"] = "1"
    return params


def _build_params_trf3(consulta: dict, token: str) -> dict:
    """TRF3 Regional: token + tipo + tipo_documento + cpf/cnpj + nome_social + abrangencia."""
    params = _token_and_doc(consulta, token)
    params["tipo"] = "1"
    params["tipo_documento"] = "1" if consulta["tipo_documento"] == "cpf" else "2"
    if consulta.get("nome"):
        params["nome_social"] = consulta["nome"]
    params["abrangencia"] = "1"
    return params


def _build_params_trt2_digital(consulta: dict, token: str) -> dict:
    """TRT2 Digital: token + cpf/cnpj_raiz only."""
    doc_key = "cpf" if consulta["tipo_documento"] == "cpf" else "cnpj_raiz"
    return {"token": token, doc_key: consulta["documento"]}


def _build_params_trt2_fisico(consulta: dict, token: str) -> dict:
    """TRT2 Físico: token + cpf/cnpj + nome."""
    params = _token_and_doc(consulta, token)
    if consulta.get("nome"):
        params["nome"] = consulta["nome"]
    return params


def _build_params_simples(consulta: dict, token: str) -> dict:
    """Simple endpoints (TST, CENPROT, Fazenda SP, Dívida Ativa): token + cpf/cnpj only."""
    return _token_and_doc(consulta, token)


def _build_params_tjsp(consulta: dict, token: str) -> dict:
    """TJSP: conditional name key (nome_completo for CPF, razao_social for CNPJ).
    Requires email_envio — TJSP delivers the certificate asynchronously via email."""
    params = _token_and_doc(consulta, token)
    # CPF → nome_completo, CNPJ → razao_social
    if consulta.get("nome"):
        name_key = "nome_completo" if consulta["tipo_documento"] == "cpf" else "razao_social"
        params[name_key] = consulta["nome"]
    if consulta.get("data_nascimento"):
        params["birthdate"] = consulta["data_nascimento"]
    params["modelo"] = "4"
    # email_envio is required by the TJSP endpoint
    org_id = consulta.get("org_id")
    email = resolve_credential("infosimples_email_envio", org_id) if org_id else None
    if email:
        params["email_envio"] = email
    if consulta.get("rg"):
        params["rg"] = consulta["rg"]
    if consulta.get("genero"):
        params["genero"] = consulta["genero"]
    if consulta.get("nome_mae"):
        params["nome_mae"] = consulta["nome_mae"]
    if consulta.get("nome_pai"):
        params["nome_pai"] = consulta["nome_pai"]
    return params


PARAM_BUILDERS = {
    "cnd_federal": _build_params_cnd_federal,
    "trf3_sp": _build_params_trf3_sp,
    "trf3": _build_params_trf3,
    "trt2_digital": _build_params_trt2_digital,
    "trt2_fisico": _build_params_trt2_fisico,
    "simples": _build_params_simples,
    "tjsp": _build_params_tjsp,
}


# --------------- Core Processing ---------------

MAX_RETRIES = 3
DEFAULT_TIMEOUT = 240.0


async def _fetch_certidao(
    config: dict,
    consulta: dict,
    token: str,
    client: httpx.AsyncClient,
) -> dict:
    """Call InfoSimples API for a single certificate type, with retry logic.

    Retries up to MAX_RETRIES times on transient failures (timeouts, network
    errors, server errors). Returns dict with keys: success, pdf_url,
    html_content, raw_response, error.
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
                return {
                    "success": True,
                    "file_url": None,
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

    logger.error("InfoSimples %s failed after %d attempts: %s", config["tipo"], MAX_RETRIES, last_error)
    return {
        "success": False,
        "file_url": None,
        "raw_response": last_raw,
        "error": last_error,
    }


async def _download_file(url: str, client: httpx.AsyncClient) -> Optional[tuple[bytes, str]]:
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


def _convert_html_to_pdf(html_bytes: bytes) -> Optional[bytes]:
    """Convert HTML content to PDF using xhtml2pdf."""
    try:
        pdf_buffer = io.BytesIO()
        pisa_status = pisa.CreatePDF(io.BytesIO(html_bytes), dest=pdf_buffer)
        if pisa_status.err:
            logger.error("xhtml2pdf conversion error count: %d", pisa_status.err)
            return None
        return pdf_buffer.getvalue()
    except Exception as e:
        logger.error("HTML→PDF conversion failed: %s", e)
        return None


async def _upload_to_storage(
    pdf_bytes: bytes,
    filename: str,
    db,
    org_id: Optional[str],
    subfolder: Optional[str] = None,
) -> Optional[str]:
    """Upload PDF bytes to Supabase Storage and return public URL."""
    from app.services.storage_service import StorageService

    if not org_id:
        logger.warning("No org_id for storage upload, skipping")
        return None
    try:
        storage = StorageService(db, org_id)
        result = await storage.upload(
            pdf_bytes, filename, "application/pdf",
            categoria="certidoes", subfolder=subfolder,
        )
        return result.get("url")
    except Exception as e:
        logger.error("Storage upload failed: %s", e)
        return None


async def _analyze_with_ai(text: str, org_id: Optional[str] = None) -> Optional[str]:
    """Send document text/summary to the seed `chat_completion` wrapper for analysis.

    Returns a fallback marker if OpenAI key is not configured (AI analysis
    is optional — the certificate itself is still valid without it).

    Refactored 2026-05-11 (LLM-ERP rollout, Step A): replaced raw
    `httpx.post("https://api.openai.com/v1/chat/completions", ...)` with
    `noctusai_lib.integrations.llm.chat_completion`. Goes through the seed
    provider registry → inherits seed cache / budget / (future) audit hooks
    which the raw-httpx path bypassed. The pre-flight `resolve_credential`
    check is kept so we surface a friendly Portuguese message at the
    Certidão UI instead of bubbling up `LLMNotConfigured`.
    """
    api_key = resolve_credential("openai_api_key", org_id)
    if not api_key:
        logger.warning("AI analysis skipped — openai_api_key not configured")
        return "[Análise IA não disponível — OpenAI API Key não configurada em Configurações > Chaves de API]"

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
            model="gpt-4.1-mini",
            org_id=org_id,
            max_tokens=1000,
        )
    except Exception as e:
        logger.error("AI analysis failed: %s", e)
        return f"[Erro na análise IA: {e}]"


async def _process_single_certidao(
    config: dict,
    consulta: dict,
    infosimples_token: str,
    db,
    resultado_id: str,
    http_client: httpx.AsyncClient,
) -> None:
    """Process a single certificate: fetch → download → analyze → update DB.

    Updates the parent consulta's progress (concluidas count) after each
    certificate finishes so the frontend progress bar updates in real-time.
    """
    consulta_id = consulta["id"]

    # Update status to processando and record when the API call is about to happen.
    # api_requested_at survives status resets (reprocessing) so the TJSP cooldown
    # is always enforced — even after a resultado is reset from "erro" to "na_fila".
    db.table("certidao_resultados").update({
        "status": "processando",
        "api_requested_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", resultado_id).execute()

    # Fetch from InfoSimples
    result = await _fetch_certidao(config, consulta, infosimples_token, http_client)

    if not result["success"]:
        db.table("certidao_resultados").update({
            "status": "erro",
            "erro_mensagem": result["error"],
            "api_response": result["raw_response"],
        }).eq("id", resultado_id).execute()
        _atualizar_status_consulta(consulta_id, db)
        return

    # "Nada consta" result (e.g., no protests found) — success without PDF
    if result.get("nada_consta"):
        db.table("certidao_resultados").update({
            "status": "sucesso",
            "analise_ia": result["nada_consta"],
            "api_response": result["raw_response"],
            "erro_mensagem": None,
        }).eq("id", resultado_id).execute()
        _atualizar_status_consulta(consulta_id, db)
        return

    file_url = result["file_url"]
    arquivo_url = file_url
    is_html = config["response_format"] == "html"

    # Download document and persist to Supabase Storage so we don't
    # depend on InfoSimples keeping the site_receipt URL alive.
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
                pdf_bytes = _convert_html_to_pdf(raw_bytes)
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
                filename = f"{config['tipo']}_{uuid.uuid4().hex[:8]}.pdf"
                stored_url = await _upload_to_storage(
                    pdf_bytes, filename, db, consulta.get("org_id"),
                    subfolder=consulta.get("nome"),
                )
                if stored_url:
                    arquivo_url = stored_url
        else:
            logger.warning(
                "Failed to download file for %s from %s, keeping original URL",
                config["tipo"], file_url,
            )

    # AI analysis (use raw response summary as text input)
    analise = None
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
            analise = await _analyze_with_ai(text_for_analysis, consulta.get("org_id"))

    # Update resultado — always store as .pdf
    update_data = {
        "status": "sucesso",
        "arquivo_url": arquivo_url,
        "arquivo_nome": f"{config['tipo']}.pdf",
        "analise_ia": analise,
        "api_response": result["raw_response"],
        "erro_mensagem": None,
    }
    db.table("certidao_resultados").update(update_data).eq("id", resultado_id).execute()
    _atualizar_status_consulta(consulta_id, db)


def _atualizar_status_consulta(consulta_id: str, db) -> None:
    """Recalculate and update the consulta's progress and status.

    Called after each certificate finishes (success or error) so the
    frontend progress bar updates in real-time. Also called by the TJSP
    queue worker after processing queued items.

    Status logic:
    - Any resultado still pending/processing/queued → "processando"
    - All done, at least one success → "concluida"
    - All done, zero successes → "erro"
    """
    updated = db.table("certidao_resultados").select("status").eq(
        "consulta_id", consulta_id
    ).execute()
    rows = updated.data or []

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

    db.table("certidao_consultas").update({
        "status": final_status,
        "concluidas": sucessos,
    }).eq("id", consulta_id).execute()


async def processar_consulta(consulta_id: str, db) -> None:
    """Process all certificates for a consulta (runs in background).

    All certificates are processed in parallel. TJSP is included if the
    35-minute cooldown has passed; otherwise it's queued ("na_fila") for
    the background worker. A premature TJSP request resets the API counter,
    so we never fire before the cooldown expires.
    """
    # Fetch consulta
    consulta_result = db.table("certidao_consultas").select("*").eq(
        "id", consulta_id
    ).single().execute()
    consulta = consulta_result.data

    # Update status
    db.table("certidao_consultas").update({
        "status": "processando",
    }).eq("id", consulta_id).execute()

    # Fetch all resultados
    resultados_result = db.table("certidao_resultados").select("*").eq(
        "consulta_id", consulta_id
    ).order("ordem").execute()
    resultados = resultados_result.data or []

    # Validate InfoSimples token — required for certificate issuance
    infosimples_token = _get_infosimples_token(consulta.get("org_id"))
    if not infosimples_token:
        error_msg = (
            "Token InfoSimples não configurado. "
            "Acesse Configurações e insira o token para emitir certidões."
        )
        logger.error("InfoSimples token missing for consulta %s", consulta_id)
        resultado_ids = [r["id"] for r in resultados]
        if resultado_ids:
            db.table("certidao_resultados").update({
                "status": "erro",
                "erro_mensagem": error_msg,
            }).in_("id", resultado_ids).execute()
        db.table("certidao_consultas").update({
            "status": "erro",
            "concluidas": 0,
        }).eq("id", consulta_id).execute()
        return

    # Build config lookup
    config_by_tipo = {c["tipo"]: c for c in CERTIDOES_CONFIG}

    # Only process resultados that are pending (skip already succeeded ones)
    pending = [r for r in resultados if r["status"] == "pendente"]

    # Separate TJSP from non-TJSP
    tjsp_pending = [r for r in pending if r["tipo"] == TJSP_TIPO]
    non_tjsp_pending = [r for r in pending if r["tipo"] != TJSP_TIPO]

    # Check TJSP cooldown — if clear, process in parallel; otherwise queue
    tjsp_can_run = False
    if tjsp_pending:
        org_id = consulta.get("org_id")
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
            # No previous successful TJSP request — safe to run immediately
            tjsp_can_run = True

    # Process all eligible certificates in parallel
    async with httpx.AsyncClient() as http_client:
        tasks = []
        for r in non_tjsp_pending:
            config = config_by_tipo.get(r["tipo"])
            if not config:
                continue
            tasks.append(
                _process_single_certidao(
                    config, consulta, infosimples_token, db, r["id"], http_client
                )
            )
        if tjsp_can_run:
            for r in tjsp_pending:
                config = config_by_tipo.get(r["tipo"])
                if config:
                    tasks.append(
                        _process_single_certidao(
                            config, consulta, infosimples_token, db, r["id"], http_client
                        )
                    )
                    logger.info("TJSP resultado %s processing immediately (cooldown clear)", r["id"])
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Log any unexpected exceptions
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error("Certificate processing failed: %s", result)

    # Queue TJSP items that couldn't run due to cooldown and schedule deferred processing
    if not tjsp_can_run and tjsp_pending:
        tjsp_ids = [r["id"] for r in tjsp_pending]
        db.table("certidao_resultados").update({
            "status": "na_fila",
        }).in_("id", tjsp_ids).execute()
        for r in tjsp_pending:
            logger.info("TJSP resultado %s queued (na_fila) — cooldown active", r["id"])
        org_id = consulta.get("org_id")
        if org_id:
            schedule_tjsp_for_org(org_id, db)

    # Update consulta status (may be "processando" if TJSP items are still queued)
    _atualizar_status_consulta(consulta_id, db)


# Maximum time a resultado can stay "processando" before being considered stuck.
# InfoSimples API calls timeout at 240s with 3 retries = ~12 min worst case.
STALE_PROCESSANDO_SECONDS = 15 * 60  # 15 minutes


def recover_stale_processando(db) -> int:
    """Detect and recover resultados stuck in 'processando' for too long.

    Called on every list/detail fetch so the frontend never loops forever
    on stuck items. Uses api_requested_at (set right before the API call in
    _process_single_certidao) to determine staleness — NOT updated_at which
    may reflect the original creation time.

    Only recovers items that have an api_requested_at older than the threshold.
    Items still in 'processando' without api_requested_at are waiting to start
    and are handled by recover_stuck_processando on server startup.

    Returns the number of recovered items.
    """
    cutoff = (
        datetime.now(timezone.utc) - timedelta(seconds=STALE_PROCESSANDO_SECONDS)
    ).isoformat()

    # Fetch all "processando" items, then filter in Python for stale ones.
    # We can't use .lt("api_requested_at", cutoff) directly because items
    # without api_requested_at (NULL) would be silently included or excluded
    # depending on the PostgREST version.
    stuck = db.table("certidao_resultados").select(
        "id, tipo, consulta_id, api_requested_at"
    ).eq("status", "processando").execute()

    stale = [
        item for item in (stuck.data or [])
        if item.get("api_requested_at") and item["api_requested_at"] < cutoff
    ]

    if not stale:
        return 0

    logger.warning("Auto-recovering %d stale 'processando' items (>%ds old)", len(stale), STALE_PROCESSANDO_SECONDS)

    stale_ids = [item["id"] for item in stale]
    db.table("certidao_resultados").update({
        "status": "erro",
        "erro_mensagem": "Processamento expirou — a automação foi interrompida. Tente reprocessar ou faça upload manual.",
    }).in_("id", stale_ids).execute()

    consulta_ids: set[str] = set()
    for item in stale:
        consulta_ids.add(item["consulta_id"])
        logger.info("Auto-recovered stale resultado %s (api_requested_at=%s) → erro", item["id"], item["api_requested_at"])

    for cid in consulta_ids:
        _atualizar_status_consulta(cid, db)

    return len(stale)


def cancelar_processamento(consulta_id: str, db) -> dict:
    """Cancel in-progress certificate processing for a specific consulta.

    Resets all resultados of the given consulta that are pendente/processando/na_fila
    to 'erro' with a cancellation message. Also cancels any scheduled TJSP tasks
    for affected orgs.

    Returns counts of cancelled items.
    """
    in_progress = db.table("certidao_resultados").select(
        "id, tipo, org_id"
    ).eq("consulta_id", consulta_id).in_(
        "status", ["pendente", "processando", "na_fila"]
    ).execute()

    items = in_progress.data or []
    if not items:
        return {"cancelados": 0}

    item_ids = [item["id"] for item in items]
    db.table("certidao_resultados").update({
        "status": "erro",
        "erro_mensagem": "Cancelado manualmente pelo usuário.",
    }).in_("id", item_ids).execute()

    # Cancel any scheduled TJSP tasks for affected orgs
    org_ids = set(item.get("org_id") for item in items if item.get("org_id"))
    for oid in org_ids:
        task = _tjsp_scheduled_tasks.pop(oid, None)
        if task and not task.done():
            task.cancel()
            logger.info("Cancelled scheduled TJSP task for org %s", oid)

    _atualizar_status_consulta(consulta_id, db)

    logger.info("Cancelled %d in-progress resultados for consulta %s", len(items), consulta_id)
    return {"cancelados": len(items)}


def _get_infosimples_token(org_id: Optional[str] = None) -> Optional[str]:
    """Resolve InfoSimples token via the standard credential chain."""
    return resolve_credential("infosimples_token", org_id)


def check_required_credentials(org_id: Optional[str] = None) -> list[str]:
    """Check which required credentials are missing for certificate issuance.

    Returns a list of human-readable messages for each missing credential.
    Empty list means all credentials are configured.
    """
    missing = []
    if not resolve_credential("infosimples_token", org_id):
        missing.append(
            "Token InfoSimples não configurado — necessário para emissão de certidões."
        )
    return missing


def get_certidoes_tipos() -> list[dict]:
    """Return the list of available certificate types for the frontend."""
    return [
        {"tipo": c["tipo"], "nome": c["nome"], "ordem": c["ordem"]}
        for c in CERTIDOES_CONFIG
    ]


async def process_manual_upload(
    pdf_bytes: bytes,
    resultado_id: str,
    consulta: dict,
    tipo: str,
    nome_display: str,
    org_id: Optional[str],
    db,
) -> dict:
    """Process a manually uploaded certificate PDF using the same pipeline
    as the automated flow (post-download steps of _process_single_certidao).

    Steps replicated from the automated flow:
    1. Upload to Supabase Storage (same bucket/path pattern)
    2. Extract text from PDF for AI analysis
    3. Run AI analysis on extracted text
    4. Update resultado → sucesso
    5. Recalculate consulta status

    Returns the update_data dict applied to the resultado.
    """
    consulta_id = consulta["id"]

    # Mark as processando (same as automated flow)
    db.table("certidao_resultados").update({
        "status": "processando",
    }).eq("id", resultado_id).execute()

    # 1. Upload to Supabase Storage — same pattern as _process_single_certidao
    filename = f"{tipo}_{uuid.uuid4().hex[:8]}.pdf"
    arquivo_url = await _upload_to_storage(
        pdf_bytes, filename, db, org_id,
        subfolder=consulta.get("nome"),
    )

    # 2. Extract text from PDF for AI analysis (replaces the API response
    #    data that the automated flow uses as input for _analyze_with_ai)
    text_for_analysis = _extract_pdf_text(pdf_bytes, nome_display)

    # 3. AI analysis — same function as automated flow
    analise = None
    if text_for_analysis:
        analise = await _analyze_with_ai(text_for_analysis, org_id)

    # 4. Update resultado → sucesso (same fields as automated flow)
    update_data: dict = {
        "status": "sucesso",
        "arquivo_url": arquivo_url,
        "arquivo_nome": f"{tipo}.pdf",
        "analise_ia": analise,
        "api_response": None,
        "erro_mensagem": None,
    }
    db.table("certidao_resultados").update(update_data).eq(
        "id", resultado_id
    ).execute()

    # 5. Recalculate consulta status — same function as automated flow
    _atualizar_status_consulta(consulta_id, db)

    return update_data


def _extract_pdf_text(pdf_bytes: bytes, nome_display: str) -> Optional[str]:
    """Extract text content from a PDF for AI analysis.

    Uses the seed classifier rather than a bare `get_text()` sweep: a
    scanned certidão carries a digital-signature stamp as real text, so
    "the page returned something" is not evidence the certidão is
    readable. Feeding that stamp to `_analyze_with_ai` spends a model call
    to analyse a validation URL. Returns None when nothing trustworthy is
    there, which the caller already treats as "no analysis".
    """
    try:
        from noctusai_lib.integrations.media import classify_pdf_text_layer

        camada = classify_pdf_text_layer(pdf_bytes)
        # Per-page: a certidão whose first pages are typeset and whose
        # annexes are scanned still yields its readable half.
        extracted = camada.text
        if not extracted:
            return None
        # Prefix with certificate type for context (mirrors how the
        # automated flow sends structured API response data)
        # Truncate to avoid exceeding token limits
        return f"Certidão: {nome_display}\n\n{extracted[:4000]}"
    except Exception as e:
        logger.warning("PDF text extraction failed: %s", e)
        return None


# --------------- TJSP On-Demand Scheduler ---------------
#
# Instead of polling every N seconds, TJSP items are scheduled to fire at the
# exact moment the cooldown expires. Each org has at most one scheduled task.
# After processing, the task chains the next queued item (if any) with a fresh
# 35-minute delay.

# One scheduled asyncio.Task per org — prevents double-scheduling and holds
# a strong reference so the task isn't garbage-collected.
_tjsp_scheduled_tasks: dict[str, asyncio.Task] = {}


def _get_tjsp_last_request_at(org_id: str, db) -> Optional[datetime]:
    """Get the timestamp of the last TJSP API request for an org.

    Uses the dedicated api_requested_at column which is set right before
    calling the InfoSimples API and is NEVER cleared on reprocessing.
    This ensures the cooldown is always enforced — even after a resultado
    is reset from "erro" to "na_fila" for retry.

    Fetches recent TJSP resultados and filters NULLs in Python rather than
    relying on supabase-py's .not_.is_() filter, which can silently return
    NULL rows depending on the client version.
    """
    result = db.table("certidao_resultados").select(
        "api_requested_at"
    ).eq("tipo", TJSP_TIPO).eq("org_id", org_id).order(
        "created_at", desc=True
    ).limit(10).execute()

    # Find the most recent non-null api_requested_at
    for row in (result.data or []):
        ts_str = row.get("api_requested_at")
        if not ts_str:
            continue
        try:
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as exc:
            logger.warning(
                "certidoes_service: certidao id=%s has unparseable api_requested_at=%r (%s); "
                "skipping when computing TJSP cooldown",
                row.get("id"), ts_str, exc,
            )
            continue
    return None


def _get_tjsp_remaining_cooldown(org_id: str, db) -> float:
    """Calculate seconds remaining on TJSP cooldown for an org. Returns 0.0 if clear."""
    last_at = _get_tjsp_last_request_at(org_id, db)
    if not last_at:
        logger.info("TJSP cooldown: no previous api_requested_at found for org %s", org_id)
        return 0.0
    elapsed = (datetime.now(timezone.utc) - last_at).total_seconds()
    remaining = max(0.0, TJSP_COOLDOWN_SECONDS - elapsed)
    logger.info(
        "TJSP cooldown for org %s: last_at=%s, elapsed=%.0fs, remaining=%.0fs",
        org_id, last_at.isoformat(), elapsed, remaining,
    )
    return remaining


async def _process_single_tjsp_item(resultado: dict, db) -> None:
    """Process one queued TJSP resultado: fetch its consulta, call InfoSimples."""
    consulta_id = resultado["consulta_id"]
    org_id = resultado.get("org_id")

    # Fetch parent consulta for params
    consulta_result = db.table("certidao_consultas").select("*").eq(
        "id", consulta_id
    ).single().execute()
    consulta = consulta_result.data
    if not consulta:
        logger.error("TJSP queue: consulta %s not found for resultado %s", consulta_id, resultado["id"])
        db.table("certidao_resultados").update({
            "status": "erro",
            "erro_mensagem": "Consulta não encontrada",
        }).eq("id", resultado["id"]).execute()
        _atualizar_status_consulta(consulta_id, db)
        return

    infosimples_token = _get_infosimples_token(org_id)
    if not infosimples_token:
        db.table("certidao_resultados").update({
            "status": "erro",
            "erro_mensagem": "Token InfoSimples não configurado.",
        }).eq("id", resultado["id"]).execute()
        _atualizar_status_consulta(consulta_id, db)
        return

    config = next((c for c in CERTIDOES_CONFIG if c["tipo"] == TJSP_TIPO), None)
    if not config:
        return

    async with httpx.AsyncClient() as http_client:
        await _process_single_certidao(
            config, consulta, infosimples_token, db, resultado["id"], http_client
        )

    _atualizar_status_consulta(consulta_id, db)


async def _delayed_tjsp_process(delay: float, resultado: dict, org_id: str, db) -> None:
    """Sleep for the remaining cooldown, process one TJSP item, then chain the next.

    Runs as a one-shot asyncio.Task in the main event loop. After completion
    (success or failure), checks for more queued items for the same org and
    schedules the next one with a fresh cooldown delay.

    On CancelledError (server shutdown / --reload), does NOT reschedule —
    the new process's schedule_all_pending_tjsp handles that on startup.
    """
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

        # Verify the item is still queued (might have been deleted or reprocessed)
        check = db.table("certidao_resultados").select("status").eq(
            "id", resultado_id
        ).execute()
        if not check.data or check.data[0]["status"] != "na_fila":
            logger.info("TJSP resultado %s no longer na_fila, skipping", resultado_id)
            return

        logger.info("TJSP processing: resultado %s (org %s)", resultado_id, org_id)
        await _process_single_tjsp_item(resultado, db)

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
        db.table("certidao_resultados").update({
            "status": "erro",
            "erro_mensagem": f"Erro no processamento: {e}",
        }).eq("id", resultado_id).execute()
        _atualizar_status_consulta(resultado["consulta_id"], db)
    finally:
        _tjsp_scheduled_tasks.pop(org_id, None)
        # Only reschedule on normal completion or handled errors — NOT on
        # CancelledError (server shutdown). The new process's lifespan
        # calls schedule_all_pending_tjsp which handles rescheduling.
        if not cancelled:
            schedule_tjsp_for_org(org_id, db)


def schedule_tjsp_for_org(org_id: str, db) -> None:
    """Schedule the next queued TJSP item for an org.

    Idempotent: if a task is already in-flight for this org, does nothing.
    Calculates the exact delay from api_requested_at so the item fires
    precisely when the cooldown expires — no polling.
    """
    existing = _tjsp_scheduled_tasks.get(org_id)
    if existing and not existing.done():
        return  # Already scheduled

    # Find next queued item for this org (oldest first)
    queued = db.table("certidao_resultados").select(
        "id, consulta_id, org_id"
    ).eq("tipo", TJSP_TIPO).eq("status", "na_fila").eq(
        "org_id", org_id
    ).order("created_at").limit(1).execute()

    items = queued.data or []
    if not items:
        return

    remaining = _get_tjsp_remaining_cooldown(org_id, db)
    task = schedule_coro(
        _delayed_tjsp_process(remaining, items[0], org_id, db),
        logger=logger,
        name=f"tjsp_{org_id}",
    )
    _tjsp_scheduled_tasks[org_id] = task
    logger.info(
        "TJSP task scheduled for org %s: resultado %s in %.0fs",
        org_id, items[0]["id"], remaining,
    )


def schedule_all_pending_tjsp(db) -> None:
    """Scan for all queued TJSP items and schedule one task per org.

    Called once on server startup (after recover_stuck_processando) to
    resume any items that were waiting before the server restarted.
    """
    queued = db.table("certidao_resultados").select(
        "org_id"
    ).eq("tipo", TJSP_TIPO).eq("status", "na_fila").execute()

    org_ids = set(
        item["org_id"] for item in (queued.data or []) if item.get("org_id")
    )
    if org_ids:
        logger.info("Scheduling pending TJSP items for %d org(s) on startup", len(org_ids))
    for oid in org_ids:
        schedule_tjsp_for_org(oid, db)


def recover_stuck_processando(db) -> None:
    """Reset orphaned "processando" items left by killed background tasks.

    Called once on server startup. Non-TJSP items go back to "pendente",
    TJSP items go back to "na_fila", so they are picked up by
    schedule_all_pending_tjsp.
    """
    stuck = db.table("certidao_resultados").select(
        "id, tipo, consulta_id"
    ).eq("status", "processando").execute()

    items = stuck.data or []
    if not items:
        return

    logger.warning("Recovering %d stuck 'processando' items on startup", len(items))

    # Batch update: split by TJSP vs non-TJSP (different target statuses)
    tjsp_ids = [item["id"] for item in items if item["tipo"] == TJSP_TIPO]
    non_tjsp_ids = [item["id"] for item in items if item["tipo"] != TJSP_TIPO]

    if non_tjsp_ids:
        db.table("certidao_resultados").update({
            "status": "pendente",
            "erro_mensagem": None,
        }).in_("id", non_tjsp_ids).execute()

    if tjsp_ids:
        db.table("certidao_resultados").update({
            "status": "na_fila",
            "erro_mensagem": None,
        }).in_("id", tjsp_ids).execute()

    consulta_ids = {item["consulta_id"] for item in items}
    for cid in consulta_ids:
        _atualizar_status_consulta(cid, db)
