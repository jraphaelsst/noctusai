"""Lais wave 11 -- Equipes / Distribuicao (contract section 13, owner decision 2026-10-15 #5).

Distribution data and rules live in SW; Julia only consumes them.

  * teams CRUD + members (add / remove / order / active) -- `lais_equipes`, `lais_equipe_membros`;
  * `atribuir_responsavel(...)` -- picks the attendant BEFORE anyone is notified and sets
    `lais_contatos.responsavel_user_id`:
        1. keep-last-responsible: a team with `manter_ultimo` on whose ACTIVE member is the contato's current
           responsavel keeps it (a returning lead goes back to the same attendant);
        2. else round-robin by the cursor (`lais_distribuicao_cursor`) among the ACTIVE members of the teams with
           `atende_apos_julia = true AND modo = 'julia'` (several teams: the one whose cursor moved least recently);
    teams with `atende_apos_julia = false` (manual assignment only) or `modo = 'funil'` (the SW lead/card flow
    decides) never auto-assign;
  * the `estado.atendente_nome` provider -- Julia can say who continues;
  * `metricas(...)` -- per member: ultimo acesso (core `noctus_users.last_active_at`; null when never recorded),
    TPR (first outbound message of the chat after the assignment, minus the assignment time -- Julia is paused after
    a handoff, so that outbound is the human's), conversas (contatos the member currently owns), distribuicao
    (assignments in the month, with the share of the team's).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.primitives.exceptions import AppException

from app.services import lais_contatos_service, lais_contexto_service

logger = logging.getLogger(__name__)

T_EQUIPES = "lais_equipes"
T_MEMBROS = "lais_equipe_membros"
T_CURSOR = "lais_distribuicao_cursor"
T_ATRIBUICOES = "lais_atribuicoes"
T_CONTATOS = "lais_contatos"
T_MENSAGENS = "conversation_messages"

MODOS = ("funil", "julia")
MOTIVOS = ("handoff", "qualificacao", "envio")
_EPOCH = "0000-00-00"
_METRICAS_MAX_ATRIBUICOES = 500


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _todas(fetch_page, label: str, id_key: str = "id") -> list[dict[str, Any]]:
    return list(iter_paged_rows(fetch_page, id_key=id_key, label=label))


# ── validation ──────────────────────────────────────────────────────────────
def _nome_valido(nome: Optional[str]) -> Optional[str]:
    if nome is None:
        return None
    nome = nome.strip()
    if not 1 <= len(nome) <= 60:
        raise AppException("equipe_invalida", "O nome da equipe deve ter de 1 a 60 caracteres.", status_code=422)
    return nome


def _modo_valido(modo: Optional[str]) -> Optional[str]:
    if modo is not None and modo not in MODOS:
        raise AppException("equipe_invalida", "Use modo=funil ou modo=julia.", status_code=422)
    return modo


def _usuarios_da_org(core: Any, org_id: UUID | str, ids: list[str]) -> dict[str, dict[str, Any]]:
    """`{user_id: noctus_users row}` of the ids that belong to THIS org (trusted DB, never user_metadata)."""
    ids = sorted({str(i) for i in ids if i})
    if not ids:
        return {}
    rows = core.table("noctus_users").select("id, org_id, nome, last_active_at").in_("id", ids).execute().data or []
    return {str(r["id"]): r for r in rows if str(r.get("org_id")) == str(org_id)}


# ── teams ───────────────────────────────────────────────────────────────────
def _membros_da_equipe(client: Any, org_id: UUID | str, equipe_id: UUID | str) -> list[dict[str, Any]]:
    rows = _todas(
        lambda a, b: client.table(T_MEMBROS).select("*").eq("org_id", str(org_id)).eq("equipe_id", str(equipe_id))
        .order("user_id").range(a, b).execute().data, "lais_equipe_membros", id_key="user_id")
    return sorted(rows, key=lambda m: (int(m.get("ordem") or 0), str(m.get("created_at") or ""), str(m["user_id"])))


def _saida(equipe: dict[str, Any], membros: list[dict[str, Any]], nomes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": str(equipe["id"]), "nome": equipe["nome"],
        "atende_apos_julia": bool(equipe.get("atende_apos_julia")),
        "modo": equipe.get("modo") or "funil",
        "manter_ultimo": bool(equipe.get("manter_ultimo")),
        "membros": [
            {"user_id": str(m["user_id"]), "nome": (nomes.get(str(m["user_id"])) or {}).get("nome"),
             "ativo": bool(m.get("ativo")), "ordem": int(m.get("ordem") or 0)}
            for m in membros
        ],
    }


def listar(client: Any, core: Any, org_id: UUID | str) -> list[dict[str, Any]]:
    equipes = sorted(
        _todas(lambda a, b: client.table(T_EQUIPES).select("*").eq("org_id", str(org_id)).order("id").range(a, b).execute().data,
               "lais_equipes"),
        key=lambda e: (str(e.get("nome") or "").lower(), str(e["id"])))
    membros = {str(e["id"]): _membros_da_equipe(client, org_id, e["id"]) for e in equipes}
    nomes = _usuarios_da_org(core, org_id, [str(m["user_id"]) for ms in membros.values() for m in ms])
    return [_saida(e, membros[str(e["id"])], nomes) for e in equipes]


def _equipe(client: Any, org_id: UUID | str, equipe_id: UUID | str) -> dict[str, Any]:
    rows = (client.table(T_EQUIPES).select("*").eq("org_id", str(org_id)).eq("id", str(equipe_id)).limit(1).execute().data or [])
    if not rows:
        raise AppException("equipe_nao_encontrada", "Equipe não encontrada.", status_code=404)
    return rows[0]


def obter(client: Any, core: Any, org_id: UUID | str, equipe_id: UUID | str) -> dict[str, Any]:
    e = _equipe(client, org_id, equipe_id)
    ms = _membros_da_equipe(client, org_id, e["id"])
    return _saida(e, ms, _usuarios_da_org(core, org_id, [str(m["user_id"]) for m in ms]))


def _nome_em_uso(client: Any, org_id: UUID | str, nome: str, *, exceto: Optional[str] = None) -> bool:
    alvo = nome.strip().lower()
    rows = client.table(T_EQUIPES).select("id, nome").eq("org_id", str(org_id)).limit(1000).execute().data or []
    return any(str(r.get("nome") or "").strip().lower() == alvo and str(r["id"]) != str(exceto or "") for r in rows)


def criar(client: Any, core: Any, org_id: UUID | str, *, nome: str, atende_apos_julia: bool = True, modo: str = "funil",
          manter_ultimo: bool = True) -> dict[str, Any]:
    nome = _nome_valido(nome) or ""
    _modo_valido(modo)
    if _nome_em_uso(client, org_id, nome):
        raise AppException("equipe_duplicada", "Já existe uma equipe com esse nome.", status_code=409)
    equipe_id = str(uuid4())
    client.table(T_EQUIPES).insert({
        "id": equipe_id, "org_id": str(org_id), "nome": nome, "atende_apos_julia": bool(atende_apos_julia),
        "modo": modo, "manter_ultimo": bool(manter_ultimo)}).execute()
    return obter(client, core, org_id, equipe_id)


def atualizar(client: Any, core: Any, org_id: UUID | str, equipe_id: UUID | str, campos: dict[str, Any]) -> dict[str, Any]:
    _equipe(client, org_id, equipe_id)
    patch: dict[str, Any] = {}
    if campos.get("nome") is not None:
        patch["nome"] = _nome_valido(campos["nome"])
        if _nome_em_uso(client, org_id, patch["nome"], exceto=str(equipe_id)):
            raise AppException("equipe_duplicada", "Já existe uma equipe com esse nome.", status_code=409)
    if campos.get("modo") is not None:
        patch["modo"] = _modo_valido(campos["modo"])
    for k in ("atende_apos_julia", "manter_ultimo"):
        if campos.get(k) is not None:
            patch[k] = bool(campos[k])
    if patch:
        client.table(T_EQUIPES).update({**patch, "updated_at": _agora().isoformat()}).eq("org_id", str(org_id)).eq("id", str(equipe_id)).execute()
    return obter(client, core, org_id, equipe_id)


def excluir(client: Any, org_id: UUID | str, equipe_id: UUID | str) -> None:
    _equipe(client, org_id, equipe_id)
    client.table(T_EQUIPES).delete().eq("org_id", str(org_id)).eq("id", str(equipe_id)).execute()


# ── members ─────────────────────────────────────────────────────────────────
def adicionar_membro(client: Any, core: Any, org_id: UUID | str, equipe_id: UUID | str, user_id: UUID | str, *,
                     ativo: bool = True) -> dict[str, Any]:
    _equipe(client, org_id, equipe_id)
    if not _usuarios_da_org(core, org_id, [str(user_id)]):
        raise AppException("membro_invalido", "O membro precisa ser um usuário da organização.", status_code=422)
    atuais = _membros_da_equipe(client, org_id, equipe_id)
    if any(str(m["user_id"]) == str(user_id) for m in atuais):
        raise AppException("membro_duplicado", "Esse usuário já está na equipe.", status_code=409)
    ordem = max((int(m.get("ordem") or 0) for m in atuais), default=-1) + 1
    client.table(T_MEMBROS).insert({
        "equipe_id": str(equipe_id), "org_id": str(org_id), "user_id": str(user_id), "ativo": bool(ativo), "ordem": ordem}).execute()
    return obter(client, core, org_id, equipe_id)


def atualizar_membro(client: Any, core: Any, org_id: UUID | str, equipe_id: UUID | str, user_id: UUID | str, *,
                     ativo: bool) -> dict[str, Any]:
    _equipe(client, org_id, equipe_id)
    _membro(client, org_id, equipe_id, user_id)
    client.table(T_MEMBROS).update({"ativo": bool(ativo)}).eq("org_id", str(org_id)).eq("equipe_id", str(equipe_id)).eq("user_id", str(user_id)).execute()
    return obter(client, core, org_id, equipe_id)


def _membro(client: Any, org_id: UUID | str, equipe_id: UUID | str, user_id: UUID | str) -> dict[str, Any]:
    for m in _membros_da_equipe(client, org_id, equipe_id):
        if str(m["user_id"]) == str(user_id):
            return m
    raise AppException("membro_nao_encontrado", "Esse usuário não está na equipe.", status_code=404)


def remover_membro(client: Any, org_id: UUID | str, equipe_id: UUID | str, user_id: UUID | str) -> None:
    _equipe(client, org_id, equipe_id)
    _membro(client, org_id, equipe_id, user_id)
    client.table(T_MEMBROS).delete().eq("org_id", str(org_id)).eq("equipe_id", str(equipe_id)).eq("user_id", str(user_id)).execute()


def ordenar_membros(client: Any, core: Any, org_id: UUID | str, equipe_id: UUID | str, ordem: list[str]) -> dict[str, Any]:
    """`ordem` = the member user ids in the wanted order; it must be exactly the team's current members."""
    _equipe(client, org_id, equipe_id)
    atuais = {str(m["user_id"]) for m in _membros_da_equipe(client, org_id, equipe_id)}
    pedidos = [str(u) for u in ordem]
    if len(set(pedidos)) != len(pedidos) or set(pedidos) != atuais:
        raise AppException("ordem_invalida", "A ordem deve listar exatamente os membros da equipe, sem repetir.", status_code=422)
    for i, uid in enumerate(pedidos):
        client.table(T_MEMBROS).update({"ordem": i}).eq("org_id", str(org_id)).eq("equipe_id", str(equipe_id)).eq("user_id", uid).execute()
    return obter(client, core, org_id, equipe_id)


