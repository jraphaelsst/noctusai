"""Lais > Conversas v2 (wave 7, contract section 9): the conversation list + kanban, contato mutations
(responsavel / arquivar / bloquear / etiquetas), internal notes, feedback, tags and the history read.

Pure table logic over the schema-scoped service client. WHO may see a contato is NEVER decided here:
callers pass contatos through `lais_acesso` first (single) or let `listar`/`kanban` filter through it.

Inbound policy (`aplicar_politica_inbound`): a BLOCKED number is dropped (Julia never answers it);
an ARCHIVED contato is handed back to Julia on its next inbound (un-archived + un-paused).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.primitives.exceptions import AppException

from app.services import lais_acesso, lais_contatos_service, lais_conhecimento_service, lais_visitas_service
from app.services.lais_acesso import AcessoCtx

logger = logging.getLogger(__name__)

T_ETIQUETAS = "lais_etiquetas"
T_CONTATO_ETIQUETAS = "lais_contato_etiquetas"
T_NOTAS = "lais_notas"
T_FEEDBACK = "lais_feedback"
T_CHATS = "whatsapp_chats"
T_MENSAGENS = "conversation_messages"

ABAS = ("todas", "minhas", "arquivadas")
ATENDIMENTOS = ("julia", "manual")
COR_PADRAO = "#6366f1"
_COR = re.compile(r"^#[0-9a-fA-F]{6}$")
_IN_LOTE = 200
MENSAGENS_HISTORICO = 200


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lotes(valores: list[str]):
    for i in range(0, len(valores), _IN_LOTE):
        yield valores[i:i + _IN_LOTE]


def _todas(fetch_page, label: str) -> list[dict[str, Any]]:
    return list(iter_paged_rows(fetch_page, id_key="id", label=label))


# ── etiquetas ───────────────────────────────────────────────────────────────
def listar_etiquetas(client: Any, org_id: UUID | str) -> list[dict[str, Any]]:
    rows = _todas(
        lambda a, b: client.table(T_ETIQUETAS).select("id, nome, cor, created_at").eq("org_id", str(org_id))
        .order("id").range(a, b).execute().data, "lais_etiquetas")
    return sorted(rows, key=lambda r: (str(r.get("nome") or "").lower(), str(r["id"])))


def _etiqueta_por_nome(client: Any, org_id: UUID | str, nome: str, *, exceto: Optional[str] = None) -> Optional[dict[str, Any]]:
    alvo = nome.strip().lower()
    for r in listar_etiquetas(client, org_id):
        if str(r.get("nome") or "").strip().lower() == alvo and str(r["id"]) != str(exceto or ""):
            return r
    return None


def _validar_etiqueta(nome: Optional[str], cor: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if nome is not None:
        nome = nome.strip()
        if not 1 <= len(nome) <= 40:
            raise AppException("etiqueta_invalida", "O nome da etiqueta deve ter de 1 a 40 caracteres.", status_code=422)
    if cor is not None and not _COR.match(cor):
        raise AppException("etiqueta_invalida", "A cor deve estar no formato #rrggbb.", status_code=422)
    return nome, cor


def criar_etiqueta(client: Any, org_id: UUID | str, nome: str, cor: Optional[str]) -> dict[str, Any]:
    nome, cor = _validar_etiqueta(nome, cor or COR_PADRAO)
    if _etiqueta_por_nome(client, org_id, nome or ""):
        raise AppException("etiqueta_duplicada", "Já existe uma etiqueta com esse nome.", status_code=409)
    client.table(T_ETIQUETAS).insert({"id": str(uuid4()), "org_id": str(org_id), "nome": nome, "cor": cor}).execute()
    return _etiqueta_por_nome(client, org_id, nome or "") or {}


def _etiqueta(client: Any, org_id: UUID | str, etiqueta_id: UUID | str) -> dict[str, Any]:
    rows = (client.table(T_ETIQUETAS).select("*").eq("org_id", str(org_id)).eq("id", str(etiqueta_id))
            .limit(1).execute().data or [])
    if not rows:
        raise AppException("etiqueta_nao_encontrada", "Etiqueta não encontrada.", status_code=404)
    return rows[0]


def atualizar_etiqueta(client: Any, org_id: UUID | str, etiqueta_id: UUID | str, *, nome: Optional[str], cor: Optional[str]) -> dict[str, Any]:
    atual = _etiqueta(client, org_id, etiqueta_id)
    nome, cor = _validar_etiqueta(nome, cor)
    patch: dict[str, Any] = {}
    if nome is not None:
        if _etiqueta_por_nome(client, org_id, nome, exceto=str(etiqueta_id)):
            raise AppException("etiqueta_duplicada", "Já existe uma etiqueta com esse nome.", status_code=409)
        patch["nome"] = nome
    if cor is not None:
        patch["cor"] = cor
    if patch:
        client.table(T_ETIQUETAS).update(patch).eq("org_id", str(org_id)).eq("id", str(etiqueta_id)).execute()
    return {**atual, **patch}


def excluir_etiqueta(client: Any, org_id: UUID | str, etiqueta_id: UUID | str) -> None:
    _etiqueta(client, org_id, etiqueta_id)
    # explicit child delete -- not only the FK cascade -- so removal never depends on ON DELETE behaviour
    client.table(T_CONTATO_ETIQUETAS).delete().eq("org_id", str(org_id)).eq("etiqueta_id", str(etiqueta_id)).execute()
    client.table(T_ETIQUETAS).delete().eq("org_id", str(org_id)).eq("id", str(etiqueta_id)).execute()


def _etiquetas_dos_contatos(client: Any, org_id: UUID | str, contato_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not contato_ids:
        return {}
    catalogo = {str(e["id"]): e for e in listar_etiquetas(client, org_id)}
    out: dict[str, list[dict[str, Any]]] = {}
    for lote in _lotes(contato_ids):
        for r in (client.table(T_CONTATO_ETIQUETAS).select("contato_id, etiqueta_id").eq("org_id", str(org_id))
                  .in_("contato_id", lote).execute().data or []):
            e = catalogo.get(str(r["etiqueta_id"]))
            if e:
                out.setdefault(str(r["contato_id"]), []).append({"id": str(e["id"]), "nome": e["nome"], "cor": e["cor"]})
    return out


def definir_etiquetas(client: Any, org_id: UUID | str, contato_id: UUID | str, etiqueta_ids: list[str]) -> None:
    """Replace the tag set of a contato. Every id must be a tag of this org (422 otherwise)."""
    ids = sorted({str(i) for i in etiqueta_ids})
    validas = {str(e["id"]) for e in listar_etiquetas(client, org_id)}
    if not set(ids) <= validas:
        raise AppException("etiqueta_invalida", "Etiqueta desconhecida.", status_code=422)
    atuais = {
        str(r["etiqueta_id"]) for r in (
            client.table(T_CONTATO_ETIQUETAS).select("etiqueta_id").eq("org_id", str(org_id))
            .eq("contato_id", str(contato_id)).execute().data or [])
    }
    remover = sorted(atuais - set(ids))
    if remover:
        client.table(T_CONTATO_ETIQUETAS).delete().eq("org_id", str(org_id)).eq("contato_id", str(contato_id)) \
            .in_("etiqueta_id", remover).execute()
    novas = sorted(set(ids) - atuais)
    if novas:
        client.table(T_CONTATO_ETIQUETAS).insert(
            [{"org_id": str(org_id), "contato_id": str(contato_id), "etiqueta_id": e} for e in novas]).execute()


# ── list / kanban ───────────────────────────────────────────────────────────
def _chats_dos_contatos(client: Any, org_id: UUID | str, contatos: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    chat_ids = sorted({str(c["chat_id"]) for c in contatos})
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for lote in _lotes(chat_ids):
        for r in (client.table(T_CHATS)
                  .select("connection_id, chat_id, agente_pausado, last_message_at, last_message_preview, unread_count, title")
                  .eq("org_id", str(org_id)).in_("chat_id", lote).execute().data or []):
            out[(str(r["connection_id"]), str(r["chat_id"]))] = r
    return out


def _item(c: dict[str, Any], chat: Optional[dict[str, Any]], etiquetas: list[dict[str, Any]]) -> dict[str, Any]:
    pausado = bool((chat or {}).get("agente_pausado"))
    return {
        "id": str(c["id"]), "contato_id": str(c["id"]), "connection_id": str(c["connection_id"]), "chat_id": c["chat_id"],
        "nome": c.get("nome"), "telefone_e164": c.get("telefone_e164"), "telefone": c.get("telefone_e164"), "operacao": c.get("operacao"),
        "status_envio": c.get("status_envio"), "canal": c.get("canal"),
        "responsavel_user_id": c.get("responsavel_user_id"),
        "arquivado": bool(c.get("arquivado")), "bloqueado": bool(c.get("bloqueado")),
        "ultimo_inbound_at": c.get("ultimo_inbound_at"), "encerrado_at": c.get("encerrado_at"),
        "atendimento": "manual" if pausado else "julia", "agente_pausado": pausado,
        "last_message_at": (chat or {}).get("last_message_at"),
        "last_message_preview": (chat or {}).get("last_message_preview"),
        "unread_count": (chat or {}).get("unread_count") or 0,
        "nao_lidas": (chat or {}).get("unread_count") or 0,
        "etiquetas": etiquetas,
    }


def _contatos_visiveis(client: Any, ctx: AcessoCtx, **eq: Any) -> list[dict[str, Any]]:
    def page(a: int, b: int):
        q = client.table(lais_acesso.T_CONTATOS).select("*").eq("org_id", str(ctx.org_id))
        for k, v in eq.items():
            q = q.eq(k, v)
        return q.order("id").range(a, b).execute().data

    return lais_acesso.filtrar_contatos(client, ctx, _todas(page, "lais_contatos"))


def _filtros_de_coluna(itens: list[dict[str, Any]], *, operacao: list[str], status_sw: list[str],
                       atendimento: list[str], responsavel: list[str]) -> list[dict[str, Any]]:
    """The comma-joined list filters (OR within a filter, AND across). `sem` in `responsavel` = unassigned."""
    out = []
    for i in itens:
        if operacao and i.get("operacao") not in operacao:
            continue
        if status_sw and i.get("status_envio") not in status_sw:
            continue
        if atendimento and i["atendimento"] not in atendimento:
            continue
        if responsavel and not (
            (i.get("responsavel_user_id") is None and "sem" in responsavel)
            or str(i.get("responsavel_user_id")) in responsavel
        ):
            continue
        out.append(i)
    return out


def _enriquecer(client: Any, ctx: AcessoCtx, contatos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chats = _chats_dos_contatos(client, ctx.org_id, contatos)
    tags = _etiquetas_dos_contatos(client, ctx.org_id, [str(c["id"]) for c in contatos])
    return [_item(c, chats.get((str(c["connection_id"]), str(c["chat_id"]))), tags.get(str(c["id"]), [])) for c in contatos]


def _ordenar(itens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(itens, key=lambda i: (str(i.get("last_message_at") or i.get("ultimo_inbound_at") or ""), i["id"]), reverse=True)


def _filtrar(itens: list[dict[str, Any]], ctx: AcessoCtx, donos: dict[str, Optional[str]], *, aba: str,
             etiquetas: list[str], busca: Optional[str]) -> list[dict[str, Any]]:
    out = []
    termo = (busca or "").strip().lower()
    for i in itens:
        if aba == "minhas" and lais_acesso.dono_do_contato(i, donos) != ctx.user_id:
            continue
        if etiquetas and not ({e["id"] for e in i["etiquetas"]} & set(etiquetas)):
            continue
        if termo and termo not in f"{i.get('nome') or ''} {i.get('telefone_e164') or ''}".lower():
            continue
        out.append(i)
    return out


def listar(
    client: Any, ctx: AcessoCtx, *, aba: str = "todas", operacao: Optional[list[str]] = None,
    status_sw: Optional[list[str]] = None, atendimento: Optional[list[str]] = None,
    responsavel: Optional[list[str]] = None, etiquetas: Optional[list[str]] = None,
    busca: Optional[str] = None, limit: int = 50, offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """`(page, total)` of the conversations the caller may see, newest first. `aba`:
    todas / minhas (the caller OWNS them) / arquivadas. List filters are OR-within / AND-across."""
    contatos = _contatos_visiveis(client, ctx, arquivado=(aba == "arquivadas"))
    donos = lais_acesso.donos_das_conexoes(client, ctx.org_id, (c["connection_id"] for c in contatos))
    itens = _filtros_de_coluna(
        _ordenar(_enriquecer(client, ctx, contatos)), operacao=operacao or [], status_sw=status_sw or [],
        atendimento=atendimento or [], responsavel=responsavel or [])
    itens = _filtrar(itens, ctx, donos, aba=aba, etiquetas=etiquetas or [], busca=busca)
    return itens[offset:offset + limit], len(itens)


def kanban(
    client: Any, ctx: AcessoCtx, *, etiquetas: Optional[list[str]] = None, operacao: Optional[list[str]] = None,
    status_sw: Optional[list[str]] = None, atendimento: Optional[list[str]] = None,
    responsavel: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Columns: a fixed `todas` (every live conversation), one per etiqueta (the `etiquetas` ids pick which;
    default = every tag of the org) and a collapsed `arquivadas` (count only)."""
    contatos = _contatos_visiveis(client, ctx)
    itens = _filtros_de_coluna(
        _ordenar(_enriquecer(client, ctx, contatos)), operacao=operacao or [], status_sw=status_sw or [],
        atendimento=atendimento or [], responsavel=responsavel or [])
    vivos = [i for i in itens if not i["arquivado"]]
    catalogo = listar_etiquetas(client, ctx.org_id)
    escolhidas = [e for e in catalogo if not etiquetas or str(e["id"]) in set(etiquetas)]
    colunas: list[dict[str, Any]] = [{"tipo": "todas", "id": "todas", "itens": vivos}]
    for e in escolhidas:
        colunas.append({
            "tipo": "etiqueta", "id": str(e["id"]),
            "etiqueta": {"id": str(e["id"]), "nome": e["nome"], "cor": e["cor"]},
            "itens": [i for i in vivos if str(e["id"]) in {t["id"] for t in i["etiquetas"]}],
        })
    colunas.append({"tipo": "arquivadas", "id": "arquivadas", "total": sum(1 for i in itens if i["arquivado"])})
    return {"colunas": colunas}


