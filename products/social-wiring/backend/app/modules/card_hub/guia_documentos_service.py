"""`GET /api/guia-documentos` — ONE place the UI reads "which document gives
which data, what each certidão needs, and what each stage of the lead flow
asks for".

🔴 DERIVED, NEVER A HAND-KEPT COPY. Every list below is computed at request
time from the catalog that already owns the fact:

- documents and the fields read off each one — `proveniencia.fontes`
  (`FONTES_REGISTRO`, bounded by the seed's `capacidades.py`) plus the imóvel
  structured read (`imovel_hub.documentos_service.CAMPOS_ESTRUTURA_POR_TIPO`);
- field → documents — `contrato_gerador.derivacao._sugestoes_para_campo`, the
  SAME list the readiness "Envie …" suggestions show (same order);
- certidão requirements — `certidoes.registry.requisitos_catalogo()` (the
  declarations `pendencia_pre_chamada` enforces before every paid call);
- dados obrigatórios — `documento_checklist_service.ITENS`;
- the lead flow — `atendimento_blocos.blocos` (blocks + stage ownership) and
  `pipeline.stage_gate.EXIGENCIAS` (the only rule that gates a stage move).

What does NOT exist in code is said, never invented: no stage gates on a
document, so each stage's `observacao` says what applies there and why.

The only per-org inputs are presentation: the org's stage labels
(`pipeline_stages.label`) and its block configuration (which block owns which
stage) — passed in by the router so this module stays pure.

Contract: the `GuiaDocumentos` type (owner brief 2026-10-26).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping, Optional

from app.modules.atendimento_blocos import blocos as blocos_mod
from app.modules.card_hub import documento_checklist_service as checklist
from app.modules.card_hub.contrato_gerador import derivacao
from app.modules.card_hub.proveniencia import fontes as fontes_mod
from app.modules.certidoes import registry
from app.modules.imovel_hub.documentos_service import CAMPOS_ESTRUTURA_POR_TIPO
from app.modules.pipeline import stage_gate

# ─── field labels ──────────────────────────────────────────────────────────

#: Labels for canonical fields no other catalog names. Presentation only —
#: WHICH fields exist is always derived; a test fails when a catalog field
#: has no label here or upstream (`test_guia_documentos.py`).
_ROTULOS_EXTRA: dict[str, str] = {
    "banco_codigo": "Código do banco",
    "banco_nome": "Banco",
    "cnpj": "CNPJ",
    "conta_credito_vendedor": "Conta de crédito do vendedor",
    "data_abertura": "Data de abertura",
    "data_emissao": "Data de emissão do documento",
    "data_situacao_cadastral": "Data da situação cadastral",
    "email": "E-mail",
    "emitida_em": "Data de emissão",
    "inscricao_imobiliaria": "Inscrição imobiliária",
    "motivo_situacao": "Motivo da situação cadastral",
    "naturalidade": "Naturalidade",
    "natureza_juridica": "Natureza jurídica",
    "nome": "Nome",
    "nome_fantasia": "Nome fantasia",
    "numero": "Número da certidão",
    "numero_matricula": "Número da matrícula",
    "numero_proposta": "Número da proposta",
    "pacto_antenupcial_data": "Data do pacto antenupcial",
    "pacto_antenupcial_folha": "Folha do pacto antenupcial",
    "pacto_antenupcial_livro": "Livro do pacto antenupcial",
    "pacto_antenupcial_tabelionato": "Tabelionato do pacto antenupcial",
    "quadro_encontrado": "Quadro-resumo do contrato",
    "razao_social": "Razão social",
    "resultado": "Resultado (negativa/positiva)",
    "rg_orgao": "Órgão expedidor do RG",
    "situacao_cadastral": "Situação cadastral",
    "uf": "UF",
    "validade_ate": "Validade",
    "valor_compra_venda": "Valor de compra e venda",
    "valor_fgts": "Valor do FGTS",
    "valor_financiado": "Valor financiado",
    "valor_transacao": "Valor da transação (ITBI)",
}

#: The contract's qualificação, in canonical names (`nome_oficial -> nome`).
_QUALIFICACAO: dict[str, str] = {
    fontes_mod.RENOMEADOS_CAMPO.get(chave, chave): rotulo
    for chave, rotulo in derivacao.ROTULO_QUALIFICACAO.items()
}

_ROTULOS_CHECKLIST: dict[str, str] = {item["key"]: item["label"] for item in checklist.ITENS}


def rotulo_campo(campo: str) -> str:
    """pt-BR label of a canonical field: the explicit table first (so `nome`
    reads "Nome", not the qualificação's "Nome oficial"), then the contract's
    qualificação labels, the checklist's, the certidão registry's; the raw
    key only as a visible last resort (a test keeps it unreachable)."""
    if campo in _ROTULOS_EXTRA:
        return _ROTULOS_EXTRA[campo]
    if campo in _QUALIFICACAO:
        return _QUALIFICACAO[campo]
    if campo in _ROTULOS_CHECKLIST:
        return _ROTULOS_CHECKLIST[campo]
    if campo in registry.ROTULO_CAMPO:
        return registry.rotulo_campo(campo)
    return campo


def _campo(campo: str) -> dict[str, str]:
    return {"campo": campo, "rotulo": rotulo_campo(campo)}


# ─── documentos ────────────────────────────────────────────────────────────


def _campos_do_documento(fonte: fontes_mod.Fonte) -> list[str]:
    campos = set(fonte.campos) | set(fonte.campos_sem_capacidade)
    if fonte.estrutura_extraivel:
        campos |= set(CAMPOS_ESTRUTURA_POR_TIPO.get(fonte.tipo_documento, ()))
    return sorted(campos, key=lambda c: (rotulo_campo(c).lower(), c))


def _observacao_documento(fonte: fontes_mod.Fonte) -> Optional[str]:
    notas = []
    if fonte.leitura_integral:
        notas.append("Leitura de todas as páginas")
    if fonte.estrutura_extraivel:
        notas.append("Leitura estruturada (emissão, validade, resultado) — revise antes de usar")
    if fonte.campos_sem_capacidade:
        notas.append("Dados vindos da resposta da consulta, não de um arquivo enviado")
    if fonte.dominio == "empresa":
        notas.append("Dados de empresas vão para Empresas")
    if fonte.dominio == "atendimento":
        notas.append("Documento do negócio (aba Financiamento/Escritura), não da pessoa")
    return " · ".join(notas) or None


def _usos_documento(
    fonte: fontes_mod.Fonte, campos: Iterable[str], certidoes: list[dict], obrigatorios: list[dict]
) -> list[str]:
    """Where this document's fields are consumed — explicit, one rule per line:
    the contract's qualificação, a certidão requirement, a dados-obrigatórios
    item that names it, and its domain's contract section."""
    campos = set(campos)
    usos: list[str] = []
    if campos & set(_QUALIFICACAO):
        usos.append("Qualificação no contrato")
    for cert in certidoes:
        exigidos = {c["campo"] for r in cert["requisitos"] for c in r["campos"]}
        nome = cert["rotulo"] if cert["rotulo"].startswith("Certidão") else f"Certidão {cert['rotulo']}"
        for campo in sorted(exigidos & campos):
            usos.append(f"{nome} ({registry.ROTULO_CAMPO.get(campo, rotulo_campo(campo).lower())})")
    for item in obrigatorios:
        if fonte.tipo_documento in item["documentos"]:
            usos.append(f"Dados obrigatórios: {item['rotulo']}")
    if fonte.tipo_documento in derivacao.ORDEM_CERTIDOES_IMOVEL:
        usos.append("Certidões do imóvel no contrato")
    elif fonte.dominio == "imovel":
        usos.append("Dados do imóvel no contrato")
    if fonte.dominio == "empresa":
        usos.append("Qualificação da empresa no contrato")
    if fonte.dominio == "atendimento":
        usos.append("Negociação e financiamento no contrato")
    if fonte.dominio == "certidao":
        usos.append("Matriz de certidões")
    return list(dict.fromkeys(usos))


def _documentos(certidoes: list[dict], obrigatorios: list[dict]) -> list[dict]:
    saida = []
    for fonte in fontes_mod.FONTES_REGISTRO:
        campos = _campos_do_documento(fonte)
        saida.append({
            "tipo_documento": fonte.tipo_documento,
            "rotulo": fontes_mod.ROTULOS_TIPO_DOCUMENTO.get(fonte.tipo_documento, fonte.tipo_documento),
            "campos": [_campo(c) for c in campos],
            "observacao": _observacao_documento(fonte),
            "usos": _usos_documento(fonte, campos, certidoes, obrigatorios),
        })
    return saida


# ─── campos (reverse index) ────────────────────────────────────────────────


def documentos_do_campo(campo: str) -> list[str]:
    """The readiness suggestion list for `campo`, as tipo_documento keys."""
    return [s["tipo_documento"] for s in derivacao._sugestoes_para_campo(campo)]


def _campos() -> list[dict]:
    todos = sorted(
        {c for f in fontes_mod.FONTES_REGISTRO for c in f.campos},
        key=lambda c: (rotulo_campo(c).lower(), c),
    )
    return [{**_campo(c), "documentos": documentos_do_campo(c)} for c in todos]


# ─── dados obrigatórios ────────────────────────────────────────────────────


def _documentos_do_item(item: Mapping[str, Any]) -> list[str]:
    """The upload slots the item names, else its `documento`, else every
    document that supplies one of its fields (readiness order)."""
    if item.get("documentos"):
        return list(item["documentos"])
    if item.get("documento"):
        return [item["documento"]]
    campos = tuple(item.get("campos") or ()) + tuple(item.get("campos_todos") or ())
    return list(dict.fromkeys(d for c in campos for d in documentos_do_campo(c)))


def _dados_obrigatorios() -> list[dict]:
    return [
        {
            "chave": item["key"],
            "rotulo": item["label"],
            "documentos": _documentos_do_item(item),
            "escopo": item.get("escopo"),
            "dica": item.get("dica"),
        }
        for item in checklist.ITENS
    ]


# ─── certidões ─────────────────────────────────────────────────────────────


def _certidoes() -> list[dict]:
    saida = []
    for cert in registry.requisitos_catalogo():
        if cert["tipo"] == derivacao.TIPO_CRF_FGTS:
            # Migration 295: optional unless the deal opts in.
            cert = {**cert, "observacao": " · ".join(
                filter(None, [cert["observacao"], "Opcional por padrão (o negócio pode exigir)"])
            )}
        saida.append(cert)
    return saida


# ─── etapas (lead flow) ────────────────────────────────────────────────────

_OBS_GATE = (
    "Para o card do funil mudar de etapa o titular precisa de nome e celular "
    "(única regra que trava a movimentação)."
)
_OBS_SEM_GATE = "Nenhuma regra trava a movimentação nesta etapa."
_OBS_SEM_REGRA = "Nenhum documento é exigido nesta etapa."
_OBS_JURIDICO = (
    "A geração do contrato pede os dados obrigatórios e as certidões das partes "
    "(prontidão do contrato); isso não trava a mudança de etapa."
)
_OBS_SDR = "Antes do funil: a conversa é qualificada; nenhum documento é pedido."


def _exige_gate() -> list[dict]:
    return [{"rotulo": e["label"], "tipo": "campo", "ref": e["key"]} for e in stage_gate.EXIGENCIAS]


def _exige_juridico(obrigatorios: list[dict], certidoes: list[dict]) -> list[dict]:
    return (
        [{"rotulo": i["rotulo"], "tipo": "campo", "ref": i["chave"]} for i in obrigatorios]
        + [{"rotulo": c["rotulo"], "tipo": "certidao", "ref": c["tipo"]} for c in certidoes]
    )


def _rotulo_etapa(slug: str, rotulos: Mapping[str, str]) -> str:
    return rotulos.get(slug) or slug.replace("_", " ").capitalize()


def _etapas(
    obrigatorios: list[dict],
    certidoes: list[dict],
    rotulos_etapa: Mapping[str, str],
    config_blocos: Mapping[str, blocos_mod.ConfigBloco],
    etapas_org: Optional[Mapping[str, list[str]]],
) -> list[dict]:
    sdr = blocos_mod.BLOCO_POR_NOME[blocos_mod.BLOCO_SDR]
    saida = [{
        "chave": sdr.bloco, "rotulo": sdr.rotulo, "bloco": sdr.bloco, "exige": [],
        "observacao": _OBS_SDR,
    }]
    for pipeline in blocos_mod.PIPELINES_ATENDIMENTO:
        slugs = (etapas_org or {}).get(pipeline) or [
            s for b in blocos_mod.BLOCOS if b.pipeline == pipeline
            for s in config_blocos[b.bloco].etapas
        ]
        for slug in slugs:
            bloco = blocos_mod.dono(config_blocos, pipeline, slug)
            # `stage_gate` runs on FUNIL moves only (boards.mover_card,
            # funil_eventos); a processos_venda move is never gated.
            if pipeline == blocos_mod.PIPELINE_FUNIL:
                exige, notas = _exige_gate(), [_OBS_GATE]
            else:
                exige, notas = [], [_OBS_SEM_GATE]
            if bloco == "juridico":
                exige += _exige_juridico(obrigatorios, certidoes)
                notas.append(_OBS_JURIDICO)
            else:
                notas.append(_OBS_SEM_REGRA)
            saida.append({
                "chave": slug,
                "rotulo": _rotulo_etapa(slug, rotulos_etapa),
                "bloco": bloco,
                "exige": exige,
                "observacao": " ".join(notas),
            })
    return saida


# ─── assembly ──────────────────────────────────────────────────────────────


def montar_guia(
    *,
    rotulos_etapa: Optional[Mapping[str, str]] = None,
    config_blocos: Optional[Mapping[str, blocos_mod.ConfigBloco]] = None,
    etapas_org: Optional[Mapping[str, list[str]]] = None,
) -> dict:
    """The whole `GuiaDocumentos` payload. Without org inputs, the code
    defaults (`ETAPAS_PADRAO`, slug-derived stage labels)."""
    config = dict(config_blocos or {b.bloco: blocos_mod.config_padrao(b.bloco) for b in blocos_mod.BLOCOS})
    certidoes = _certidoes()
    obrigatorios = _dados_obrigatorios()
    corpo = {
        "documentos": _documentos(certidoes, obrigatorios),
        "campos": _campos(),
        "certidoes": certidoes,
        "etapas": _etapas(obrigatorios, certidoes, rotulos_etapa or {}, config, etapas_org),
        "dados_obrigatorios": obrigatorios,
    }
    versao = hashlib.sha256(
        json.dumps(corpo, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]
    return {"versao": versao, **corpo}


def etapas_da_org(linhas: Iterable[Mapping[str, Any]]) -> tuple[dict[str, str], dict[str, list[str]]]:
    """`(slug -> label, pipeline -> [slug in board order])` off the rows of
    `atendimento_blocos.repository.etapas_da_org` (already board-ordered)."""
    rotulos: dict[str, str] = {}
    por_pipeline: dict[str, list[str]] = {}
    for r in linhas:
        if r.get("slug") and r.get("pipeline"):
            rotulos.setdefault(r["slug"], r.get("label") or "")
            por_pipeline.setdefault(r["pipeline"], []).append(r["slug"])
    return rotulos, por_pipeline


__all__ = ["documentos_do_campo", "etapas_da_org", "montar_guia", "rotulo_campo"]
