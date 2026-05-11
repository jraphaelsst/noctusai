# PF Auth Factory Migration + AI Rate-Limit — Project Document

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Done (Phase 1 + Phase 2 shipped, tests green, keeper clean)
- **Owner / stakeholders:** Architect (orchestrator) · Engineer PF-AUTH-MIG
- **Related docs:**
  - `KB § PATTERNS/backend.md § Auth — canonical pattern`
  - `seed/lib/backend/noctusai_lib/api/auth.py` (`make_get_current_user_org`)
  - `products/youtube-crawler/backend/app/dependencies.py` (canonical adopter)
  - `archive/projects/2026-05-04/04-daily-life-goals-seed-wiring/` (DL-P1 prior art)
  - `projects/ratelimit-coverage-audit-2026-05-11/` (RATELIMIT-AUDIT source)
- **Project slug:** `pf-auth-factory-migration` (cross-product scope → root `projects/`)

---

## §1 · Context

PF is the **originator** of `make_get_current_user_org` (per memory
`feedback_auth_factory_pattern` — N=2 PF/ERP recurrence formalized at
seed-lib level 2026-05-04), but until today still shipped an inline
`async def get_current_user_org(authorization: Optional[str] = Header(None))`
at `products/personal-finance/backend/app/dependencies.py:17-25`. The
inline body called `await get_current_user(authorization)` and resolved
`org_id` via `(user.user_metadata or {}).get("org_id")` — byte-identical
to the factory's `required=True` path.

Every PF router used the imperative pattern:

```python
async def listar_contas(
    ativo: Optional[bool] = Query(None),
    authorization: Optional[str] = Header(None),
):
    user, token, org_id = await get_current_user_org(authorization)
    db = get_user_client(token)
```

The canonical shape — already adopted by daily-life, youtube-crawler,
imobi-scheduling, mailing, and others — is:

```python
async def listar_contas(
    ativo: Optional[bool] = Query(None),
    auth: tuple = Depends(get_current_user_org),
):
    user, token, org_id = auth
    db = get_user_client(token)
```

Concurrent finding from `projects/ratelimit-coverage-audit-2026-05-11/`:
PF's `ai.py` (4 LLM-invoking endpoints) was uncovered by rate-limit,
exposing LLM-spend to abuse. ERP's `ai.py` (`@limiter.limit("30/minute")`)
is the reference adopter.

Both changes touch PF backend and are scoped tightly enough to combine
into one engineer brief.

---

## §2 · Interrogation log (Q→A from user)

This project was dispatched directly by the architect — no interrogation
ceremony. The two surfaced findings (WWW invalidation finding + post-
Wave 8 audit identifying PF as the lone non-factory adopter, plus
RATELIMIT-AUDIT identifying PF AI endpoints as uncovered) are the input.

---

## §3 · Goals

1. Lift PF onto the canonical `make_get_current_user_org` factory.
2. Migrate every PF router callsite to `Depends(get_current_user_org)`
   via libcst codemod (AST-first per KB).
3. Add `@limiter.limit("30/minute")` to all 4 PF AI endpoints +
   `request: Request` param (slowapi requirement).
4. Verify 595 → ≥595 pytest baseline + 0 NEW keeper issues.

### §3a Seed-first analysis

**Cross-product concern?** Yes — `make_get_current_user_org` already
lives in `noctusai_lib.api.auth`. This project is a **consumer-side
migration**, not a seed-extension. Per-product code-count for the
*authentication wrapper logic* drops from N=1 (PF's inline) to N=0
(everyone consumes the seed factory). Symmetry restored.

The rate-limit decorator is a stdlib-ish FastAPI surface — `limiter`
itself is already a seed primitive (`noctusai_seed.rate_limit.create_product_limiter`).
This project just adopts the decorator at the right call-sites.

---

## §5 · Files touched

### Phase 1 — Auth factory migration
- `products/personal-finance/backend/app/dependencies.py` —
  inline `async def get_current_user_org` replaced with
  `make_get_current_user_org(...)` factory call. `get_user_client`
  preserved as a late-binding wrapper (test patches `_db.get_client`
  AFTER module import).
- `products/personal-finance/backend/app/routers/{contas,transacoes,categorias,
  orcamentos,metas,carteira,ativos,operacoes,watchlist,recorrentes,
  patrimonio,relatorios,cotacoes,dashboard,ai}.py` — 15 routers,
  80 functions, 80 callsites migrated via libcst codemod.
  `Header` import dropped where it became unused, `Depends` added
  where missing.

### Phase 2 — AI rate-limit
- `products/personal-finance/backend/app/routers/ai.py` —
  4 endpoints decorated with `@limiter.limit("30/minute")` +
  `request: Request` param added. `from app.rate_limit import limiter`
  + `Request` import added (already had limiter wired in `main.py`).
- `products/personal-finance/backend/tests/routers/test_ai_router.py` —
  `TestRateLimit` class added (2 tests: 200 under limit, 429 over
  limit, both assert on `.status_code` per status-code-assertion rule).

---

## §6 · Phase plan

**Phase 1 — Auth factory migration (done)**
- 1.1 Rewrite `dependencies.py` to use `make_get_current_user_org`
  factory mirroring `youtube-crawler/backend/app/dependencies.py`.
- 1.2 Author libcst codemod (`/tmp/pf_auth_codemod.py`) — two-pass:
  Pass 1 rewrites function signatures + bodies (drop `authorization`
  param, add `auth` param, replace `await get_current_user_org(authorization)`
  with `auth`). Pass 2 fixes fastapi imports (add `Depends`, drop
  `Header` if unused).
- 1.3 Run codemod against `app/routers/` → 80 callsites migrated.
- 1.4 `pytest -q` → 595 passed, 10 skipped (baseline preserved).

**Phase 2 — AI rate-limit (done)**
- 2.1 Author libcst codemod (`/tmp/pf_ai_ratelimit_codemod.py`) —
  injects `@limiter.limit("30/minute")` AFTER each `@router.<verb>`
  decorator (slowapi requires the limiter decorator to be the
  innermost), adds `request: Request` as first param.
- 2.2 Run codemod against `ai.py` → 4 endpoints decorated.
- 2.3 Add `TestRateLimit` class with 200/429 pair.
- 2.4 `pytest -q` → 597 passed, 10 skipped (baseline + 2 new tests).

---

## §7 · Verification commands

```bash
cd products/personal-finance/backend && \
  PYTHONPATH="$PWD:$PWD/../../../seed/lib/backend:$PWD/../../../seed/framework/backend" \
  /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest -q

# Expected: 597 passed, 10 skipped

/Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python mcp/noctusai/cli.py \
  --review --product personal-finance --worktree-path "$PWD"

# Expected: 0 NEW keeper issues
```

---

## §11 · Change log

- 2026-05-11 — Engineer PF-AUTH-MIG dispatched (combined Pattern F migration
  + AI rate-limit). Both completed:
  - Pattern F: 80 callsites migrated (15 routers, 80 functions).
  - AI rate-limit: 4 endpoints decorated, 2 tests added.
  - pytest: 595 → 597 passed (baseline preserved + 2 new).
  - keeper: 0 NEW issues.
  - Codemods preserved at `/tmp/pf_auth_codemod.py` +
    `/tmp/pf_ai_ratelimit_codemod.py` for archival reference.