# ── contato mutations ───────────────────────────────────────────────────────
def _validar_responsavel(core: Any, org_id: UUID | str, user_id: Optional[str]) -> None:
    if user_id is None:
        return
    rows = (core.table("noctus_users").select("id").eq("id", str(user_id)).eq("org_id", str(org_id))
            .limit(1).execute().data or [])
    if not rows:
        raise AppException("responsavel_invalido", "O responsável precisa ser um usuário da organização.", status_code=422)


def atualizar_contato(
    client: Any, core: Any, ctx: AcessoCtx, contato: dict[str, Any], campos: dict[str, Any],
) -> dict[str, Any]:
    """Apply `{responsavel_user_id?, arquivado?, bloqueado?, etiquetas?}` (only the keys present).
    Archiving / blocking bumps `gen`, which cancels every queued job of the contato (re-engagement included)."""
    patch: dict[str, Any] = {}
    if "responsavel_user_id" in campos:
        novo = campos["responsavel_user_id"]
        _validar_responsavel(core, ctx.org_id, str(novo) if novo else None)
        patch["responsavel_user_id"] = str(novo) if novo else None
    for k in ("arquivado", "bloqueado"):
        if k in campos and campos[k] is not None:
            patch[k] = bool(campos[k])
    if "etiquetas" in campos and campos["etiquetas"] is not None:
        definir_etiquetas(client, ctx.org_id, contato["id"], [str(e) for e in campos["etiquetas"]])
    if patch:
        if patch.get("arquivado") or patch.get("bloqueado"):
            lais_contatos_service.bump_gen(client, contato["id"], **patch)
        else:
            lais_contatos_service.atualizar_contato(client, contato["id"], patch)
    novo_contato = (client.table(lais_acesso.T_CONTATOS).select("*").eq("id", str(contato["id"])).limit(1).execute().data or [contato])[0]
    return _enriquecer(client, ctx, [novo_contato])[0]


