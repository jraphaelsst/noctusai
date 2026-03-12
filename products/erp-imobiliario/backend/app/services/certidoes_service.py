"""
Certidões Negativas Service — Orchestrates certificate issuance via InfoSimples API,
AI-powered document analysis, and result persistence.

Each certificate type is defined declaratively in CERTIDOES_CONFIG. The processing
pipeline (fetch → download → analyze → store) is shared across all types.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from app.services.credential_resolver import resolve_credential

logger = logging.getLogger(__name__)


# --------------- Certificate Registry ---------------

CERTIDOES_CONFIG = [
    {
        "tipo": "cnd_federal",
        "nome": "CND Federal (Receita)",
        "endpoint": "receita-federal/pgfn",
        "ordem": 1,
        "params_fn": "basico",
        "response_format": "pdf",
    },
    {
        "tipo": "trf3",
        "nome": "Certidão TRF3 (Regional)",
        "endpoint": "tribunal/trf3/certidao-distr",
        "ordem": 2,
        "params_fn": "trf3",
        "response_format": "pdf",
    },
    {
        "tipo": "trt2_digital",
        "nome": "TRT2 (Trabalhista SP) Digital",
        "endpoint": "tribunal/trt2/ceat-digital",
        "ordem": 3,
        "params_fn": "basico",
        "response_format": "pdf",
    },
    {
        "tipo": "trt2_fisico",
        "nome": "TRT2 (Trabalhista SP) Físico",
        "endpoint": "tribunal/trt2/ceat",
        "ordem": 4,
        "params_fn": "basico",
        "response_format": "html",
    },
    {
        "tipo": "cnd_trabalhista_tst",
        "nome": "CND Trabalhistas (TST)",
        "endpoint": "tst/cndt",
        "ordem": 5,
        "params_fn": "basico",
        "response_format": "pdf",
    },
    {
        "tipo": "tjsp",
        "nome": "Certidão TJSP",
        "endpoint": "tribunal/tjsp/pedido-certidao",
        "ordem": 6,
        "params_fn": "tjsp",
        "response_format": "pdf",
    },
    {
        "tipo": "cenprot",
        "nome": "CENPROT (Protestos)",
        "endpoint": "cenprot-sp/protestos",
        "ordem": 7,
        "params_fn": "basico",
        "response_format": "pdf",
    },
    {
        "tipo": "cnd_fazenda_sp",
        "nome": "CND Fazenda SP",
        "endpoint": "sefaz/sp/certidao-debitos",
        "ordem": 8,
        "params_fn": "basico",
        "response_format": "pdf",
    },
    {
        "tipo": "divida_ativa_sp",
        "nome": "Dívida Ativa SP",
        "endpoint": "pge/sp/cndt",
        "ordem": 9,
        "params_fn": "basico",
        "response_format": "pdf",
    },
]

INFOSIMPLES_BASE_URL = "https://api.infosimples.com/api/v2/consultas"


# --------------- Parameter Builders ---------------

def _build_params_basico(consulta: dict, token: str) -> dict:
    """Basic params: token + CPF/CNPJ + birthdate."""
    doc_key = "cpf" if consulta["tipo_documento"] == "cpf" else "cnpj"
    params = {"token": token, doc_key: consulta["documento"]}
    if consulta.get("data_nascimento"):
        params["birthdate"] = consulta["data_nascimento"]
    return params


def _build_params_trf3(consulta: dict, token: str) -> dict:
    """TRF3 params: basic + type and scope."""
    params = _build_params_basico(consulta, token)
    params["tipo"] = "1"
    params["abrangencia"] = "1"
    return params


def _build_params_tjsp(consulta: dict, token: str) -> dict:
    """TJSP params: basic + modelo + optional RG/gender/parents."""
    params = _build_params_basico(consulta, token)
    params["modelo"] = "4"
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
    "basico": _build_params_basico,
    "trf3": _build_params_trf3,
    "tjsp": _build_params_tjsp,
}


# --------------- Core Processing ---------------

async def _fetch_certidao(
    config: dict,
    consulta: dict,
    token: str,
    client: httpx.AsyncClient,
) -> dict:
    """Call InfoSimples API for a single certificate type.

    Returns dict with keys: success, pdf_url, html_content, raw_response, error.
    """
    builder = PARAM_BUILDERS[config["params_fn"]]
    params = builder(consulta, token)

    url = f"{INFOSIMPLES_BASE_URL}/{config['endpoint']}"

    try:
        resp = await client.get(url, params=params, timeout=120.0)
        data = resp.json()

        if data.get("code") == 200 and data.get("data"):
            site_receipt = data["data"][0].get("site_receipt", "")
            return {
                "success": True,
                "pdf_url": site_receipt if config["response_format"] == "pdf" else None,
                "html_content": site_receipt if config["response_format"] == "html" else None,
                "raw_response": data,
                "error": None,
            }

        error_msg = data.get("message") or data.get("code_message") or "Erro na consulta"
        return {
            "success": False,
            "pdf_url": None,
            "html_content": None,
            "raw_response": data,
            "error": error_msg,
        }
    except Exception as e:
        logger.error("InfoSimples request failed for %s: %s", config["tipo"], e)
        return {
            "success": False,
            "pdf_url": None,
            "html_content": None,
            "raw_response": None,
            "error": str(e),
        }


async def _download_pdf(url: str, client: httpx.AsyncClient) -> Optional[bytes]:
    """Download a PDF from a URL."""
    try:
        resp = await client.get(url, timeout=60.0)
        if resp.status_code == 200:
            return resp.content
        logger.warning("PDF download failed with status %d", resp.status_code)
        return None
    except Exception as e:
        logger.error("PDF download error: %s", e)
        return None


async def _analyze_with_ai(text: str, org_id: Optional[str] = None) -> Optional[str]:
    """Send document text/summary to OpenAI for analysis.

    Follows dry-run pattern: returns mock if OPENAI_API_KEY is not configured.
    """
    api_key = resolve_credential("openai_api_key", org_id)
    if not api_key:
        logger.info("[dry-run] AI analysis skipped — OPENAI_API_KEY not configured")
        return "[Análise IA indisponível — chave de API não configurada]"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "gpt-4.1-mini",
                    "messages": [
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
                    "max_tokens": 1000,
                },
                timeout=60.0,
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"]
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
    """Process a single certificate: fetch → download → analyze → update DB."""
    # Update status to processando
    db.table("certidao_resultados").update({
        "status": "processando",
    }).eq("id", resultado_id).execute()

    # Fetch from InfoSimples
    result = await _fetch_certidao(config, consulta, infosimples_token, http_client)

    if not result["success"]:
        db.table("certidao_resultados").update({
            "status": "erro",
            "erro_mensagem": result["error"],
            "api_response": result["raw_response"],
        }).eq("id", resultado_id).execute()
        return

    # Download PDF if available
    arquivo_url = None
    if result["pdf_url"]:
        arquivo_url = result["pdf_url"]

    # AI analysis (use raw response summary as text input)
    analise = None
    raw = result["raw_response"]
    if raw and raw.get("data"):
        # Build text summary from API response for AI analysis
        summary_parts = []
        for item in raw["data"]:
            if isinstance(item, dict):
                for k, v in item.items():
                    if k != "site_receipt" and v:
                        summary_parts.append(f"{k}: {v}")
        if summary_parts:
            text_for_analysis = "\n".join(summary_parts)
            analise = await _analyze_with_ai(text_for_analysis, consulta.get("org_id"))

    # Update resultado
    update_data = {
        "status": "sucesso",
        "arquivo_url": arquivo_url,
        "arquivo_nome": f"{config['tipo']}.pdf",
        "analise_ia": analise,
        "api_response": result["raw_response"],
    }
    db.table("certidao_resultados").update(update_data).eq("id", resultado_id).execute()


async def processar_consulta(consulta_id: str, db) -> None:
    """Process all certificates for a consulta (runs in background).

    Fans out to all certificate types in parallel, updating each resultado
    independently so partial results are visible immediately.
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

    # Get InfoSimples token (dry-run pattern)
    infosimples_token = _get_infosimples_token(consulta.get("org_id"))
    if not infosimples_token:
        logger.info("[dry-run] InfoSimples token not configured — marking all as dry-run")
        for r in resultados:
            db.table("certidao_resultados").update({
                "status": "sucesso",
                "analise_ia": "[Modo simulação — token InfoSimples não configurado]",
            }).eq("id", r["id"]).execute()
        db.table("certidao_consultas").update({
            "status": "concluida",
            "concluidas": len(resultados),
        }).eq("id", consulta_id).execute()
        return

    # Build config lookup
    config_by_tipo = {c["tipo"]: c for c in CERTIDOES_CONFIG}

    # Process all certificates in parallel
    async with httpx.AsyncClient() as http_client:
        tasks = []
        for r in resultados:
            config = config_by_tipo.get(r["tipo"])
            if not config:
                continue
            tasks.append(
                _process_single_certidao(
                    config, consulta, infosimples_token, db, r["id"], http_client
                )
            )
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Log any unexpected exceptions
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error("Certificate processing failed: %s", result)

    # Count successes and update consulta
    updated_resultados = db.table("certidao_resultados").select("status").eq(
        "consulta_id", consulta_id
    ).execute()
    concluidas = sum(
        1 for r in (updated_resultados.data or []) if r["status"] == "sucesso"
    )
    erros = sum(
        1 for r in (updated_resultados.data or []) if r["status"] == "erro"
    )

    final_status = "concluida"
    if concluidas == 0 and erros > 0:
        final_status = "erro"

    db.table("certidao_consultas").update({
        "status": final_status,
        "concluidas": concluidas,
    }).eq("id", consulta_id).execute()


def _get_infosimples_token(org_id: Optional[str] = None) -> Optional[str]:
    """Resolve InfoSimples token via the standard credential chain."""
    return resolve_credential("infosimples_token", org_id)


def get_certidoes_tipos() -> list[dict]:
    """Return the list of available certificate types for the frontend."""
    return [
        {"tipo": c["tipo"], "nome": c["nome"], "ordem": c["ordem"]}
        for c in CERTIDOES_CONFIG
    ]
