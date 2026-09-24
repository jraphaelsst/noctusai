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

from datetime import datetime
from typing import Any, Optional

from app.modules.certidoes.credentials import (
    INFOSIMPLES_EMAIL_ENVIO,
    resolve_key,
)

#: The `resultado` vocabulary — kept in sync BY HAND with migration 107's
#: `certidao_resultados_resultado_check` (widened by migration 116 to add
#: `negativa_com_homonimos`) and `schemas.ResultadoPatch`'s `Literal`. Not a
#: shared import across those three because two of them (SQL, Pydantic)
#: cannot import a Python frozenset; this is the same duplicated-but-documented
#: vocabulary `genero`'s `M`/`F` already lives with elsewhere in this schema.
#:
#: `negativa_com_homonimos` (migration 116): a negativa whose document itself
#: says so ONLY WITH A CAVEAT — the source found no record for this exact
#: identity, but flags that OTHER records exist under the same name/CPF that
#: could not be ruled out (a homônimo). That is materially different due-
#: diligence information from a clean `negativa` and must not be collapsed
#: into it; see `service._analyze_estrutura_with_ai`'s prompt, the one place
#: today capable of reading that caveat off the document text.
RESULTADO_VALUES = frozenset({
    "negativa", "positiva", "positiva_com_efeito_de_negativa", "nao_emitida",
    "negativa_com_homonimos",
})

# --------------- Certificate Registry ---------------

CERTIDOES_CONFIG = [
    {
        "tipo": "cnd_federal",
        "nome": "CND Federal (Receita)",
        "endpoint": "receita-federal/pgfn",
        "ordem": 1,
        "params_fn": "cnd_federal",
        "parse_fn": "padrao",
        "response_format": "pdf",
    },
    {
        "tipo": "trf3_sp",
        "nome": "Certidão TRF3 Cível — São Paulo (1ª instância)",
        "endpoint": "tribunal/trf3/certidao-distr",
        "ordem": 2,
        "params_fn": "trf3_sp",
        "parse_fn": "padrao",
        "response_format": "html",
    },
    {
        "tipo": "trf3",
        "nome": "Certidão TRF3 Cível — Tribunal Regional (2ª instância)",
        "endpoint": "tribunal/trf3/certidao-distr",
        "ordem": 3,
        "params_fn": "trf3",
        "parse_fn": "padrao",
        "response_format": "html",
    },
    {
        "tipo": "trt2_digital",
        "nome": "TRT2 (Trabalhista SP) Digital",
        "endpoint": "tribunal/trt2/ceat-digital",
        "ordem": 4,
        "params_fn": "trt2_digital",
        "parse_fn": "padrao",
        "response_format": "html",
    },
    {
        "tipo": "trt2_fisico",
        "nome": "TRT2 (Trabalhista SP) Físico",
        "endpoint": "tribunal/trt2/ceat",
        "ordem": 5,
        "params_fn": "trt2_fisico",
        "parse_fn": "padrao",
        "response_format": "pdf",
    },
    {
        "tipo": "cnd_trabalhista_tst",
        "nome": "CND Trabalhistas (TST)",
        "endpoint": "tst/cndt",
        "ordem": 6,
        "params_fn": "simples",
        "parse_fn": "padrao",
        "response_format": "pdf",
    },
    {
        "tipo": "tjsp",
        "nome": "Certidão TJSP",
        "endpoint": "tribunal/tjsp/pedido-certidao",
        "ordem": 7,
        "params_fn": "tjsp",
        "parse_fn": "padrao",
        "response_format": "pdf",
    },
    {
        "tipo": "cenprot",
        "nome": "CENPROT (Protestos)",
        "endpoint": "cenprot-sp/protestos",
        "ordem": 8,
        "params_fn": "simples",
        "parse_fn": "cenprot",
        "response_format": "html",
    },
    {
        "tipo": "cnd_fazenda_sp",
        "nome": "CND Fazenda SP",
        "endpoint": "sefaz/sp/certidao-debitos",
        "ordem": 9,
        "params_fn": "simples",
        "parse_fn": "padrao",
        "response_format": "pdf",
    },
    {
        "tipo": "divida_ativa_sp",
        "nome": "Dívida Ativa SP",
        "endpoint": "pge/sp/cndt",
        "ordem": 10,
        "params_fn": "simples",
        "parse_fn": "padrao",
        "response_format": "pdf",
    },
]

