"""Conversation storage for the help-chat organ — Protocol + Fake + Supabase
Real + factory (CLAUDE.md §1 "seed IO modules ship Fake+Real+factory").

Owner decisions (2026-10-07): the FULL text of every turn is stored, kept
forever (`NOC-REMEDIATE[help-chat-retention]`: no retention job yet), readable
ONLY by the NoctusAI platform team — the tables are `public.help_chat_conversas`
/ `public.help_chat_mensagens` with RLS on, NO policy for anon/authenticated
and the grants revoked, so only the service role (this module's client) can
touch them. Product-agnostic: one `produto` column instead of one table per
product.

The Protocol is synchronous (the PostgREST client is); the router runs it in a
threadpool. A store failure must never break the user's answer — the router
catches it and logs at ERROR with org/conversa ids (never message text).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Optional, Protocol, runtime_checkable

# NOC-REMEDIATE[help-chat-retention]: conversations are kept forever (owner
# decision 2026-10-07); add a retention/purge job when the owner sets a window — 2026-10-07

TABELA_CONVERSAS = "help_chat_conversas"
TABELA_MENSAGENS = "help_chat_mensagens"

MotivoEncerramento = Literal["concluido", "inatividade"]


class HelpChatStoreError(RuntimeError):
    """The store could not persist/read (network, constraint, ...)."""


class HelpChatConversaAlheia(HelpChatStoreError):
    """`conversa_id` already exists and belongs to another user/org."""


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


@runtime_checkable
class HelpChatStore(Protocol):
    def registrar_turno_usuario(
        self,
        *,
        conversa_id: str,
        produto: str,
        org_id: str,
        user_id: Optional[str],
        conteudo: str,
        pagina_atual: Optional[str],
    ) -> None:
        """Create the conversation if new (ownership-checked) and append the
        user turn. Raises `HelpChatConversaAlheia` for someone else's id."""

    def registrar_resposta(
        self,
        *,
        conversa_id: str,
        conteudo: str,
        modelo: str,
        latency_ms: int,
        truncated: bool,
        parcial: bool,
    ) -> None:
        """Append the assistant reply (`parcial` = the stream died mid-way)."""

    def avaliar(
        self,
        *,
        conversa_id: str,
        org_id: str,
        user_id: Optional[str],
        nota: int,
        comentario: Optional[str],
        motivo: MotivoEncerramento,
    ) -> bool:
        """Upsert the rating (last wins). False = not the caller's conversation."""


@dataclass
class FakeHelpChatStore:
    """In-memory store for tests. `falhar` makes every call raise (to prove a
    store outage never breaks the answer)."""

    conversas: dict[str, dict] = field(default_factory=dict)
    mensagens: list[dict] = field(default_factory=list)
    falhar: Optional[BaseException] = None

    def _check(self) -> None:
        if self.falhar is not None:
            raise self.falhar

    def registrar_turno_usuario(self, *, conversa_id, produto, org_id, user_id, conteudo, pagina_atual) -> None:
        self._check()
        existente = self.conversas.get(conversa_id)
        if existente is None:
            self.conversas[conversa_id] = {
                "id": conversa_id, "produto": produto, "org_id": org_id, "user_id": user_id,
                "iniciada_em": _agora(), "atualizada_em": _agora(), "encerrada_em": None,
                "motivo_encerramento": None, "nota": None, "comentario": None, "avaliada_em": None,
            }
        elif (existente["org_id"], existente["user_id"]) != (org_id, user_id):
            raise HelpChatConversaAlheia(conversa_id)
        self.mensagens.append({
            "conversa_id": conversa_id, "papel": "user", "conteudo": conteudo,
            "pagina_atual": pagina_atual, "modelo": None, "latency_ms": None,
            "truncated": False, "parcial": False,
        })

    def registrar_resposta(self, *, conversa_id, conteudo, modelo, latency_ms, truncated, parcial) -> None:
        self._check()
        self.mensagens.append({
            "conversa_id": conversa_id, "papel": "assistant", "conteudo": conteudo,
            "pagina_atual": None, "modelo": modelo, "latency_ms": latency_ms,
            "truncated": truncated, "parcial": parcial,
        })
        self.conversas[conversa_id]["atualizada_em"] = _agora()

    def avaliar(self, *, conversa_id, org_id, user_id, nota, comentario, motivo) -> bool:
        self._check()
        conversa = self.conversas.get(conversa_id)
        if conversa is None or (conversa["org_id"], conversa["user_id"]) != (org_id, user_id):
            return False
        conversa.update(
            nota=nota, comentario=comentario, motivo_encerramento=motivo,
            avaliada_em=_agora(), encerrada_em=_agora(),
        )
        return True


