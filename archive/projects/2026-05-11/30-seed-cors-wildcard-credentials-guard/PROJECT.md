# seed-cors-wildcard-credentials-guard — Project Document

> **Living document.** Per CLAUDE.md §1, project docs evolve as we learn.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 1 complete (guard shipped + tests green + KB amended). Ready for orchestrator FF-to-main.
- **Owner / stakeholders:** Architect (orchestrator) · Engineer SEED-GUARD
- **Related docs:**
  - CORS-AUDIT findings (commit `9754871` on main)
  - Parallel projects: CORE-ORIGINS (enumerates `products/core/backend/app/config.py` origins); ENV-EXAMPLE (adds `CORS_ORIGINS` slot to `.env.example`)
  - KB § PATTERNS/environment.md § CORS_ORIGINS cascade (amended)
- **Project slug:** `seed-cors-wildcard-credentials-guard`
- **Location:** `projects/<slug>/` (cross-product seed-platform hardening)

---

## 1. Context & Purpose

The CORS audit on 2026-05-11 surfaced a CRITICAL gap in the seed bootstrap: `noctusai_lib.api.app_factory.configure_app()` hardcoded `allow_credentials=True` while `BaseAppSettings.cors_origins_list` accepted `cors_origins="*"` via the explicit `if self.cors_origins == "*": return ["*"]` branch. Together those two facts made the textbook auth-replay vulnerability *the default boot path* — any product setting `CORS_ORIGINS=*` (which `products/core/backend/app/config.py` did) shipped with browsers willing to attach credentialed requests for any origin.

**Win:** Refuse the dangerous combination *at boot, not at request time*. Loud crash beats silent compromise. Production must enumerate origins; local-dev override is a single env var with a LOUD warning.

---

## 2. Confirmed constraints