def membros_das_equipes(client: Any, org_id: UUID | str, equipe_ids: list[str]) -> set[str]:
    """Union of the user ids of the given teams of THIS org (a foreign / unknown team contributes nothing)."""
    out: set[str] = set()
    for eid in equipe_ids:
        rows = client.table(T_EQUIPES).select("id").eq("org_id", str(org_id)).eq("id", str(eid)).limit(1).execute().data or []
        if rows:
            out |= {str(m["user_id"]) for m in _membros_da_equipe(client, org_id, eid)}
    return out


# ── distribution ────────────────────────────────────────────────────────────
def _equipes_automaticas(client: Any, org_id: UUID | str) -> list[dict[str, Any]]:
    rows = _todas(
        lambda a, b: client.table(T_EQUIPES).select("*").eq("org_id", str(org_id)).order("id").range(a, b).execute().data,
        "lais_equipes")
    return sorted((e for e in rows if e.get("atende_apos_julia") and e.get("modo") == "julia"),
                  key=lambda e: (str(e.get("created_at") or ""), str(e["id"])))


def _cursor(client: Any, equipe_id: UUID | str) -> Optional[dict[str, Any]]:
    rows = client.table(T_CURSOR).select("*").eq("equipe_id", str(equipe_id)).limit(1).execute().data or []
    return rows[0] if rows else None