# --------------- Manual-upload-only types ---------------
#
# 🔴 DELIBERATELY SEPARATE FROM `CERTIDOES_CONFIG`, NOT FOLDED IN.
# `criar_consulta`'s fan-out iterates `CERTIDOES_CONFIG` verbatim — ten items,
# an existing frontend-facing contract (`test_fan_out_grava_um_resultado_por_
# tipo` pins the count) this change does not touch. These have no
# `endpoint`/`params_fn`: there is no InfoSimples call to make for a Serasa
# report, a TJSP e-SAJ/e-PROC screenshot or an FGTS regularity certificate,
# only a resultado placeholder a human fills by hand via `POST /resultados/
# {id}/upload`. `vincular_parte`/`vincular_cliente`/`vincular_empresa`
# (routers/certidoes.py) fan these out onto a consulta once it is linked to
# a party/titular/empresa, lazily and idempotently — see `_fan_out_tipos_
# manuais`.
#
# `aplicavel_a`: which `certidao_consultas.tipo_documento` values this type
# fans out onto. Default (absent key) is both — `serasa` is a PF credit
# report (CPF-only), `fgts_regularidade` (the Levantamento de Certidões
# matriz's row 5.13, "Regularidade do FGTS (empresas)") is a company-payroll
# obligation (CNPJ-only, N/A for a person — the matriz shows grey N/A for
# every PF column on that row without a resultado ever existing). Read by
# `_fan_out_tipos_manuais`, which generalizes the old serasa-only special
# case into this per-type table.
#
# `fgts_regularidade` backs the matriz's row 5.13 (`MATRIZ_LINHAS` below) —
# added for the "Certidões" card tab (Levantamento de Certidões.xlsx, first
# tab).
#
# 🔴 `outras_1`/`outras_2` (this module's two-fixed-slot first pass at the
# spreadsheet's "Outras: <nome>" rows) are GONE, replaced by owner directive
# (2026-09-24 follow-up) with per-card CUSTOM rows an operator adds/renames/
# removes from the matriz UI itself (migration 170,
# `card_hub.certidoes_matriz_linhas_service`) — "Outras" is not a fixed
# catalogue entry, it is a fact about ONE card. Those two entries and their
# `certidao_resultados` rows never reached `dev`/prod (this whole feature
# shipped on this same still-unmerged branch), so removing them here
# orphans nothing; a resultado for a custom row instead carries
# `tipo='outras_custom'` + `certidao_resultados.linha_customizada_id`
# (migration 170's pairing CHECK), never a registry-catalogue `tipo`.
MANUAL_TIPOS_CONFIG = [
    {"tipo": "serasa", "nome": "Serasa", "ordem": 11, "aplicavel_a": ("cpf",)},
    {"tipo": "tjsp_esaj", "nome": "TJSP e-SAJ", "ordem": 12},
    {"tipo": "tjsp_eproc", "nome": "TJSP e-PROC", "ordem": 13},
    {
        "tipo": "fgts_regularidade",
        "nome": "Regularidade do FGTS (empresas)",
        "ordem": 14,
        "aplicavel_a": ("cnpj",),
    },
]

MANUAL_CONFIG_BY_TIPO: dict[str, dict] = {c["tipo"]: c for c in MANUAL_TIPOS_CONFIG}

#: The sentinel `certidao_resultados.tipo` value for a resultado recording a
#: matriz CUSTOM row's cell — `tipo` stays NOT NULL (migration 091), so a
#: real `NULL` was never an option; `linha_customizada_id` (migration 170)
#: is what actually names WHICH custom row. Never appears in `CERTIDOES_
#: CONFIG`/`MANUAL_TIPOS_CONFIG` — there is no fixed catalogue entry for it.
CUSTOM_ROW_TIPO = "outras_custom"

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


# `tribunal/trf3/certidao-distr` codes, verbatim from the InfoSimples docs
# (API v2.2.39):
#   tipo:        1 = Cível · 2 = Criminal · 3 = Eleitoral
#   abrangencia: 1 = Regional · 2 = Seção Judiciária de São Paulo ·
#                3 = Tribunal Regional Federal da 3ª Região ·
#                4 = Seção Judiciária de Mato Grosso do Sul
# Both TRF3 entries are the Cível certidão; they differ ONLY in abrangência —
# 1ª instância (SJSP + JEF) vs 2ª instância (the Tribunal itself).
TRF3_TIPO_CIVEL = "1"
TRF3_ABRANGENCIA_SAO_PAULO = "2"
TRF3_ABRANGENCIA_TRIBUNAL_REGIONAL = "3"