# ── notas ───────────────────────────────────────────────────────────────────
def _nota_saida(r: dict[str, Any]) -> dict[str, Any]:
    return {k: r.get(k) for k in ("id", "contato_id", "autor_user_id", "texto", "created_at")}


def listar_notas(client: Any, org_id: UUID | str, contato_id: UUID | str) -> list[dict[str, Any]]:
    rows = _todas(
        lambda a, b: client.table(T_NOTAS).select("*").eq("org_id", str(org_id)).eq("contato_id", str(contato_id))
        .is_("deleted_at", "null").order("id").range(a, b).execute().data, "lais_notas")
    return [_nota_saida(r) for r in sorted(rows, key=lambda r: (str(r.get("created_at") or ""), str(r["id"])), reverse=True)]


def criar_nota(client: Any, ctx: AcessoCtx, contato_id: UUID | str, texto: str) -> dict[str, Any]:
    texto = texto.strip()
    if not 1 <= len(texto) <= 4000:
        raise AppException("nota_invalida", "A nota deve ter de 1 a 4000 caracteres.", status_code=422)
    res = client.table(T_NOTAS).insert({
        "id": str(uuid4()), "org_id": str(ctx.org_id), "contato_id": str(contato_id), "autor_user_id": ctx.user_id or None,
        "texto": texto, "deleted_at": None,
    }).execute().data or []
    row = res[0] if res else next(
        (r for r in listar_notas(client, ctx.org_id, contato_id) if r["texto"] == texto), {})
    return _nota_saida(row) if row else {"contato_id": str(contato_id), "texto": texto}