def _gravar_cursor(client: Any, org_id: UUID | str, equipe_id: UUID | str, user_id: str) -> None:
    agora = _agora().isoformat()
    if _cursor(client, equipe_id):
        client.table(T_CURSOR).update({"ultimo_user_id": user_id, "updated_at": agora}).eq("equipe_id", str(equipe_id)).execute()
    else:
        client.table(T_CURSOR).insert({"equipe_id": str(equipe_id), "org_id": str(org_id), "ultimo_user_id": user_id,
                                       "updated_at": agora}).execute()


def _ativos(client: Any, core: Any, org_id: UUID | str, equipe_id: UUID | str) -> list[str]:
    """Active members, in order, that are STILL users of the org (a user who left the org is skipped)."""
    ms = [str(m["user_id"]) for m in _membros_da_equipe(client, org_id, equipe_id) if m.get("ativo")]
    vivos = _usuarios_da_org(core, org_id, ms)
    return [u for u in ms if u in vivos]


def _proximo(ativos: list[str], ultimo: Optional[str]) -> str:
    if ultimo in ativos:
        return ativos[(ativos.index(ultimo) + 1) % len(ativos)]
    return ativos[0]


def atribuir_responsavel(
    client: Any, core: Any, org_id: UUID | str, contato: dict[str, Any], motivo: str = "handoff",
    *, agora: Optional[datetime] = None,
) -> Optional[dict[str, Any]]:
    """Pick the attendant for `contato` and persist `lais_contatos.responsavel_user_id` (+ the log row).

    Returns `{user_id, nome, equipe_id, criterio}` or None when no team distributes (no auto team, no active
    member). Call it BEFORE notifying so the notification reaches the chosen attendant."""
    if motivo not in MOTIVOS:
        raise AppException("motivo_invalido", f"motivo deve ser um de {', '.join(MOTIVOS)}.", status_code=422)
    agora = agora or _agora()
    equipes = _equipes_automaticas(client, org_id)
    if not equipes:
        return None
    ativos = {str(e["id"]): _ativos(client, core, org_id, e["id"]) for e in equipes}
    atual = str(contato["responsavel_user_id"]) if contato.get("responsavel_user_id") else None

    escolha: Optional[tuple[str, str, str]] = None  # (user_id, equipe_id, criterio)
    if atual:
        for e in equipes:
            if e.get("manter_ultimo") and atual in ativos[str(e["id"])]:
                escolha = (atual, str(e["id"]), "ultimo_responsavel")
                break
    if escolha is None:
        candidatas = [e for e in equipes if ativos[str(e["id"])]]
        if not candidatas:
            return None
        # fairness across teams: the team whose cursor moved least recently goes next
        cursores = {str(e["id"]): _cursor(client, e["id"]) for e in candidatas}
        equipe = min(candidatas, key=lambda e: (str((cursores[str(e["id"])] or {}).get("updated_at") or _EPOCH), str(e.get("created_at") or ""), str(e["id"])))
        eid = str(equipe["id"])
        user_id = _proximo(ativos[eid], str((cursores[eid] or {}).get("ultimo_user_id") or "") or None)
        _gravar_cursor(client, org_id, eid, user_id)
        escolha = (user_id, eid, "round_robin")

    user_id, equipe_id, criterio = escolha
    lais_contatos_service.atualizar_contato(client, contato["id"], {"responsavel_user_id": user_id})
    client.table(T_ATRIBUICOES).insert({
        "id": str(uuid4()), "org_id": str(org_id), "contato_id": str(contato["id"]), "equipe_id": equipe_id,
        "user_id": user_id, "motivo": motivo, "criterio": criterio, "created_at": agora.isoformat()}).execute()
    nome = (_usuarios_da_org(core, org_id, [user_id]).get(user_id) or {}).get("nome")
    return {"user_id": user_id, "nome": nome, "equipe_id": equipe_id, "criterio": criterio}


