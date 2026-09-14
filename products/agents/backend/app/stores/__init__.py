"""Data-layer stores for the ``agents`` product (contract §E.1/§E.2).

Each aggregate module (``agents``, ``personas``, ``conversations``,
``messages``, ``approvals``) ships the seed IO shape: a Protocol, a
deterministic in-memory Fake, a Postgres-backed Real (Supabase admin
client), and a ``get_<x>_store(settings)`` factory that picks between them.
See ``KB § PATTERNS/backend/seed-fake-real-adapter.md``.

Re-exported here for import-shortcut ergonomics — e.g.
``from app.stores import get_agent_store, AgentRecord``.
"""
from __future__ import annotations

from app.stores.agents import (
    AgentRecord,
    AgentStore,
    FakeAgentStore,
    SupabaseAgentStore,
    get_agent_store,
)
from app.stores.approvals import (
    ApprovalRecord,
    ApprovalStore,
    FakeApprovalStore,
    SupabaseApprovalStore,
    get_approval_store,
)
from app.stores.conversations import (
    ConversationRecord,
    ConversationStore,
    FakeConversationStore,
    SupabaseConversationStore,
    get_conversation_store,
)
from app.stores.errors import AlreadyDecided, Conflict, NotFound, StoreError, TurnInProgress
from app.stores.messages import (
    MessageRecord,
    MessageStore,
    FakeMessageStore,
    SupabaseMessageStore,
    get_message_store,
)
from app.stores.personas import (
    PersonaInput,
    PersonaRecord,
    PersonaStore,
    FakePersonaStore,
    SupabasePersonaStore,
    get_persona_store,
)

__all__ = [
    # errors
    "StoreError",
    "NotFound",
    "Conflict",
    "AlreadyDecided",
    "TurnInProgress",
    # agents
    "AgentRecord",
    "AgentStore",
    "FakeAgentStore",
    "SupabaseAgentStore",
    "get_agent_store",
    # personas
    "PersonaInput",
    "PersonaRecord",
    "PersonaStore",
    "FakePersonaStore",
    "SupabasePersonaStore",
    "get_persona_store",
    # conversations
    "ConversationRecord",
    "ConversationStore",
    "FakeConversationStore",
    "SupabaseConversationStore",
    "get_conversation_store",
    # messages
    "MessageRecord",
    "MessageStore",
    "FakeMessageStore",
    "SupabaseMessageStore",
    "get_message_store",
    # approvals
    "ApprovalRecord",
    "ApprovalStore",
    "FakeApprovalStore",
    "SupabaseApprovalStore",
    "get_approval_store",
]
