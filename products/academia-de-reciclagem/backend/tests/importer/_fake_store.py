"""Minimal in-memory ``KnowledgeStore`` stand-in for A2 (importer) tests
ONLY.

``app/knowledge/`` (A1, the real ``KnowledgeStore`` + ``FakeKnowledgeStore``
+ ``Provenance``, contract §A.11) does not exist on this branch — A1
builds it in parallel off the same contract. This fake implements ONLY
the three methods ``app/importer/run.py`` actually calls:
``transaction()``, ``import_entity()``, and ``seed_counters()``. It is
NOT a full Protocol implementation (no ``search_kb``, ``get_kb``,
``create_decision``, ...) — it exists solely so A2's tests can exercise
``run_import`` without A1's code.

Behaviour mirrors §A.11's stated contract for the methods it covers:
  - ``import_entity`` upserts by ``(entity_type, natural_key)`` and is
    idempotent on ``(git_sha, natural_key)`` — a duplicate write is a
    no-op that returns the existing row.
  - ``transaction()`` is an async context manager; an exception raised
    inside it rolls back every entity/counter/revision write made
    inside that transaction.

**INTEGRATION NOTE — read this before wiring A2 into the real app.**
Swap this file for A1's real ``FakeKnowledgeStore``
(``app/knowledge/store.py``) once it lands, and delete this file. The
call shape (`import_entity(org_id, entity_type, natural_key, snapshot,
prov)` / `seed_counters(org_id, counters)` / `async with
store.transaction():`) is designed to match §A.11 exactly, so
``run_import`` itself needs no change at swap time — only the store
fixture used in these tests does.
"""
from __future__ import annotations

import contextlib
import copy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeKnowledgeStore:
    entities: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    revisions: list[dict[str, Any]] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)
    _seen_git_natural_keys: set[tuple[str | None, str]] = field(default_factory=set)

    @contextlib.asynccontextmanager
    async def transaction(self):
        snapshot = (
            copy.deepcopy(self.entities),
            copy.deepcopy(self.revisions),
            copy.deepcopy(self.counters),
            set(self._seen_git_natural_keys),
        )
        try:
            yield self
        except Exception:
            self.entities, self.revisions, self.counters, self._seen_git_natural_keys = snapshot
            raise

    async def import_entity(
        self,
        org_id: Any,
        entity_type: str,
        natural_key: str,
        snapshot: dict[str, Any],
        prov: Any,
    ) -> dict[str, Any]:
        dedup_key = (prov.git_sha, natural_key)
        if dedup_key in self._seen_git_natural_keys:
            return self.entities[(entity_type, natural_key)]

        self._seen_git_natural_keys.add(dedup_key)
        row = dict(snapshot)
        self.entities[(entity_type, natural_key)] = row
        self.revisions.append(
            {
                "entity_type": entity_type,
                "natural_key": natural_key,
                "op": "import",
                "snapshot": row,
                "author_kind": prov.author_kind,
                "user_id": prov.user_id,
                "git_sha": prov.git_sha,
                "git_author_raw": prov.git_author_raw,
                "git_committed_at": prov.git_committed_at,
                "git_message": prov.git_message,
            }
        )
        return row

    async def seed_counters(self, org_id: Any, counters: dict[str, int]) -> None:
        for prefix, value in counters.items():
            self.counters[prefix] = max(self.counters.get(prefix, 0), value)
