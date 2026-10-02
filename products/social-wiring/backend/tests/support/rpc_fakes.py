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