class SupabaseHelpChatStore:
    """Real store over PostgREST. `client_fn` must return a SERVICE-ROLE client
    bound to the `public` schema (e.g. a product's `get_core_client()`)."""

    def __init__(self, client_fn: Callable[[], Any]) -> None:
        self._client_fn = client_fn

    def _owner_filters(self, query: Any, org_id: str, user_id: Optional[str]) -> Any:
        query = query.eq("org_id", org_id)
        return query.eq("user_id", user_id) if user_id is not None else query.is_("user_id", "null")

    def registrar_turno_usuario(self, *, conversa_id, produto, org_id, user_id, conteudo, pagina_atual) -> None:
        db = self._client_fn()
        try:
            db.table(TABELA_CONVERSAS).upsert(
                {"id": conversa_id, "produto": produto, "org_id": org_id, "user_id": user_id},
                on_conflict="id", ignore_duplicates=True,
            ).execute()
            dono = self._owner_filters(
                db.table(TABELA_CONVERSAS).select("id").eq("id", conversa_id), org_id, user_id
            ).execute()
        except Exception as exc:
            raise HelpChatStoreError("falha ao registrar conversa") from exc
        if not dono.data:
            raise HelpChatConversaAlheia(conversa_id)
        self._inserir_mensagem(db, {
            "conversa_id": conversa_id, "papel": "user", "conteudo": conteudo,
            "pagina_atual": pagina_atual,
        })
        self._tocar(db, conversa_id)

    def registrar_resposta(self, *, conversa_id, conteudo, modelo, latency_ms, truncated, parcial) -> None:
        db = self._client_fn()
        self._inserir_mensagem(db, {
            "conversa_id": conversa_id, "papel": "assistant", "conteudo": conteudo,
            "modelo": modelo, "latency_ms": latency_ms, "truncated": truncated, "parcial": parcial,
        })
        self._tocar(db, conversa_id)

    def avaliar(self, *, conversa_id, org_id, user_id, nota, comentario, motivo) -> bool:
        db = self._client_fn()
        agora = _agora()
        try:
            query = db.table(TABELA_CONVERSAS).update({
                "nota": nota, "comentario": comentario, "motivo_encerramento": motivo,
                "avaliada_em": agora, "encerrada_em": agora, "atualizada_em": agora,
            }).eq("id", conversa_id)
            resp = self._owner_filters(query, org_id, user_id).execute()
        except Exception as exc:
            raise HelpChatStoreError("falha ao registrar avaliação") from exc
        return bool(resp.data)

    @staticmethod
    def _inserir_mensagem(db: Any, row: dict) -> None:
        try:
            db.table(TABELA_MENSAGENS).insert(row).execute()
        except Exception as exc:
            raise HelpChatStoreError("falha ao registrar mensagem") from exc

    @staticmethod
    def _tocar(db: Any, conversa_id: str) -> None:
        try:
            db.table(TABELA_CONVERSAS).update({"atualizada_em": _agora()}).eq("id", conversa_id).execute()
        except Exception as exc:
            raise HelpChatStoreError("falha ao atualizar conversa") from exc


def make_help_chat_store(*, client_fn: Callable[[], Any]) -> HelpChatStore:
    """Factory: the Supabase-backed store. Tests build `FakeHelpChatStore()`
    directly and inject it through `create_help_chat_router(store=...)`."""
    return SupabaseHelpChatStore(client_fn)


__all__ = [
    "FakeHelpChatStore",
    "HelpChatConversaAlheia",
    "HelpChatStore",
    "HelpChatStoreError",
    "MotivoEncerramento",
    "SupabaseHelpChatStore",
    "TABELA_CONVERSAS",
    "TABELA_MENSAGENS",
    "make_help_chat_store",
]
