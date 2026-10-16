"""Lais notifications (wave 6, contract 8).

Fan-out: every `lais_eventos` row of a notifiable type becomes one in-app notification per recipient
(`noctusai_lib.domain.notifications.write_in_app`, kind `lais_<tipo>`, in core's `public.notifications`)
unless that user switched the type off. It rides the `lais_eventos_service.registrar_sink` seam, so no
emitting caller changes.

Recipients (same target rule as the page-0 handoff, 11.4): the contato's `responsavel_user_id`, else the
connection owner (`whatsapp_connections.user_id`), else the org's owners/admins. Each candidate must still
belong to the org (a stale id falls through to the next tier).

`handoff` is NOT fanned out here: `lais_agente_service.notificar_handoff` already writes it (with the
configured target + link) and nothing emits a `handoff` event, so it can never double-fire; the sink also
skips it explicitly so a future emitter cannot.

The feed reads the SAME `public.notifications` rows, scoped to the caller (`user_id` + `org_id`): a member
sees only their own.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Callable, Iterable, Optional
from uuid import UUID

from noctusai_lib.api.auth.session.scopes import ADMIN_ORG_ROLES
from noctusai_lib.domain.notifications import write_in_app
from noctusai_lib.integrations.persistence.paging import iter_paged_rows
from noctusai_lib.primitives.exceptions import AppException

from app.services import lais_eventos_service as eventos

logger = logging.getLogger(__name__)

T_PREFS = "lais_notificacao_prefs"
KIND_PREFIX = "lais_"
#: Header toggle "Notificar lead pronto para atendimento": gates `novo_atendimento` (a lead ready to be attended).
LEAD_PRONTO = "lead_pronto"
GATE_POR_TIPO = {"novo_atendimento": LEAD_PRONTO}
TIPOS_FANOUT = eventos.TIPOS_NOTIFICAVEIS - {"handoff"}
TIPOS_PREF = sorted(eventos.TIPOS_NOTIFICAVEIS) + [LEAD_PRONTO]
OPERACOES = ("compra", "aluguel")
PAGE_SIZE_MAX = 100

TITULOS = {
    "pre_agendamento_visita": "Solicitação de pré-agendamento de visita",
    "cobranca_atendimento": "Cobrança de atendimento",
    "relatorio": "Relatórios da Lais",
    "remarketing": "Remarketing",
    "captacao": "Captação",
    "atualizacao_base_imoveis": "Atualização de base de imóveis",
    "novo_lead": "Novo lead gerado",
    "novo_atendimento": "Novo atendimento",
    "nova_mensagem": "Nova mensagem",
    "avaliacao_google": "Avaliações no Google",
    "handoff": "Atendimento humano solicitado",
}
CORPOS = {
    "pre_agendamento_visita": "A Julia registrou uma solicitação de pré-agendamento de visita.",
    "cobranca_atendimento": "Um lead cobrou atendimento: ninguém respondeu a ele.",
    "relatorio": "Há um novo relatório da Lais disponível.",
    "remarketing": "Houve movimento de remarketing.",
    "captacao": "A Julia identificou uma potencial captação de imóvel.",
    "atualizacao_base_imoveis": "A base de imóveis foi atualizada.",
    "novo_lead": "Um novo lead foi gerado.",
    "novo_atendimento": "Um lead está pronto para atendimento.",
    "nova_mensagem": "Você recebeu uma nova mensagem.",
    "avaliacao_google": "Há uma nova avaliação no Google.",
}
LINKS = {"captacao": "/lais/captacao", "pre_agendamento_visita": "/lais/visitas", "relatorio": "/lais/relatorios"}
#: Intent tokens in the episode summary that mean "the lead complained nobody answered".
INTENCOES_COBRANCA = frozenset({"cobranca_atendimento", "cobranca", "cobrar_atendimento"})


_core_provider: Optional[Callable[[], Any]] = None


def registrar_core_provider(fn: Optional[Callable[[], Any]]) -> None:
    """Core client used to resolve recipients (org users); default `get_core_client()`. Tests inject here."""
    global _core_provider
    _core_provider = fn


def _core() -> Any:
    if _core_provider is not None:
        return _core_provider()
    from app.dependencies import get_core_client

    return get_core_client()


# ── recipients ──────────────────────────────────────────────────────────────
def _membros_da_org(core: Any, org_id: Any, ids: Iterable[Any]) -> set[str]:
    ids = [str(i) for i in ids if i]
    if not ids:
        return set()
    rows = core.table("noctus_users").select("id,org_id").in_("id", ids).execute().data or []
    return {str(r["id"]) for r in rows if str(r.get("org_id")) == str(org_id)}


def admins_da_org(core: Any, org_id: Any) -> list[str]:
    rows = core.table("noctus_users").select("id,org_role").eq("org_id", str(org_id)).execute().data or []
    return sorted({str(r["id"]) for r in rows if r.get("org_role") in ADMIN_ORG_ROLES})


def resolver_destinatarios(client: Any, core: Any, org_id: Any, contato_id: Any = None) -> list[str]:
    """responsável -> connection owner -> org owners/admins (first non-empty tier wins)."""
    contato: dict[str, Any] = {}
    if contato_id:
        rows = (client.table("lais_contatos").select("*").eq("id", str(contato_id)).eq("org_id", str(org_id))
                .limit(1).execute().data or [])
        contato = rows[0] if rows else {}
    ativos = _membros_da_org(core, org_id, [contato.get("responsavel_user_id")])
    if ativos:
        return sorted(ativos)
    if contato.get("connection_id"):
        con = (client.table("whatsapp_connections").select("user_id").eq("id", str(contato["connection_id"]))
               .eq("org_id", str(org_id)).limit(1).execute().data or [])
        dono = _membros_da_org(core, org_id, [con[0].get("user_id")] if con else [])
        if dono:
            return sorted(dono)
    return admins_da_org(core, org_id)


# ── preferences ─────────────────────────────────────────────────────────────
def preferencias(client: Any, org_id: Any, user_ids: Iterable[Any]) -> dict[str, dict[str, bool]]:
    """`{user_id: {tipo: in_app}}` for explicitly stored rows only (absent = on)."""
    ids = sorted({str(u) for u in user_ids if u})
    out: dict[str, dict[str, bool]] = {u: {} for u in ids}
    if not ids:
        return out
    rows = client.table(T_PREFS).select("user_id,tipo,in_app").eq("org_id", str(org_id)).in_("user_id", ids).execute().data or []
    for r in rows:
        out.setdefault(str(r["user_id"]), {})[r["tipo"]] = bool(r["in_app"])
    return out


def permite(prefs_do_usuario: dict[str, bool], tipo: str) -> bool:
    if prefs_do_usuario.get(tipo) is False:
        return False
    gate = GATE_POR_TIPO.get(tipo)
    return not (gate and prefs_do_usuario.get(gate) is False)


def ler_preferencias(client: Any, org_id: Any, user_id: Any) -> dict[str, Any]:
    guardadas = preferencias(client, org_id, [user_id])[str(user_id)]
    return {"tipos": [{"tipo": t, "in_app": guardadas.get(t, True)} for t in TIPOS_PREF],
            LEAD_PRONTO: guardadas.get(LEAD_PRONTO, True)}


def salvar_preferencias(client: Any, org_id: Any, user_id: Any, itens: dict[str, bool]) -> dict[str, Any]:
    desconhecidos = sorted(set(itens) - set(TIPOS_PREF))
    if desconhecidos:
        raise AppException("tipo_invalido", f"Tipo de notificação desconhecido: {', '.join(desconhecidos)}.", status_code=422)
    if itens:
        client.table(T_PREFS).upsert(
            [{"org_id": str(org_id), "user_id": str(user_id), "tipo": t, "in_app": bool(v)} for t, v in itens.items()],
            on_conflict="org_id,user_id,tipo",
        ).execute()
    return ler_preferencias(client, org_id, user_id)


# ── fan-out ─────────────────────────────────────────────────────────────────
def notificar(client: Any, evento: dict[str, Any], core: Any = None) -> int:
    """Fan one event out; returns notifications written. Raises on a failed insert (the sink wrapper logs it)."""
    tipo = evento.get("tipo")
    if tipo not in TIPOS_FANOUT:
        return 0
    core = core or _core()
    org_id = evento["org_id"]
    contato_id = evento.get("contato_id")
    destinatarios = resolver_destinatarios(client, core, org_id, contato_id)
    prefs = preferencias(client, org_id, destinatarios)
    alvo = [u for u in destinatarios if permite(prefs.get(u, {}), tipo)]
    if not alvo:
        return 0
    payload = evento.get("payload") or {}
    operacao = payload.get("operacao")
    if not operacao and contato_id:
        rows = client.table("lais_contatos").select("operacao").eq("id", str(contato_id)).limit(1).execute().data or []
        operacao = rows[0].get("operacao") if rows else None
    link = LINKS.get(tipo) or (f"/lais/conversas?contato={contato_id}" if contato_id else "/lais/notificacoes")
    return write_in_app(
        core, user_ids=alvo, kind=KIND_PREFIX + tipo, title=TITULOS[tipo],
        message=str(payload.get("texto") or CORPOS[tipo])[:500],
        metadata={"link": link, "evento_id": evento.get("id"), "contato_id": str(contato_id) if contato_id else None,
                  "operacao": operacao, "lais": True},
        org_id=org_id,
    )


def registrar() -> None:
    eventos.registrar_sink(notificar)


def avisar_cobranca(client: Any, org_id: Any, contato: dict[str, Any], interacao: dict[str, Any], intencoes: Iterable[Any]) -> None:
    """Episode closed with a "lead says nobody answered" intent -> a `cobranca_atendimento` event. Never raises."""
    if not any(str(i).strip().lower() in INTENCOES_COBRANCA for i in intencoes):
        return
    eventos.emitir(client, org_id, "cobranca_atendimento", contato.get("id"),
                   {"interacao_id": str(interacao.get("id")), "operacao": interacao.get("operacao") or contato.get("operacao")})


# ── feed ────────────────────────────────────────────────────────────────────
def _dia(valor: Any) -> Optional[date]:
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _minhas(core: Any, org_id: Any, user_id: Any) -> list[dict[str, Any]]:
    def fetch(start: int, end: int):
        return (core.table("notifications").select("*").eq("user_id", str(user_id)).eq("org_id", str(org_id))
                .order("id").range(start, end).execute().data)

    rows = [r for r in iter_paged_rows(fetch, label="lais notifications")
            if str((r.get("metadata") or {}).get("tipo", "")).startswith(KIND_PREFIX)]
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return rows


def listar(core: Any, org_id: Any, user_id: Any, *, tipo: Optional[str] = None, operacao: Optional[str] = None,
           de: Optional[date] = None, ate: Optional[date] = None, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    if tipo is not None and tipo not in eventos.TIPOS_NOTIFICAVEIS:
        raise AppException("tipo_invalido", "Tipo de notificação inválido.", status_code=422)
    if operacao is not None and operacao not in OPERACOES:
        raise AppException("operacao_invalida", "Use operacao=compra ou operacao=aluguel.", status_code=422)
    if de and ate and de > ate:
        raise AppException("periodo_invalido", "`de` não pode ser depois de `ate`.", status_code=422)
    todas = _minhas(core, org_id, user_id)
    nao_lidas = sum(1 for r in todas if not r.get("read"))
    sel = []
    for r in todas:
        meta = r.get("metadata") or {}
        if tipo and meta.get("tipo") != KIND_PREFIX + tipo:
            continue
        if operacao and meta.get("operacao") != operacao:
            continue
        d = _dia(r.get("created_at"))
        if (de and (d is None or d < de)) or (ate and (d is None or d > ate)):
            continue
        sel.append({"id": r["id"], "tipo": str(meta["tipo"])[len(KIND_PREFIX):], "titulo": r.get("title"),
                    "mensagem": r.get("message"), "operacao": meta.get("operacao"), "link": meta.get("link"),
                    "contato_id": meta.get("contato_id"), "lida": bool(r.get("read")), "created_at": r.get("created_at")})
    inicio = (page - 1) * page_size
    return {"items": sel[inicio:inicio + page_size], "total": len(sel), "nao_lidas": nao_lidas}


def marcar_lidas(core: Any, org_id: Any, user_id: Any, *, ids: Optional[list[UUID]] = None, todas: bool = False) -> None:
    """Only the caller's own Lais notifications; foreign / non-Lais ids are silently not touched."""
    minhas = [r for r in _minhas(core, org_id, user_id) if not r.get("read")]
    alvo = [str(r["id"]) for r in minhas if todas or str(r["id"]) in {str(i) for i in (ids or [])}]
    for i in range(0, len(alvo), 100):
        (core.table("notifications").update({"read": True}).eq("user_id", str(user_id)).eq("org_id", str(org_id))
         .in_("id", alvo[i:i + 100]).execute())
