# Proposal: Remove product-level health.py in mailing — delegate to framework health router

**Agent:** claude-opus-4-7
**Origin:** keeper:noctusai_validate:mailing (evaluation run)
**Generated:** 2026-04-19 01:51
**Severity:** warning
**Effort:** low
**Affected products:** mailing
**Status:** pending

---

## 1. Context

Keeper's deterministic compliance detector (`check_seed_compliance` in `mcp/noctusai/tools/compliance.py`) flagged a custom `health.py` router in the mailing product during an evaluation run. The file was induced on 2026-04-19 specifically to exercise the keeper review flow and compare agent vs. headless OpenAI proposal authoring. It will be removed as part of the eval cleanup — but this proposal remains valid as a template for any real occurrence of the same pattern, which is a recurring violation category in NoctusAI (three of the four `check_seed_compliance` router checks target `health.py`, `notificacoes.py`, `team.py`).

---

## 2. Situation

The file `products/mailing/backend/app/routers/health.py` contains a 10-line FastAPI `APIRouter` with prefix `/api/health` and a single `GET ''` handler returning `{"status": "ok", "service": "mailing"}`. The seed framework mounts its own health router via `create_product_app()` in `seed/framework/backend/noctusai_seed/app.py`, which in turn pulls from `seed/framework/backend/noctusai_seed/routers.py::health_router` and exposes `GET /api/health` to every product by default. Whether the product-level router is actually reachable depends on FastAPI's router-mount order in `main.py` — typically the framework route wins silently, masking the duplicate until the seed evolves its health semantics. The pattern exists because early products (pre-seed-v3) carried their own health endpoints and the habit propagated.

---

## 3. Proposed Solution

### 3.1 Linkage — why this solution fits this situation

Deletion is the right move precisely because the framework already provides the same endpoint — leaving the file creates a silent divergence the router-mount order papers over today but the next seed health-schema change (e.g. adding a dependency-check payload) will break without warning. Keeping the file as a customization point also violates the 'Seed first — always' rule and the 'No quick fixes' rule in CLAUDE.md §1 (the real fix lives one layer up: extend the framework's health router if mailing genuinely needs custom telemetry).

### 3.2 Application instructions

1. Diff `products/mailing/backend/app/routers/health.py` against `seed/framework/backend/noctusai_seed/routers.py` — specifically the `health_router` definition — to confirm no mailing-specific customization (custom payload fields, dependency checks, auth requirements) has accreted.
2. If the diff shows only the framework-provided shape, delete the file: `rm products/mailing/backend/app/routers/health.py`.
3. `grep -r 'from app.routers.health' products/mailing/` — there should be zero hits; if any, remove those imports too.
4. Check `products/mailing/backend/app/main.py` for an explicit `include_router(health.router)` and remove it if present — `create_product_app()` already mounts the framework health router.
5. Hit `GET /api/health` manually (`curl http://localhost:<mailing-port>/api/health`) and confirm the response is the framework shape, not the mailing-specific one.
6. Run `pytest products/mailing/backend/tests/routers/test_health.py` — if a product-level test exercises the old shape, remove or migrate it (the template's health test is framework-level and stays in the seed tests).

### 3.3 Seed APIs / shared lib involved

- `noctusai_seed.routers.health_router` — Framework-supplied `APIRouter` mounted by `create_product_app()` at `/api/health`; returns the standard health payload every product inherits.
- `noctusai_seed.create_product_app()` — Factory in `seed/framework/backend/noctusai_seed/app.py` that auto-includes the framework health router. Product `main.py` files must not include their own.

### 3.4 Risks before applying

**Diff before deleting.** If mailing-specific health logic has accreted (e.g. a queue-depth check, Redis ping, SMTP reachability probe), delete-and-forget silently drops that signal. Preferred path in that case: contribute the product-specific check upstream to `noctusai_seed.routers.health_router` as a dependency-check hook, or expose it as a separate `/api/mailing/diagnostics` endpoint — not as a shadowing `/api/health`. **Watch mount order.** If the current product includes the router explicitly, FastAPI may resolve the product route first — deleting the file without also removing the include call leaves an ImportError. **Health check is infra-facing.** Load balancers, uptime monitors, and the platform's own observability hit this endpoint. If response shape differs between framework and product versions, downstream alerting may misfire during the transition — deploy the change off-hours or announce the cutover.

### 3.5 Alternatives considered

- **Leave the file with a deprecation comment** — Router-mount resolution is silent — the comment rots, the framework version silently wins, and the next reader assumes the comment is current. Deprecation comments in Python without a runtime `DeprecationWarning` are noise.
- **Extend the framework health router with mailing hooks** — Only correct if mailing genuinely has custom telemetry. Don't extend the framework for a file that currently returns the default shape — that's upgrading in the wrong direction.
- **Rename the product endpoint to `/api/mailing/health`** — Keeps duplication while adding confusion. Framework endpoint is the contract; product-scoped diagnostics belong under `/api/<product>/diagnostics` with a different purpose (deep status, not liveness).

---

## 4. Effects

When this is applied, these change:

- **Behavior:** `GET /api/health` continues to respond; response shape converges to the framework payload. No user-facing downtime.
- **Risk profile:** Silent divergence risk between product and framework health semantics is removed. Future seed evolutions to the health contract now propagate to mailing automatically.
- **Ergonomics:** Mailing backend loses 10 lines of boilerplate; one fewer file in the product-local routers list. Pattern becomes: 'health is a framework concern, not a product concern.'
- **Coverage:** Framework-level health tests (in `seed/framework/backend/tests/`) now exclusively cover the endpoint for mailing — no duplicate product-level test maintenance.

---

## 5. Acceptance Criteria

- [ ] Fix applied to every affected product (not just the one that triggered detection)
- [ ] `python mcp/noctusai/cli.py --validate` shows 100/100 for the affected product(s)
- [ ] `python mcp/noctusai/cli.py --review --product mailing` files no new proposals for this issue
- [ ] Backend tests still pass for the affected product(s)
- [ ] If the change touched shared code, `python mcp/noctusai/cli.py --catalog` shows no new orphans or duplicate candidates
- [ ] Documentation updated KB-first, CLAUDE.md second (per `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md → Docs stay in sync`)
- [ ] Diff against `seed/framework/backend/noctusai_seed/routers.py::health_router` captured in the commit message (or explicitly confirmed no diff).
- [ ] Framework health endpoint verified reachable: `curl http://localhost:<port>/api/health` returns framework payload.

---

## 6. Related files

- `products/mailing/backend/app/routers/health.py` — The file to delete (after diff).
- `seed/framework/backend/noctusai_seed/routers.py` — Contains `health_router` — the framework-supplied replacement. Confirm shape matches.
- `seed/framework/backend/noctusai_seed/app.py` — `create_product_app()` — auto-includes the framework health router; product `main.py` files inherit automatically.
- `products/mailing/backend/app/main.py` — Check for explicit `include_router(health.router)` — remove if present.
- `mcp/noctusai/tools/compliance.py` — `check_seed_compliance` — the detector that flagged this. Same check fires for `notificacoes.py`, `team.py`; the fix pattern documented here applies to all three.