# ── Julia's next turn: `contexto.estado.atendente_nome` ──────────────────────
def _nome_do_responsavel(ctx: lais_contexto_service.ContextoCtx) -> Optional[str]:
    uid = ctx.contato.get("responsavel_user_id")
    if not uid:
        return None
    from app.dependencies import get_core_client

    nome = ((_usuarios_da_org(get_core_client(), ctx.org_id, [str(uid)]).get(str(uid)) or {}).get("nome") or "").strip()
    return nome or None


def _estender_estado(base: lais_contexto_service.Provider) -> lais_contexto_service.Provider:
    """The `estado` provider + `atendente_nome` (additive: every key `base` returns is kept)."""
    def provider(ctx: lais_contexto_service.ContextoCtx) -> dict[str, Any]:
        out = base(ctx)
        try:
            nome = _nome_do_responsavel(ctx)
        except Exception:
            logger.exception("lais: could not resolve atendente_nome (org=%s) -- estado goes without it", ctx.org_id)
            nome = None
        if nome:
            out = {**out, "estado": {**(out.get("estado") or {}), "atendente_nome": nome}}
        return out

    return provider


# Replaces the `estado` provider IN PLACE (the registry order is a tested contract), wrapping the current one.
lais_contexto_service.registrar_provider("estado", _estender_estado(dict(lais_contexto_service.PROVIDERS)["estado"]))


