"""`FakeKnowledgeStore` — in-memory `KnowledgeStore`, same invariants as Pg.

Every write appends exactly one `kb_revisions` row (a supersede writes
two). `approval_consumptions` is single-use, checked BEFORE any write.
`transaction()` snapshots on entry and rolls back the ENTIRE in-memory
state on an exception raised inside the `async with` block — the Fake's
answer to "a single import transaction is opened by the caller" (contract
§A.11 "Transactions").

Single-threaded, no locking: this is a test double, not a concurrency
model. `PgKnowledgeStore` gets its atomicity from Postgres functions
(see `pg.py`'s module docstring); this class gets it from running
entirely inside one Python call with no `await` between the read-check
and the mutation.
"""
from __future__ import annotations

import contextlib
import copy
from dataclasses import asdict
from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from app.knowledge.errors import AssertionUsed, Conflict, Invalid, NotFound
from app.knowledge.store import Provenance

_ENTITY_TABLES = (
    "kb_entries",
    "decisions",
    "open_questions",
    "roadmap_phases",
    "tasks",
    "content_drafts",
    "timeline_events",
    "research_sources",
)

# entity_type (kb_revisions CHECK value) -> backing table attr name.
_ENTITY_TYPE_TABLE = {
    "kb_entry": "kb_entries",
    "decision": "decisions",
    "open_question": "open_questions",
    "roadmap_phase": "roadmap_phases",
    "task": "tasks",
    "content_draft": "content_drafts",
    "timeline_event": "timeline_events",
    "research_source": "research_sources",
}

_PHASE_TASK_ESTADOS = ("pendente", "em-andamento", "concluida", "cancelada")


def _now() -> datetime:
    return datetime.now(timezone.utc)


#: DATE columns an import snapshot carries as ISO strings. Postgres casts
#: them (`(p_snapshot->>'data')::date`); the fake must too, or its
#: natural-key lookup (`data=date(...)`) never matches a stored string and
#: every re-import of the same timeline section becomes a NEW row.
_IMPORT_DATE_COLUMNS: dict[str, tuple[str, ...]] = {
    "timeline_event": ("data",),
    "decision": ("data",),
}

#: NOT NULL columns without a default, per imported entity (migration 006) —
#: what the real `import_bundle` RPC would refuse. `id`/`org_id`/timestamps
#: and the natural-key column the fake sets itself are covered elsewhere.
_IMPORT_REQUIRED: dict[str, tuple[str, ...]] = {
    "kb_entry": ("titulo", "categoria", "corpo_md"),
    "decision": ("data", "titulo", "decisao", "motivo"),
    "open_question": ("pergunta", "por_que_importa", "bloqueia"),
    # `ordem` is COALESCEd to 0 by the RPC — not a refusal.
    "roadmap_phase": ("titulo", "objetivo", "concluida_quando"),
    "task": ("titulo", "fase"),
    "content_draft": ("tipo", "titulo", "corpo_md"),
    "timeline_event": ("data", "titulo", "descricao"),
    "research_source": ("titulo", "resumo", "trecho_citado", "accessed_at"),
}


