"""noctus.dev.ensure_schema_exposure — PostgREST exposed-schemas gate.

THE INCIDENT (2026-09-16, agents/academia-de-reciclagem cutover). Two new
products' declared schemas were never added to the `authenticator` role's
`pgrst.db_schemas` setting (Supabase dashboard Settings -> API -> Exposed
schemas; `KB § GUIDES/production-deploy.md § 6` "DROP SCHEMA on an
API-exposed Supabase schema"). `agents`' own startup-hook PostgREST probe
failed with `PGRST106` while its plain `/api/health` stayed 200 (the guard
sets `startup_hook_error`, it doesn't crash-loop) — every gate that shells
`curl /api/health` reported green. `academia-de-reciclagem` would have
5xx'd on its first real REST call. The tech-lead fixed it LIVE with
`ALTER ROLE authenticator SET pgrst.db_schemas=…` + `NOTIFY
pgrst,'reload config'`. This tool is the mechanism that makes that check
routine instead of a live incident response, and `check == "schema_exposure"`
in `noctus.dev.predeploy_check` is the gate that runs it before a NEW
product's first deploy.

SCHEMA DERIVATION — reuses `migrate_product._resolve_schema` verbatim (the
product's own `create_product_app(schema="…")` declaration, AST-derived,
never a hand-maintained slug map — `CLAUDE.md` §1 "derive, don't sync by
hand"). Two tools deriving the same fact independently is exactly the drift
class this repo gates elsewhere; importing keeps it ONE source.

ROSTER — reuses `deploy_verify._resolve_live_products` (catalog `ativo=true
AND deploy_scope='live'` + `core`, graceful-degrading to the checked-in
`deploy/fleet/build-scope.txt` snapshot when the catalog is unreachable).
Pass `products=[...]` to check/apply an explicit set instead (what
`predeploy_check`'s per-product leg does — it already knows which ONE
product it is gating and has no reason to pay for a catalog round-trip).

EXPOSED-LIST SQL — `SELECT setconfig FROM pg_db_role_setting s JOIN
pg_roles r ON r.oid = s.setrole WHERE r.rolname = 'authenticator'` (the
exact query in the KB incident row above). `setconfig` is a
`text[]` of `key=value` GUC overrides; `pgrst.db_schemas=<csv>` is the one
this tool reads/writes.

action='check' (default, read-only): resolves the roster, derives each
product's schema, reads the exposed list, and reports every product whose
schema is NOT in it. Never mutates.

action='apply': DRY-RUN by default (confirm=False — returns the planned new
exposed-list). confirm=True runs `ALTER ROLE authenticator SET
pgrst.db_schemas='<old ∪ missing>'` (APPEND-ONLY — union, never a schema
removed by this tool; removal is the `DROP SCHEMA` runbook's job, which
has its own safe-order procedure) then `NOTIFY pgrst,'reload config'`.

action='prune' (2026-11-06, closes access-tier finding AT-847e83bb: the `erp`
schema of the ASLEEP product erp-imobiliario stayed exposed): the one
sanctioned REMOVAL path. DRY-RUN by default (confirm=False returns the plan:
current list, schemas to drop, owning products, the exact SQL). ASLEEP is
DERIVED, never hand-listed: a product dir under products/ that is in neither
`deploy/fleet/active-scope.txt` (catalog `ativo=true`, any scope) nor the
live catalog roster. A schema is dropped from the list ONLY when (a) it is
attributed by the product's own `create_product_app(schema=...)` declaration
(a slug-fallback guess never qualifies), (b) EVERY product declaring it is
asleep, and (c) it is not Supabase/platform infra (`_PROTECTED_SCHEMAS`).
An exposed schema nobody declares, or one attributed only by slug guess, is
REFUSED and listed (`refused`), never silently kept or dropped. confirm=True
runs ALTER ROLE + NOTIFY, then RE-READS the list and fails loudly unless
exactly the planned schemas are gone. This tool never DROPs a schema; the
`DROP SCHEMA` runbook (KB § GUIDES/production-deploy.md § 6) stays separate.

Requires a Supabase Personal Access Token, resolved the SAME DB-first way
`noctus.dev.migrate_product` resolves it (reuses `make_sql_executor`).
Returns `not_configured` (never a silent skip) when no token resolves —
`noctus.dev.predeploy_check`'s `schema_exposure` leg treats `not_configured`
as a FAILURE, not a pass, because "we couldn't check" must never read as
"it's fine" for a gate whose whole point is catching a PGRST106 before it
ships.

KB § GUIDES/production-deploy.md § 6.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from . import migrate_product as _mp

logger = logging.getLogger(__name__)

_EXPOSED_SCHEMAS_SETTING = "pgrst.db_schemas"

#: Supabase / platform-infra schemas prune must never remove, whatever the
#: product tree says. These are NOT product-derived (no create_product_app
#: declaration owns them), so a closed constant is the honest source.
_PROTECTED_SCHEMAS = frozenset({
    "public", "graphql_public", "graphql", "extensions", "auth", "storage",
    "realtime", "vault", "pgbouncer", "supabase_functions", "net", "cron",
    "core", "seed",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _exposed_schemas_sql() -> str:
    """The exact query from `KB § GUIDES/production-deploy.md § 6` — reads
    the `authenticator` role's `pgrst.db_schemas` GUC override (what the
    Supabase dashboard's Settings -> API -> Exposed-schemas panel reads and
    writes; a SQL change here IS the dashboard change)."""
    return (
        "SELECT setconfig FROM pg_db_role_setting s "
        "JOIN pg_roles r ON r.oid = s.setrole "
        "WHERE r.rolname = 'authenticator';"
    )


def _parse_exposed_schemas(rows: list[dict] | None) -> list[str] | None:
    """Extract the `pgrst.db_schemas=<csv>` value out of the role's
    `setconfig` array-of-`key=value` rows. Returns ``None`` when the
    setting is not present at all (no role-level override configured) —
    distinct from an empty list, so callers never conflate "nothing
    exposed" with "we couldn't tell" (no-silent-errors)."""
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        setconfig = row.get("setconfig")
        if not setconfig:
            continue
        for entry in setconfig:
            if not isinstance(entry, str):
                continue
            if entry.startswith(f"{_EXPOSED_SCHEMAS_SETTING}="):
                value = entry[len(_EXPOSED_SCHEMAS_SETTING) + 1 :]
                return [s.strip() for s in value.split(",") if s.strip()]
    return None