- **Refuse at boot, not at request** — *(brief failure is loud, audit-visible, blocks deploy; request-time misbehavior is invisible until exploited)*.
- **Escape hatch required** — *(local dev tooling sometimes legitimately needs `*` + credentials; killing the option entirely would force agents to bypass the guard later. Env-var override with LOUD warn keeps the path traceable.)*
- **Per-product label in error** — *(the auditor surfaced N=1 core breakage immediately; the guard's error message must name which product is misconfigured so the cascade fix is obvious.)*
- **Wildcard + credentials=False stays legal** — *(public-read APIs are a real shape; the guard targets the *combination*, not wildcards in isolation.)*

---

## 3. Design principles

1. **Default-deny.** Boot crash by default when the combination is detected; opt-in to override.
2. **Single seam.** Guard lives in seed `configure_app()` — every product inherits via `create_product_app()`. Per-product code count = 0.
3. **Verifiable.** 10 tests cover the truth table (combination matrix × env override × truthy/falsy values × product-name surfacing).
4. **Audit-friendly error.** Error message names the vulnerability, the fix, the product, AND the override path.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every product?** YES — every product mounts CORSMiddleware via the same seed factory. The vulnerability is universal.
2. **Is the data source product-specific?** NO — uniform: `settings.cors_origins_list` shape is identical across products.
3. **Is the placement product-specific?** NO — universal: lives in `app_factory.configure_app()`.
4. **Is the visibility / permission rule the same?** YES — uniform refusal at boot.
5. **Does the seam already exist in seed?** YES — `noctusai_lib.api.app_factory.configure_app()` (the CORS section is the natural anchor; we extended the function signature with two kw-only params).
6. **Default-on or opt-in?** DEFAULT-ON — universally beneficial; opt-out via `NOCTUSAI_ALLOW_CORS_WILDCARD_WITH_CREDS=1` for local dev.

**Per-product code count:** **0 lines.** Pure cross-product concern. Products inherit through the factory. CORE-ORIGINS is fixing core's *misconfiguration*, not the guard.

---

## 5. Files touched

- `seed/lib/backend/noctusai_lib/api/app_factory.py` (+57 / −1)
  - Add `import os`.
  - Add 2 kw-only params: `allow_credentials: bool = True`, `product_name: str | None = None`.
  - Insert guard block between Rate-limiting and CORS sections.
  - Pass `allow_credentials` to `CORSMiddleware` (was hardcoded `True`).
  - Docstring updates for new params + `Raises:` section.
- `seed/lib/backend/tests/api/test_cors_wildcard_credentials_guard.py` (+170 new)
  - 10 tests covering the truth table.
- `KNOWLEDGE-BASE/CONTEXT/PATTERNS/environment.md` (+25)
  - Amend `## CORS_ORIGINS cascade` with `### CORS wildcard+credentials guard` subsection (vulnerability description, escape hatch, legitimate combinations table, test pointer).

---

## 6. Phase plan

### Phase 1 — Guard implementation + tests + KB (DONE)

1. AST-first edit via libcst transform (`/tmp/cors_guard_transform.py`) — add params, insert guard block, rewrite `allow_credentials=True` → `allow_credentials=allow_credentials` in CORSMiddleware call.
2. Cosmetic cleanup via exact-string Edit (libcst formatter reshuffles whitespace; aesthetic-only fixes for import ordering, signature wrap, section-comment restoration).
3. Author 10 tests in `tests/api/test_cors_wildcard_credentials_guard.py` covering: vulnerability rejected, legitimate shapes boot, env override with LOUD warn, truthy/falsy env values, product-name fallback chain.
4. KB amend `environment.md § CORS_ORIGINS cascade` with new subsection.
5. `pytest tests/api/` → 24 passed (14 baseline + 10 new). `pytest tests/test_max_body_size_middleware.py` → 5 passed (regression baseline).
6. Live-verify: seed defaults boot cleanly; wildcard+credentials shape raises RuntimeError with vulnerability description.

**Improvements (in-scope):**
- Surfaced `product_name` fallback chain (explicit kwarg → `settings.product_name` → `<unknown>`) for traceability.
- Override accepts case-insensitive `1`/`true`/`yes`; anything else still blocks (defensive — typoed `truee` should NOT silently activate).

### Phase 2 — Orchestrator FF-to-main (BLOCKED on parallel agents)

- Per §16/§17 branching methodology: engineer branch-pushes; orchestrator does fresh-eyes diff + FF-to-main.
- CORE-ORIGINS engineer must land FIRST (or simultaneously) — without their fix, the seed guard will crash core at boot. That's the *point* of the fix, but co-merging avoids a transient red main.
- ENV-EXAMPLE engineer's `.env.example` adds the `CORS_ORIGINS` slot referenced in the KB amendment — co-merge as a courtesy.

---

## 7. Open questions

(None outstanding — brief was unambiguous.)

---

## 10. Commands

```bash
# Verify guard test suite
cd seed/lib/backend
PYTHONPATH=$PWD /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python \
  -m pytest tests/api/test_cors_wildcard_credentials_guard.py -q

# Verify no regression in existing configure_app baseline
PYTHONPATH=$PWD /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python \
  -m pytest tests/api/ tests/test_max_body_size_middleware.py -q

# Smoke: seed defaults boot cleanly
PYTHONPATH=$PWD /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -c "
from types import SimpleNamespace
from fastapi import FastAPI
from noctusai_lib.api.app_factory import configure_app
settings = SimpleNamespace(
    cors_origins_list=['http://localhost:5173'],
    sentry_dsn='', is_production=False, debug=True,
)
configure_app(FastAPI(), settings)
print('OK')
"
```

---

## 11. Change log

- **2026-05-11 (Engineer SEED-GUARD)** — Phase 1 complete. Guard shipped (`configure_app` + 2 kw-only params + boot-time RuntimeError + env override + LOUD WARN). 10 tests green. KB amendment landed at `environment.md § CORS wildcard+credentials guard`. Findings captured at `projects/seed-cors-wildcard-credentials-guard/findings.md`.

---

## 12. Lessons (synthesized at close)

(Filled in by orchestrator at project close — see `findings.md` for the live in-the-moment log.)
