"""The certificate catalogue and its per-endpoint parameter builders.

🔴 `CERTIDOES_CONFIG` IS A CONTRACT WITH TEN THIRD-PARTY ENDPOINTS.
Every entry — `tipo`, `nome`, `endpoint`, `ordem`, `params_fn`,
`response_format` — is carried over from
`products/erp-imobiliario/backend/app/services/certidoes_service.py` UNCHANGED.
Each `params_fn` matches the exact parameter set one InfoSimples endpoint
accepts; the endpoints REJECT unknown parameters, so "send everything and let
them ignore it" is not an option, and a dropped or reordered type is a
certificate a user silently stops getting rather than an error anyone sees.

`ordem` is also the display order of the checklist the operator reads down.

Split out of `service.py` (which the ERP kept as one 1 195-line file) because
this half is DATA about other people's systems and the other half is our
pipeline: they change for entirely different reasons.
"""
from __future__ import annotations

from typing import Optional

from app.modules.certidoes.credentials import (
    INFOSIMPLES_EMAIL_ENVIO,
    resolve_key,
)

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
    email = resolve_key(INFOSIMPLES_EMAIL_ENVIO, org_id) if org_id else None
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

#: `tipo` → its config row. Built once; every lookup in the pipeline goes
#: through it rather than re-scanning the list per resultado.
CONFIG_BY_TIPO: dict[str, dict] = {c["tipo"]: c for c in CERTIDOES_CONFIG}


def get_certidoes_tipos() -> list[dict]:
    """Return the list of available certificate types for the frontend."""
    return [
        {"tipo": c["tipo"], "nome": c["nome"], "ordem": c["ordem"]}
        for c in CERTIDOES_CONFIG
    ]


def config_for(tipo: str) -> Optional[dict]:
    """The config row for `tipo`, or `None` when the registry has no such type.

    `None` is a real answer, not a swallowed error: a `certidao_resultados` row
    can outlive a type that was removed from the registry, and the callers
    treat that as "skip this one" rather than crashing the whole consulta.
    """
    return CONFIG_BY_TIPO.get(tipo)


__all__ = [
    "CERTIDOES_CONFIG",
    "CONFIG_BY_TIPO",
    "INFOSIMPLES_BASE_URL",
    "PARAM_BUILDERS",
    "TJSP_COOLDOWN_SECONDS",
    "TJSP_TIPO",
    "config_for",
    "get_certidoes_tipos",
]
