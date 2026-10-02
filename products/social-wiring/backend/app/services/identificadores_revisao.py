"""The human hand-in for identifiers that do not fit their type.

OWNER RULE (2026-10-01, `canonical-identifiers`): a stored document number that
does not fit its type is NEVER rewritten — it stays as read and shows up in
`vw_identificadores_nao_conformes` (migration 187). This module is the READ side
of the screen that puts those rows in front of an operator: what is stored,
WHY it does not fit (pt-BR), and where to correct it. The correction itself goes
through the EXISTING manual-edit endpoints (`PATCH /api/clientes/{id}`,
`PATCH /api/imoveis/{codigo}/dados`), which canonicalize/validate on write — no
second write path exists here.

Only org-scoped rows are read; the view is `security_invoker` and the service
client bypasses RLS, so the `org_id` filter below IS the tenant boundary.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from app.services import identificadores as idf
from app.services import table_reads

VIEW = "vw_identificadores_nao_conformes"

SITUACOES = ("nao_cabe", "canonizavel")

#: (tabela, campo) → how an operator names the field + the registry type. A
#: `None` type is resolved per row (certidao_consultas.tipo_documento).
CAMPOS: dict[tuple[str, str], tuple[str, Optional[str]]] = {
    ("clientes", "cpf"): ("CPF", "cpf"),
    ("clientes", "rg"): ("RG", "rg"),
    ("clientes", "endereco_cep"): ("CEP do endereço", "cep"),
    ("imovel_dados", "numero_matricula"): ("Nº da matrícula", "matricula_imovel"),
    ("certidao_consultas", "documento"): ("Documento da consulta de certidão", None),
}

#: registry `motivo` code → pt-BR reason. A code absent here is shown generically
#: (never blank, never a raw code).
MOTIVOS: dict[str, str] = {
    "dv_invalido": "O dígito verificador não confere — confira os números digitados.",
    "tamanho": "A quantidade de dígitos não corresponde a este tipo de documento.",
    "digitos_incompativeis": "Os dígitos não são compatíveis com este tipo de documento.",
    "caracteres_invalidos": "Contém caracteres que não pertencem a este tipo de documento.",
    "zero": "Número zerado.",
    "rg_formato_desconhecido": "Formato de RG não reconhecido.",
    "rg_uf_sem_mascara": "RG de outro estado, sem máscara conhecida — confira o órgão expedidor.",
    "municipio_sem_perfil": "Município sem perfil de inscrição conhecido.",
    "vazio": "Valor vazio.",
}
_MOTIVO_GENERICO = "O valor não corresponde ao formato esperado para este campo."
_MOTIVO_CANONIZAVEL = "O valor é válido, mas está em outra grafia — será padronizado na próxima gravação."

_TIPOS_PT = {"cpf": "CPF", "cnpj": "CNPJ", "rg": "RG", "cin": "CIN", "cep": "CEP",
             "matricula_imovel": "matrícula", "inscricao_municipal": "inscrição municipal"}


def motivo_pt(tipo: Optional[str], valor: Any, *, situacao: str, uf: Optional[str] = None) -> str:
    """Why `valor` does not fit `tipo`, in pt-BR, for an operator."""
    if situacao == "canonizavel":
        return _MOTIVO_CANONIZAVEL
    if not tipo:
        return _MOTIVO_GENERICO
    gravacao = idf.para_gravar(tipo, valor, uf=uf)
    if gravacao.tipo_detectado:
        outro = _TIPOS_PT.get(gravacao.tipo_detectado, gravacao.tipo_detectado)
        esperado = _TIPOS_PT.get(tipo, tipo)
        return f"Este valor é um {outro} válido, não um(a) {esperado} — está no campo errado?"
    return MOTIVOS.get(gravacao.motivo, _MOTIVO_GENERICO)


def _enriquecer(client: Any, org_id: UUID, linhas: list[dict]) -> list[dict]:
    ids = {
        tabela: sorted({r["linha_id"] for r in linhas if r["tabela"] == tabela})
        for tabela in ("clientes", "certidao_consultas")
    }
    clientes: dict[str, dict] = {}
    for lote in table_reads.batched(ids["clientes"]):
        for c in (
            table_reads.table(client, "clientes")
            .select("id, nome, nome_oficial, rg_orgao_expedidor")
            .eq("org_id", str(org_id))
            .in_("id", lote)
            .execute()
        ).data or []:
            clientes[str(c["id"])] = c
    consultas: dict[str, dict] = {}
    for lote in table_reads.batched(ids["certidao_consultas"]):
        for q in (
            table_reads.table(client, "certidao_consultas")
            .select("id, nome, tipo_documento, cliente_id, empresa_id")
            .eq("org_id", str(org_id))
            .in_("id", lote)
            .execute()
        ).data or []:
            consultas[str(q["id"])] = q
    return [_item(r, clientes, consultas) for r in linhas]


def _item(r: dict, clientes: dict[str, dict], consultas: dict[str, dict]) -> dict:
    tabela, campo, valor, situacao = r["tabela"], r["campo"], r["valor"], r["situacao"]
    rotulo, tipo = CAMPOS.get((tabela, campo), (campo, None))
    uf: Optional[str] = None
    entidade, link, edicao = "", None, None
    if tabela == "clientes":
        c = clientes.get(str(r["linha_id"])) or {}
        entidade = c.get("nome_oficial") or c.get("nome") or "Cliente"
        link = {"tipo": "cliente", "id": r["linha_id"]}
        edicao = {"tipo": "cliente", "id": r["linha_id"], "campo": campo}
        uf = idf.uf_do_orgao(c.get("rg_orgao_expedidor"))
    elif tabela == "imovel_dados":
        entidade = f"Imóvel {r['linha_id']}"
        link = {"tipo": "imovel", "id": r["linha_id"]}
        edicao = {"tipo": "imovel", "id": r["linha_id"], "campo": campo}
    elif tabela == "certidao_consultas":
        q = consultas.get(str(r["linha_id"])) or {}
        tipo = q.get("tipo_documento") or None
        entidade = q.get("nome") or "Consulta de certidão"
        # The consulta's documento is the key of an emission already made —
        # corrected at the PERSON it belongs to, not rewritten in place. A
        # consulta not linked to a cliente has no editable target.
        if q.get("cliente_id"):
            link = {"tipo": "cliente", "id": str(q["cliente_id"])}
    return {
        "chave": f"{tabela}:{r['linha_id']}:{campo}",
        "tabela": tabela,
        "linha_id": r["linha_id"],
        "campo": campo,
        "rotulo_campo": rotulo,
        "valor": valor,
        "canonico": r.get("canonico"),
        "situacao": situacao,
        "motivo": motivo_pt(tipo, valor, situacao=situacao, uf=uf),
        "entidade_nome": entidade,
        "link": link,
        "edicao": edicao,
    }


def listar_nao_conformes(
    client: Any, org_id: UUID, *, situacao: str = "nao_cabe", page: int = 1, page_size: int = 50
) -> dict:
    """One page of the org's non-conforming identifiers + the total.

    `situacao` defaults to `nao_cabe` (a human must fix those);
    `canonizavel` rows are fixed by the backfill / the next write and are only
    listed on request."""
    if situacao not in SITUACOES:
        raise ValueError(f"situacao must be one of {SITUACOES}, got {situacao!r}")
    inicio = (page - 1) * page_size
    resp = (
        table_reads.table(client, VIEW)
        .select("*", count="exact")
        .eq("org_id", str(org_id))
        .eq("situacao", situacao)
        .order("tabela")
        .order("linha_id")
        .order("campo")
        .range(inicio, inicio + page_size - 1)
        .execute()
    )
    linhas = resp.data or []
    total = resp.count if resp.count is not None else len(linhas)
    return {
        "items": _enriquecer(client, org_id, linhas),
        "total": total,
        "page": page,
        "page_size": page_size,
    }


__all__ = ["CAMPOS", "MOTIVOS", "VIEW", "listar_nao_conformes", "motivo_pt"]