def _alter_role_sql(schemas: list[str]) -> str:
    """`ALTER ROLE authenticator SET pgrst.db_schemas='a,b,c'` — the exact
    write the KB incident row's safe-order procedure uses."""
    csv = ",".join(schemas)
    safe = csv.replace("'", "''")
    return f"ALTER ROLE authenticator SET {_EXPOSED_SCHEMAS_SETTING}='{safe}';"


_RELOAD_CONFIG_SQL = "NOTIFY pgrst,'reload config';"


def _resolve_roster(
    products: list[str] | None,
    live_products_fn: Any = None,
) -> tuple[list[str] | None, str, str | None]:
    """Explicit `products=` wins (what a per-product predeploy leg passes).
    Otherwise reuse `deploy_verify._resolve_live_products` — the SAME
    catalog-derived (`ativo=true AND deploy_scope='live'` + `core`) roster
    `noctus.dev.deploy_verify` uses, so this tool never grows a second,
    independently-drifting definition of "what's live". Returns
    (slugs_or_None, source, warning)."""
    if products:
        return sorted(set(products)), "explicit", None
    from .deploy_verify import _resolve_live_products

    live, source, warning = _resolve_live_products(live_products_fn)
    if live is None:
        return None, source, warning
    return sorted(live), source, warning


# ---------------------------------------------------------------------------
# Prune (removal of asleep products' schemas)
# ---------------------------------------------------------------------------


