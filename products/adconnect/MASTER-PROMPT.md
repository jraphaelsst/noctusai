# AdConnect -- Master Prompt

## Purpose

B2B marketplace connecting a brand to its distributor network. Distributors log in, browse the brand's catalog at preferential prices, build a cart, place orders, file sellout reports, and earn cashback on qualifying sellout. The brand-side admin manages catalog, distributors, reward rules, and reviews sellout/financial state.

## Architecture

- Schema: `adconnect`
- Backend port: 8007 | Frontend port: 8130
- Tenant key: `org_id`
- Auth: TBD by implementation project — current scaffold ships custom JWT for distributor self-registration; the production auth model (single-org SSO vs. distributor-as-external-org) is one of the questions the implementation project resolves.
- Backend path: `products/adconnect/backend/app/`
- Frontend path: `products/adconnect/frontend/src/`

## Key Domains

### Catalog and ordering
- **products** -- brand catalog browsing with category, search, sort, in-stock filtering. Today reads from `app/data/products.json`.
- **cart** -- per-distributor cart, line-level quantity edits, totals. Today in-memory in `store.users` / `store.orders`.
- **orders** -- order placement (cart → order), order history, status lifecycle.

### Rewards and sellout
- **sellout** -- distributors file sellout reports (the input that proves resale to end-customer). Today reads `app/data/sellout-reports.json`.
- **rewards** -- cashback rules + accrual ledger; reward rules live in `app/data/reward-rules.json`. The accrual logic is a candidate for `noctusai_lib.domain.rewards` extraction once it stabilises (recurrence rule will fire on N=2 if mailing/PF use a similar engine).

### Brand-side operations
- **financial** -- invoices, payment terms, ledger of charges/payments. Today reads `app/data/invoices.json`.
- **distributors** -- distributor account list and detail; brand admin views and manages.
- **admin** -- brand-side administration surface.

### Auth
- **auth** -- distributor invitation acceptance + `/me` endpoint. Custom JWT retired (Option A locked in Phase 0); SSO consumed via canonical `app/dependencies.py` (`make_get_current_user` + `make_get_current_user_org` + `make_require_role` factories), the 3-product-formalized shape mirroring `products/erp-imobiliario/backend/app/dependencies.py` + `products/personal-finance/backend/app/dependencies.py` + `products/youtube-crawler/backend/app/dependencies.py`. The dict-wrapper `app/auth_deps.py` retired 2026-05-11 in `projects/adconnect-migration/` Phase 2; every router consumes `Depends(get_current_user_org)` returning a `(user, token, org_id)` triple.

## Production state (post-MVP, 2026-05-10)

Backend 100% Supabase-backed. Single `001_adconnect.sql` builds the full schema (16 tables in topological order: identity → catalog → sellout → orders → rewards → financial). All routers DB-backed with constructor-time `prefix=` (FastAPI 0.115 wildcard-route bug structurally fixed). Frontend ships 9 distributor pages + 5 React Query hooks against live endpoints.

- ✅ 208 mock-backed tests passing; realdb suites scaffolded; 9 LGPD flags landed.
- ✅ Brand admin V1 operates the marketplace via `/api/admin/*` — V2 (brand-side UI) ≡ separate follow-up project.
- ✅ NF-e issuance via `FocusNFeProvider` Real adapter (lazy-imported httpx; sandbox vs prod via `ambiente=`); cancel + status round-trip implemented.
- ✅ Stripe pattern inherited from `products/core` (cross-product Python import infeasible; SDK called directly with idempotency keys derived from `fatura.id`).

## Rules