def excluir_nota(client: Any, ctx: AcessoCtx, contato_id: UUID | str, nota_id: UUID | str) -> None:
    """Soft delete. The author or an org admin; anyone else with access to the contato gets 403."""
    rows = (client.table(T_NOTAS).select("*").eq("org_id", str(ctx.org_id)).eq("contato_id", str(contato_id))
            .eq("id", str(nota_id)).is_("deleted_at", "null").limit(1).execute().data or [])
    if not rows:
        raise AppException("nota_nao_encontrada", "Nota não encontrada.", status_code=404)
    if not ctx.admin and str(rows[0].get("autor_user_id") or "") != ctx.user_id:
        raise AppException("sem_acesso", "Só o autor ou um administrador pode excluir a nota.", status_code=403)
    client.table(T_NOTAS).update({"deleted_at": _agora()}).eq("org_id", str(ctx.org_id)).eq("id", str(nota_id)).execute()


# ── feedback ────────────────────────────────────────────────────────────────
def registrar_feedback(
    client: Any, ctx: AcessoCtx, contato: dict[str, Any], *, nota: str, comentario: Optional[str], interacao_id: Optional[str],
) -> dict[str, Any]:
    if nota not in ("like", "dislike"):
        raise AppException("feedback_invalido", "A nota deve ser like ou dislike.", status_code=422)
    if interacao_id:
        rows = (client.table(lais_contatos_service.T_INTERACOES).select("id").eq("org_id", str(ctx.org_id))
                .eq("contato_id", str(contato["id"])).eq("id", str(interacao_id)).limit(1).execute().data or [])
        if not rows:
            raise AppException("interacao_invalida", "Interação desconhecida para este contato.", status_code=422)
    else:
        aberta = lais_contatos_service.interacao_aberta(client, contato["id"])
        interacao_id = str(aberta["id"]) if aberta else None
    linha = {
        "id": str(uuid4()), "org_id": str(ctx.org_id), "contato_id": str(contato["id"]), "interacao_id": interacao_id,
        "user_id": ctx.user_id or None, "nota": nota, "comentario": (comentario or "").strip() or None,
    }
    res = client.table(T_FEEDBACK).insert(linha).execute().data or []
    return {k: (res[0] if res else linha).get(k) for k in ("id", "contato_id", "interacao_id", "user_id", "nota", "comentario", "created_at")}


