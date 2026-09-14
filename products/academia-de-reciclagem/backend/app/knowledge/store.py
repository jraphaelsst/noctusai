"""The `KnowledgeStore` seam — contract §A.11.

This Protocol is the shared contract between A1 (implements: `FakeKnowledgeStore`
here, `PgKnowledgeStore` in `pg.py`) and A2/B-routes (consume). Its method
names and parameter names are pinned CHARACTER-FOR-CHARACTER against
`projects/julia-agents-academia-CONTRACT.md` §A.11 — A2 is building the
importer against this exact signature in parallel, so ANY deviation here
breaks their slice silently (a renamed kwarg is a `TypeError` at their call
site, not a merge conflict). `tests/knowledge/test_store_conformance.py`
asserts this via `inspect.signature` — don't hand-edit a signature without
re-running that test.

`transaction()` (used by `import_entity`/`seed_counters` batching, see the
`pg.py` module docstring for why) is deliberately NOT part of this Protocol
— it is an implementation-side convenience both concrete stores happen to
expose, not a contract member A2 depends on structurally.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID


@dataclass(frozen=True)
class Provenance:
    """Audit + authorization context carried on every write.

    `motivo` here is the AUDIT annotation ("why this store call happened"),
    landing in `kb_revisions.motivo` — distinct from a domain field like
    `decisions.motivo` (the decision's own rationale), which travels inside
    a write method's `data`/`changes` dict instead. The two can legitimately
    differ and are never conflated at the store boundary.
    """

    author_kind: Literal["human", "agent", "import"]
    user_id: UUID | None = None
    agent_id: UUID | None = None
    approval_id: UUID | None = None
    channel: str | None = None
    conversation_id: UUID | None = None
    motivo: str | None = None
    git_sha: str | None = None
    git_author_raw: str | None = None
    git_committed_at: datetime | None = None
    git_message: str | None = None


class KnowledgeStore(Protocol):
    """The seam every academia-de-reciclagem knowledge write/read goes through.

    Every method takes `org_id` first. Every write takes a trailing
    `prov: Provenance`. Every method is `async`.
    """

    # kb entries
    async def search_kb(self, org_id, *, consulta: str | None, categoria: str | None,
                        subcategoria: str | None, tag: str | None, limite: int, offset: int) -> tuple[list[dict], int]: ...

    async def get_kb(self, org_id, slug: str) -> dict: ...  # raises NotFound

    async def create_kb(self, org_id, data: dict, prov: Provenance) -> dict: ...  # raises Conflict

    async def update_kb(self, org_id, slug: str, changes: dict, prov: Provenance) -> dict: ...  # novo_slug inside changes; raises NotFound/Conflict

    async def archive_kb(self, org_id, slug: str, prov: Provenance) -> dict: ...

    async def list_revisions(self, org_id, entity_type: str, entity_id: UUID) -> list[dict]: ...

    # decisions
    async def list_decisions(self, org_id, *, estado: str | None) -> list[dict]: ...

    async def get_decision(self, org_id, codigo: str) -> dict: ...

    async def create_decision(self, org_id, data: dict, prov: Provenance) -> dict: ...

    async def supersede_decision(self, org_id, codigo: str, data: dict, prov: Provenance) -> tuple[dict, dict]: ...  # (nova, substituida); raises Conflict if already superseded

    # open questions
    async def list_questions(self, org_id, *, estado: Literal["aberta", "respondida", "todas"]) -> list[dict]: ...

    async def create_question(self, org_id, data: dict, prov: Provenance) -> dict: ...

    async def answer_question(self, org_id, codigo: str, resposta: str, prov: Provenance) -> dict: ...  # raises Conflict if answered

    # roadmap + tasks
    async def list_phases(self, org_id) -> list[dict]: ...

    async def update_phase(self, org_id, codigo: str, changes: dict, prov: Provenance) -> dict: ...

    async def list_tasks(self, org_id, *, fase: str | None, estado: str | None) -> list[dict]: ...

    async def create_task(self, org_id, data: dict, prov: Provenance) -> dict: ...  # raises Invalid if fase unknown

    async def update_task(self, org_id, codigo: str, changes: dict, prov: Provenance) -> dict: ...

    async def session_prep(self, org_id) -> dict: ...

    # content / timeline / sources
    async def list_content(self, org_id, *, tipo: str | None) -> list[dict]: ...

    async def get_content(self, org_id, codigo: str) -> dict: ...

    async def create_content(self, org_id, data: dict, prov: Provenance) -> dict: ...

    async def list_timeline(self, org_id, *, limite: int) -> list[dict]: ...

    async def create_timeline_event(self, org_id, data: dict, prov: Provenance) -> dict: ...

    async def create_source(self, org_id, data: dict, prov: Provenance) -> dict: ...  # raises NotFound if kb_slug unknown

    # import (A2)
    async def import_entity(self, org_id, entity_type: str, natural_key: str, snapshot: dict,
                            prov: Provenance) -> dict: ...  # upsert-by-natural-key + one 'import' revision; idempotent on (git_sha, natural_key)

    async def seed_counters(self, org_id, counters: dict[str, int]) -> None: ...  # sets code_counters to max(current, given)