- Seed framework non-negotiable — domain routers attach through `create_product_app()`'s `routers=[...]` seam. ¬ re-wire CORS, exception handlers, or middleware locally.
- Single `001_adconnect.sql` is the fresh-start migration. Schema changes edit 001 in-place ∧ ship additive `002+` patches for live DBs (single-001 convention; → `KB § PATTERNS/database-rls.md`).
- Constructor-time `APIRouter(prefix=...)` everywhere. ¬ `router.prefix = ...` post-construction (FastAPI 0.115 silently no-ops it — Phase 2-6 structural fix).
- Module-level `from ..database import X` binds at import time ∧ defeats conftest patches. Use `_db.get_client()` lazy attribute access in services.
- Recurrence on rewards/sellout/financial/NF-e primitives ⇒ absorb to `noctusai_lib.domain.*` per the recurrence rule if mailing/PF/ERP grow similar engines.
- LGPD-first: distributor PII (CNPJ, addresses, financial state, NF-e XML) flagged at every write site via `noctus.dev.lgpd_flag`.
- Rate-limit policies: prefer named imports from `noctusai_lib.api.rate_limit_policies` (`DEFAULT_AI_RL` / `DEFAULT_AUTH_RL` / `DEFAULT_WEBHOOK_RL` / `DEFAULT_PORTAL_RL`) over inline `"30/minute"` literals. Adconnect already config-drives the financial webhook (`settings.webhook_rate_limit`); future limiter decorators adopt the canonical module so per-policy tuning lifts to one seed-side change.
- Doc-code coherence: tool/script/MCP-tool Δ referenced here ⇒ update this MASTER-PROMPT in the same commit — discover drift via `grep -rn "<tool-name>" products/adconnect/`. (CLAUDE.md §1 — doc-code coherence rule.)

## Testing

```bash
cd products/adconnect/backend && pytest
cd products/adconnect/frontend && npx vite build
```

Framework-test suites inherit from `noctusai_lib.testing` (FrameworkEndpointsSuite / TeamFlowSuite / NotificationFlowSuite / AuthBoundarySuite). Adconnect overrides `TeamFlowSuite.test_list_members_returns_data` because the product's `client` fixture binds `MockUser(org_id=ORG_ID_BRAND)` ≠ seed-default `test-org-123`. As of 2026-05-11 the suite ships an `expected_org_id: ClassVar[str]` class attribute — override simplifies to `expected_org_id = ORG_ID_BRAND` (¬ method override). Follow-up cleanup tracked under recurrence-rule N=2+ if other products surface the same shape.

Seed mocks: `MockSupabaseClient` (2026-05-11) deep-copies caller inputs at storage time so UPDATE ∨ DELETE write-propagation ¬ mutates module-level fixture dicts; `_eval_is` handles PostgREST IS-NULL semantics; `_FilterMixin.not_` actually negates. Adconnect tests hitting `.is_(..., None)` ∨ `.not_(...)` ¬ need local workarounds.

## Common commands

- Compliance review (LGPD / webhook-pins / status-assertion / 10 new detectors added 2026-05-11): `noctus.dev.review --product adconnect`. New detectors: `check_doc_tool_reference_drift` (this doc), `check_no_silent_ok_comment`, `check_auth_dep_anti_pattern`, `check_mcp_path_via_settings`, `check_mcp_write_tool_worktree_arg`, `check_pipefail_grep_q`, `check_archive_staleness`, `check_dispatcher_staleness`, `check_branch_orphan`, `check_gitignore_drift` — live inventory: `noctus.dev.outline_python mcp/noctusai/tools/noctus/dev/compliance.py`.
- Cleanup triage (cross-product ∨ cross-tool ∨ intra-file hygiene): `noctus.hound.scan`.
- Storage triage (artifacts ∨ environments ∨ stale worktrees): `python mcp/noctusai/cli.py --mole scan`.
- Fresh-clone bootstrap auto-hydrates every `products/*/backend/requirements.txt` into the shared venv (`scripts/bootstrap-worktree.sh` + `scripts/setup.sh`, 2026-05-11) — ¬ per-product `pip install -r` step needed.

## Dependencies

- Backend: `noctusai_lib` (code library) + `noctusai_seed` (framework)
- Frontend: `@noctusai/lib` (code library) + `@noctusai/seed` (framework)