# ── history ─────────────────────────────────────────────────────────────────
def historico(client: Any, ctx: AcessoCtx, contato: dict[str, Any]) -> dict[str, Any]:
    interacoes = (
        client.table(lais_contatos_service.T_INTERACOES).select("*").eq("org_id", str(ctx.org_id))
        .eq("contato_id", str(contato["id"])).order("iniciada_at", desc=True).limit(100).execute().data or []
    )
    mensagens = (
        client.table(T_MENSAGENS).select("id, direction, body, created_at, provider_message_id")
        .eq("org_id", str(ctx.org_id)).eq("connection_id", str(contato["connection_id"])).eq("chat_id", contato["chat_id"])
        .order("created_at", desc=True).limit(MENSAGENS_HISTORICO).execute().data or []
    )
    item = _enriquecer(client, ctx, [contato])[0]
    visitas = sorted(
        client.table("lais_visitas").select("*").eq("org_id", str(ctx.org_id)).eq("contato_id", str(contato["id"]))
        .execute().data or [], key=lambda v: str(v.get("inicio") or ""), reverse=True)
    return {
        "contato": {**item, "email": contato.get("email"), "slots": contato.get("slots") or {},
                    "visitas": [lais_visitas_service.saida(v) for v in visitas]},
        "interacoes": interacoes,
        "mensagens": sorted(mensagens, key=lambda m: (str(m.get("created_at") or ""), str(m.get("id")))),
    }


