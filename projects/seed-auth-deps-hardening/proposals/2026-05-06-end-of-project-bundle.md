# seed-auth-deps-hardening — End-of-project bundle

Date: 2026-05-06
Owner: engineer-agent (worktree `seed-auth-deps-hardening`)
Status: ready for architect review

---

## Applied inline (this project)

1. **Factory wiring in workspace YouTube Crawler** — `products/youtube-crawler/backend/app/dependencies.py` now uses `make_get_current_user_org` with a late-binding lambda. Both routers in the workspace (`upload_router.py` + `settings_router.py`) refactored to `Depends(get_current_user_org)`. Workspace tests stayed green throughout (94 → 112 as parallel-agent test files landed; all passing). Note: only `dependencies.py` is committed on this branch — the two router files live on parallel sh-yt-* branches; the architect's FF-merge will reconcile.

2. **OAuth callback fix** (drive-by) — discovered `youtube_oauth_callback` was using `Depends(get_user_client)` which would fail on every Google redirect (no Authorization header → 422 query-param trap). Switched to `get_admin_client()` with state-token tenant binding. Pre-existing latent bug, not a regression.

3. **Late-binding pattern in `app/dependencies.py`** — `lambda: _db.get_client()` instead of capturing `_db.get_client` at module load. Applied in workspace + worktree. Resolves the module-load vs conftest-patch ordering problem; documented in the canonical KB pattern.

4. **Frame-aware DeprecationWarning** — `seed/framework/backend/noctusai_seed/dependencies.py` now wraps `get_org_id` / `get_user_role` / `get_user_client` with `_warn_if_fastapi_caller(qualname)` that fires only when `fastapi.dependencies.utils` is the immediate caller. Honors PROJECT.md §3 design principle 3 strictly. Regression suite at `seed/framework/backend/tests/test_dependencies_deprecation.py` (4 tests).

5. **Three-way sync** — `KB § PATTERNS/backend.md § Auth — canonical pattern` rewritten with full code blocks + anti-patterns + migration history; CLAUDE.md §3 row added; `feedback_auth_factory_pattern.md` memory entry + MEMORY.md index line. `bash scripts/verify-kb-sync.sh` green.

---

## Deferred — destinations named

### A. Cross-product rollout (PF / Therapy / Mailing / AdConnect / ERP / Daily Life / Personal Finance / Media Scheduling / Therapy Platform)

**Status:** explicitly deferred per PROJECT.md §4 "Out of scope".
**Destination:** **file follow-up project `seed-auth-deps-cross-product-rollout`** after the keeper-detector Project (`keeper-test-status-assertion` or its successor) lands. The detector catches new occurrences of `Depends(get_org_id)` automatically, which makes the rollout safer.

**Why ordering:** if rollout lands first without the detector, any product that gets missed silently keeps the bug. With the detector, every PR introducing the broken shape gets flagged.

### B. Seed-internal team_router migration to the factory

**Status:** deferred — seed's own `team_router` (in `seed/framework/backend/noctusai_seed/routers.py`) calls `deps.get_user_role(user)` + `deps.get_org_id(user)` imperatively at lines 112, 123, 178, 188, 199. These calls are SAFE (imperative shape works fine), but they are an N=2+ recurrence with the workspace product's pre-Phase-1 state — the seed itself should consume the canonical pattern.

**Destination:** absorption candidate; logged here. Not filed as a separate project because the work is small (~20 lines, single file) and naturally part of a future seed-cleanup pass. Architect may choose to fold into `seed-auth-deps-cross-product-rollout` or apply inline.

### C. Keeper-detector for `Depends(<broken_seed_dep>)`

**Status:** explicitly out of scope per the dispatch brief (the parallel `keeper-test-status-assertion` engineer owns the AST-detector infrastructure).

**Destination:** new follow-up project once `keeper-test-status-assertion` lands. The detector should AST-walk product router files looking for `Depends(get_org_id)` / `Depends(get_user_role)` / `Depends(get_user_client)` patterns and surface them as warnings. This closes the third defense layer.

### D. shadcn UI absorption into `noctusai_lib/frontend/ui` (N=4 confirmed)

**Status:** spotted while reading the workspace findings.md — `components/ui/*.tsx` files are duplicated across products (PF, Therapy, AdConnect, YouTube Crawler). N≥3 already, N=4 with workspace YT Crawler.

**Destination:** out of scope here; logged as catalog candidate. The cross-product rollout project may include this if the architect wants to bundle.

### E. ProductDependencies cleanup — eventual deletion of broken methods

**Status:** PROJECT.md §4 explicitly defers deletion. The DeprecationWarning has shipped today; one+ release cycle of warning life is the correct cadence before deletion.

**Destination:** new follow-up project `seed-auth-deps-deletion` after the cross-product rollout completes. Filed as a future project; not actionable until rollout closes.

---

## Verification snapshot

| Suite | Result | Note |
|---|---|---|
| `cd products/youtube-crawler/backend && pytest` (workspace) | **112/112 passed** in 0.40s | 2 unrelated pre-existing warnings (multipart, utcnow) |
| `cd seed/framework/backend && pytest` (noc-main) | **37/37 passed** in 1.28s | +4 from new `test_dependencies_deprecation.py` |
| `cd products/seed/backend && pytest` (noc-main) | **31/31 passed** in 0.23s | |
| `cd mcp/noctusai && pytest tests/` | **738 passed / 4 failed** in 85.90s | All 4 failures pre-existing (dev-team E2E, openai version drift, ERP monkey-patching, seed-version stamp drift) — none caused by this project's changes. |
| `cd products/youtube-crawler/frontend && npx vite build` (workspace) | **✓ built in 3.07s** | No API contract change; expected pass |
| `bash scripts/verify-kb-sync.sh` | **✓ green** | All CLAUDE.md pointers resolve, all KB docs indexed, Layout tree current |

---

## Notes for architect FF-merge

1. **Noc-main worktree (`/Users/rapha/Documents/repository/NoctusAI/noctusai`) has uncommitted bytes** in `seed/framework/backend/noctusai_seed/dependencies.py` — these are the mirror of my Phase 2 edit applied so the workspace runtime could test (workspace's `seed/` symlink points there). Architect can either (a) discard the noc-main worktree changes (`git -C /Users/rapha/Documents/repository/NoctusAI/noctusai checkout -- seed/framework/backend/noctusai_seed/dependencies.py`) before FF-merging my branch (the FF-merge will then re-apply the same bytes via my commit), or (b) accept them as the same content my commit will produce.

2. **Two commits ahead of origin/main** plus the project filing commit (`b3bdb87`):
   - `1b743cf` Phase 1 — wire factory in YouTube Crawler
   - `c00fb49` Phase 2 — deprecate broken seed export
   - `4a9da53` Phase 3 — three-way sync of auth pattern
   - (Phase 4 close commit will follow this proposal)

3. **The two router files (`upload_router.py`, `settings_router.py`) at `products/youtube-crawler/backend/app/routers/`** are NOT in this branch — they live on parallel sh-yt-* branches. Architect's eventual FF-merge of those branches plus this one will produce the full picture.

4. **Pre-commit's seed-version-stamp** is one commit behind by design (chicken-and-egg). After the architect's FF-merge to main, running `bash scripts/stamp-seed-version.sh && git commit ...` (or letting the next commit auto-stamp) brings the version-static files current.