# ── metrics ─────────────────────────────────────────────────────────────────
def _janela(mes: str) -> tuple[datetime, datetime]:
    try:
        ini = datetime.strptime(mes, "%Y-%m").replace(tzinfo=timezone.utc)
    except ValueError:
        raise AppException("mes_invalido", "Use mes=YYYY-MM.", status_code=422)
    fim = (ini.replace(day=28) + timedelta(days=4)).replace(day=1)
    return ini, fim


def _ts(valor: Any) -> Optional[datetime]:
    if not valor:
        return None
    try:
        d = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _primeira_resposta(client: Any, org_id: UUID | str, contato: dict[str, Any], desde: datetime) -> Optional[datetime]:
    rows = (client.table(T_MENSAGENS).select("created_at").eq("org_id", str(org_id)).eq("connection_id", str(contato["connection_id"]))
            .eq("chat_id", contato["chat_id"]).eq("direction", "outbound").gte("created_at", desde.isoformat())
            .order("created_at").limit(5).execute().data or [])
    for r in rows:
        t = _ts(r.get("created_at"))
        if t and t > desde:
            return t
    return None


def metricas(client: Any, core: Any, org_id: UUID | str, equipe_id: UUID | str, mes: str) -> dict[str, Any]:
    ini, fim = _janela(mes)
    e = _equipe(client, org_id, equipe_id)
    membros = _membros_da_equipe(client, org_id, e["id"])
    usuarios = _usuarios_da_org(core, org_id, [str(m["user_id"]) for m in membros])
    atrib = _todas(
        lambda a, b: client.table(T_ATRIBUICOES).select("*").eq("org_id", str(org_id)).eq("equipe_id", str(e["id"]))
        .gte("created_at", ini.isoformat()).lt("created_at", fim.isoformat()).order("id").range(a, b).execute().data,
        "lais_atribuicoes")
    atrib = sorted(atrib, key=lambda r: str(r.get("created_at") or ""), reverse=True)[:_METRICAS_MAX_ATRIBUICOES]
    total = len(atrib)
    contatos = {}
    for r in atrib:
        cid = str(r["contato_id"])
        if cid not in contatos:
            rows = client.table(T_CONTATOS).select("id, connection_id, chat_id").eq("org_id", str(org_id)).eq("id", cid).limit(1).execute().data or []
            contatos[cid] = rows[0] if rows else None
    saida = []
    for m in membros:
        uid = str(m["user_id"])
        minhas = [r for r in atrib if str(r["user_id"]) == uid]
        tprs: list[float] = []
        for r in minhas:
            c, t0 = contatos.get(str(r["contato_id"])), _ts(r.get("created_at"))
            resp = _primeira_resposta(client, org_id, c, t0) if c and t0 else None
            if resp and t0:
                tprs.append((resp - t0).total_seconds())
        conversas = _todas(
            lambda a, b: client.table(T_CONTATOS).select("id").eq("org_id", str(org_id)).eq("responsavel_user_id", uid)
            .order("id").range(a, b).execute().data, "lais_contatos")
        ultimo = (usuarios.get(uid) or {}).get("last_active_at")
        saida.append({
            "user_id": uid, "nome": (usuarios.get(uid) or {}).get("nome"), "ativo": bool(m.get("ativo")),
            "ultimo_acesso": ultimo,
            "tpr_medio_s": round(sum(tprs) / len(tprs), 1) if tprs else None,
            "tpr_amostras": len(tprs),
            "conversas": len(conversas),
            "distribuicao": len(minhas),
            "distribuicao_pct": round(100 * len(minhas) / total, 1) if total else 0.0,
        })
    return {"equipe_id": str(e["id"]), "mes": mes, "total_atribuicoes": total, "membros": saida,
            "fontes": {"ultimo_acesso": "core.noctus_users.last_active_at",
                       "tpr": "primeira mensagem outbound do chat apos a atribuicao"}}