def _build_params_trf3_civel(consulta: dict, token: str, abrangencia: str) -> dict:
    """TRF3 Cível at one `abrangencia`: token + cpf/cnpj + tipo + abrangencia
    (+ nome_social for CPF).

    Deliberately NOT sent: `tipo_documento` is this endpoint's
    supplementary-ID type (1=não informado, 2=RG, 3=Passaporte), not CPF/CNPJ;
    `nome`/`razao_social` switch the search to by-name; `nome_social` is
    CPF-only per the docs.
    """
    params = _token_and_doc(consulta, token)
    params["tipo"] = TRF3_TIPO_CIVEL
    params["abrangencia"] = abrangencia
    if consulta["tipo_documento"] == "cpf" and consulta.get("nome"):
        params["nome_social"] = consulta["nome"]
    return params


def _build_params_trf3_sp(consulta: dict, token: str) -> dict:
    """TRF3 1ª instância: Cível, Seção Judiciária e JEF de São Paulo."""
    return _build_params_trf3_civel(consulta, token, TRF3_ABRANGENCIA_SAO_PAULO)


def _build_params_trf3(consulta: dict, token: str) -> dict:
    """TRF3 2ª instância: Cível, Tribunal Regional Federal da 3ª Região."""
    return _build_params_trf3_civel(consulta, token, TRF3_ABRANGENCIA_TRIBUNAL_REGIONAL)


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


# --------------- Structured-field parsers ---------------
#
# `parse_fn` mirrors `params_fn`'s shape: a name on the config row, dispatched
# through a dict, so every type declares WHICH reader applies to its
# response rather than the pipeline guessing. All ten API types share the
# same reader today ("padrao") because they are all the same family of
# InfoSimples "situação fiscal/judicial" lookups.