class FakeKnowledgeStore:
    """In-memory `KnowledgeStore`. See module docstring for the invariants."""

    def __init__(self) -> None:
        self.kb_entries: list[dict] = []
        self.decisions: list[dict] = []
        self.open_questions: list[dict] = []
        self.roadmap_phases: list[dict] = []
        self.tasks: list[dict] = []
        self.content_drafts: list[dict] = []
        self.timeline_events: list[dict] = []
        self.research_sources: list[dict] = []
        self.code_counters: dict[tuple, int] = {}
        self.kb_revisions: list[dict] = []
        self.approval_consumptions: dict[UUID, dict] = {}

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _table(self, name: str) -> list[dict]:
        return getattr(self, name)

    def _consume_approval(self, org_id, approval_id: UUID | None) -> None:
        """Single-use guard, called ONCE per store-level write call.

        A no-op when `approval_id` is None (human/SSO writes and
        `human_personal` product-token writes need no assertion — §B.0).
        """
        if approval_id is None:
            return
        if approval_id in self.approval_consumptions:
            raise AssertionUsed(f"approval {approval_id} already consumed")
        self.approval_consumptions[approval_id] = {"org_id": org_id, "consumed_at": _now()}

    def _next_rev_no(self, entity_type: str, entity_id) -> int:
        existing = [
            r["rev_no"] for r in self.kb_revisions
            if r["entity_type"] == entity_type and r["entity_id"] == entity_id
        ]
        return (max(existing) if existing else 0) + 1

    def _append_revision(
        self,
        org_id,
        entity_type: str,
        entity_id,
        op: str,
        snapshot: dict,
        prov: Provenance,
    ) -> dict:
        rev = {
            "id": uuid4(),
            "org_id": org_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "rev_no": self._next_rev_no(entity_type, entity_id),
            "op": op,
            "snapshot": copy.deepcopy(snapshot),
            "author_kind": prov.author_kind,
            "user_id": prov.user_id,
            "agent_id": prov.agent_id,
            "approval_id": prov.approval_id,
            "channel": prov.channel,
            "conversation_id": prov.conversation_id,
            "motivo": prov.motivo,
            "git_sha": prov.git_sha,
            "git_author_raw": prov.git_author_raw,
            "git_committed_at": prov.git_committed_at,
            "git_message": prov.git_message,
            "created_at": _now(),
        }
        self.kb_revisions.append(rev)
        return rev

    def _allocate_code(self, org_id, prefix: str, width: int) -> str:
        key = (org_id, prefix)
        nxt = self.code_counters.get(key, 0) + 1
        self.code_counters[key] = nxt
        return f"{prefix}-{nxt:0{width}d}"

    def _find(self, table: str, org_id, **kwargs) -> dict | None:
        for row in self._table(table):
            if row["org_id"] != org_id:
                continue
            if all(row.get(k) == v for k, v in kwargs.items()):
                return row
        return None

    def _require(self, table: str, org_id, label: str, **kwargs) -> dict:
        row = self._find(table, org_id, **kwargs)
        if row is None:
            raise NotFound(f"{label} not found: {kwargs}")
        return row

    # ------------------------------------------------------------------
    # kb entries
    # ------------------------------------------------------------------

    async def search_kb(self, org_id, *, consulta, categoria, subcategoria, tag, limite, offset):
        rows = [r for r in self.kb_entries if r["org_id"] == org_id]
        if categoria is not None:
            rows = [r for r in rows if r["categoria"] == categoria]
        if subcategoria is not None:
            rows = [r for r in rows if r["subcategoria"] == subcategoria]
        if tag is not None:
            rows = [r for r in rows if tag in (r.get("tags") or [])]
        if consulta is not None:
            needle = consulta.lower()
            rows = [
                r for r in rows
                if needle in (r.get("titulo") or "").lower()
                or needle in (r.get("resumo") or "").lower()
                or needle in (r.get("corpo_md") or "").lower()
            ]
        rows = sorted(rows, key=lambda r: r["slug"])
        total = len(rows)
        return [copy.deepcopy(r) for r in rows[offset:offset + limite]], total

    async def get_kb(self, org_id, slug: str) -> dict:
        row = self._require("kb_entries", org_id, "kb_entry", slug=slug)
        return copy.deepcopy(row)

    async def create_kb(self, org_id, data: dict, prov: Provenance) -> dict:
        slug = data["slug"]
        if self._find("kb_entries", org_id, slug=slug) is not None:
            raise Conflict(f"kb_entry slug already exists: {slug}")

        self._consume_approval(org_id, prov.approval_id)

        row = {
            "id": uuid4(),
            "org_id": org_id,
            "slug": slug,
            "categoria": data["categoria"],
            "subcategoria": data.get("subcategoria"),
            "titulo": data["titulo"],
            "resumo": data.get("resumo"),
            "tags": list(data.get("tags") or []),
            "corpo_md": data["corpo_md"],
            "frontmatter": dict(data.get("frontmatter") or {}),
            "current_revision_id": None,
            "arquivado": False,
            "created_at": _now(),
            "updated_at": _now(),
        }
        self.kb_entries.append(row)

        rev = self._append_revision(org_id, "kb_entry", row["id"], "create", row, prov)
        row["current_revision_id"] = rev["id"]
        return copy.deepcopy(row)

    async def update_kb(self, org_id, slug: str, changes: dict, prov: Provenance) -> dict:
        row = self._require("kb_entries", org_id, "kb_entry", slug=slug)

        novo_slug = changes.get("novo_slug")
        if novo_slug and novo_slug != slug:
            other = self._find("kb_entries", org_id, slug=novo_slug)
            if other is not None and other["id"] != row["id"]:
                raise Conflict(f"kb_entry slug already exists: {novo_slug}")

        self._consume_approval(org_id, prov.approval_id)

        if novo_slug:
            row["slug"] = novo_slug
        for field in ("titulo", "resumo", "tags", "corpo_md", "categoria", "subcategoria"):
            if field in changes:
                row[field] = changes[field]
        row["updated_at"] = _now()

        rev = self._append_revision(org_id, "kb_entry", row["id"], "update", row, prov)
        row["current_revision_id"] = rev["id"]
        return copy.deepcopy(row)

    async def archive_kb(self, org_id, slug: str, prov: Provenance) -> dict:
        row = self._require("kb_entries", org_id, "kb_entry", slug=slug)
        self._consume_approval(org_id, prov.approval_id)

        row["arquivado"] = True
        row["updated_at"] = _now()

        rev = self._append_revision(org_id, "kb_entry", row["id"], "archive", row, prov)
        row["current_revision_id"] = rev["id"]
        return copy.deepcopy(row)

    async def list_revisions(self, org_id, entity_type: str, entity_id) -> list[dict]:
        rows = [
            r for r in self.kb_revisions
            if r["org_id"] == org_id and r["entity_type"] == entity_type and r["entity_id"] == entity_id
        ]
        rows = sorted(rows, key=lambda r: r["rev_no"], reverse=True)
        return [copy.deepcopy(r) for r in rows]

    # ------------------------------------------------------------------
    # decisions
    # ------------------------------------------------------------------

    async def list_decisions(self, org_id, *, estado):
        rows = [r for r in self.decisions if r["org_id"] == org_id]
        if estado is not None:
            rows = [r for r in rows if r["estado"] == estado]
        rows = sorted(rows, key=lambda r: r["codigo"])
        return [copy.deepcopy(r) for r in rows]

    async def get_decision(self, org_id, codigo: str) -> dict:
        row = self._require("decisions", org_id, "decision", codigo=codigo)
        return copy.deepcopy(row)

    async def create_decision(self, org_id, data: dict, prov: Provenance) -> dict:
        self._consume_approval(org_id, prov.approval_id)

        codigo = self._allocate_code(org_id, "D", 2)
        row = {
            "id": uuid4(),
            "org_id": org_id,
            "codigo": codigo,
            "titulo": data["titulo"],
            "contexto": data.get("contexto"),
            "decisao": data["decisao"],
            "motivo": data["motivo"],
            "alternativas_rejeitadas": data.get("alternativas_rejeitadas"),
            "data": date.today(),
            "estado": "vigente",
            "substitui": None,
            "superseded_by": None,
            "relacionadas": list(data.get("relacionadas") or []),
            "created_at": _now(),
            "updated_at": _now(),
        }
        self.decisions.append(row)
        self._append_revision(org_id, "decision", row["id"], "create", row, prov)
        return copy.deepcopy(row)

    async def supersede_decision(self, org_id, codigo: str, data: dict, prov: Provenance) -> tuple[dict, dict]:
        old = self._require("decisions", org_id, "decision", codigo=codigo)
        if old["estado"] == "superseded":
            raise Conflict(f"decision already superseded: {codigo}")

        self._consume_approval(org_id, prov.approval_id)

        new_codigo = self._allocate_code(org_id, "D", 2)
        nova = {
            "id": uuid4(),
            "org_id": org_id,
            "codigo": new_codigo,
            "titulo": data["titulo"],
            "contexto": data.get("contexto"),
            "decisao": data["decisao"],
            "motivo": data["motivo"],
            "alternativas_rejeitadas": data.get("alternativas_rejeitadas"),
            "data": date.today(),
            "estado": "vigente",
            "substitui": codigo,
            "superseded_by": None,
            "relacionadas": list(data.get("relacionadas") or []),
            "created_at": _now(),
            "updated_at": _now(),
        }
        self.decisions.append(nova)

        old["estado"] = "superseded"
        old["superseded_by"] = new_codigo
        old["updated_at"] = _now()

        # Two revisions, one op ('supersede'), one already-consumed approval.
        self._append_revision(org_id, "decision", nova["id"], "supersede", nova, prov)
        self._append_revision(org_id, "decision", old["id"], "supersede", old, prov)

        return copy.deepcopy(nova), copy.deepcopy(old)

    # ------------------------------------------------------------------
    # open questions
    # ------------------------------------------------------------------

    async def list_questions(self, org_id, *, estado: Literal["aberta", "respondida", "todas"]):
        rows = [r for r in self.open_questions if r["org_id"] == org_id]
        if estado != "todas":
            rows = [r for r in rows if r["estado"] == estado]
        rows = sorted(rows, key=lambda r: r["codigo"])
        return [copy.deepcopy(r) for r in rows]

    async def create_question(self, org_id, data: dict, prov: Provenance) -> dict:
        self._consume_approval(org_id, prov.approval_id)

        codigo = self._allocate_code(org_id, "Q", 2)
        row = {
            "id": uuid4(),
            "org_id": org_id,
            "codigo": codigo,
            "pergunta": data["pergunta"],
            "por_que_importa": data["por_que_importa"],
            "bloqueia": data["bloqueia"],
            "destino_kb": data.get("destino_kb"),
            "estado": "aberta",
            "resposta": None,
            "respondida_em": None,
            "created_at": _now(),
            "updated_at": _now(),
        }
        self.open_questions.append(row)
        self._append_revision(org_id, "open_question", row["id"], "create", row, prov)
        return copy.deepcopy(row)

    async def answer_question(self, org_id, codigo: str, resposta: str, prov: Provenance) -> dict:
        row = self._require("open_questions", org_id, "open_question", codigo=codigo)
        if row["estado"] == "respondida":
            raise Conflict(f"open_question already answered: {codigo}")

        self._consume_approval(org_id, prov.approval_id)

        row["resposta"] = resposta
        row["estado"] = "respondida"
        row["respondida_em"] = _now()
        row["updated_at"] = _now()

        self._append_revision(org_id, "open_question", row["id"], "update", row, prov)
        return copy.deepcopy(row)

    # ------------------------------------------------------------------
    # roadmap + tasks
    # ------------------------------------------------------------------

    async def list_phases(self, org_id):
        rows = [r for r in self.roadmap_phases if r["org_id"] == org_id]
        rows = sorted(rows, key=lambda r: r["ordem"])
        return [copy.deepcopy(r) for r in rows]

    async def update_phase(self, org_id, codigo: str, changes: dict, prov: Provenance) -> dict:
        row = self._require("roadmap_phases", org_id, "roadmap_phase", codigo=codigo)
        self._consume_approval(org_id, prov.approval_id)

        for field in ("estado", "titulo", "objetivo", "concluida_quando"):
            if field in changes:
                row[field] = changes[field]
        row["updated_at"] = _now()

        self._append_revision(org_id, "roadmap_phase", row["id"], "update", row, prov)
        return copy.deepcopy(row)

    async def list_tasks(self, org_id, *, fase, estado):
        rows = [r for r in self.tasks if r["org_id"] == org_id]
        if fase is not None:
            rows = [r for r in rows if r["fase"] == fase]
        if estado is not None:
            rows = [r for r in rows if r["estado"] == estado]
        rows = sorted(rows, key=lambda r: r["codigo"])
        return [copy.deepcopy(r) for r in rows]

    async def create_task(self, org_id, data: dict, prov: Provenance) -> dict:
        fase = data["fase"]
        if self._find("roadmap_phases", org_id, codigo=fase) is None:
            raise Invalid(f"unknown fase: {fase}")

        self._consume_approval(org_id, prov.approval_id)

        codigo = self._allocate_code(org_id, "T", 3)
        row = {
            "id": uuid4(),
            "org_id": org_id,
            "codigo": codigo,
            "titulo": data["titulo"],
            "fase": fase,
            "detalhe": data.get("detalhe"),
            "estado": "pendente",
            "bloqueada_por": data.get("bloqueada_por"),
            "created_at": _now(),
            "updated_at": _now(),
        }
        self.tasks.append(row)
        self._append_revision(org_id, "task", row["id"], "create", row, prov)
        return copy.deepcopy(row)

    async def update_task(self, org_id, codigo: str, changes: dict, prov: Provenance) -> dict:
        row = self._require("tasks", org_id, "task", codigo=codigo)
        self._consume_approval(org_id, prov.approval_id)

        for field in ("estado", "detalhe", "bloqueada_por"):
            if field in changes:
                row[field] = changes[field]
        row["updated_at"] = _now()

        self._append_revision(org_id, "task", row["id"], "update", row, prov)
        return copy.deepcopy(row)

    async def session_prep(self, org_id) -> dict:
        phases = [r for r in self.roadmap_phases if r["org_id"] == org_id]
        fase_atual = next(
            (copy.deepcopy(p) for p in sorted(phases, key=lambda r: r["ordem"]) if p["estado"] == "em-andamento"),
            None,
        )

        tasks = [r for r in self.tasks if r["org_id"] == org_id]
        proximas = sorted(
            (t for t in tasks if t["estado"] == "pendente" and not t.get("bloqueada_por")),
            key=lambda r: r["codigo"],
        )
        bloqueadas = sorted(
            (t for t in tasks if t.get("bloqueada_por") and t["estado"] in ("pendente", "em-andamento")),
            key=lambda r: r["codigo"],
        )

        questions = [r for r in self.open_questions if r["org_id"] == org_id]
        abertas = [q for q in questions if q["estado"] == "aberta"]
        bloqueantes = sorted(
            (q for q in abertas if q.get("bloqueia")),
            key=lambda r: r["codigo"],
        )

        return {
            "fase_atual": fase_atual,
            "proximas": [copy.deepcopy(t) for t in proximas],
            "bloqueadas": [copy.deepcopy(t) for t in bloqueadas],
            "perguntas_abertas": len(abertas),
            "perguntas_bloqueantes": [copy.deepcopy(q) for q in bloqueantes],
        }

    # ------------------------------------------------------------------
    # content / timeline / sources
    # ------------------------------------------------------------------

    async def list_content(self, org_id, *, tipo):
        rows = [r for r in self.content_drafts if r["org_id"] == org_id]
        if tipo is not None:
            rows = [r for r in rows if r["tipo"] == tipo]
        rows = sorted(rows, key=lambda r: r["codigo"])
        return [copy.deepcopy(r) for r in rows]

    async def get_content(self, org_id, codigo: str) -> dict:
        row = self._require("content_drafts", org_id, "content_draft", codigo=codigo)
        return copy.deepcopy(row)

    async def create_content(self, org_id, data: dict, prov: Provenance) -> dict:
        self._consume_approval(org_id, prov.approval_id)

        codigo = self._allocate_code(org_id, "C", 3)
        row = {
            "id": uuid4(),
            "org_id": org_id,
            "codigo": codigo,
            "tipo": data["tipo"],
            "titulo": data["titulo"],
            "corpo_md": data["corpo_md"],
            "referencia": data.get("referencia"),
            "fontes": list(data.get("fontes") or []),
            "created_at": _now(),
            "updated_at": _now(),
        }
        self.content_drafts.append(row)
        self._append_revision(org_id, "content_draft", row["id"], "create", row, prov)
        return copy.deepcopy(row)

    async def list_timeline(self, org_id, *, limite):
        rows = [r for r in self.timeline_events if r["org_id"] == org_id]
        rows = sorted(rows, key=lambda r: (r["data"], r["created_at"]), reverse=True)
        return [copy.deepcopy(r) for r in rows[:limite]]

    async def create_timeline_event(self, org_id, data: dict, prov: Provenance) -> dict:
        self._consume_approval(org_id, prov.approval_id)

        row = {
            "id": uuid4(),
            "org_id": org_id,
            "data": data.get("data") or date.today(),
            "titulo": data["titulo"],
            "descricao": data["descricao"],
            "created_at": _now(),
            "updated_at": _now(),
        }
        self.timeline_events.append(row)
        self._append_revision(org_id, "timeline_event", row["id"], "create", row, prov)
        return copy.deepcopy(row)

    async def create_source(self, org_id, data: dict, prov: Provenance) -> dict:
        kb_slug = data["kb_slug"]
        if self._find("kb_entries", org_id, slug=kb_slug) is None:
            raise NotFound(f"kb_slug not found: {kb_slug}")

        self._consume_approval(org_id, prov.approval_id)

        row = {
            "id": uuid4(),
            "org_id": org_id,
            "url": data["url"],
            "titulo": data["titulo"],
            "trecho_citado": data["trecho_citado"],
            "resumo": data["resumo"],
            "kb_slug": kb_slug,
            "vigencia_confirmada": bool(data.get("vigencia_confirmada", False)),
            "exige_da_empresa": data.get("exige_da_empresa"),
            "accessed_at": _now(),
            "created_at": _now(),
            "updated_at": _now(),
        }
        self.research_sources.append(row)
        self._append_revision(org_id, "research_source", row["id"], "create", row, prov)
        return copy.deepcopy(row)

    # ------------------------------------------------------------------
    # import (A2)
    # ------------------------------------------------------------------

    def _lookup_by_natural_key(self, org_id, entity_type: str, natural_key: str) -> dict | None:
        table = _ENTITY_TYPE_TABLE[entity_type]
        if entity_type == "kb_entry":
            return self._find(table, org_id, slug=natural_key)
        if entity_type in ("decision", "open_question", "task", "content_draft", "roadmap_phase"):
            return self._find(table, org_id, codigo=natural_key)
        if entity_type == "timeline_event":
            data_str, _, titulo = natural_key.partition("|")
            return self._find(table, org_id, data=date.fromisoformat(data_str), titulo=titulo)
        if entity_type == "research_source":
            url, _, kb_slug = natural_key.partition("|")
            return self._find(table, org_id, url=url, kb_slug=kb_slug)
        raise Invalid(f"import_entity: unknown entity_type {entity_type}")

    async def import_entity(self, org_id, entity_type: str, natural_key: str, snapshot: dict, prov: Provenance) -> dict:
        """(see `KnowledgeStore.import_entity`)

        🔴 Refuses what Postgres refuses: a NEW row missing a NOT NULL column
        (migration 006, `_IMPORT_REQUIRED`). Without this the fake accepted an
        untitled timeline section that the real `import_bundle` RPC rejected
        (23502) on the first prod import, 2026-09-17."""
        if entity_type not in _ENTITY_TYPE_TABLE:
            raise Invalid(f"import_entity: unknown entity_type {entity_type}")

        snapshot = dict(snapshot)
        for coluna in _IMPORT_DATE_COLUMNS.get(entity_type, ()):
            if isinstance(snapshot.get(coluna), str):
                snapshot[coluna] = date.fromisoformat(snapshot[coluna])

        existing = self._lookup_by_natural_key(org_id, entity_type, natural_key)

        if existing is not None and prov.git_sha is not None:
            already = any(
                r["entity_type"] == entity_type and r["entity_id"] == existing["id"]
                and r["op"] == "import" and r["git_sha"] == prov.git_sha
                for r in self.kb_revisions
            )
            if already:
                return copy.deepcopy(existing)

        self._consume_approval(org_id, prov.approval_id)

        table = _ENTITY_TYPE_TABLE[entity_type]
        now = _now()

        if existing is None:
            row = {"id": uuid4(), "org_id": org_id, "created_at": now, "updated_at": now, **copy.deepcopy(snapshot)}
            # The natural key always wins over whatever the snapshot carries
            # (a bundle line's own path/codigo is the source of truth).
            if entity_type == "kb_entry":
                row["slug"] = natural_key
                row.setdefault("current_revision_id", None)
                row.setdefault("arquivado", False)
                row.setdefault("tags", [])
                row.setdefault("frontmatter", {})
            elif entity_type in ("decision", "open_question", "task", "content_draft", "roadmap_phase"):
                row["codigo"] = natural_key
                if entity_type == "decision":
                    row.setdefault("estado", "vigente")
                    row.setdefault("substitui", None)
                    row.setdefault("superseded_by", None)
                    row.setdefault("relacionadas", [])
                elif entity_type == "open_question":
                    row.setdefault("estado", "aberta")
                    row.setdefault("resposta", None)
                    row.setdefault("respondida_em", None)
                elif entity_type == "task":
                    row.setdefault("estado", "pendente")
                elif entity_type == "roadmap_phase":
                    row.setdefault("estado", "pendente")
            # NULL only — Postgres NOT NULL accepts an empty string.
            faltando = [c for c in _IMPORT_REQUIRED.get(entity_type, ()) if row.get(c) is None]
            if faltando:
                raise Invalid(
                    f"import_entity: {entity_type} {natural_key!r} missing NOT NULL column(s) {faltando}"
                )
            self._table(table).append(row)
        else:
            row = existing
            # Import replays git history verbatim, including a decision's
            # own historical edits — this bypasses the append-only trigger
            # analog deliberately (the importer is the one authorized path
            # that overwrites decisions.* directly).
            for key, value in snapshot.items():
                row[key] = value
            row["updated_at"] = now

        rev = self._append_revision(org_id, entity_type, row["id"], "import", row, prov)
        if entity_type == "kb_entry":
            row["current_revision_id"] = rev["id"]

        return copy.deepcopy(row)

    async def seed_counters(self, org_id, counters: dict[str, int]) -> None:
        for prefix, value in counters.items():
            key = (org_id, prefix)
            self.code_counters[key] = max(self.code_counters.get(key, 0), value)

    # ------------------------------------------------------------------
    # transaction — NOT part of the Protocol (see module + store.py docstrings)
    # ------------------------------------------------------------------

    def _snapshot_state(self) -> dict:
        return {
            name: copy.deepcopy(getattr(self, name))
            for name in (*_ENTITY_TABLES, "code_counters", "kb_revisions", "approval_consumptions")
        }

    def _restore_state(self, snapshot: dict) -> None:
        for name, value in snapshot.items():
            setattr(self, name, value)

    @contextlib.asynccontextmanager
    async def transaction(self):
        """All-or-nothing block for `import_entity`/`seed_counters` batches.

        Mirrors the real all-or-nothing requirement (contract §B.6) without
        a real DB transaction: snapshot the whole in-memory state on enter,
        and if the body raises, restore it — a true rollback, since nothing
        outside this object observed the intermediate state anyway.
        """
        snapshot = self._snapshot_state()
        try:
            yield self
        except Exception:
            self._restore_state(snapshot)
            raise


def asdict_provenance(prov: Provenance) -> dict:
    """`Provenance` -> plain dict, for callers that serialize it (e.g. `PgKnowledgeStore`'s jsonb payloads)."""
    return asdict(prov)
