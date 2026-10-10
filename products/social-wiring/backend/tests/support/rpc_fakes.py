"""Fakes of product SQL functions, for `MockSupabaseClient.rpc` (which only
replays `set_rpc_data` and cannot execute SQL).

Each fake reimplements the function's CONTRACT over the mock's own table data;
the real SQL is pinned structurally by its migration test.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


def reservar_transcricao(client: Any, params: dict) -> MockSelectBuilder:
    """Migration 225 `social_wiring.reservar_transcricao(...)`: the atomic quota gate
    + insert. Same limits, order and codes as the SQL (transcription-contract.md
    section 3): per user 2 in flight, 10/h, 1800 s rolling 24 h; per org 7200 s;
    global queue depth 20 (503), global 36000 s (503). Refunded rows
    (`minutos_reembolsados`) never count toward the windows."""
    tabela = "transcricoes"
    agora = datetime.now(timezone.utc)
    rows = client.table(tabela).select("*").execute().data or []

    def quando(r: dict) -> datetime:
        return datetime.fromisoformat(str(r["criado_em"]))

    def nega(codigo: str, http: int, retry: int) -> MockSelectBuilder:
        return MockSelectBuilder([{"ok": False, "codigo": codigo, "http": http, "retry_after_s": retry}])

    def alivio(janela: list[dict], horas: int) -> int:
        mais_antigo = min(quando(r) for r in janela)
        return max(60, int((mais_antigo + timedelta(hours=horas) - agora).total_seconds()) + 1)

    user, org = str(params["p_user"]), str(params["p_org"])
    dur = float(params["p_duracao_s"])
    nao_reembolsadas = [r for r in rows if not r.get("minutos_reembolsados")]
    meus = [r for r in rows if str(r["user_id"]) == user]

    if sum(1 for r in meus if r["status"] in ("na_fila", "processando")) >= 2:
        return nega("limite_usuario", 429, 60)
    hora = [r for r in meus if not r.get("minutos_reembolsados") and quando(r) > agora - timedelta(hours=1)]
    if len(hora) >= 10:
        return nega("limite_usuario", 429, alivio(hora, 1))
    dia_user = [r for r in meus if not r.get("minutos_reembolsados") and quando(r) > agora - timedelta(hours=24)]
    if sum(float(r["duracao_s"]) for r in dia_user) + dur > 1800:
        return nega("cota_diaria_usuario", 429, alivio(dia_user, 24))
    dia_org = [r for r in nao_reembolsadas if str(r["org_id"]) == org and quando(r) > agora - timedelta(hours=24)]
    if sum(float(r["duracao_s"]) for r in dia_org) + dur > 7200:
        return nega("cota_diaria_org", 429, alivio(dia_org, 24))
    if sum(1 for r in rows if r["status"] in ("na_fila", "processando")) >= 20:
        return nega("fila_cheia", 503, 120)
    dia_global = [r for r in nao_reembolsadas if quando(r) > agora - timedelta(hours=24)]
    if sum(float(r["duracao_s"]) for r in dia_global) + dur > 36000:
        return nega("capacidade_diaria", 503, alivio(dia_global, 24))

    row = {
        "id": params["p_id"], "org_id": org, "user_id": user,
        "contexto_tipo": params["p_contexto_tipo"], "contexto_ref": params["p_contexto_ref"],
        "storage_path": params["p_storage_path"], "bytes": params["p_bytes"], "duracao_s": dur,
        "formato": params["p_formato"], "status": "na_fila", "texto": None, "erro_codigo": None,
        "modelo": None, "rtf": None, "criado_em": agora.isoformat(), "iniciado_em": None,
        "concluido_em": None, "audio_apagado_em": None, "minutos_reembolsados": False,
        "hook_aplicado_em": None,
    }
    client.table(tabela).insert(row).execute()
    return MockSelectBuilder([{"ok": True, "row": row}])
