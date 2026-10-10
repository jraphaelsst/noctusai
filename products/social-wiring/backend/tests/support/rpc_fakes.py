"""Fakes of product SQL functions, for `MockSupabaseClient.rpc` (which only
replays `set_rpc_data` and cannot execute SQL).

Each fake reimplements the function's CONTRACT over the mock's own table data;
the real SQL is pinned structurally by its migration test.
"""
from __future__ import annotations

from typing import Any

from noctusai_lib.primitives import identificador
from noctusai_lib.testing import MockSelectBuilder


def _norm(valor: Any) -> str | None:
    """Python twin of `social_wiring.chave_busca_documento('cpf', ...)` (187,
    over the seed's `identificador_chave_busca`) — the key `clientes_por_cpf`
    matches on; it superseded 097's `normalizar_documento()` (a CPF's key is
    the same eleven digits either way)."""
    return identificador.chave_busca("cpf", valor)


def clientes_por_cpf(client: Any, params: dict) -> MockSelectBuilder:
    """Migration 185 `social_wiring.clientes_por_cpf(p_org_id, p_cpfs)`, as
    re-keyed by 187."""
    chaves = {k for k in map(_norm, params.get("p_cpfs") or []) if k}
    rows = client.table("clientes").select("*").execute().data or []
    achados = [
        r
        for r in rows
        if str(r.get("org_id")) == str(params["p_org_id"])
        and r.get("cpf")
        and _norm(r["cpf"]) in chaves
    ]
    achados.sort(key=lambda r: (str(r.get("created_at") or ""), str(r.get("id"))))
    return MockSelectBuilder(achados)


def reordenar_negociacao_parcelas(client: Any, params: dict) -> MockSelectBuilder:
    """Migration 195 `social_wiring.reordenar_negociacao_parcelas(p_org_id,
    p_atendimento_id, p_parcela_ids, p_usuario_id)`: refuses unless the ids are
    exactly the atendimento's current parcela set, then sets `ordem` to each
    id's 0-based position. Returns the count of rows whose `ordem` changed."""
    tabela = "atendimento_negociacao_parcelas"
    org, aid = str(params["p_org_id"]), str(params["p_atendimento_id"])
    ids = [str(i) for i in params.get("p_parcela_ids") or []]
    atuais = [
        r
        for r in client.table(tabela).select("*").execute().data or []
        if str(r.get("org_id")) == org and str(r.get("atendimento_id")) == aid
    ]
    if len(set(ids)) != len(ids) or set(ids) != {str(r["id"]) for r in atuais}:
        raise ValueError("22023: a nova ordem deve listar exatamente as parcelas atuais")
    alterados = 0
    for pos, pid in enumerate(ids):
        atual = next(r for r in atuais if str(r["id"]) == pid)
        if atual.get("ordem") != pos:
            client.table(tabela).update(
                {"ordem": pos, "updated_por": params.get("p_usuario_id")}
            ).eq("id", pid).execute()
            alterados += 1
    return MockSelectBuilder([alterados])


def cs_brain_append(client: Any, params: dict) -> MockSelectBuilder:
    """Migration 224 `social_wiring.cs_brain_append(p_brain, p_org, p_block)`:
    one statement appends the block (separated by a rule when the brain already
    has content), bumps `content_version` and returns the new version; over
    200 000 chars the table CHECK raises `check_violation` (nothing truncated);
    an unknown brain / org raises `no_data_found`."""
    brain, org, block = str(params["p_brain"]), str(params["p_org"]), params["p_block"]
    rows = [
        r
        for r in client.table("cs_brains").select("*").execute().data or []
        if str(r.get("id")) == brain and str(r.get("org_id")) == org
    ]
    if not rows:
        raise ValueError("P0002: cs_brain_append: brain not found")
    atual = rows[0]
    content = atual.get("content") or ""
    novo = block if not content.strip() else content + "\n\n---\n\n" + block
    if len(novo) > 200_000:
        raise ValueError('23514: new row violates check constraint "cs_brains_content_check"')
    versao = (atual.get("content_version") or 0) + 1
    client.table("cs_brains").update({"content": novo, "content_version": versao}).eq("id", brain).execute()
    return MockSelectBuilder([versao])
