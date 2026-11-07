"""noctus.dev.projection_rebuild -- rebuild one event-store projection of a product from position 0.

The event store organ (`noctusai_lib.domain.event_store`, KB § PATTERNS/backend/event-store.md) derives every read
model from the log, so a drifted, buggy or re-designed read model is repaired by REPLAYING, never by hand-editing
rows. This tool drives the organ's own RPCs against the product's schema, through the Supabase Management API
(`migrate_product.make_sql_executor` -- PAT resolved DB-first):

    es_rebuild_begin   -> shadow table `<target>__rebuild` (LIKE target, RLS on) + a `<projection>#rebuild` cursor
    es_rebuild_step*   -> one settled batch per call, each its OWN transaction (the live read model keeps serving)
    es_rebuild_swap    -> locks the target, catches up, swaps the CONTENTS in (the target keeps its RLS, grants,
                          triggers and indexes), drops the shadow, resets the live checkpoint

DRY-RUN by default: reads the registration, the checkpoint and the number of events it would replay, writes
nothing. `confirm=True` runs the rebuild. Refuses (`refused_catalog_scope`) a product that is not
`ativo=true AND deploy_scope='live'` (shared `_catalog_scope_guard`; `allow_inactive=True` is the supervised
escape hatch). No PAT -> `not_configured`, never a silent skip.

Status: planned | rebuilt | refused | not_configured | refused_catalog_scope | error.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional

from . import migrate_product as _mp
from ._catalog_scope_guard import REFUSED_STATUS, catalog_scope_refusal_reason, check_catalog_scope

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_MAX_BATCH = 5000


def _lit(text: str) -> str:
    return "'" + str(text).replace("'", "''") + "'"


def _json_cell(rows: Optional[list[dict]], column: str = "r") -> Any:
    if not rows:
        return None
    value = rows[0].get(column)
    return json.loads(value) if isinstance(value, str) else value


def projection_rebuild(
    product: str,
    projection: str,
    *,
    confirm: bool = False,
    batch: int = 1000,
    max_steps: int = 10000,
    schema: Optional[str] = None,
    project_ref: str = "nyplttplcoyiiqjrvtiw",
    allow_inactive: bool = False,
    executor: Any = None,
    live_products_fn: Optional[Callable[[], list[str]]] = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "status": "error", "product": product, "projection": projection,
                           "confirm": confirm, "error": None}
    if not _NAME_RE.match(projection or ""):
        return {**out, "error": f"projection must match {_NAME_RE.pattern}"}
    batch = max(1, min(int(batch), _MAX_BATCH))
    resolved_schema, schema_source = _mp._resolve_schema(product, schema)
    out.update(schema=resolved_schema, schema_source=schema_source)

    scope = check_catalog_scope(product, live_products_fn)
    out["catalog_scope"] = scope
    if not scope["in_scope"] and not allow_inactive:
        return {**out, "status": REFUSED_STATUS, "error": catalog_scope_refusal_reason(
            product, scope, action="rebuild a projection of", escape_hatch="allow_inactive",
            untouched_clause="Nothing was read or written.")}

    ex = executor or _mp.make_sql_executor(project_ref=project_ref)
    if ex is None:
        return {**out, "status": "not_configured",
                "error": "no Supabase access token (platform_settings.supabase_access_token / SUPABASE_ACCESS_TOKEN)"}

    s, p = resolved_schema, _lit(projection)
    q = f'"{s}"'

    def call(sql: str) -> Any:
        res = ex.execute(sql)
        if not res.get("ok"):
            raise RuntimeError(res.get("error") or "query failed")
        return res.get("rows")

    try:
        reg = call(f"SELECT handler, target, stream_types, mode FROM {q}.es_projections WHERE projection = {p}")
        if not reg:
            return {**out, "status": "refused", "error": f"projection {projection!r} is not registered in {s}.es_projections"}
        reg = reg[0]
        types = reg["stream_types"] if isinstance(reg["stream_types"], list) else str(reg["stream_types"]).strip("{}").split(",")
        cp = _json_cell(call(f"SELECT {q}.es_checkpoint_get({p}) AS r")) or {}
        events = call(f"SELECT count(*)::bigint AS n FROM {q}.es_events WHERE stream_type = ANY(ARRAY[{', '.join(_lit(t) for t in types)}]::text[])")
        plan = {"handler": reg["handler"], "target": reg["target"], "mode": reg["mode"], "stream_types": types,
                "events_to_replay": int((events or [{"n": 0}])[0]["n"]), "checkpoint": cp.get("checkpoint"),
                "batch": batch, "estimated_steps": -(-int((events or [{"n": 0}])[0]["n"]) // batch) or 1}
        out["plan"] = plan
        if not confirm:
            return {**out, "ok": True, "status": "planned"}

        begun = _json_cell(call(f"SELECT {q}.es_rebuild_begin({p}) AS r"))
        if not begun or begun.get("status") != "ok":
            return {**out, "status": "refused", "error": f"es_rebuild_begin: {begun}"}
        steps, applied = 0, 0
        while True:
            step = _json_cell(call(f"SELECT {q}.es_rebuild_step({p}, {batch}) AS r"))
            steps += 1
            if not step or step.get("status") != "ok":
                return {**out, "status": "refused", "steps": steps, "error": f"es_rebuild_step: {step}"}
            applied += int(step.get("applied") or 0)
            if step.get("done"):
                break
            if steps >= max_steps:
                return {**out, "status": "refused", "steps": steps, "applied": applied,
                        "error": f"stopped after max_steps={max_steps} without swapping; the live read model is untouched"}
        swapped = _json_cell(call(f"SELECT {q}.es_rebuild_swap({p}) AS r"))
        if not swapped or swapped.get("status") != "ok":
            return {**out, "status": "refused", "steps": steps, "applied": applied, "error": f"es_rebuild_swap: {swapped}"}
        return {**out, "ok": True, "status": "rebuilt", "steps": steps, "applied": applied,
                "rows": swapped.get("rows"), "cursor": swapped.get("cursor")}
    except RuntimeError as exc:
        return {**out, "status": "error", "error": str(exc)}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.projection_rebuild",
        description=(
            "Rebuild one event-store projection of a product from position 0 (event store organ, "
            "noctusai_lib.domain.event_store): es_rebuild_begin -> shadow table, es_rebuild_step* (one settled batch "
            "per transaction; the live read model keeps serving) -> es_rebuild_swap (locks the target, catches up, "
            "swaps the contents in, resets the checkpoint). DRY-RUN by default (registration + checkpoint + events "
            "to replay); confirm=True runs it. Refuses a product outside ativo+live (allow_inactive=True = "
            "supervised escape hatch); no Supabase PAT -> not_configured. Status: planned | rebuilt | refused | "
            "not_configured | refused_catalog_scope | error. KB § PATTERNS/backend/event-store.md."
        ),
    )
    def _projection_rebuild(
        product: str,
        projection: str,
        confirm: bool = False,
        batch: int = 1000,
        max_steps: int = 10000,
        schema: Optional[str] = None,
        project_ref: str = "nyplttplcoyiiqjrvtiw",
        allow_inactive: bool = False,
    ) -> dict:
        return projection_rebuild(product, projection, confirm=confirm, batch=batch, max_steps=max_steps,
                                  schema=schema, project_ref=project_ref, allow_inactive=allow_inactive)


__all__ = ["projection_rebuild", "register"]