# ── inbound policy + attendant prefix ───────────────────────────────────────
def aplicar_politica_inbound(client: Any, chat_store: Any, *, org_id: UUID | str, connection_id: UUID | str, chat_id: str) -> str:
    """Called for every Julia-lead inbound. `bloqueado` -> the caller drops the message (Julia never
    answers a blocked number); `devolvido` -> an archived contato goes back to Julia (un-archived and
    un-paused) and the turn proceeds; `ok` -> nothing to do."""
    contato = lais_contatos_service.buscar_contato(client, org_id, connection_id, chat_id)
    if contato is None:
        return "ok"
    if contato.get("bloqueado"):
        return "bloqueado"
    if contato.get("arquivado"):
        lais_contatos_service.atualizar_contato(client, contato["id"], {"arquivado": False})
        chat_store.set_agente_pausado(connection_id=UUID(str(connection_id)), chat_id=chat_id, pausado=False)
        return "devolvido"
    return "ok"


def nome_do_atendente(user: Any) -> Optional[str]:
    """Display name for the `*{nome}*:` prefix (cosmetic only -- never an authz source)."""
    meta = getattr(user, "user_metadata", None) or {}
    for k in ("full_name", "name", "nome"):
        v = str(meta.get(k) or "").strip()
        if v:
            return v
    email = str(getattr(user, "email", "") or "").strip()
    return email.split("@")[0] if email else None


def prefixar_atendente(client: Any, org_id: UUID | str, user: Any, texto: str) -> str:
    """`*{nome}*:\\n{texto}` when the org enabled Conhecimento `exibir_atendente` and the sender has a name."""
    try:
        ativo = bool(lais_conhecimento_service.ler_secoes(client, org_id)["exibir_atendente"]["dados"].get("ativo"))
    except Exception:
        logger.exception("lais: could not read exibir_atendente org=%s -- sending without the prefix", org_id)
        return texto
    nome = nome_do_atendente(user) if ativo else None
    return f"*{nome}*:\n{texto}" if nome else texto
