"""`PgKnowledgeStore` — the real `KnowledgeStore` over Supabase/PostgREST.

WHY THE WRITE PATHS ARE `.rpc()` CALLS, NOT `.table().insert()`
-----------------------------------------------------------------
Every product backend on this platform talks to Postgres exclusively
through PostgREST (`noctusai_seed.database.DatabaseModule` — there is no
asyncpg/psycopg anywhere in this codebase). Each `.table(...).execute()`
call is its OWN Postgres transaction; there is no client-side way to span
two PostgREST calls in one transaction. The contract's invariant ("every
write to A.1–A.8 inserts exactly one `kb_revisions` row in the SAME
transaction... a write without one is a bug") is only honestly achievable
by doing the entity write AND the revision insert inside ONE Postgres
function, invoked as ONE `.rpc()` call — the same pattern this schema
already uses for `social_wiring.try_acquire_sync_lease`. Migration
`007_revisions.sql` ships those functions; this module just calls them
and translates their custom SQLSTATEs (`NA404`/`NA409`/`NA422`/`NA001`,
plus the standard `23505` unique_violation) into `app/knowledge/errors.py`.

Read paths (`search_kb`, `list_*`, `get_*`, `session_prep`) need no
cross-statement atomicity, so they go straight through `.table().select()`
— plain PostgREST, org_id filtered explicitly on every call (routes use
the admin/service-role client per contract §B.0, so RLS here is defence
in depth, never the authorization boundary).

`transaction()` — see its own docstring below — batches `import_entity`/
`seed_counters` calls made inside the block and sends them as ONE
`import_bundle` RPC call on a clean exit, which is the only way to honor
"a single import transaction" (contract §B.6) given the PostgREST
constraint above.

NOC-REMEDIATE[pg-knowledge-store-untested]: this module is NOT exercised
by this slice's test suite — the hard rule against applying migrations to
any database (see the A1 dispatch brief) means there is no live Postgres
to run it against here. The Protocol-conformance suite in
`tests/knowledge/` runs exclusively against `FakeKnowledgeStore`. This
class is written to be correct by inspection and structurally mirrors
`FakeKnowledgeStore`'s invariants method-for-method, but a first real
integration pass (once a dev/staging DB exists) is still owed. — 2026-09-14
"""
from __future__ import annotations

import contextlib
from dataclasses import asdict
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

from noctusai_lib.integrations.persistence.paging import iter_paged_rows

from app.knowledge.errors import AssertionUsed, Conflict, Invalid, NotFound
from app.knowledge.store import Provenance

#: Custom SQLSTATE convention declared in 007_revisions.sql's header.
_ERROR_MAP: dict[str, type[Exception]] = {
    "NA404": NotFound,
    "NA409": Conflict,
    "NA422": Invalid,
    "NA001": AssertionUsed,
    "23505": Conflict,  # a bare unique_violation (e.g. slug/codigo collision)
}


def _prov_json(prov: Provenance) -> dict:
    """`Provenance` -> a jsonb-safe dict (UUID/datetime -> str)."""
    out = asdict(prov)
    for key, value in out.items():
        if isinstance(value, UUID):
            out[key] = str(value)
        elif isinstance(value, datetime):
            out[key] = value.isoformat()
    return out


def _raise_mapped(exc: APIError) -> None:
    """Translate a Postgres RPC error into the typed errors, or re-raise."""
    code = getattr(exc, "code", None) or ""
    mapped = _ERROR_MAP.get(code)
    if mapped is not None:
        raise mapped(str(exc)) from exc
    raise