def _parse_date_br(value: Any) -> Optional[str]:
    """`"dd/mm/yyyy"` (InfoSimples' own date format) → ISO `"yyyy-mm-dd"`.

    `None` for anything else, INCLUDING an already-ISO string — no field
    observed in these responses has ever used one, so accepting it would
    silently mask a format InfoSimples actually changed rather than one this
    parser correctly declines to guess at.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.strptime(value.strip(), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def _parse_resultado_padrao(raw_response: dict) -> dict:
    """Best-effort structured read of an InfoSimples response's `data[0]`.

    Deliberately narrow: only `numero`/`emitida_em`/`validade_ate`, off the
    handful of field names InfoSimples uses across these ten endpoints
    (`numero_controle`/`codigo_controle`/`numero_certidao`/`numero`,
    `data_emissao`/`data_consulta`, `data_validade`/`validade`).

    It does NOT guess `resultado`. A `code=200` response can be a negativa OR
    a positiva PDF depending on what the DOCUMENT itself says — this module
    has no verified per-endpoint field mapping that tells them apart, and
    InfoSimples' own field names are not consistent enough across all ten to
    risk one. Guessing would write a confident-looking WRONG verdict onto a
    due-diligence screen, which is worse than leaving it undetermined for
    `service._analyze_estrutura_with_ai` (which at least reads the actual
    document text) or a human's `PATCH /resultados/{id}`. See
    `parse_resultado` for the one case (`nada_consta`) that IS unambiguous.
    """
    data = (raw_response or {}).get("data") or []
    if not data or not isinstance(data[0], dict):
        return {}
    item = data[0]
    out: dict = {}
    numero = (
        item.get("numero_controle") or item.get("codigo_controle")
        or item.get("numero_certidao") or item.get("numero")
    )
    if isinstance(numero, str) and numero.strip():
        out["numero"] = numero.strip()
    emitida = _parse_date_br(item.get("data_emissao") or item.get("data_consulta"))
    if emitida:
        out["emitida_em"] = emitida
    validade = _parse_date_br(item.get("data_validade") or item.get("validade"))
    if validade:
        out["validade_ate"] = validade
    return out


def _cenprot_protocolo_date(protocolo: Any) -> Optional[str]:
    """The CENPROT protocol number's own date prefix, `YYMMDD` (20YY).

    A CENPROT 200 ("protests found") `data[0]` carries no `data_emissao` /
    `data_consulta` field at all — verified against this module's own
    fixtures (`tests/modules/test_certidoes_service.py`, 2026-09-15) — only
    `protocolo_consulta`, whose first six digits ARE the date the consulta
    ran, per InfoSimples' own numbering for this endpoint. This is "the
    consulta/protocol date" the office named as an acceptable substitute for
    a printed emission date on a source that has no such date itself (see
    `_parse_resultado_cenprot`).

    `None` on anything that does not look like that shape — a malformed or
    unexpectedly-shaped protocol must fall through to "undetermined", never
    a guessed date."""
    if not isinstance(protocolo, str) or len(protocolo) < 6 or not protocolo[:6].isdigit():
        return None
    try:
        return datetime.strptime(protocolo[:6], "%y%m%d").date().isoformat()
    except ValueError:
        return None


def _parse_resultado_cenprot(raw_response: dict) -> dict:
    """`_parse_resultado_padrao`, plus CENPROT's own fallback for the one
    date field the generic reader cannot find on this endpoint: when no
    `emitida_em` came off `data_emissao`/`data_consulta` (there is neither
    on a CENPROT response), derive it from `protocolo_consulta`'s date
    prefix instead — see `_cenprot_protocolo_date`.

    A 612 ("nada consta") response has no `protocolo_consulta` either (see
    `_cenprot_protocolo_consulta`'s own docstring), so this naturally adds
    nothing for that case — `parse_resultado` never calls a `parse_fn` for
    a `nada_consta` result in the first place.
    """
    out = _parse_resultado_padrao(raw_response)
    if "emitida_em" not in out:
        data = (raw_response or {}).get("data") or []
        if data and isinstance(data[0], dict):
            derived = _cenprot_protocolo_date(data[0].get("protocolo_consulta"))
            if derived:
                out["emitida_em"] = derived
    return out


PARSE_BUILDERS = {
    "padrao": _parse_resultado_padrao,
    "cenprot": _parse_resultado_cenprot,
}


def parse_resultado(config: dict, fetch_result: dict) -> dict:
    """The structured-field patch derivable straight from `_fetch_certidao`'s
    own return shape, with NO AI call.

    `nada_consta` (InfoSimples code 612 — "no record at the source") is the
    one unambiguous signal this module has: for a negative-certificate
    lookup, no record found IS a negativa. Every other field is read off
    `raw_response` by the type's own `parse_fn`; `resultado` specifically is
    left for `service._analyze_estrutura_with_ai` or a human when the parser
    cannot say — see `_parse_resultado_padrao`'s docstring for why guessing
    it is worse than leaving it undetermined.
    """
    if fetch_result.get("nada_consta"):
        return {"resultado": "negativa"}
    parser = PARSE_BUILDERS.get(config.get("parse_fn", ""))
    if not parser:
        return {}
    return parser(fetch_result.get("raw_response") or {})


#: `tipo` → its config row. Built once; every lookup in the pipeline goes
#: through it rather than re-scanning the list per resultado.
CONFIG_BY_TIPO: dict[str, dict] = {c["tipo"]: c for c in CERTIDOES_CONFIG}


def get_certidoes_tipos() -> list[dict]:
    """Return the list of available certificate types for the frontend."""
    return [
        {"tipo": c["tipo"], "nome": c["nome"], "ordem": c["ordem"]}
        for c in CERTIDOES_CONFIG
    ]


def get_manual_tipos() -> list[dict]:
    """The manual-upload-only certidão types — Serasa, TJSP e-SAJ, TJSP
    e-PROC — as a catalogue SEPARATE from `get_certidoes_tipos()`.

    See `MANUAL_TIPOS_CONFIG`'s own comment for why these are not folded into
    the ten-item automated catalogue.
    """
    return [
        {"tipo": c["tipo"], "nome": c["nome"], "ordem": c["ordem"]}
        for c in MANUAL_TIPOS_CONFIG
    ]


#: The "Levantamento de Certidões" card tab's MATRIX row order — the FIXED
#: 13 (owner rule, 2026-09-24: "Rows 5.1-5.13 stay fixed"), the Excel
#: source's Nº 5.1-5.13, its own PT-BR labels (some abbreviated compared to
#: `CERTIDOES_CONFIG`'s/`MANUAL_TIPOS_CONFIG`'s emission-checklist `nome`,
#: on purpose: a due-diligence spreadsheet reader and an emission operator
#: read different registers of the same fact). This is a DISPLAY/ORDERING
#: concern separate from `ordem` (the emission checklist's own order,
#: `CERTIDOES_CONFIG`'s 1-10 / `MANUAL_TIPOS_CONFIG`'s 11-14) — the matriz's
#: row 5.7/5.8 (TJSP e-SAJ/e-PROC) sit right after 5.6, while their `ordem`
#: is 12/13; two registries reading the SAME `tipo` key in a different
#: sequence for a different screen, never re-deriving each other.
#:
#: Rows 5.14, 5.15, ... are CUSTOM per-card rows (migration 170,
#: `card_hub.certidoes_matriz_linhas_service`) — NOT in this fixed list;
#: `card_hub.certidoes_matriz_service.montar_matriz` appends them live.
MATRIZ_LINHAS = [
    {"tipo": "cnd_federal", "linha": "5.1", "rotulo": "Receita Federal"},
    {"tipo": "trf3_sp", "linha": "5.2", "rotulo": "Justiça Federal – 1ª instância"},
    {"tipo": "trf3", "linha": "5.3", "rotulo": "Justiça Federal – 2ª instância"},
    {"tipo": "trt2_digital", "linha": "5.4", "rotulo": "Ação trabalhista digital"},
    {"tipo": "trt2_fisico", "linha": "5.5", "rotulo": "Ação trabalhista física"},
    {"tipo": "cnd_trabalhista_tst", "linha": "5.6", "rotulo": "Débito trabalhista (CNDT)"},
    {"tipo": "tjsp_esaj", "linha": "5.7", "rotulo": "TJSP – e-SAJ"},
    {"tipo": "tjsp_eproc", "linha": "5.8", "rotulo": "TJSP – e-Proc"},
    {"tipo": "serasa", "linha": "5.9", "rotulo": "SERASA"},
    {"tipo": "cenprot", "linha": "5.10", "rotulo": "CENPROT"},
    {"tipo": "cnd_fazenda_sp", "linha": "5.11", "rotulo": "Débitos não inscritos"},
    {"tipo": "divida_ativa_sp", "linha": "5.12", "rotulo": "Dívida ativa"},
    {"tipo": "fgts_regularidade", "linha": "5.13", "rotulo": "Regularidade do FGTS (empresas)"},
]


def aplicavel_a_tipo_documento(tipo: str, tipo_documento: str) -> bool:
    """Does the manual type `tipo` fan out onto a `tipo_documento`
    ('cpf'/'cnpj') consulta? Automated `CERTIDOES_CONFIG` types have no
    per-type restriction (every one applies to both) — only `MANUAL_TIPOS_
    CONFIG` rows carry an `aplicavel_a`, defaulting to both when absent
    (`serasa`→cpf-only, `fgts_regularidade`→cnpj-only; see that config's own
    comment). Unknown `tipo` → True (never silently drop a resultado the
    caller already knows about over a registry miss)."""
    config = MANUAL_CONFIG_BY_TIPO.get(tipo)
    if config is None:
        return True
    return tipo_documento in config.get("aplicavel_a", ("cpf", "cnpj"))


def config_for(tipo: str) -> Optional[dict]:
    """The config row for `tipo`, or `None` when the registry has no such type.

    `None` is a real answer, not a swallowed error: a `certidao_resultados` row
    can outlive a type that was removed from the registry, and the callers
    treat that as "skip this one" rather than crashing the whole consulta.

    Only the ten AUTOMATED types — `manual_config_for` is the manual-type
    sibling, kept separate because a manual type has no `endpoint`/
    `params_fn` and every existing caller of THIS function (`processar_
    consulta`, the TJSP scheduler) means "is there an API call to make".
    """
    return CONFIG_BY_TIPO.get(tipo)


def manual_config_for(tipo: str) -> Optional[dict]:
    """The manual-type config row for `tipo`, or `None`."""
    return MANUAL_CONFIG_BY_TIPO.get(tipo)


__all__ = [
    "CERTIDOES_CONFIG",
    "CONFIG_BY_TIPO",
    "CUSTOM_ROW_TIPO",
    "INFOSIMPLES_BASE_URL",
    "MANUAL_CONFIG_BY_TIPO",
    "MANUAL_TIPOS_CONFIG",
    "MATRIZ_LINHAS",
    "PARAM_BUILDERS",
    "PARSE_BUILDERS",
    "RESULTADO_VALUES",
    "TJSP_COOLDOWN_SECONDS",
    "TJSP_TIPO",
    "aplicavel_a_tipo_documento",
    "config_for",
    "get_certidoes_tipos",
    "get_manual_tipos",
    "manual_config_for",
    "parse_resultado",
]