def _read_active_scope(path: Path | None = None) -> set[str] | None:
    """Slugs in `deploy/fleet/active-scope.txt` (catalog `ativo=true`, any
    scope, plus `core`). ``None`` when the file is missing/empty — prune then
    REFUSES (it cannot tell asleep from active, and guessing is the failure)."""
    p = path or (_mp.PRODUCTS_DIR.parent / "deploy" / "fleet" / "active-scope.txt")
    if not p.exists():
        return None
    slugs = {
        line.strip()
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    return slugs or None


def _running_products_default() -> set[str]:
    """Slugs with a RUNNING prod container, via the helper behind
    noctus.vps.ps (`vps.ps`, throttled SSH). Raises on failure."""
    from . import vps as _vps

    res = _vps.ps()
    if not res.get("ok"):
        raise RuntimeError(res.get("error") or "vps.ps failed")
    return {c["name"][len(_vps.CONTAINER_PREFIX):] for c in res["containers"]}


def plan_prune(
    exposed: list[str],
    owners: dict[str, list[dict[str, str]]],
    active: set[str],
    running: set[str] | None = None,
) -> dict[str, Any]:
    """Pure planner. ``owners``: schema -> [{product, schema_source}] for every
    product on disk. Returns {to_drop, refused, kept}. A schema is dropped only
    if declared (main_py_declaration) and owned exclusively by asleep products."""
    to_drop: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    kept: list[str] = []
    for schema in exposed:
        if schema in _PROTECTED_SCHEMAS:
            kept.append(schema)
            continue
        own = owners.get(schema, [])
        if not own:
            refused.append({"schema": schema, "reason": "no product declares this schema (unattributable)"})
            continue
        if any(o["product"] in active for o in own):
            kept.append(schema)
            continue
        up = sorted(o["product"] for o in own if o["product"] in (running or ()))
        if up:
            refused.append({"schema": schema, "reason": "container running", "products": up})
            continue
        if any(o["schema_source"] != "main_py_declaration" for o in own):
            refused.append({
                "schema": schema,
                "reason": "attributed only by slug-name guess, not a create_product_app(schema=...) declaration",
                "products": sorted(o["product"] for o in own),
            })
            continue
        to_drop.append({"schema": schema, "products": sorted(o["product"] for o in own)})
    return {"to_drop": to_drop, "refused": refused, "kept": kept}


def _prune(
    *,
    executor: _mp.SqlExecutor,
    confirm: bool,
    products_dir: Path | None,
    live_products_fn: Any,
    active_products: set[str] | None,
    running_products_fn: Any,
    result: Any,
) -> dict[str, Any]:
    active = active_products if active_products is not None else _read_active_scope()
    if active is None:
        return result(
            "unavailable",
            error="deploy/fleet/active-scope.txt missing/empty — cannot derive the asleep set; REFUSING to guess.",
        )
    # A catalog-asleep product can still be RUNNING in prod: read the real
    # container set; unreadable => unavailable, never "none running".
    try:
        running = set((running_products_fn or _running_products_default)())
    except Exception as exc:  # noqa: BLE001 — any read failure refuses, never assumes empty
        return result("unavailable", error=f"could not read running prod containers: {exc} — REFUSING to assume none are running.")
    live, roster_source, warning = _resolve_roster(None, live_products_fn)
    if live is not None:
        active = set(active) | set(live)  # live is already ⊆ active; belt and braces
    base = products_dir or _mp.PRODUCTS_DIR
    owners: dict[str, list[dict[str, str]]] = {}
    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        schema, source = _mp._resolve_schema(d.name, None, base)
        owners.setdefault(schema, []).append({"product": d.name, "schema_source": source})

    fetch = executor.execute(_exposed_schemas_sql())
    if not fetch.get("ok"):
        return result("error", warning=warning, error="could not read authenticator's pgrst.db_schemas: " + (fetch.get("error") or "unknown error"))
    exposed = _parse_exposed_schemas(fetch.get("rows"))
    if exposed is None:
        return result("error", warning=warning, error="authenticator has no pgrst.db_schemas override — nothing to prune and nothing to verify against.")

    plan = plan_prune(exposed, owners, active, running)
    drop = {d["schema"] for d in plan["to_drop"]}
    new_exposed = [s for s in exposed if s not in drop]
    extra: dict[str, Any] = {
        "exposed_schemas": exposed,
        "to_drop": plan["to_drop"],
        "refused": plan["refused"],
        "kept": plan["kept"],
        "roster_source": roster_source,
        "warning": warning,
    }
    if not drop:
        return result("up_to_date", new_exposed_schemas=exposed, **extra)
    if not new_exposed:
        return result("error", error="prune would leave an empty exposed list — refusing.", **extra)

    sql = [_alter_role_sql(new_exposed), _RELOAD_CONFIG_SQL]
    extra["sql"] = sql
    if not confirm:
        return result("planned", new_exposed_schemas=new_exposed, **extra)

    alter = executor.execute(sql[0])
    if not alter.get("ok"):
        return result("error", error="ALTER ROLE failed: " + (alter.get("error") or "unknown error"), **extra)
    reload_ = executor.execute(sql[1])
    if not reload_.get("ok"):
        extra["warning"] = (warning + "; " if warning else "") + "NOTIFY reload failed: " + (reload_.get("error") or "unknown")
    after = _parse_exposed_schemas(executor.execute(_exposed_schemas_sql()).get("rows"))
    if after is None or set(after) != set(new_exposed):
        return result(
            "error",
            error=f"post-apply verify FAILED: expected {sorted(new_exposed)}, read back {after}",
            applied=True,
            new_exposed_schemas=new_exposed,
            **extra,
        )
    return result("pruned", applied=True, new_exposed_schemas=new_exposed, **extra)


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------


def check_schema_exposure(
    *,
    action: str = "check",
    confirm: bool = False,
    products: list[str] | None = None,
    project_ref: str = "nyplttplcoyiiqjrvtiw",
    executor: _mp.SqlExecutor | None = None,
    products_dir: Path | None = None,
    live_products_fn: Any = None,
    active_products: set[str] | None = None,
    running_products_fn: Any = None,
) -> dict[str, Any]:
    """Compare every checked product's declared DB schema against the
    `authenticator` role's exposed-schemas list; optionally close the gap.

    Args:
        action:        'check' (default, read-only) | 'apply' | 'prune'.
        running_products_fn: Injection seam returning the slugs with a running
                       prod container (action='prune'; default = vps.ps).
        active_products: Injection seam for the `active-scope.txt` set
                       (action='prune' only).
        confirm:       For action='apply' — False (default) = dry-run
                       (returns the planned new exposed-list, writes
                       nothing). True = actually ALTER ROLE + NOTIFY.
        products:      Explicit slug list. Omitted -> catalog-live roster
                       (`ativo=true AND deploy_scope='live'` + `core`).
        project_ref:   Supabase project reference.
        executor:      Injection seam for tests (`migrate_product.FakeSqlExecutor`).
        products_dir:  Override PRODUCTS_DIR (injection seam for tests).
        live_products_fn: Injection seam for the catalog-roster resolver.

    Returns a dict with keys::

        status, action, exposed_schemas, checked, missing, applied,
        new_exposed_schemas, roster_source, warning, error
    """
    if action not in ("check", "apply", "prune"):
        return {
            "ok": False,
            "status": "error",
            "action": action,
            "error": f"unknown action {action!r} — must be 'check', 'apply' or 'prune'",
        }

    def _result(status: str, **overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "ok": status not in ("error", "not_configured", "unavailable"),
            "status": status,
            "action": action,
            "exposed_schemas": [],
            "checked": [],
            "missing": [],
            "applied": False,
            "new_exposed_schemas": None,
            "roster_source": None,
            "warning": None,
            "error": None,
        }
        base.update(overrides)
        return base

    # ── Resolve executor ────────────────────────────────────────────────
    if executor is None:
        executor = _mp.make_sql_executor(project_ref=project_ref)
    if executor is None:
        # NOC-REMEDIATE[credentials]: no supabase_access_token resolved.
        # Same resolution path as noctus.dev.migrate_product — see there.
        return _result(
            "not_configured",
            error=(
                "NOC-REMEDIATE[credentials]: no supabase_access_token resolved. "
                "Store it DB-first in platform_settings (key='supabase_access_token', "
                "global scope) — or set env SUPABASE_ACCESS_TOKEN in the MCP .env."
            ),
        )

    if action == "prune":
        return _prune(
            executor=executor,
            confirm=confirm,
            products_dir=products_dir,
            live_products_fn=live_products_fn,
            active_products=active_products,
            running_products_fn=running_products_fn,
            result=_result,
        )

    # ── Resolve roster ──────────────────────────────────────────────────
    roster, roster_source, warning = _resolve_roster(products, live_products_fn)
    if roster is None:
        return _result("unavailable", roster_source=roster_source, error=warning)

    # ── Derive each product's declared schema (reuses migrate_product) ──
    checked: list[dict[str, str]] = []
    for slug in roster:
        schema, schema_source = _mp._resolve_schema(slug, None, products_dir)
        checked.append({"product": slug, "schema": schema, "schema_source": schema_source})

    # ── Read the exposed list ───────────────────────────────────────────
    fetch = executor.execute(_exposed_schemas_sql())
    if not fetch.get("ok"):
        return _result(
            "error",
            checked=checked,
            roster_source=roster_source,
            warning=warning,
            error=(
                "could not read authenticator's pgrst.db_schemas: "
                + (fetch.get("error") or "unknown error")
            ),
        )
    exposed = _parse_exposed_schemas(fetch.get("rows"))
    if exposed is None:
        exposed = []

    exposed_set = set(exposed)
    missing = sorted({c["schema"] for c in checked if c["schema"] not in exposed_set})

    if action == "check":
        status = "in_sync" if not missing else "drift_detected"
        return _result(
            status,
            exposed_schemas=exposed,
            checked=checked,
            missing=missing,
            roster_source=roster_source,
            warning=warning,
        )

    # ── action == 'apply' ───────────────────────────────────────────────
    if not missing:
        return _result(
            "up_to_date",
            exposed_schemas=exposed,
            checked=checked,
            roster_source=roster_source,
            warning=warning,
        )

    new_exposed = sorted(exposed_set | set(missing))  # APPEND-ONLY — union, never a removal
    if not confirm:
        return _result(
            "planned",
            exposed_schemas=exposed,
            checked=checked,
            missing=missing,
            new_exposed_schemas=new_exposed,
            roster_source=roster_source,
            warning=warning,
        )

    alter_result = executor.execute(_alter_role_sql(new_exposed))
    if not alter_result.get("ok"):
        return _result(
            "error",
            exposed_schemas=exposed,
            checked=checked,
            missing=missing,
            roster_source=roster_source,
            warning=warning,
            error="ALTER ROLE failed: " + (alter_result.get("error") or "unknown error"),
        )
    reload_result = executor.execute(_RELOAD_CONFIG_SQL)
    if not reload_result.get("ok"):
        logger.warning(
            "ensure_schema_exposure: ALTER ROLE applied but NOTIFY reload failed: %s",
            reload_result.get("error"),
        )
        # Non-fatal: the GUC override landed; PostgREST's own ~32s poll picks it
        # up eventually even without the explicit reload nudge.

    return _result(
        "applied",
        exposed_schemas=exposed,
        checked=checked,
        missing=missing,
        applied=True,
        new_exposed_schemas=new_exposed,
        roster_source=roster_source,
        warning=warning,
    )


# ---------------------------------------------------------------------------
# MCP registration
# ---------------------------------------------------------------------------


def register(server) -> None:
    @server.tool(
        name="noctus.dev.ensure_schema_exposure",
        description=(
            "PostgREST exposed-schemas gate. Compares every catalog-live "
            "product's (ativo=true AND deploy_scope='live' + core) declared "
            "DB schema — AST-derived from its own create_product_app(schema="
            "\"...\") declaration, the SAME derivation noctus.dev.migrate_product "
            "uses — against the authenticator role's pgrst.db_schemas exposed "
            "list (Supabase dashboard Settings -> API -> Exposed schemas; a SQL "
            "change here IS the dashboard change). action='check' (default, "
            "read-only) reports every product whose schema is unexposed — this "
            "is the PGRST106 class that hit agents' startup hook on the "
            "2026-09-16 agents/academia-de-reciclagem cutover while /api/health "
            "stayed 200. action='apply' is DRY-RUN by default (confirm=False — "
            "returns the planned new exposed-list); confirm=True runs ALTER "
            "ROLE authenticator SET pgrst.db_schemas=... (APPEND-ONLY — union "
            "with the current list, never removes a schema) then NOTIFY "
            "pgrst,'reload config'. action='prune' is the ONLY removal path: "
            "DRY-RUN by default (plan = current list, to_drop + owning "
            "products, refused, exact sql); drops only schemas declared "
            "solely by ASLEEP products (not in active-scope.txt / live "
            "catalog), never infra/core/seed schemas, REFUSES unattributable "
            "ones, and any whose owning product has a RUNNING prod container "
            "(reason 'container running'; unreadable => unavailable); "
            "confirm=True applies, NOTIFYs and re-reads to verify. "
            "Pass products=[...] to scope to an "
            "explicit set instead of the catalog roster. Requires a Supabase "
            "Personal Access Token, resolved DB-first the same way "
            "migrate_product resolves it; returns not_configured (never a "
            "silent skip) when none resolves. Returns {status, action, "
            "exposed_schemas, checked, missing, applied, new_exposed_schemas, "
            "roster_source, warning, error}. "
            "KB § GUIDES/production-deploy.md § 6."
        ),
    )
    def _ensure_schema_exposure(
        action: str = "check",
        confirm: bool = False,
        products: list[str] | None = None,
        project_ref: str = "nyplttplcoyiiqjrvtiw",
    ) -> dict:
        return check_schema_exposure(
            action=action,
            confirm=confirm,
            products=products,
            project_ref=project_ref,
        )


__all__ = [
    "check_schema_exposure",
    "_exposed_schemas_sql",
    "_parse_exposed_schemas",
    "_alter_role_sql",
    "_resolve_roster",
    "plan_prune",
    "register",
]
