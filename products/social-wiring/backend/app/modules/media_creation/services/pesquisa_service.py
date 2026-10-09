"""Minha Pesquisa — per-marca research items (list / add / classify / review).

Pure data service over the PostgREST client; the LLM is an injected callable
(:data:`PesquisaLlm`) so the classify flow is testable through its real seam.
Every read/write is org-scoped AND marca-scoped; ``rejected`` rows are soft
(kept for dedupe/audit) and never returned.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Awaitable, Callable, Optional

from noctusai_lib.integrations.llm import chat_completion
from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.integrations.persistence.table_reads import PAGE_SIZE, batched

from app.modules.media_creation.pesquisa_variables import (
    CLASSIFIABLE_SLUGS,
    VARIABLE_SLUGS,
)
from app.modules.media_creation.prompts.pesquisa_classifier import (
    PESQUISA_CLASSIFIER_SYSTEM_PROMPT,
    parse_classifier_output,
    split_input_lines,
)
from app.modules.media_creation.schemas.pesquisa import MAX_CONTENT_CHARS

logger = logging.getLogger(__name__)

ITEMS = "cs_research_items"
VARIABLES = "cs_research_variables"
ITEM_COLS = "id,marca_id,variable_slug,content,status,origin,plays,source_ref,created_at"

#: ``(system_prompt, user_message, org_id) -> raw model reply``. The FastAPI
#: dependency ``get_pesquisa_llm`` provides it; tests override that seam.
PesquisaLlm = Callable[[str, str, Optional[str]], Awaitable[str]]


async def chat_pesquisa_llm(system_prompt: str, user_message: str, org_id: Optional[str]) -> str:
    return await chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        org_id=org_id,
        temperature=0.0,
    )


class PesquisaError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class PesquisaService:
    def __init__(self, db, org_id: str, user_id: Optional[str] = None):
        self.db = db
        self.org_id = org_id
        self.user_id = user_id

    # ── guards ──────────────────────────────────────────────────────────

    def assert_marca(self, marca_id: str) -> None:
        rows = (
            self.db.table("marcas").select("id")
            .eq("id", marca_id).eq("org_id", self.org_id).execute().data
        )
        if not rows:
            raise PesquisaError(404, "Marca não encontrada")

    def _items(self):
        return self.db.table(ITEMS)

    def _get_item(self, item_id: str) -> dict[str, Any]:
        rows = (
            self._items().select(ITEM_COLS)
            .eq("id", item_id).eq("org_id", self.org_id).neq("status", "rejected")
            .execute().data
        )
        if not rows:
            raise PesquisaError(404, "Item não encontrado")
        return rows[0]

    # ── reads ───────────────────────────────────────────────────────────

    def list_variables(self) -> list[dict[str, Any]]:
        return (
            self.db.table(VARIABLES)
            .select("slug,label,grupo,description,classifiable,sort_order")
            .order("sort_order").execute().data or []
        )

    def list_items(
        self, marca_id: str, *, status: str, variable_slug: Optional[str],
        sort: str, limit: int, offset: int,
    ) -> dict[str, Any]:
        self.assert_marca(marca_id)
        q = (
            self._items().select(ITEM_COLS, count="exact")
            .eq("org_id", self.org_id).eq("marca_id", marca_id).eq("status", status)
        )
        if variable_slug:
            q = q.eq("variable_slug", variable_slug)
        if sort == "plays":
            q = q.order("plays", desc=True, nullsfirst=False)
        q = q.order("created_at", desc=True).order("id").range(offset, offset + limit - 1)
        res = q.execute()
        rows = res.data or []
        total = res.count if getattr(res, "count", None) is not None else len(rows)
        return {"items": rows, "total": total}

    def counts(self, marca_id: str) -> dict[str, Any]:
        self.assert_marca(marca_id)

        def page(start: int, end: int):
            return (
                self._items().select("id,variable_slug,status")
                .eq("org_id", self.org_id).eq("marca_id", marca_id)
                .neq("status", "rejected").order("id").range(start, end).execute().data
            )

        out: dict[str, Any] = {"approved": 0, "pending": 0, "by_variable": {}}
        for row in iter_paged_rows(page, page_size=PAGE_SIZE, label="cs_research_items counts"):
            st = row["status"]
            out[st] += 1
            slot = out["by_variable"].setdefault(row["variable_slug"], {"approved": 0, "pending": 0})
            slot[st] += 1
        return out

    # ── writes ──────────────────────────────────────────────────────────

    def _existing(self, marca_id: str, slugs: set[str]) -> dict[tuple[str, str], dict[str, Any]]:
        found: dict[tuple[str, str], dict[str, Any]] = {}
        for slug in slugs:
            def page(start: int, end: int, _slug=slug):
                return (
                    self._items().select("id,variable_slug,content,status")
                    .eq("org_id", self.org_id).eq("marca_id", marca_id)
                    .eq("variable_slug", _slug).order("id").range(start, end).execute().data
                )
            for row in iter_paged_rows(page, page_size=PAGE_SIZE, label="cs_research_items dedupe"):
                found[(row["variable_slug"], row["content"].lower())] = row
        return found

    def _save(
        self, marca_id: str, pairs: list[tuple[str, str]], *, origin: str, status: str,
    ) -> dict[str, Any]:
        """Insert ``(slug, content)`` pairs; duplicates are skipped. A *manual*
        add of a previously rejected duplicate flips it to approved."""
        existing = self._existing(marca_id, {s for s, _ in pairs})
        saved: list[dict[str, Any]] = []
        skipped = 0
        batch_seen: set[tuple[str, str]] = set()
        for slug, content in pairs:
            key = (slug, content.lower())
            if key in batch_seen:
                skipped += 1
                continue
            batch_seen.add(key)
            prior = existing.get(key)
            if prior is not None:
                if origin == "manual" and prior["status"] == "rejected":
                    upd = (
                        self._items().update({"status": "approved", "origin": "manual"})
                        .eq("id", prior["id"]).eq("org_id", self.org_id).execute().data
                    )
                    if upd:
                        saved.append(upd[0])
                        continue
                skipped += 1
                continue
            res = self._items().insert({
                "id": str(uuid.uuid4()), "org_id": self.org_id, "marca_id": marca_id,
                "variable_slug": slug,
                "content": content, "status": status, "origin": origin,
                "created_by": self.user_id,
            }).execute().data
            if res:
                saved.append(res[0])
        return {"saved": len(saved), "skipped": skipped, "items": saved}

    def add_manual(self, marca_id: str, variable_slug: str, lines: list[str]) -> dict[str, Any]:
        self.assert_marca(marca_id)
        if variable_slug not in VARIABLE_SLUGS:
            raise PesquisaError(422, "Variável desconhecida")
        return self._save(
            marca_id, [(variable_slug, ln) for ln in lines], origin="manual", status="approved"
        )

    async def classify(self, marca_id: str, text: str, llm: PesquisaLlm) -> dict[str, Any]:
        self.assert_marca(marca_id)
        input_lines = split_input_lines(text)
        if not input_lines:
            raise PesquisaError(422, "Informe ao menos um item")
        try:
            reply = await llm(PESQUISA_CLASSIFIER_SYSTEM_PROMPT, "\n".join(input_lines), self.org_id)
        except Exception as exc:  # noqa: BLE001 - surfaced as 502, nothing saved
            logger.error("pesquisa classify: LLM call failed: %s", exc)
            raise PesquisaError(502, "Falha ao classificar com IA") from exc
        parsed = parse_classifier_output(reply, input_lines)

        pairs: list[tuple[str, str]] = []
        unclassified = list(parsed.unclassified)
        for slug, contents in parsed.classified.items():
            assert slug in CLASSIFIABLE_SLUGS
            for c in contents:
                if len(c) > MAX_CONTENT_CHARS:
                    unclassified.append(c)
                else:
                    pairs.append((slug, c))
        res = self._save(marca_id, pairs, origin="ai_classified", status="pending")
        classified: dict[str, list[str]] = {}
        for slug, c in pairs:
            classified.setdefault(slug, []).append(c)
        return {
            "saved": res["saved"], "skipped": res["skipped"],
            "classified": classified, "unclassified": unclassified,
        }

    def _set_status(self, item: dict[str, Any], status: str, allowed_from: tuple[str, ...]):
        if item["status"] not in allowed_from:
            return item
        res = (
            self._items().update({"status": status})
            .eq("id", item["id"]).eq("org_id", self.org_id).execute().data
        )
        return res[0] if res else item

    def approve(self, item_id: str) -> dict[str, Any]:
        return self._set_status(self._get_item(item_id), "approved", ("pending",))

    def reject(self, item_id: str) -> dict[str, Any]:
        return self._set_status(self._get_item(item_id), "rejected", ("pending", "approved"))

    def delete(self, item_id: str) -> None:
        rows = (
            self._items().select("id").eq("id", item_id).eq("org_id", self.org_id).execute().data
        )
        if not rows:
            raise PesquisaError(404, "Item não encontrado")
        self._items().delete().eq("id", item_id).eq("org_id", self.org_id).execute()

    def bulk(self, marca_id: str, action: str, ids: list[str]) -> int:
        self.assert_marca(marca_id)
        affected = 0
        for chunk in batched(sorted(set(ids))):
            base = lambda q: q.in_("id", chunk).eq("org_id", self.org_id).eq("marca_id", marca_id)  # noqa: E731
            if action == "delete":
                affected += len(base(self._items().delete()).execute().data or [])
            elif action == "approve":
                affected += len(
                    base(self._items().update({"status": "approved"})).eq("status", "pending")
                    .execute().data or []
                )
            else:
                affected += len(
                    base(self._items().update({"status": "rejected"})).neq("status", "rejected")
                    .execute().data or []
                )
        return affected

    def empty(self, marca_id: str) -> int:
        self.assert_marca(marca_id)
        res = (
            self._items().delete()
            .eq("org_id", self.org_id).eq("marca_id", marca_id).execute().data
        )
        return len(res or [])
