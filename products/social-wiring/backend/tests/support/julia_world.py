"""Shared builders for the Julia (lead agent) tests: a seeded mock DB, a Julia-on
connection, the seed `FakeWahaClient`, the fake bus / redis / buffer, and a ready-made
`LeadDeps`. The external seams (DB, WAHA, Redis, bus, agents) are the Fakes the seed
and the product ship -- nothing of ours is patched.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import fakeredis
from cryptography.fernet import Fernet

from noctusai_lib.domain.chatbot import ConversationBufferService
from noctusai_lib.integrations.redis import make_fake_redis_client
from noctusai_lib.integrations.whatsapp.fake_adapter import FakeWahaClient
from noctusai_lib.realtime import FakeRealtimeBus
from noctusai_lib.testing import MockSupabaseClient

from app.clients.agents import FakeAgentsClient
from app.config import SocialWiringSettings
from app.services.julia_lead_turn_service import LeadDeps
from app.services.message_store import MessageStore
from app.services.whatsapp_chat_store import WhatsAppChatStore
from app.services.whatsapp_connection_store import WhatsAppConnectionRecord
from app.services.whatsapp_realtime import whatsapp_scope

ORG_ID = "00000000-0000-4000-8000-0000000000e1"
OTHER_ORG_ID = "00000000-0000-4000-8000-0000000000f1"
OWNER_ID = "00000000-0000-4000-8000-0000000000e2"
ADMIN_ID = "00000000-0000-4000-8000-0000000000a1"
CORRETOR_ID = "00000000-0000-4000-8000-0000000000c1"
MEMBER_ID = "00000000-0000-4000-8000-0000000000b1"
CONNECTION_ID = "00000000-0000-4000-8000-0000000000e3"
WEBHOOK_TOKEN = "test-webhook-token-abc"
OPERATOR = "+5511999990000"
LEAD_PHONE = "5511988887777"
LEAD_CHAT = f"{LEAD_PHONE}@c.us"
ENCRYPTION_KEY = Fernet.generate_key().decode()
ATIVADO_EM = "2026-10-01T00:00:00+00:00"
MENSAGEM_INICIAL_MIGRACAO = "Oi! Eu sou {agente}, assistente virtual da {empresa}. 😊 Como tratamos seus dados: {link}"
THREAD_ID = "11111111-1111-4111-8111-111111111111"


class SchemaCachingClient:
    """`MockSupabaseClient.schema(...)` builds a FRESH wrapper (empty row cache) per
    call; cache one per schema so writes from one call are visible to the next."""

    def __init__(self, root: MockSupabaseClient) -> None:
        self._root = root
        self._scoped: dict[str, Any] = {}

    def schema(self, name: str):
        if name not in self._scoped:
            self._scoped[name] = self._root.schema(name)
        return self._scoped[name]

    def __getattr__(self, item):
        return getattr(self._root, item)


class InsertFailingClient:
    """A core client whose INSERTs into `tabela` raise -- a real fault in an injected
    collaborator, so a test exercises the caller's failure path without patching our
    own code. Every other table and operation goes to the wrapped client."""

    def __init__(self, root: Any, tabela: str, erro: str = "notifications down") -> None:
        self._root = root
        self._tabela = tabela
        self._erro = erro

    def table(self, name: str):
        query = self._root.table(name)
        if name != self._tabela:
            return query
        erro = self._erro

        class _Falha:
            def __init__(self, inner: Any) -> None:
                self._inner = inner

            def insert(self, *a: Any, **kw: Any):
                raise RuntimeError(erro)

            def __getattr__(self, item: str):
                return getattr(self._inner, item)

        return _Falha(query)

    def __getattr__(self, item):
        return getattr(self._root, item)


class World:
    """One mock DB + the process-level fakes, wired the way production wires them."""

    def __init__(self) -> None:
        self.root = MockSupabaseClient()
        self.admin = SchemaCachingClient(self.root)
        self.sw = self.admin.schema("social_wiring")
        self.core = self.root
        self.redis = fakeredis.FakeRedis(decode_responses=True)
        self.bus = FakeRealtimeBus()
        self.waha = FakeWahaClient(session="default")
        self.agents = FakeAgentsClient()
        self.buffer = ConversationBufferService(
            redis_client=make_fake_redis_client(), debounce_seconds=0, memory_ttl_seconds=3600
        )
        self.cfg = SocialWiringSettings(
            encryption_key=ENCRYPTION_KEY, redis_url="redis://fake:6379/0",
            whatsapp_paragraph_delay_seconds=0.0,
        )
        self.slept: list[float] = []
        self.core.set_table_data("organizations", [{"id": ORG_ID, "nome": "Empresa Exemplo"}])
        self.core.set_table_data("noctus_users", [
            {"id": OWNER_ID, "org_id": ORG_ID, "org_role": "owner"},
            {"id": ADMIN_ID, "org_id": ORG_ID, "org_role": "admin"},
            {"id": CORRETOR_ID, "org_id": ORG_ID, "org_role": "corretor"},
            {"id": MEMBER_ID, "org_id": ORG_ID, "org_role": "member"},
        ])
        self.core.set_table_data("notifications", [])
        # the org-membership seam of the handoff sweep reads THIS world's core (reset per test by the autouse fixture
        # in tests/conftest.py). The notification-recipient seam is NOT bound here on purpose: a sink left registered by
        # an earlier test would otherwise start fanning out in tests that call `notificar` directly.
        from app.modules.atendimento_blocos import handoffs as _handoffs

        _handoffs.registrar_core_provider(lambda: self.core)
        self.sw.set_table_data("conversation_messages", [])
        self.sw.set_table_data("whatsapp_chats", [])
        self.sw.set_table_data("contacts", [])
        self.sw.set_table_data("julia_agente_chats_preexistentes", [])
        self.sw.set_table_data("julia_aviso_privacidade", [])
        self.sw.set_table_data("whatsapp_connections", [])
        for t in ("julia_contatos", "julia_interacoes", "julia_acoes_aplicadas", "julia_eventos", "julia_solicitacoes_titular",
                  "julia_staff", "julia_protecao_config", "julia_numeros_bloqueados"):
            self.sw.set_table_data(t, [])
        # the platform default texts are DATA (migration julia_v2_espelhos): this is the migration's row, asserted equal to the SQL in
        # tests/services/test_julia_v2_espelhos_migration.py
        self.sw.set_table_data("julia_textos_padrao", [{"chave": "mensagem_inicial", "conteudo": MENSAGEM_INICIAL_MIGRACAO}])

    # ── seeding ────────────────────────────────────────────────────────────
    def seed_connection(self, **over: Any) -> dict[str, Any]:
        fernet = Fernet(ENCRYPTION_KEY.encode())
        row = {
            "id": CONNECTION_ID, "org_id": ORG_ID, "user_id": OWNER_ID, "label": "Linha da Julia",
            "base_url": "https://waha.example.com", "session_name": "default",
            "encrypted_api_key": fernet.encrypt(b"fake-waha-api-key").decode("ascii"),
            "webhook_url": None, "webhook_token": WEBHOOK_TOKEN, "auto_reply_enabled": False,
            "authorized_numbers": [OPERATOR], "bound_chats": [], "marca_id": None,
            "agente_leads_ativo": True, "agente_leads_key": "julia",
            "agente_leads_ativado_em": ATIVADO_EM, "agente_handoff_notificar_user_id": None,
            "created_at": "2026-08-01T00:00:00Z", "updated_at": "2026-08-01T00:00:00Z",
        }
        row.update(over)
        # `set_table_data` (not insert): the row carries `marca_id`, which the stores read
        # defensively but the migration-derived mock schema names differently.
        self._connections = [*getattr(self, "_connections", []), row]
        self.sw.set_table_data("whatsapp_connections", self._connections)
        return row

    def seed_chat(self, chat_id: str = LEAD_CHAT, **over: Any) -> dict[str, Any]:
        row = {
            "connection_id": CONNECTION_ID, "org_id": ORG_ID, "chat_id": chat_id, "title": "Ana",
            "last_message_at": "2026-10-14T10:00:00+00:00", "last_message_preview": "oi",
            "last_direction": "inbound", "unread_count": 0, "archived": False, "pinned": False,
            "created_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            "updated_at": "2026-10-14T10:00:00+00:00",
            "agente_pausado": False, "agente_conversation_id": None, "agente_thread_id": None, "agente_estado": None,
        }
        row.update(over)
        self.sw.table("whatsapp_chats").insert(row).execute()
        return row

    def chat_row(self, chat_id: str = LEAD_CHAT) -> dict[str, Any] | None:
        rows = self.sw.table("whatsapp_chats").select("*").eq("connection_id", CONNECTION_ID).eq("chat_id", chat_id).execute().data
        return rows[0] if rows else None

    def messages(self, chat_id: str = LEAD_CHAT) -> list[dict[str, Any]]:
        return self.sw.table("conversation_messages").select("*").eq("chat_id", chat_id).execute().data or []

    def rows(self, table: str, **eq: Any) -> list[dict[str, Any]]:
        q = self.sw.table(table).select("*")
        for k, v in eq.items():
            q = q.eq(k, v)
        return q.execute().data or []

    def contato(self, chat_id: str = LEAD_CHAT) -> dict[str, Any] | None:
        rows = self.rows("julia_contatos", connection_id=CONNECTION_ID, chat_id=chat_id)
        return rows[0] if rows else None

    def notifications(self) -> list[dict[str, Any]]:
        return self.core.table("notifications").select("*").execute().data or []

    def notificar_via_sink(self) -> None:
        """Bind the `julia_eventos -> in-app notification` sink and point its recipient lookup at THIS world's core
        (undone by the autouse fixture in tests/conftest.py). For tests asserting an alert's notification."""
        from app.services import julia_notificacoes_service as _notificacoes

        _notificacoes.registrar()
        _notificacoes.registrar_core_provider(lambda: self.core)

    def sent_texts(self) -> list[str]:
        return [m["text"] for m in self.waha.sent_messages]

    def bus_events(self, connection_id: str = CONNECTION_ID) -> list[tuple[str, dict]]:
        """`(event, payload)` pairs published on the connection's scope (the Fake bus's
        own stream)."""
        stream = self.bus._streams.get(whatsapp_scope(connection_id), [])
        return [(e.event, e.payload) for e in stream]

    # ── connection lookup (the DI seam the worker takes) ───────────────────
    def record(self, connection_id: UUID) -> WhatsAppConnectionRecord | None:
        from app.services.whatsapp_connection_store import build_whatsapp_connection_store

        store = build_whatsapp_connection_store(self.admin, encryption_key=ENCRYPTION_KEY)
        return store.get_by_id(connection_id, decrypt=True)

    def deps(self, **over: Any) -> LeadDeps:
        async def sleep(seconds: float) -> None:
            self.slept.append(seconds)

        args: dict[str, Any] = dict(
            buffer=self.buffer, admin=self.admin, cfg=self.cfg, scoped=self.sw, core_client=self.core,
            agents_client_factory=lambda org_id: self.agents,
            waha_factory=lambda **kw: self.waha,
            connection_lookup=self.record,
            chat_store_factory=lambda org_id: WhatsAppChatStore(admin_supabase=self.admin, org_id=org_id),
            message_store_factory=lambda org_id: MessageStore(admin_supabase=self.admin, org_id=org_id),
            redis=self.redis, bus=self.bus, sleep=sleep,
        )
        args.update(over)
        return LeadDeps(**args)


def buffer_lead(world: World, chat_id: str, texts: list[str], *, ids: list[str] | None = None, start: int = 1,
                midias: list[dict | None] | None = None) -> str:
    """Put inbound messages on the lead buffer key exactly as the webhook does."""
    from noctusai_lib.domain.chatbot import QueuedConversationMessage

    from app.services import julia_agente_service as julia

    key = julia.lead_key(CONNECTION_ID, chat_id)
    for i, text in enumerate(texts):
        world.buffer.buffer_inbound(QueuedConversationMessage(
            conversation_id=key, text=text, direction="inbound",
            provider_message_id=(ids[i] if ids else f"m{start + i}"),
            metadata={"push_name": "Ana", **({"midia": midias[i]} if midias and midias[i] else {})},
        ))
    return key