class PgKnowledgeStore:
    """`KnowledgeStore` over the product's own Supabase admin client.

    `admin` MUST already be schema-scoped to `academia_de_reciclagem`
    (i.e. `create_database_module(settings, schema="academia_de_reciclagem").get_admin_client()`)
    — every `.table()`/`.rpc()` call below resolves unqualified names
    against that schema.
    """

    def __init__(self, admin: Client) -> None:
        self._admin = admin
        self._batch: list[dict] | None = None
        self._pending_counters: dict[str, int] = {}
        self._batch_org_id: Any = None

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _call_rpc(self, fn_name: str, params: dict) -> Any:
        try:
            resp = self._admin.rpc(fn_name, params).execute()
        except APIError as exc:
            _raise_mapped(exc)
            raise  # pragma: no cover — _raise_mapped always raises
        return resp.data

    def _select_one(self, table: str, org_id, label: str, **eq) -> dict:
        query = self._admin.table(table).select("*").eq("org_id", str(org_id))
        for key, value in eq.items():
            query = query.eq(key, value)
        rows = query.execute().data or []
        if not rows:
            raise NotFound(f"{label} not found: {eq}")
        return rows[0]

    def _select_paged(self, table: str, org_id, *, order: str = "id", **eq) -> list[dict]:
        query = self._admin.table(table).select("*").eq("org_id", str(org_id))
        for key, value in eq.items():
            if value is not None:
                query = query.eq(key, value)

        def fetch_page(start: int, end: int):
            return query.order(order).range(start, end).execute().data

        return list(iter_paged_rows(fetch_page, id_key="id", label=f"{table} for org_id={org_id}"))

    # ------------------------------------------------------------------
    # kb entries
    # ------------------------------------------------------------------

    async def search_kb(self, org_id, *, consulta, categoria, subcategoria, tag, limite, offset):
        query = self._admin.table("kb_entries").select("*", count="exact").eq("org_id", str(org_id))
        if categoria is not None:
            query = query.eq("categoria", categoria)
        if subcategoria is not None:
            query = query.eq("subcategoria", subcategoria)
        if tag is not None:
            query = query.contains("tags", [tag])
        if consulta is not None:
            needle = consulta.replace(",", " ").replace("%", " ")
            query = query.or_(f"titulo.ilike.%{needle}%,resumo.ilike.%{needle}%,corpo_md.ilike.%{needle}%")
        resp = query.order("slug").range(offset, offset + limite - 1).execute()
        return list(resp.data or []), resp.count or 0

    async def get_kb(self, org_id, slug: str) -> dict:
        return self._select_one("kb_entries", org_id, "kb_entry", slug=slug)

    async def create_kb(self, org_id, data: dict, prov: Provenance) -> dict:
        return self._call_rpc("create_kb_entry", {
            "p_org_id": str(org_id),
            "p_slug": data["slug"],
            "p_categoria": data["categoria"],
            "p_subcategoria": data.get("subcategoria"),
            "p_titulo": data["titulo"],
            "p_resumo": data.get("resumo"),
            "p_tags": list(data.get("tags") or []),
            "p_corpo_md": data["corpo_md"],
            "p_frontmatter": data.get("frontmatter") or {},
            "p_prov": _prov_json(prov),
        })

    async def update_kb(self, org_id, slug: str, changes: dict, prov: Provenance) -> dict:
        return self._call_rpc("update_kb_entry", {
            "p_org_id": str(org_id),
            "p_slug": slug,
            "p_changes": changes,
            "p_prov": _prov_json(prov),
        })

    async def archive_kb(self, org_id, slug: str, prov: Provenance) -> dict:
        return self._call_rpc("archive_kb_entry", {
            "p_org_id": str(org_id),
            "p_slug": slug,
            "p_prov": _prov_json(prov),
        })

    async def list_revisions(self, org_id, entity_type: str, entity_id: UUID) -> list[dict]:
        resp = (
            self._admin.table("kb_revisions").select("*")
            .eq("org_id", str(org_id))
            .eq("entity_type", entity_type)
            .eq("entity_id", str(entity_id))
            .order("rev_no", desc=True)
            .execute()
        )
        return list(resp.data or [])

    # ------------------------------------------------------------------
    # decisions
    # ------------------------------------------------------------------

    async def list_decisions(self, org_id, *, estado):
        return self._select_paged("decisions", org_id, order="codigo", estado=estado)

    async def get_decision(self, org_id, codigo: str) -> dict:
        return self._select_one("decisions", org_id, "decision", codigo=codigo)

    async def create_decision(self, org_id, data: dict, prov: Provenance) -> dict:
        return self._call_rpc("create_decision", {
            "p_org_id": str(org_id),
            "p_titulo": data["titulo"],
            "p_contexto": data.get("contexto"),
            "p_decisao": data["decisao"],
            "p_motivo": data["motivo"],
            "p_alternativas_rejeitadas": data.get("alternativas_rejeitadas"),
            "p_relacionadas": list(data.get("relacionadas") or []),
            "p_prov": _prov_json(prov),
        })

    async def supersede_decision(self, org_id, codigo: str, data: dict, prov: Provenance) -> tuple[dict, dict]:
        result = self._call_rpc("supersede_decision", {
            "p_org_id": str(org_id),
            "p_codigo": codigo,
            "p_titulo": data["titulo"],
            "p_contexto": data.get("contexto"),
            "p_decisao": data["decisao"],
            "p_motivo": data["motivo"],
            "p_alternativas_rejeitadas": data.get("alternativas_rejeitadas"),
            "p_relacionadas": list(data.get("relacionadas") or []),
            "p_prov": _prov_json(prov),
        })
        return result["nova"], result["substituida"]

    # ------------------------------------------------------------------
    # open questions
    # ------------------------------------------------------------------

    async def list_questions(self, org_id, *, estado: Literal["aberta", "respondida", "todas"]):
        return self._select_paged(
            "open_questions", org_id, order="codigo",
            estado=None if estado == "todas" else estado,
        )

    async def create_question(self, org_id, data: dict, prov: Provenance) -> dict:
        return self._call_rpc("create_open_question", {
            "p_org_id": str(org_id),
            "p_pergunta": data["pergunta"],
            "p_por_que_importa": data["por_que_importa"],
            "p_bloqueia": data["bloqueia"],
            "p_destino_kb": data.get("destino_kb"),
            "p_prov": _prov_json(prov),
        })

    async def answer_question(self, org_id, codigo: str, resposta: str, prov: Provenance) -> dict:
        return self._call_rpc("answer_open_question", {
            "p_org_id": str(org_id),
            "p_codigo": codigo,
            "p_resposta": resposta,
            "p_prov": _prov_json(prov),
        })

    # ------------------------------------------------------------------
    # roadmap + tasks
    # ------------------------------------------------------------------

    async def list_phases(self, org_id):
        return self._select_paged("roadmap_phases", org_id, order="ordem")

    async def update_phase(self, org_id, codigo: str, changes: dict, prov: Provenance) -> dict:
        return self._call_rpc("update_roadmap_phase", {
            "p_org_id": str(org_id),
            "p_codigo": codigo,
            "p_changes": changes,
            "p_prov": _prov_json(prov),
        })

    async def list_tasks(self, org_id, *, fase, estado):
        return self._select_paged("tasks", org_id, order="codigo", fase=fase, estado=estado)

    async def create_task(self, org_id, data: dict, prov: Provenance) -> dict:
        return self._call_rpc("create_task", {
            "p_org_id": str(org_id),
            "p_titulo": data["titulo"],
            "p_fase": data["fase"],
            "p_detalhe": data.get("detalhe"),
            "p_bloqueada_por": data.get("bloqueada_por"),
            "p_prov": _prov_json(prov),
        })

    async def update_task(self, org_id, codigo: str, changes: dict, prov: Provenance) -> dict:
        return self._call_rpc("update_task", {
            "p_org_id": str(org_id),
            "p_codigo": codigo,
            "p_changes": changes,
            "p_prov": _prov_json(prov),
        })

    async def session_prep(self, org_id) -> dict:
        phases = self._select_paged("roadmap_phases", org_id, order="ordem")
        fase_atual = next((p for p in phases if p["estado"] == "em-andamento"), None)

        tasks = self._select_paged("tasks", org_id, order="codigo")
        proximas = sorted(
            (t for t in tasks if t["estado"] == "pendente" and not t.get("bloqueada_por")),
            key=lambda r: r["codigo"],
        )
        bloqueadas = sorted(
            (t for t in tasks if t.get("bloqueada_por") and t["estado"] in ("pendente", "em-andamento")),
            key=lambda r: r["codigo"],
        )

        questions = self._select_paged("open_questions", org_id, order="codigo", estado="aberta")
        bloqueantes = sorted((q for q in questions if q.get("bloqueia")), key=lambda r: r["codigo"])

        return {
            "fase_atual": fase_atual,
            "proximas": proximas,
            "bloqueadas": bloqueadas,
            "perguntas_abertas": len(questions),
            "perguntas_bloqueantes": bloqueantes,
        }

    # ------------------------------------------------------------------
    # content / timeline / sources
    # ------------------------------------------------------------------

    async def list_content(self, org_id, *, tipo):
        return self._select_paged("content_drafts", org_id, order="codigo", tipo=tipo)

    async def get_content(self, org_id, codigo: str) -> dict:
        return self._select_one("content_drafts", org_id, "content_draft", codigo=codigo)

    async def create_content(self, org_id, data: dict, prov: Provenance) -> dict:
        return self._call_rpc("create_content_draft", {
            "p_org_id": str(org_id),
            "p_tipo": data["tipo"],
            "p_titulo": data["titulo"],
            "p_corpo_md": data["corpo_md"],
            "p_referencia": data.get("referencia"),
            "p_fontes": list(data.get("fontes") or []),
            "p_prov": _prov_json(prov),
        })

    async def list_timeline(self, org_id, *, limite):
        resp = (
            self._admin.table("timeline_events").select("*")
            .eq("org_id", str(org_id))
            .order("data", desc=True).order("created_at", desc=True)
            .range(0, limite - 1)
            .execute()
        )
        return list(resp.data or [])

    async def create_timeline_event(self, org_id, data: dict, prov: Provenance) -> dict:
        return self._call_rpc("create_timeline_event", {
            "p_org_id": str(org_id),
            "p_data": data.get("data"),
            "p_titulo": data["titulo"],
            "p_descricao": data["descricao"],
            "p_prov": _prov_json(prov),
        })

    async def create_source(self, org_id, data: dict, prov: Provenance) -> dict:
        return self._call_rpc("create_research_source", {
            "p_org_id": str(org_id),
            "p_url": data["url"],
            "p_titulo": data["titulo"],
            "p_trecho_citado": data["trecho_citado"],
            "p_resumo": data["resumo"],
            "p_kb_slug": data["kb_slug"],
            "p_vigencia_confirmada": bool(data.get("vigencia_confirmada", False)),
            "p_exige_da_empresa": data.get("exige_da_empresa"),
            "p_prov": _prov_json(prov),
        })

    # ------------------------------------------------------------------
    # import (A2)
    # ------------------------------------------------------------------

    async def import_entity(self, org_id, entity_type: str, natural_key: str, snapshot: dict, prov: Provenance) -> dict:
        if self._batch is not None:
            # Inside `transaction()`: nothing is persisted yet — queue it
            # for the single `import_bundle` call on a clean exit. The
            # returned shape is a best-effort echo, not the persisted row
            # (there is none yet); callers that need the real row must
            # read it back AFTER the `async with` block exits.
            self._batch_org_id = self._batch_org_id or org_id
            self._batch.append({
                "entity_type": entity_type,
                "natural_key": natural_key,
                "snapshot": snapshot,
                "prov": _prov_json(prov),
            })
            return {"entity_type": entity_type, "natural_key": natural_key, **snapshot, "_pending_import": True}

        return self._call_rpc("import_entity", {
            "p_org_id": str(org_id),
            "p_entity_type": entity_type,
            "p_natural_key": natural_key,
            "p_snapshot": snapshot,
            "p_prov": _prov_json(prov),
        })

    async def seed_counters(self, org_id, counters: dict[str, int]) -> None:
        if self._batch is not None:
            self._batch_org_id = self._batch_org_id or org_id
            self._pending_counters.update(counters)
            return
        self._call_rpc("seed_counters", {"p_org_id": str(org_id), "p_counters": counters})
        return None

    # ------------------------------------------------------------------
    # transaction — NOT part of the Protocol (see store.py's docstring)
    # ------------------------------------------------------------------

    @contextlib.asynccontextmanager
    async def transaction(self):
        """All-or-nothing block for `import_entity`/`seed_counters` (§B.6).

        PostgREST gives no client-side way to span multiple `.rpc()` calls
        in one Postgres transaction (see this module's docstring), so this
        BATCHES every call made inside the block and, only on a clean
        exit, sends the whole batch as ONE `import_bundle` call — one
        function invocation, one real transaction. An exception raised
        inside the block discards the batch: nothing was ever sent, so
        there is nothing to roll back.
        """
        self._batch = []
        self._pending_counters = {}
        self._batch_org_id = None
        try:
            yield self
        except Exception:
            self._batch = None
            self._pending_counters = {}
            self._batch_org_id = None
            raise
        else:
            items, counters, org_id = self._batch, self._pending_counters, self._batch_org_id
            self._batch = None
            self._pending_counters = {}
            self._batch_org_id = None
            if items or counters:
                if org_id is None:
                    raise RuntimeError(
                        "PgKnowledgeStore.transaction(): committed with no "
                        "org_id recorded — import_entity/seed_counters were "
                        "never called inside the block"
                    )
                self._call_rpc("import_bundle", {
                    "p_org_id": str(org_id),
                    "p_items": items,
                    "p_counters": counters or None,
                })
