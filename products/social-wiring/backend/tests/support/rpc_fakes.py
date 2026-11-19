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
    """`social_wiring.reservar_transcricao(...)` (migrations 225/229, daily caps removed by 343):
    the atomic load gate + insert. Same limits, order and codes as the SQL (transcription-contract.md
    section 3): per user 2 in flight and 120/h; global queue depth 20 (503). No daily usage quota
    (owner 2026-11-14). Refunded rows never count toward the hourly window."""
    tabela = "transcricoes"
    agora = datetime.now(timezone.utc)
    # migration 229: every voice counter sees only origem = 'usuario' (library rows never 429 a voice answer)
    rows = [r for r in (client.table(tabela).select("*").execute().data or []) if (r.get("origem") or "usuario") == "usuario"]

    def quando(r: dict) -> datetime:
        return datetime.fromisoformat(str(r["criado_em"]))

    def nega(codigo: str, http: int, retry: int) -> MockSelectBuilder:
        return MockSelectBuilder([{"ok": False, "codigo": codigo, "http": http, "retry_after_s": retry}])

    def alivio(janela: list[dict], horas: int) -> int:
        mais_antigo = min(quando(r) for r in janela)
        return max(60, int((mais_antigo + timedelta(hours=horas) - agora).total_seconds()) + 1)

    user, org = str(params["p_user"]), str(params["p_org"])
    dur = float(params["p_duracao_s"])
    meus = [r for r in rows if str(r["user_id"]) == user]

    if sum(1 for r in meus if r["status"] in ("na_fila", "processando")) >= 2:
        return nega("limite_usuario", 429, 60)
    hora = [r for r in meus if not r.get("minutos_reembolsados") and quando(r) > agora - timedelta(hours=1)]
    if len(hora) >= 120:
        return nega("limite_usuario", 429, alivio(hora, 1))
    if sum(1 for r in rows if r["status"] in ("na_fila", "processando")) >= 20:
        return nega("fila_cheia", 503, 120)

    row = {
        "id": params["p_id"], "org_id": org, "user_id": user,
        "contexto_tipo": params["p_contexto_tipo"], "contexto_ref": params["p_contexto_ref"],
        "storage_path": params["p_storage_path"], "bytes": params["p_bytes"], "duracao_s": dur,
        "formato": params["p_formato"], "status": "na_fila", "texto": None, "erro_codigo": None,
        "modelo": None, "rtf": None, "criado_em": agora.isoformat(), "iniciado_em": None,
        "concluido_em": None, "audio_apagado_em": None, "minutos_reembolsados": False,
        "hook_aplicado_em": None, "origem": "usuario",
    }
    client.table(tabela).insert(row).execute()
    return MockSelectBuilder([{"ok": True, "row": row}])


def reservar_transcricao_biblioteca(client: Any, params: dict) -> MockSelectBuilder:
    """Migration 229 `social_wiring.reservar_transcricao_biblioteca(...)`: the library lane's
    own gate + insert (geracao-contract 3.4). Counters see only origem = 'biblioteca': <= 180 s
    per reel (422), <= 5 queued/processing (503). No daily budget (migration 343, owner 2026-11-14)."""
    tabela = "transcricoes"
    agora = datetime.now(timezone.utc)
    rows = [r for r in (client.table(tabela).select("*").execute().data or []) if r.get("origem") == "biblioteca"]
    org, dur = str(params["p_org"]), float(params["p_duracao_s"])

    def nega(codigo: str, http: int, retry: int) -> MockSelectBuilder:
        return MockSelectBuilder([{"ok": False, "codigo": codigo, "http": http, "retry_after_s": retry}])

    if dur > 180:
        return nega("reel_longo", 422, 0)
    if sum(1 for r in rows if r["status"] in ("na_fila", "processando")) >= 5:
        return nega("fila_biblioteca_cheia", 503, 120)

    row = {
        "id": params["p_id"], "org_id": org, "user_id": str(params["p_user"]),
        "contexto_tipo": "biblioteca_viral", "contexto_ref": params["p_contexto_ref"],
        "storage_path": params["p_storage_path"], "bytes": params["p_bytes"], "duracao_s": dur,
        "formato": params["p_formato"], "status": "na_fila", "texto": None, "erro_codigo": None,
        "modelo": None, "rtf": None, "criado_em": agora.isoformat(), "iniciado_em": None,
        "concluido_em": None, "audio_apagado_em": None, "minutos_reembolsados": False,
        "hook_aplicado_em": None, "origem": "biblioteca",
    }
    client.table(tabela).insert(row).execute()
    return MockSelectBuilder([{"ok": True, "row": row}])



_LIMITE_CHAVES = frozenset({
    "headline_lotes_dia_usuario", "headlines_sugeridas_por_dia_marca", "roteiros_dia_usuario",
    "legendas_dia_usuario", "chat_mensagens_dia_usuario", "chat_mensagens_dia_org",
})


def cs_limite_geracao_definir(client: Any, params: dict) -> MockSelectBuilder:
    """Migration 361 `social_wiring.cs_limite_geracao_definir(p_org, p_chave, p_valor, p_ator)`: upserts (or, with
    `p_valor` NULL, deletes) the org's `public.org_settings` row and, when the value changed, appends ONE
    `cs_limite_geracao_eventos` row; returns `{anterior, novo, mudou}`. Unknown key / value < 1 raise `22023`."""
    org, chave, valor, ator = str(params["p_org"]), params["p_chave"], params.get("p_valor"), params.get("p_ator")
    if chave not in _LIMITE_CHAVES or (valor is not None and valor < 1):
        raise ValueError("22023: cs_limite_geracao_definir: invalid argument")
    linhas = [
        r for r in client.table("org_settings").select("*").execute().data or []
        if str(r.get("org_id")) == org and r.get("key") == chave
    ]
    texto = str(linhas[0].get("value") or "") if linhas else ""
    anterior = int(texto) if texto.isdigit() and 1 <= int(texto) <= 999_999_999 else None
    if valor is None:
        client.table("org_settings").delete().eq("org_id", org).eq("key", chave).execute()
    elif linhas:
        client.table("org_settings").update({"value": str(valor)}).eq("org_id", org).eq("key", chave).execute()
    else:
        client.table("org_settings").insert(
            {"org_id": org, "key": chave, "value": str(valor), "is_secret": False}
        ).execute()
    mudou = anterior != valor
    if mudou:
        client.table("cs_limite_geracao_eventos").insert({
            "org_id": org, "chave": chave, "evento": "limite_restaurado" if valor is None else "limite_definido",
            "valor_anterior": anterior, "valor_novo": valor, "ator_id": ator,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    return MockSelectBuilder([{"anterior": anterior, "novo": valor, "mudou": mudou}])
