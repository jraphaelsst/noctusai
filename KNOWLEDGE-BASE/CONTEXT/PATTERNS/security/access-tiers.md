# Access tiers — every route and every table declares who may touch it; undeclared is refused

> **Why this exists (2026-11-05).** The owner found a competitor's full system prompt in their web app's network requests; our own audit found the same class here: (P1-A) the `agents` schema is exposed to PostgREST and `authenticated` kept `SELECT` on every definition table (`compiled_prompts`, `agent_prompt_sections`, `agent_skills`, `agent_skill_files`, `agent_versions`, `eval_*`, `knowledge_*`, `agent_audit_log`) behind an *org-only* policy, so any non-admin member of the platform org could read Julia's whole prompt without touching the API; (P2-B) the studio eval-run routes used `require_publish_read` (every member role) while their docstring said "platform admin only". Both were *classification* misses: nothing forced the author to say whose the data is. This pattern forces the sentence, then a keeper checks it.

## The rule

**Every HTTP route and every DB table declares an access tier. A route or table without one is refused (default deny).**

| Tier | Whose | Who may touch it | Examples |
|---|---|---|---|
| **`platform`** | **Platform IP** — what NoctusAI builds and operates | Global platform admins (`noctus_users.role='admin'`, or the platform's own staff role) or the service role. **Never** a customer user, never a non-admin member of the platform org. | Agent prompts, sections, skills, tool descriptions, evals + judges, compiled prompts, canaries/markers, model + runtime config, internal tooling, other customers' data in aggregate. **Julia is `platform`**: only the owner edits her. |
| **`org`** | A customer's own data | Members of that org, with the role checks the product defines | Their leads, posts, spec values, settings, their own spend |
| **`service`** | Machine-to-machine, incl. the **signed** routes reachable from the network | Product / channel tokens; or a handler that runs a verification call | `pk_*` tokens, channel tokens; vendor webhooks (HMAC/Svix/Stripe), OAuth callbacks (`state` verified), health (`/api/health`, no data) |
| **`public`** | Intentionally anonymous — a **CLOSED allowlist** (below) | Anyone | Landing, login/signup, pricing/checkout/thank-you, legal/consent, lead capture |

Corollaries:
- **A route below `platform` never returns a Platform-IP field** (compiled prompt, sections, canary, judge rubric, tool descriptions…). A response model that carries one is as open as the weakest dependency in front of it.
- **A Platform-IP table has no `authenticated`/`anon` grant and no `TO authenticated`/`PUBLIC` policy** — service role only — unless a policy checks platform admin. **PostgREST exposure counts**: an `authenticated` `SELECT` grant plus an org-scoped policy is a read API for the whole org (that is P1-A). Reading must go through the API, which has the admin dependency.
- **The strongest gate wins.** A route behind `require_member` AND `require_platform_admin` is `platform`.
- **Org-admin is not platform-admin.** `require_admin` (org owner/admin) never satisfies `platform`. A platform org has many ordinary members and end customers.

## The public tier is a closed allowlist (owner, 2026-11-05)

Public = landing/marketing pages + their navigation (`landing`) · login, signup, password reset/recovery (`auth`) · pricing, checkout, thank-you (`pricing-checkout`; the thank-you page shows no order/PII without a signed or one-time token) · privacy, terms, data deletion — seed-mounted, Meta/Google review need them (`legal-consent`) · lead forms and newsletter on those pages (`lead-capture`). **Every other route is access-level.** Declare with `@access_tier("public", reason=..., category=<one of the five>)`; any other category, or none, is refused by the guard and the keeper, and the catalog groups the public routes by category so the owner reads the whole list in one pass.

Not anonymous although network-reachable (tier `service`, **signed**; the handler must run a verification call): vendor webhooks (`verify_hmac_*`, `verify_svix_*`, `webhook_endpoint`, …), OAuth callbacks (a `verify_state`-class call that ALSO passes the browser binding: `consume_state(state, binding=<cookie>)` — a state that only proves "this server issued it" lets an attacker hand their consent URL to a victim and link the victim's grant to the attacker's org; seed `OAuthStateStore` issues the nonce, keeper reads the `binding=` keyword; pre-existing unbound callbacks are rows in the access-tier ledger), health checks. Rules for every public API: returns only fields meant for the public · rate-limited (keeper requires a limiter) · a public write (signup, lead form, checkout) carries abuse protection (captcha/turnstile/honeypot) · never reads a table through the `anon` role when the table has token, secret or PII columns.

## The measures, each with its construction mechanism and its gate

| # | Measure | Construction (path of least resistance) | Gate (backstop) |
|---|---|---|---|
| 1 | Every route/table declares a tier; default deny | `noctusai_lib.api.access_tiers` (`DEP_TIERS`, `@access_tier`); seed example routers already gated; `scaffold_migration` emits `COMMENT ... 'tier:org'` + `REVOKE` | **write-time** `claude-guard-access-tier.py` (PreToolUse, fail-closed) · **commit** `check_access_tier_routes` · pre-commit |
| 2 | Platform-IP tables have no browser grants; no new table inherits default privileges | migration scaffolder emits explicit REVOKE, no browser GRANT by default; `COMMENT ON TABLE … 'tier:platform'` | `check_access_tier_tables` replays EVERY product's chain (grants, revokes, default privileges, policies); a NEW table needs a tier comment AND an explicit GRANT/REVOKE; `test_agents_browser_lockdown_probes_on_replay.py` is the agents-specific probe |
| 3 | Exposure verdicts come from EFFECTIVE state | `noctus.dev.access_tier_exposure` / `--access-tier-exposure` hands out the read-only queries (role_table_grants, pg_policies, pgrst.db_schemas, secret-like columns) and diffs the rows against declared tiers; `noc-daily-ops` step 2b and the security audit call it | drift is a finding; a missing input is `unmeasured`, never green. Classes: (a) anon/PUBLIC policy on a secret-column table — critical; (b) PUBLIC `USING (true)` while anon holds the grant; (c) a browser grant on a table not declared `tier:org|public`; (d) an INACTIVE product's schema served by the data API |
| 4 | LLM partial/delta output reaches a browser only through the leak filter | the filter (`FiltroDeltas`; seed-first when a streaming organ exists in seed/lib) named in `LEAK_FILTER_NAMES` | `check_access_tier_streams` (AST: a `message.delta` publish whose function never names a filter) |
| 5 | Everything prompt-derived is a leak-fingerprint source | one seam: `texto_fonte_do_prompt` in `channels/conformidade.py`; every agent tool classified `PROMPT_DERIVED_TOOLS` → source or `NOT_PROMPT_DERIVED_TOOLS` | `check_access_tier_fingerprint` (seam references every source key — aliases in `LEAK_FINGERPRINT_SOURCES`; unclassified tool refused; missing seam = unmeasurable, never green) |
| 6 | Studio/definition routes are platform-admin only | `PLATFORM_IP_ROUTES` path shapes + `PLATFORM_IP_FIELDS` response fields | the route keeper marks `require_publish_read`-class (member-role) deps on definition/eval content `too-open` |
| 6a | A scoped service token is the `service` tier of a platform route | `require_evals_run_access` / `_cancel` (`products/agents`): the platform-issued `studio:evals-run` token starts / lists / reads / cancels eval runs (both suites), nothing else. Mint: `POST /api/studio/plataforma/content-token` `{label, tipo: "avaliacoes"}` (platform admin, 1..30 days, issuer `noctus-platform`, raw secret returned once) | both deps map to `platform` in `DEP_TIERS`; tests assert strict 401/403 |
| 7 | Strict auth assertions | assert `== 403` + `code == 'platform_admin_required'` | `check_auth_boundary_false_green` now also flags `in (403, 404|422)` (write-time via `test_seam_guard` too) |

**Seams other branches must keep** (names the keepers read): `texto_fonte_do_prompt` (+ `texto_fonte_do_prompt_*` helpers) in `products/agents/backend/app/channels/conformidade.py` must reference the sources `textos`, `ferramentas`, `decisoes`, `skills` (skill bodies, incl. library skills), `skill_files`; the publish site of `message.delta` must name `FiltroDeltas` (or another `LEAK_FILTER_NAMES` entry). Landing those fixes turns the matching ledger row stale — run `cli.py --findings-ledger-reconcile access-tier` in the same commit.

## Burn-down, not grandfathering

The debt at landing and every later finding live in the **living findings ledger** `project-history/access-tiers/findings.ndjson` (rendered `FINDINGS.md`, trend in `metrics.ndjson`; mechanism: `KB § PATTERNS/common/living-findings-ledgers.md`; sections `routes · tables · grants · streams · fingerprint · schema`, grouped by product = the burn-down per-product fix slices dispatch from). Scope is every backend (active AND asleep products, seed, core, lib): asleep code is served the day it wakes. A fix closes its row through the tool (`reconcile` closes what the scanners no longer see); a new violation has no row and fails.

## How to declare (least invasive first)

**Routes** — registry + marker in `seed/lib/backend/noctusai_lib/api/access_tiers.py` (stdlib-only; the keeper loads the same file):
1. **Reuse a dependency that already says it.** `DEP_TIERS` maps the shared gates to tiers (`require_platform_admin*`, `get_current_admin`, `get_website_editor` ⇒ `platform`; `get_current_user_org`, `require_member`, `require_admin`, `get_auth_context` ⇒ `org`; `require_scopes(...)` by its arguments). A product dependency that *composes* these (a function with `Depends(...)`, `X = require_scopes(...)`, or a body that calls a gate) resolves transitively — **no entry needed**.
2. **Mark what no dependency says**: `@access_tier("public", reason="pricing page", category="pricing-checkout")` directly under the route decorator (public needs `reason` AND a category from the allowlist above). Signature-verified handlers (`verify_hmac_*`, `verify_svix_*`, `webhook_endpoint`…), `state`-verified OAuth callbacks and health probes (`/health`, `/_ready`…) resolve to tier `service` (signed) by themselves — no marker.
3. **New Platform-IP route shape?** Add its path regex to `PLATFORM_IP_ROUTES[<product>]` (and response field names to `PLATFORM_IP_FIELDS`). A route matching one that resolves below `platform` is **too-open**.

**Tables** — a migration-level convention (no new infrastructure):
`COMMENT ON TABLE agents.my_table IS 'tier:platform';` — in the same migration that creates it. Existing Platform-IP tables are matched by `PLATFORM_TABLES` globs. For a `platform` table: `REVOKE ALL ON <t> FROM authenticated, anon;` and no browser policy (or one that checks `noctus_users.role = 'admin'`).

## The keepers (gate ships with its mechanism — `gate-methodology-sync`)

| Keeper | CLI | Catches |
|---|---|---|
| `check_access_tier_routes` | `--check-access-tier-routes` | a route in ANY product (active or asleep) that resolves to no tier (`unclear`), a Platform-IP route behind a weaker dependency (`too-open`), an admin-looking path behind `org`/`public` |
| `check_access_tier_tables` | `--check-access-tier-tables [--paths <new migrations>]` | a Platform-IP table with an `authenticated`/`anon` grant or a non-admin `TO authenticated`/`PUBLIC` policy (static replay of the migration chain: grants, revokes, default privileges, policies, `ALTER POLICY`); with `--paths`, a NEW table with no tier declaration |

Both run in `scripts/hooks/pre-commit` when the route surface / migrations are staged. They are **ratcheted by the ledger**: a violation with no live row (open · in-progress · accepted) is NEW and fails; the existing ones are open rows (each listed as a `NOC-REMEDIATE[access-tier]` item in the generated catalog). Heuristic classes (`policy-pii`, `browser-grant`) are recorded but warn-only. Fixtures: `mcp/noctusai/tests/test_access_tiers_keeper.py` (red + green against the real registry).

## The endpoint catalog (derived, never hand-edited)

`python mcp/noctusai/cli.py --access-tier-catalog [--write]` / tool `noctus.dev.access_tier_catalog` classifies EVERY endpoint of every product (active or asleep) — product, method, path, resolved gates, tier, Platform IP yes/no, verdict (`ok | too-open | unclear`) — into `project-history/access-tiers/endpoint-catalog.md`. Regenerate after touching routes. Read it before adding a route near a studio/admin surface.

## Limits (state them, don't hide them)

Static inference: it follows `Depends` chains, `X = factory(...)` assignments, gate-shaped helper calls and `@access_tier`; a gate it cannot see (a closure built at runtime, an inline `if role != ...` with an unrecognised helper) shows up as `unclear`, never as `ok` — **unmeasurable is never green**. The path/field lists are the *known* Platform-IP shapes; a new Platform-IP surface needs its entry (step 3) — the review question is always "whose is this data?". Table analysis does not evaluate `DO $$ ... format(...) $$` dynamic DDL; write grants/policies as explicit statements.

## Review checklist (one line each)

- Whose is the data, in one word — `platform | org | service | public`? Is that word what the route/table declares?
- Does any response carry a prompt/section/canary/rubric/tool-description to a caller below `platform`?
- Does the gate in front say *platform admin*, or merely *member*/*org admin*?
- New table: tier comment present? `authenticated` grant / policy absent for Platform IP?

Related: `KB § PATTERNS/compliance/org-config-isolation.md` (org data never crosses orgs; this pattern is the orthogonal *platform vs customer* axis) · `KB § PATTERNS/compliance/auth-boundary-false-green.md` (prove the 401/403 with a strict assertion) · `KB § PATTERNS/backend/database-rls.md` · `KB § PATTERNS/common/gate-methodology-sync.md`.

## API docs are public; the schema is clean and every documented route is enforced (owner, 2026-11-05)

`/docs` and `/openapi.json` stay **public in prod** — so the safety is in what they contain and in what is behind them:
1. **Platform-tier routes are left out of the public schema by construction**: `make_router(tier="platform", guard=...)` sets `include_in_schema=False`; the ledger class `platform-in-public-schema` (`analyze_schema_exposure`, AST-precise, per router) tracks the legacy routers that still list Platform IP. Only a platform-admin-gated docs view may show them.
2. **Nothing sensitive in the schema**: `noctusai_lib.testing.openapi_tier_contract.schema_leaks / assert_schema_clean(app, platform_paths)` — no secrets, no internal hostnames (`*.internal`, `localhost`, private ranges, Supabase project hosts), no prompt/skill text or over-long descriptions/examples, no stack traces in error responses, no platform-tier route present.
3. **Documented ⇒ protected, proven**: `assert_tier_contract(client, tiers, org_headers=...)` walks the app's own OpenAPI document; for every operation not public/signed an unauthenticated call is strictly `== 401` (a 404/422 is never accepted) and a platform route with an org user is strictly `== 403`; a documented route with no declared tier is a failure (default deny). `tiers` comes from `noctus.dev.access_tier_catalog` (the catalog IS the expected map). Each product's CI runs both helpers against its own app (backstop; the construction leg is `make_router`). Adoption per product is an open burn-down item (0 of the 19 backends today; the helper + a pilot test on the seed template are the first step).

## Decision records — standard tool vs ours (owner: "we switch where standard tools perform better on metrics")

Measured 2026-11-05 on this tree (2935 routes in 19 backends, 991 tables scanned). A candidate is adopted only when it earns its keep; unmeasured ⇒ keep what we have, log it open.

| Candidate | Measured | Decision |
|---|---|---|
| **FastAPI native `APIRouter(dependencies=[Depends(guard)])`** (OWASP FastAPI cheat sheet) vs what seed has | seed's `create_dependencies` supplies auth deps but declares no tier and enforces nothing at construction (0 of 2935 routes carry a typed tier today). `make_router(tier=, guard=)` IS the native form (one extra line per router, zero new machinery); a router that claims `platform`/`org` without a guard fails at import, and one whose declared tier exceeds what its gates enforce is `too-open` in the catalog | **Adopt, as a thin wrapper of the native mechanism.** Open: count routes inheriting the check vs per-route `Depends` after the pilot products migrate (target: zero missed routes) |
| **Semgrep** (`--baseline-commit`, `nosemgrep`) for static checks | our AST keepers: route classification of 2935 routes ≈ 35 s cold, tables ≈ 1 s, near-zero false positives on the route class; Semgrep's baseline/suppression = our ledger + `# access-tier-ok: <reason>` | **Do not add** (second engine, no capability gain) |
| **SARIF 2.1.0 export** vs plain ledger | export is ~60 lines, 0.01 s, 1171 results = 786 KB; internal store stays NDJSON (merge-friendly). Value = GitHub code-scanning visibility; whether `upload-sarif` honours `suppressions[]` is **unverified** (older reports said v2 ignored them) | **Optional exporter only** (`--findings-ledger-sarif`, not committed, not uploaded). Open: add the CI upload step (CI-redesign owner) once suppression handling is verified |
| **Supabase security advisor** (splinter via `get_advisors` → `supabase_advisors` filter) vs our SQL | not runnable from this branch (the connector is the coordinator's). By lint definition it covers `rls_policy_always_true` (our `policy-open`: 4 erp tables) and RLS-off; it cannot see our tier declaration, so it is blind to Platform-IP `grant`/`policy`, anon `policy-secret`/`policy-pii` (erp.portal_tokens, portal_acessos, site_config), `inactive-schema-served`, `browser-grant`. Our effective-state diff ≈ <1 s | **Union**: `access_tier_exposure` accepts `advisors=` rows, reports `advisor_blind_spots` (the kinds only our SQL caught). Open: run `get_advisors` once and record recall on the known findings here |
| **pgTAP-shaped role-matrix test** per table | emitted by `scaffold_migration` as a comment block (cost ≈ 0); the existing replay probes (`test_agents_browser_lockdown_probes_on_replay`, `test_core_member_access_rules_on_replay`) cover grants for specific products only | **Keep the template, log open:** unmeasured whether it catches something the replay probes do not; promote to a generated probe only once it does |
| **Lock `/docs` + `/openapi.json` in prod** (OWASP FastAPI cheat sheet) | owner decision 2026-11-05: docs stay public | **Overruled — keep public**, protect by contract: platform routes out of the schema by construction, schema leak scanner, schema-driven 401/403 test (section above) |
| **Heuristic checks** (PII-column detection, browser-grant defence in depth) | precision unmeasured | **Warn-only** (`LedgerType.advisory`): recorded in the ledger, never blocking, until measured precise (Google SRE book ch.12: block only the near-zero-false-positive class) |

The burn-down also reports how common the class stays (CISA Secure-by-Design): `project-history/access-tiers/metrics.ndjson` gets one line per (date, sha) on every reconcile — unclassified routes, too-open routes, public-undeclared, Platform-IP tables exposed, anon-readable secret/PII tables, tables with a browser grant. Read the trend, not the snapshot.
