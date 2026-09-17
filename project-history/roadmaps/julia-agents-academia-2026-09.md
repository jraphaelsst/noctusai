# julia-agents-academia-2026-09 — absorb Julia: the `academia-de-reciclagem` knowledge product + the lean `agents` product

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: absorbing the sibling seed-workspace that built "Julia", an AI assistant for the Academia de Reciclagem project, into noc.
> Decision: **two products released to prod together.**
> - `academia-de-reciclagem` owns the project's knowledge, in its database.
> - `agents` is the home of managed agents: Julia (web UI only) plus a listing of One Chat with its on/off toggle.
> - One Chat keeps running in social-wiring on WhatsApp, unchanged apart from a scoped toggle API.
>
> Milestone bullets get ✅ only when genuinely reached. `M6` is the prod-promotion milestone referenced by `deploy/consent/<slug>.prod.yml` (`KB § PATTERNS/devops/prod-exposure-consent.md`).

## Origin

The user asked on 2026-09-12 to absorb the sibling workspace `academia-de-reciclagem` as a noc product: "the home for an agent that will grow", managed together with its chats from an app UI.

The workspace had shipped:
- **P0:** spec.
- **P1:** a markdown brain, `ar-*` skills, and an `academia.*` stdio MCP server.
- **P2:** a FastAPI backend running `claude-agent-sdk` headless behind an approval gate, with SSE. Suites: 58 backend + 34 MCP tests, green.

There was no frontend and no WhatsApp integration.

Review reshaped the design over 2026-09-12 → 2026-09-14. The drivers:
- The dev fleet is dormant, so prod is the only target.
- The noc repo is PUBLIC.
- The user clarified that Academia de Reciclagem is a real-life project Julia helps with, while the Agents product is a separate thing.
- The user later decided Julia is NOT wired to WhatsApp for now.

The decision log keeps every step.

## Milestones

- **M0: decisions + design** — two-product split, knowledge in the DB, lean agents home, isolation + hardening model, slice plan (this roadmap). ✅ reached 2026-09-15 (decision log).
- **M1: contracts on `origin/dev`** — both products scaffolded and migration numbers reserved. Four contracts:
  - the academia API, with scopes and MCP descriptors
  - the agents API: conversations, messages, approvals, persona, agent list, SSE event vocabulary
  - the product-token scheme: scope names, `expires_at`, principal, audit shape, 401 vs 403
  - the social-wiring One Chat toggle contract

  Vendored `_kit` removed. ✅ reached 2026-09-14 (contract on `dev` at `340c56b7` and earlier).
- **M2: academia knowledge product**
  - `KnowledgeStore` (Protocol + Fake + Pg + factory).
  - Append-only `kb_revisions` with provenance.
  - Code counters allocated under a row lock.
  - Sibling history imported from a bundle outside the repo, then verified (revision count + HEAD body hashes).
  - Scoped API and single-use approval assertions (H2).
  - KB / Decisions / Questions / Roadmap UI showing real data.
  - `mcp/academia` rebuilt as an HTTP client.

  ✅ reached 2026-09-17. The sibling history was imported into prod for org `6dd73140…` and verified: 72 revisions (the bundle's per-entity count), 63 entities, a replay added 0 rows, and head state equals a same-bundle import into the fake store. The bundle stayed outside the repo.
- **M3: seed uplift**
  - Product-token resolver + `require_scopes` + audit + expiry (N=3).
  - ChatWindow streaming / tool-card / approval seams.
  - Pilots green.

  ✅ reached 2026-09-14 (`1ec99a35`, SEED-1/SEED-2 slices; pilots green).
- **M4: agents product**
  - `AgentRuntime` Protocol (Claude SDK + Fake + factory) and the approval gate.
  - Hardened Julia launch.
  - Conversations with per-owner checks, persona (admin-only, model allowlist).
  - Agents list: Julia on/off; One Chat on/off through the social-wiring toggle API.
  - Julia works on academia only through scoped tools.
  - Isolation test suite green.

  ✅ reached 2026-09-16 (§E.11 isolation merged; SEC-C real-image proof 82/82, CI job green on amd64).
- **M5: social-wiring toggle API** — a scoped product-token endpoint that flips One Chat's existing auto-reply flag, with audit; no other change to the live product. Ships alone, behind `predeploy_check`. ✅ reached 2026-09-16 (bridge route on the prod tip `7e5f5ad6`, running in prod).
- **M6: prod promote** — authorized 2026-09-16 by the user in-session (consent records `cd4508d7`, `9747db4f`).
  - ✅ `academia-de-reciclagem` and `agents` public behind SSO (200 on shell/health, 401 unauthenticated, SSO preflight passes).
  - ✅ Knowledge imported (M2, 2026-09-17).
  - ⬜ Julia usable in the browser — not yet exercised end-to-end by a signed-in user.
  - ⬜ One Chat toggle works from Agents — the scoped bridge answers from inside the agents container; the UI round-trip is unverified.
  - ✅ `deploy_verify` green (prod `f2b516a5`). `spa_smoke` / `sso_cors_smoke` cannot target short hosts, so the same checks were run by hand with curl.
  - ✅ Explicit user consent per slug.

  ⬜ live; two browser checks owed.

## Trigger conditions (the "when")

| # | Trigger | Detection signal | Why it tips the balance |
|---|---|---|---|
| T1 | Julia on WhatsApp | User asks for it again | Deferred by user decision 2026-09-14. Re-opens the shared-line design (switch, dispatcher, WAHA key isolation) recorded in the decision log. |
| T2 | One Chat moves natively into `agents` | A second agent needs managing beyond on/off, or One Chat's prompt/tools need editing from a UI | Its 22 tools depend on social-wiring data; today it only needs listing + toggle. |
| T3 | Academia video platform (sibling P6) | Open question Q-02 (the offer) answered in the academia knowledge base | Platform tables are only an outline until the offer exists. |
| T4 | Agent tool gate → seed `domain/ai` | A second product runs a pre-execution tool gate | N=1 by design today. |
| T5 | MCP-over-HTTP bridge formalized in `mcp/_kit` | A third agent-callable product API | N=2 today (triage only). |
| T6 | Multi-worker approvals | The agents product needs more than one worker process | The approval wake-up is in-process today (`--workers 1` + `instance_id`). |

**Today's status**: none fired.

## Phase 1 — foundation (IN PROGRESS on `feat/absorb-academia-de-reciclagem`)

| # | Title | Files | Status | Verify recipe (live-state proof, not unit tests) |
|---|---|---|---|---|
| P1.1 | Scaffold `academia-de-reciclagem` (ports 8015/8190, schema `academia_de_reciclagem`) | `products/academia-de-reciclagem/**`, `products/core/backend/migrations/043_seed_academia_de_reciclagem_product.sql`, `start.sh`, `docker-compose.yml` | scaffolded, not committed | After M2: `GET /api/health` 200 on the product container; product row visible on the core dashboard. |
| P1.2 | Scaffold `agents` | `products/agents/**`, core seed-row migration | pending | After M4: `GET /api/health` 200; product row visible. |
| P1.3 | Absorption ledger `stage=cloned` | `project-history/absorptions.ndjson` | recorded | `noctus.dev.absorption_status` lists `academia-de-reciclagem`. |
| P1.4 | This roadmap | this doc | drafted | — (doc) |

## Phase 2 — the build (waves; each slice file-disjoint, collision class noted)

| # | Wave | Slice | Owner | Class | Verify recipe |
|---|---|---|---|---|---|
| W0 | 0 | Contract `projects/julia-agents-academia-CONTRACT.md` (academia API, approval assertion, agents API + SSE + gate + launch, social-wiring toggle, ChatWindow seams, reserved migrations, E2E checks) · `agents` scaffold · skill-content audit · advisory CODEOWNERS (see Q4) | tech-lead | — | Contract on `origin/dev` before any fork; `noctus.dev.propagate check=True` clean for both slugs. The vendored `_kit` never entered noc (slice M1 builds `mcp/academia` on noc's `_kit`). |
| A1 | 1 | academia `KnowledgeStore`, migrations, API with scopes + single-use approval assertions | backend-engineer | C1 | Live Supabase: create an entry, read its revision; UPDATE on `kb_revisions` raises; replayed assertion → 409. |
| A2 | 1 | academia importer + verifier (bundle outside the repo, secret scan first) | backend-engineer | C1 | Revision count = git revision count; HEAD body hashes match. |
| SEED-1 | 1 | Product-token resolver + scopes + audit + expiry | engineer-seed | C2 | Pilots green; strict `== 401` (missing/expired) and `403` (scope) tests. |
| SEED-2 | 1 | ChatWindow seams | engineer-seed | C2 | Every ChatWindow consumer still builds (`vite build`). |
| G1 | 1 | agents: conversations, messages, approvals, persona, agent list, API | backend-engineer | C1 | Live DB: one active persona per agent enforced; owner check 404 on a foreign conversation. |
| A3 | 2 | academia UI | frontend-engineer | C1 | `noc-wiring-audit`: every page shows real data and owns its CRUD. |
| M1 | 2 | `mcp/academia` → HTTP client | backend-engineer | C1 | Terminal round-trip `academia.kb.buscar` against the live API. |
| G2 | 2 | `AgentRuntime` + approval gate + in-process academia tool proxy | backend-engineer | C1 | Fake runtime turn persists events; approval round-trip writes a revision with `approval_id`. |
| SEC-A | 2 | Hardened Julia launch (after G2, same file) | backend-engineer | C3 | CLI argv assertion; red-team turn yields no Bash/Read/Write/WebFetch result. The launch settings: `setting_sources=[]`, explicit tools + skills, `strict_mcp_config`, minimal `env`, CLI uid `julia-cli`. |
| SEC-B | 2 | SSO owner checks, approver role, admin-only persona | backend-engineer | C3 | Strict 401 / 403 / 404 matrix. |
| SW1 | 2 | social-wiring scoped One Chat toggle endpoint (live, runs alone) | backend-engineer | C3 | Prod: agents token flips auto-reply; audit row written; a token without the scope → 403. |
| G3 | 3 | Agents UI (Julia chat, approvals, persona, agent list with One Chat toggle) | frontend-engineer | C1 | Browser: send a message, approve a KB write, see it in the academia KB; toggle One Chat and observe the flag change. |
| D1 | 3 | Container hardening + ingress + build scope for both slugs | devops-engineer | C2 | `check_product_container_shape` clean. Hardening: `cap_drop: ALL`, `no-new-privileges`, read-only root fs, `--workers 1`, per-process memory limits. `predeploy_check` green for both slugs. |
| SEC-C | 3 | Isolation test suite | backend-engineer | C1 | On the real image: EACCES on foreign `/proc/<pid>/environ` + secret files; no platform secret in Julia's env; Julia's token cannot read social-wiring; the toggle token cannot read academia. |
| W4 | 4 | Merged-tip gates + cutover (M6) | tech-lead + user | — | See M6. |

## Anti-goals (explicit non-goals)

- ❌ "Julia on WhatsApp in this release." User decision 2026-09-14 (T1).
- ❌ "Change One Chat's behaviour, prompt, tools or sender policy." Only a scoped toggle API is added.
- ❌ "Move One Chat's code into `agents`." Gated on T2.
- ❌ "A git brain repo." Knowledge lives in the academia database with append-only revision history.
- ❌ "Any client or company fact in noc's repo." The repo is public; import bundles and knowledge content stay out of git.
- ❌ "Build the academia video platform now." Gated on T3.

## Open questions (to revisit at trigger time)

- **Q1 — terminal Julia.** How the local Claude Code session loads JULIA.md + skills and authenticates to the academia API (personal token).
- **Q2 — One Chat's sender policy.** Unchanged by user decision on 2026-09-14; revisit before M6.
- **Q3 — who may approve Julia's writes.** The contract (E.2) sets the default: the requester or an org admin. Revisit if more team members need approval rights.
- **Q4 — enforced review of Julia's prompt and skills.** `.github/CODEOWNERS` is advisory only: `dev` has no branch protection (checked 2026-09-14), so direct pushes bypass it. Enforcing needs branch protection with required code-owner review. That is a repository-settings decision for the user, and until they decide, prompt changes are guarded only by the review habit plus the contract's E.8 rule.

## Decision log

- **2026-09-12**: Absorb the sibling as a noc product. Ports 8015/8190, schema `academia_de_reciclagem`.
- **2026-09-12**: In prod Julia reads, and writes only through her tools with approval. No Bash, no code writes.
- **2026-09-12**: Ship target is live behind SSO. The dev fleet is dormant.
- **2026-09-12**: Julia's router is not named CLAUDE.md inside noc, so it can't auto-load into noc sessions.
- **2026-09-13**: Julia would share the WAHA number with One Chat, with a one-active-agent switch. *Superseded 2026-09-14.*
- **2026-09-14**: `academia-de-reciclagem` stays a separate product: the real project whose knowledge Julia works on through tools. A new `agents` product hosts the agents.
- **2026-09-14**: Knowledge lives in the academia database from day one. This supersedes the git-backed brain and "files are the source of truth". The full git history is imported with provenance.
- **2026-09-14**: Release all together to prod.
- **2026-09-14**: Shared-line design worked out (dispatcher, WAHA gateway as sole key holder, key rotation, erp + social-wiring senders). Security verdict: in-product uid isolation is sufficient only when WAHA/service_role credentials live outside the agents container. *Superseded the same day.*
- **2026-09-14**: User decision: Julia is reachable only through the app UI; WhatsApp stays only for One Chat, untouched in social-wiring. This drops the shared line, switch, dispatcher, gateway, key rotation and sender migration.
- **2026-09-14**: Lean agents product: hosts Julia (chat, runtime, approvals, persona) and lists One Chat with its on/off toggle via a scoped social-wiring API. Single container, and Julia's CLI runs under its own uid with an explicit env.
- **2026-09-14**: Security controls kept from the reviews:
  - `Skill` allowed with an explicit baked list (CODEOWNERS on prompt + skills)
  - single-use signed approval assertions across products (H2)
  - token expiry, principal checks and audit (H3)
  - import bundle outside the repo, with a secret scan (H4)
- **2026-09-14 (wave 1a integration)**: SEED-2 (ChatWindow seams) and G1 (agents data layer) are on `dev`. G1's review caught a SECURITY DEFINER function executable by PUBLIC; it was fixed before integration and logged as a keeper candidate. A2 (importer) is verified and waits for A1. SEED-1 (token scopes) is integrating, and it wrote migrations social-wiring 105 and erp-imobiliario 046, which carry a mandatory deploy order (contract §F).
- **2026-09-14 (wave 1a complete)**: all five wave-1a slices are on `dev`, each re-gated on its rebased tip before push:
  - **SEED-1** `3dbd2113`: social-wiring 3516 and erp-imobiliario 2176 tests green. A concurrent session's ledger rows were recovered in a separate commit.
  - **SEED-2** `df1c2700`.
  - **G1** `e363a044`.
  - **A1** `3326faf1`: 22 SECURITY DEFINER functions, EXECUTE locked schema-wide to service_role (verified).
  - **A2** `05e069d5`.

  None of the 11 migrations is applied to any database; they are held for cutover prep.

  Wave 1b is dispatched: SW1 bridge, G1b agents API, G2 runtime + gate + launch, and A1b academia API. The import route is added when A1b integrates.

  Several engineer sessions stalled at the 600 s watchdog (A2, M1, A3, G4), and G2's dispatch twice hit an unavailable permission classifier. The tech-lead finished A2's store swap inline, and M1 / A3 / G4 are re-dispatched at lower concurrency.
- **2026-09-14 (wave 1b, part 1)**: three wave-1b slices are on `dev`, each re-gated on its rebased tip before push.
  - **A1b academia API** `c3481720`: §B.0–B.5 routes, §D assertion verification, and the seed `ApiTokenAuditMiddleware`. It also changed the seed `http_exception_handler` so the flat `{detail, code}` error shape passes through verbatim. That change was gated against the core, social-wiring and erp-imobiliario suites. A concurrent sweep's false `shipped` pointer rows were removed from its commit.
  - **G2 runtime + gate + launch** `64e2a30f`:
    - It found a load-bearing contract bug: `allowed_tools` auto-approves before `can_use_tool`, so escrita tools there would have bypassed the approval gate. §E.5 is corrected, with a regression test.
    - It required `uvicorn` 0.31.1 in the agents and root requirements. `claude-agent-sdk` → `mcp` needs ≥0.31.1, and without the bump `pip install -r` could not resolve for the agents image or CI.
    - The other products keep 0.30.6. Aligning the fleet is a follow-up, not a hidden divergence.
  - **SW1 social-wiring bridge** `27dd3a0b`: the scoped One Chat toggle route plus erp token-route tests. At integration the tech-lead switched the bridge tests to the flat error shape and wired the audit middleware, so the bridge is now audited.

  Still in flight: G1b (agents API), M1 (academia MCP client), A3 (academia UI), G4 (Agents UI).

  Blocked while the `noctusai` MCP server is disconnected: branch-pointer updates and worktree cleanups for A1b, G2 and SW1.

  Found out-of-band:
  - The dev toolkit's OpenAI account has no credits, so embedding cache refreshes fail at push. Prod impact on One Chat is unverified: no chatbot traffic appeared in the recent log window.
  - A peer session's client contracts folder is now git-ignored (`products/*/contracts/`).
- **2026-09-14 (wave 1b, part 2)**: four more slices are on `dev`, each re-gated on its rebased tip.
  - **A3 academia UI** `5d8feba4`.
  - **M1 academia MCP client** `5f25f501`: 22 tools with 77 tests, covering every §C row.
  - **Core icon registry** `6f3dec96`: migration 043 seeds the `Recycle` icon, which core's `ProductIcon` registry did not list. That left `test_all_products_compliant` red on `dev`. The fix is at the registry. A reproduction on the `dev` tip confirmed this was the only failing test; the lying-loading-state detector tests were green.
  - **G4 Agents UI** `b49613e3`:
    - pages: Julia chat on the seed `ChatWindow` organ, Agentes with the One Chat toggle, the persona editor, and Aprovações
    - held migration `agents/008`
    - `agents` added to the CI frontend test matrix
    - gates: 38 vitest, tsc, build, and the organ, loading-state, status-pagina, migration-collision and KB-sync keepers
    - the only rebase conflict was the CI matrix, where `academia-de-reciclagem` and `agents` were both new entries; both are kept
  - **Contract gap from G4:** the §E.3 tool and approval events carry no message id. The UI renders one temporary "live turn" bubble per open conversation and treats the persisted `blocks` as the durable record. Candidate for a later contract revision.
  - **DRY triage, N=2:** the seed frontend `ApiError` was not exposing the backend's `code`, so both the academia and agents UIs match on `detail` text. A peer session has since added `ApiError.code` (`2b7cbd68`). That getter reads only the nested `{error: {code}}` shape, so it returns `null` for this contract's flat `{detail, code}` errors. Queued as a small seed slice, due before a third contract-driven UI:
    - make the getter fall back to a top-level `code`;
    - switch both UIs' `errors.ts` from matching `detail` text to matching `code`.
  - **G1b agents API + SSE** (`19037004`, `843262cb`, `01db5cc7`) and **A1c import route + seed secret scan** (`d8f280bf`, `ac5eedf7`):
    - A cherry-pick at 16:08 put both on `dev` before tech-lead integration.
    - The engineer running G1b stopped on an API session limit after committing its reconciliation.
    - `dev`'s agents backend equals G1b's final tip, apart from later commits.
    - A1c's blobs are identical to the engineer's branch.
    - A1c's two secret-scan copies were already identical in behaviour, so the change is a pure move into the seed. `find_secret` also returns the matched pattern name.
    - §B.6 now states that a successful import returns 200. A product token gets 403 `product_forbidden`.
  - **Re-gate on `dev` tip `c5edb64d`**, all by exit code:
    - agents backend: 258 passed
    - academia backend: 308 passed
    - social-wiring bridge: 13 passed
    - seed secret scan and bundle export: 21 passed
    - keepers clean: migration-number-collision, every-test-file-is-gated, kb-sync, no-self-monkeypatch, ci-test-matrix-coverage

  **Wave 1b is complete.** All of M1–M3's build slices are on `dev`, and no migration has been applied. Next: D1 devops (containers, wiring for the `/app/bin` wrapper, a stable `AGENTS_INSTANCE_ID`, secrets), the SEC-C isolation suite, and the §G E2E checks.

  G4's two branch-pointer rows were set aside during its rebase. They are republished once the `noctusai` MCP server reconnects, together with the pending pointer updates and cleanups.
- **2026-09-14 (wave 3 opens; prod state changed outside this roadmap)**:
  - **Seed `ApiError.code` reads the flat `{detail, code}` shape** `1c8c307a`. The nested `{error: {code}}` shape still wins when both are present. The agents and academia `errors.ts` now map by `code`, so the N=2 text-matching triage is closed. The tech-lead re-gated the pushed tip:
    - seed lib: 397 tests, plus check
    - agents: 43 tests
    - academia: 45 tests
    - tsc and build for agents, academia, core and social-wiring
  - **Follow-up:** the seed `require_scopes` still returns English `detail` text ("Insufficient role"). Both UIs mask it by `code`, but any other consumer would show English. Queued as a small seed slice.
  - **Prod state, from another session.**
    - A second session applied social-wiring migrations 105–112 to prod, owner-approved (recorded in `products/social-wiring/backend/migrations/APPLIED.md`). It then promoted `dev` → `main`/`prod` at `c5edb64d` (16:24). That release includes SEED-1.
    - The mandatory §F order holds for social-wiring: prod has `api_tokens.expires_at` and `api_token_audit`.
    - **erp-imobiliario `046` is NOT applied.** A read-only prod probe found that `erp.api_tokens` lacks `expires_at`, `principal_agent_id` and the other new columns, and that `erp.api_token_audit` is absent.
    - Impact: erp mounts the seed `/api/settings/api-tokens` routes, and `POST` (mint) now inserts those columns, so it returns 500 in prod. `GET` and `DELETE` still work. Erp runs only `FakeApiTokenResolver`, so bearer resolution is unaffected.
    - Reach: erp has 0 tokens, and no frontend calls the route.
    - Fix: apply `046` to prod, a write that needs owner approval. It is surfaced to the user and not applied.
  - **"No migration applied" above is superseded for social-wiring `105`.** Academia `006`–`009`, agents `006`–`008` and erp `046` remain held.
  - **D1 containers is held on its branch after tech-lead review.**
    - **The `julia-cli` uid switch could not work.** The image ran `USER noctus` with `cap_add` SETUID/SETGID under `no-new-privileges`, and Docker drops those caps before a non-root exec (moby#45491, PR#36587). Every Julia turn would have raised PermissionError.
      - Rework: start as root, then `setpriv` into `noctus` with only ambient SETUID/SETGID. The wrapper drops every cap before `env -i`, because ambient caps survive the 1000→1001 switch.
    - **The `curl | bash` Claude CLI install is removed.** The claude-agent-sdk 0.2.152 manylinux wheels (x86_64 and aarch64) already bundle a CLI matched to the pin.
    - **Real-image proof is now required.** Docker Desktop is running (arm64 host). Prod is linux/amd64, so an amd64 build check is included.
    - **A security advisor is reviewing the design in parallel.**
    - **Build scope unchanged.** Both slugs were correctly left out of `deploy/fleet/build-scope.txt`: `build-and-push.yml` refuses a listed slug that is missing from `docker-compose.prod.yml`, and both catalog rows are `deploy_scope='dev'`.
  - **M6 cutover checklist, grown from D1:**
    - tunnel ingress and a `docker-compose.prod.yml` entry (consent-gated)
    - `deploy_scope` → `live`
    - secrets: `APPROVAL_ASSERTION_SECRETS`, `PRIMARY_SOURCE_ALLOWLIST`, `ACADEMIA_API_TOKEN`, `JULIA_AGENT_ID`, `SOCIAL_WIRING_API_TOKEN`
    - **`JULIA_ANTHROPIC_API_KEY`**, mapped onto the agents service's `ANTHROPIC_API_KEY` in the prod compose. The bare name is the shared root `.env` key that dev-team already reads (`docker-compose.prod.yml:240`), and §E.5 requires Julia's key to be unshared.
    - the §F migration order
- **2026-09-14 (user decisions + security review)**:
  - **User: erp-imobiliario `046` waits for cutover.** erp's `POST /api/settings/api-tokens` keeps returning 500 in prod until then (0 tokens, no UI caller). Added to the M6 checklist; it stays unapplied.
  - **User: fix the Julia chat event defects now.**
    - The contract revision is on `dev` at `340c56b7`:
      - §E.3: `approval.requested` carries the real id; `message.updated`; `message_id` on tool and approval events; placeholder `message.new`; the frontend rendering rule.
      - §E.9: `broker.request(..., on_created)`; the escrita event order; `_approval` carries only the id; non-silent resume after a restart.
      - §E.10: approval integrity.
      - The canonical stream fixture: `products/agents/contract-fixtures/escrita-turn.events.json`.
    - Two slices are dispatched in parallel against it: `feat/julia-approval-integrity-be` and `feat/julia-events-fe`.
    - Root cause of the frontend miss: its test mocked an `approval.requested` id the backend never sent. Both sides now replay one fixture.
  - **Security advisor review of SEC-C: ACCEPT-WITH-CHANGES.** The advisor built the design and measured it on Docker 29.4.3 / linuxkit 6.12.
    - **Folded into D1 (in rework):**
      - no `--bounding-set` (needs CAP_SETPCAP, so the container would not boot)
      - the uid/gid/groups switch moved into the wrapper, which also covers the SDK's `-v` spawn that runs without `user=`
      - a fail-closed root entrypoint
      - `cap_add` KILL plus `init: true`, because uvicorn otherwise cannot reap the CLI
      - setuid bits stripped
      - a dedicated `/run/julia` tmpfs, the app `/tmp` at 1770, `umask 077`
      - absolute paths and the bundled CLI path in the wrapper
      - `DISABLE_AUTOUPDATER` and `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` in the allowlist
    - **Folded into the backend slice:** §E.10. The escrita handler minted assertions from CLI-supplied `_approval`, allowing forged approvers, body swaps and replay.
    - **Deferred, each with a named destination:**
      - **Per-conversation HOME and cross-org transcript isolation** (all turns share uid 1001 and one HOME). Destination: SEC-C follow-up after D1 and the backend slice land. The choice is a per-turn uid pool or an accept-with-rationale ("requires CLI RCE; Julia has no code-executing tools"); it needs an LGPD flag and is the user's decision.
      - **uid 0 reachable from a compromised app** (CAP_SETUID). Destination: record an accept-with-rationale in the contract at M6. Ask the owner about userns-remap on the prod daemon, and keep read-write volumes out of prod.
      - **CLI network egress** reaching `127.0.0.1` and `noctus-net` services. Destination: SEC-C proof that every internal service returns 401 to an unauthenticated uid-1001 caller. An `iptables` owner-match rule stays optional.
      - **Wheel supply chain** (the bundled CLI now arrives inside the pip wheel). Destination: a hash-pinning follow-up for `products/agents/backend/requirements.txt`.
      - **Prod compose parity:** the security block is generated from one propagate source and reused by the M6 `docker-compose.prod.yml` entry, with a keeper parity check.
      - **SEC-C kill tests** must assert via `os.kill` plus `/proc` liveness, because `Popen.terminate()` gives a false pass after a reap.
- **2026-09-14 (Julia chat events + approval integrity landed)**: `7815c3fa` + `6ae348ce` (backend) and `1ac12801` (frontend) are on `dev`. Backend and frontend were stacked and checked together on one tip before a single push.
  - **Backend:**
    - `broker.request(..., on_created)` registers the wake-up future before `approval.requested` goes out, so the event carries the real id. A test covers an instant decision racing the event.
    - The route publishes a placeholder `message.new`, adds `message_id` to tool and approval events, publishes `message.updated` after every blocks write, and correlates approvals by id.
    - **§E.10 handler:** it trusts only the stored row (decision, tool, conversation, requester, instance, use window, canonical input hash). It consumes atomically with a conditional `UPDATE … consumed_at IS NULL`, then mints with the stored `decided_by`.
    - **Resume after restart:** in SDK 0.2.152 an unknown resume id surfaces as `ResultError(ProcessError)` from `connect()` (`_internal/query.py:384-439`). The runtime reconnects with a fresh session and persists the contract's system message. A startup failure that isn't a resume still propagates.
  - **Bug the canonical fixture caught (drift fixed):** the route mutated block dicts in place, so a snapshot already published changed after the fact.
  - **Frontend:** blocks render only from `message.new` / `message.updated`. The streaming bubble carries text only. Approval events invalidate the approvals list. When a turn ends, messages refetch once.
  - **Checks on the pushed tip, by exit code:**
    - agents backend: 285 passed
    - fixture, handler and resume tests: 19 passed
    - agents frontend: 45 passed, plus tsc and build
    - keepers clean: every-test-file-is-gated, no-self-monkeypatch, kb-sync, migration-number-collision, lying-loading-state, canonical-organ-consumption
    - no migration needed: `consumed_at` already exists in `006_agents.sql`
  - **Flake under load, not a defect:** `products/agents/frontend/src/pages/__tests__/Agentes.test.tsx` times out at 15s on this host under load (~17, from local `dev-noctus-*` containers, one restart-looping). It fails identically on the untouched base commit, passes with a 90s timeout (~15s of test time), and passed 45/45 once load fell to ~9. A follow-up should find why three render tests take ~15s.
  - **D1 is still reworking.** Both engineers stalled at the 600s watchdog on long foreground commands; both were resumed. D1's orphaned `docker build`, hung for 1h43m, was killed. D1 must rebase over this slice's small edits to `config.py` and `runtime/__init__.py`, keeping both sides.
- **2026-09-14 (D1 containers landed — SEC-C isolation proven on a real arm64 image)**: `0edbf1d0` + `5b9b9b11` are on `dev`.
  - **Rebase:** onto `1ac12801`, keeping both sides of `runtime/__init__.py`.
  - **Re-gated on the pushed tip:**
    - agents backend: 283 passed, 6 skipped
    - academia backend: 308 passed
    - `--propagate both --check`: in sync (14 products)
    - `check_product_container_shape`: `[]`
    - keepers clean: tunnel-ingress-snapshot, ci-test-matrix, kb-sync, every-test-file-is-gated, no-self-monkeypatch, prod-exposure-consent, hardcoded-slug-set
  - **Shape.**
    - **Entrypoint (agents only):** a root:root `bin/entrypoint.sh` fails closed unless uid is 0, NoNewPrivs is 1, CapBnd is exactly `e0` (SETUID+SETGID+KILL) and the rootfs is read-only. It then runs `setpriv` to uid 1000 with ambient SETUID/SETGID/KILL.
    - **Wrapper:** `bin/julia-cli-exec` itself switches to uid/gid 1001 with cleared groups, drops all inheritable and ambient caps, sets no_new_privs and uses `env -i` with the allowlist. It covers the SDK's `-v` spawn, which runs without `user=`.
    - **CLI:** the SDK-bundled binary, reached through a root-owned symlink with a build-time `test -x`.
    - **Image:** setuid/setgid bits stripped. `/run/julia` is a tmpfs owned by uid 1001 (mode 0700); `/tmp` is mode 1770 gid 1000.
    - **Compose:** `init: true`, `shm_size` and `mem_limit`. The local seed base images were rebuilt before the proof.
  - **Real-image proof (arm64), all passing:**
    - health 200 (degraded start with placeholder Supabase credentials, as designed)
    - uvicorn: uid 1000, CapPrm/Eff/Amb `e0`, NoNewPrivs 1
    - rootfs write: EROFS
    - wrapper, entrypoint and CLI: root:root 0755
    - the real `Popen(user=)` spawn: uid, gid and groups 1001; all caps zero; env exactly the allowlist
    - as uid 1001:
      - EACCES on uvicorn's `environ`, `mem` and `fd`
      - EPERM on `kill -0`
      - EACCES on the app's `/tmp`
      - `setpriv --reuid=1000` denied
      - `find -writable` returns only `/run/julia`
    - zero setuid/setgid files
    - SIGTERM kill observed through `/proc` state, and zero zombies after repeated spawns
    - the `-v` spawn switches to 1001
  - **Gaps, each with a named destination:**
    - **amd64 image not built.** `buildx`'s container builder cannot see the local-only seed base images, so the cross-build tried a registry pull (rc 1). Destination: the M6 build through `build-and-push.yml` (registry bases, amd64) plus a `claude -v` smoke on the built amd64 image before deploy.
    - **The wrapper's uid-switch tests skip off Linux-with-CAP_SETUID** (6 skipped, with explicit reasons), so CI has no automated coverage of the privilege drop. Destination: the SEC-C suite as a real-image CI job (build the agents image, run the proof table as assertions).
    - **Unexplained capability reading.** The real entrypoint's uvicorn showed CapInh=0 while CapAmb=`e0`, which a manual `setpriv` chain did not reproduce. Everything works, but there is no root cause. Destination: the SEC-C CI job asserts the exact cap sets, which will pin or explain it.
    - **Drift found:** agents `approval_assertion_secrets: list[str]` crashes at boot on a plain `APPROVAL_ASSERTION_SECRETS=k1,k2` (pydantic-settings 2.5.2 JSON-decodes complex env fields before validators). Academia already works around it. Dispatched as `feat/seed-csv-settings`, which hoists the raw-str + list-property idiom into a seed helper (third copy, so it must be formalized) with a red-before/green-after regression test.
    - **Methodology note:** `docker exec -u <user>` does not reproduce the app's spawn path, because it gets no ambient-cap inheritance. A proof using it gives false negatives. Candidate for `KB § PATTERNS/devops/containerization.md` / `noc-container-debug`.
- **2026-09-14 (D1 turned dev CI red; fixed; settings boot crash fixed)**:
  - **CI regression from D1, reported cross-session by a release session blocked on bless.**
    - `tests/runtime/test_wrapper.py` failed 5 tests on GitHub's ubuntu runner (run 34914554800) with `setpriv: setgroups failed: Operation not permitted`.
    - Cause: the skip guard accepted `euid in (0, 1001)`. The runner user IS uid 1001, and `--clear-groups` needs CAP_SETGID for every caller.
    - macOS skipped the tests (no setpriv), so the engineer's gate and the tech-lead's re-gate were both green.
    - **Fix `4f8cce6c`:** the guard reads CapEff and requires root or CAP_SETUID+CAP_SETGID. Reproduced in `python:3.11-slim` as uid 1001:118: the dev version gave 5 failed, the fix gives 3 passed / 6 skipped.
    - **Follow-up `736fd9ed`:** as root, the privileged tests had never worked. The stubs sat in pytest's 0700 `tmp_path`, which uid 1001 cannot read, giving exit 126. A `julia_tmp` fixture (0755, under `/tmp`) fixes it: 9 passed as root.
    - CI: agents backend green on both commits. The MCP Toolkit failure seen on dev `3eccc545` was unrelated (env leak from dotenv tests) and fixed by the release session at `dc051a3b`.
    - Lesson saved to memory: gate on capability, not uid; reproduce as the CI runner uid and as root before pushing.
  - **Agents settings boot crash fixed, `1ec99a35`.**
    - New seed helper `noctusai_lib.config.csv_settings` (`parse_csv_setting`, `reject_json_array`), extracted at the third copy of the idiom.
    - Agents `approval_assertion_secrets` is now a raw `str` with a `_list` property. Both academia properties consume the helper with unchanged behaviour.
    - The seed `cors_origins_list` stays deliberately untouched: it keeps empty items and the helper drops them. Unifying it needs its own reviewed change.
    - Regression test: red before (3 failed, `SettingsError` at import), green after. The tech-lead hardened it to restore the original `app.config` module after each test, so the re-import cannot leak into later tests.
    - Suites: seed lib 3993, agents 286 (+6 skipped), academia 308, core 619, social-wiring 3894.
- **2026-09-15 (user decisions before prod; SEC-C CI job)**:
  - **Consent:** the user gave consent to deploy both products to prod, but only after (1) the isolation test runs in CI and (2) they had decided the cross-org question. It is not yet recorded through `noctus.dev.prod_consent`; that happens at cutover.
  - **Prod facts used for the decision** (read-only queries):
    - 4 orgs. Only `noctusai` has users (19): the owner, one other admin, and 17 `corretor`, none active in the last 30 days. `one-consultoria` and two test orgs have 0 users.
    - Julia's agent rows are created per org on first use (`ensure_default_agents`), inactive by default.
  - **User decision — isolation between conversations: build it now, before deploy.** Every Julia turn currently shares uid 1001 and one HOME, so a compromised CLI could read other conversations' transcripts. Design is dispatched to an architect (read-only). Constraints:
    - no new capabilities beyond SETUID/SETGID/KILL
    - tmpfs cleanup even after SIGKILL
    - no silent context loss
    - provable by the SEC-C harness
  - **User decision — who may chat with Julia: any org member, unchanged.**
    - The agents chat routes have no role gate.
    - Julia reads academia with her own product token, so a member whose role academia's own UI refuses (for example `corretor`, which is not in academia READ/WRITE) can probably read the knowledge base through Julia. This was explained to the user before they chose. Not verified end to end.
    - Academia's approver check still refuses such members' write approvals (§D step 8).
  - **SEC-C CI job, `.github/workflows/agents-secc-ci.yml`** (`secc/` harness plus a proof-only `secc-proof` Dockerfile stage that is never tagged, pushed or deployed):
    - builds the real `runtime` image on the amd64 runner (this closes the "amd64 image never built" gap);
    - starts it with docker flags derived from the compose security block;
    - asserts 27 checks, including all three fail-closed entrypoint refusals, uvicorn identity and caps, the real spawn and `-v` spawn identity/caps/env, uid-1001 EACCES/EPERM on uvicorn's `/proc`, `/run/julia` as the only writable path, zero setuid bits, and kill/reap.
    - Local arm64: 27/27 pass. Agents suite 297 passed, 6 skipped.
    - **CapInh gap closed:** with the real entrypoint, CapInh=`e0`, equal to CapAmb, which is what `setpriv --inh-caps` requests. The earlier CapInh=0 reading is attributed to a non-app reproduction path.
- **2026-09-15 (SEC-C CI green on amd64; per-conversation isolation designed, contract §E.11)**:
  - **SEC-C CI:** the first CI run of `agents-secc-ci.yml` (run 35024788335, dev `4968dfb1`) passed with every check listed in the log (`ALL CHECKS PASSED`). This is also the first amd64 build of the agents image.
  - **Architect design, checked against SDK 0.2.152 and bundled CLI 2.1.259:**
    - 3 slot uids (2000–2002), each with its own size-capped tmpfs declared in compose (no CHOWN needed);
    - the wrapper derives the slot from the kernel's real uid;
    - a root-owned slot script that sweeps, then copies in the handoff, then execs the CLI;
    - durable transcripts in the DB through the SDK session-store mirror, bound to the trusted `conversation_id`, with a group-only handoff file for resume;
    - release kills any process of the slot uid, sweeps, and quarantines the slot on failure;
    - persona moves off argv (`/proc/cmdline` is world-readable);
    - 429 `julia_capacidade` when all slots are busy.
  - **User decisions:**
    - full memory (durable transcripts, kept across restarts);
    - 3 slots with `APPROVAL_TIMEOUT_SECONDS=300`;
    - a larger transcript cap: the user chose "larger" without a number, so the tech-lead set **24 MiB**, with 40m slot tmpfs and 80m handoff tmpfs (200 MiB worst-case tmpfs within the 1 GiB limit). CLI RSS is still unmeasured; `mem_limit` is raised if needed.
  - **Existing defects found by the design, fixed in these slices:**
    - a 409 left an orphan user message (the lock was acquired after the persist);
    - no turn deadline, and the lock TTL equalled the approval timeout;
    - persona text visible in `/proc/<pid>/cmdline`;
    - the broad `ProcessError` resume fallback would read a wrapper refusal as lost context;
    - the §E.5 env allowlist listed 5 keys, the wrapper exports 8.
  - **Also:** agents migration `009_session_transcripts.sql` is reserved (B2). An LGPD flag for stored transcripts is required before prod.
  - **Git identity:** at the user's instruction, the machine's global identity is now `jraphaelsst <joaoraphaelsst@gmail.com>` (it was `test <a@b.com>`, which invalidated consent records such as igig and p-studio).
  - **Consent:** still pending the user typing each product's exact sentence.
- **2026-09-16 (§E.11 per-conversation isolation BUILT and proven; integrated as one tip)**: seven slices plus the LGPD register and the held cutover migration, merged into `integration/julia-slot-isolation` and gated together.
  - **Slices:**
    - **D1** image, wrapper, `bin/julia-cli-slot`, entrypoint, compose (through the propagate seam)
    - **B1** `SlotPool` / `TurnSlot` with kill + sweep + quarantine
    - **B2** migration `agents/009`, `TranscriptStore`, `ConversationTranscriptMirror`
    - **B3** runtime wiring: slot user, per-slot `CLAUDE_CONFIG_DIR`, persona off argv into `append.md`, transcript handoff, narrowed `ResultError` resume fallback, fresh mirror on fallback, abandoned-session cleanup
    - **B4** route order (reserve → lock → persist), 429 `julia_capacidade`, turn deadline, startup sweep, slot health through the seed's `liveness_hooks`
    - **D2** the nine SEC-C checks plus compose-derived slot mounts
    - **F1** the capacity message in the chat UI
  - **Two real defects, both caught by a REAL-IMAGE proof and neither by any unit test:**
    1. **Slot gid ≠ uid** (D1's own check): `useradd --user-group` does not pin the group's gid to `--uid`, so groups came out 999/998/997. Silent consequence: the group-only handoff file would have been unreadable by the slot, and `julia-cli-slot`'s glob would have found nothing — a SILENT resume loss, not a loud failure. Fixed with explicit `groupadd --gid` (`f549466b`).
    2. **`append.md` vs the handoff guard** (`c1f113f1`, tech-lead's own contract error): §E.11 told B3 to write the persona file into `/run/julia-handoff/K/` AND told the slot script to refuse anything that was not a single UUID-named `*.jsonl`. Since `append.md` is written on EVERY launch, the slot refused EVERY real turn. The integration proof failed 11 checks on it; unfixed it would have been a fail-closed outage on Julia's first prod turn. The script now counts only `*.jsonl`, skips `append.md`, and still refuses more than one transcript, a non-UUID name, a symlink, a non-regular file, or any unexpected entry. §E.11 step 3 corrected; three wrapper tests pin it (verified running as root in a Linux container — they skip on macOS).
  - **Fleet drift fixed in passing (B4):** the seed `http_exception_handler` dropped `HTTPException.headers` on both response shapes, so ANY product's `Retry-After` / `WWW-Authenticate` was silently lost. Fixed and pinned by `seed/lib/backend/tests/test_exception_handlers.py`.
  - **Verification on the merged tip, every result by exit code:**
    - SEC-C real-image proof (arm64): **82 checks, 0 failures**
    - agents backend 418 passed / 15 skipped · seed lib 4180 · core 619 · academia 308 · social-wiring 4151 · erp 2184
    - agents frontend 49 · academia frontend 45 · both tsc + vite build
    - keepers clean: propagate both, ci-test-matrix, every-test-file-is-gated, no-self-monkeypatch, kb-sync, container-shape, lying-loading-state, canonical-organ-consumption, migration-number-collision, prod-exposure-consent, hardcoded-product-slug-set, tunnel-ingress-snapshot
  - **Also landed:** three LGPD register entries (durable transcripts, admins reading every conversation, Julia as a read path into academia), and core migration `045` (HELD) flipping both products to live with `https://academia.noctusai.com` / `https://agents.noctusai.com`.
  - **Not done, by design:** no migration applied, no prod compose service, no ingress hostname, no DNS. Those are the cutover, gated on the user's consent sentences.
  - **Open follow-ups:** the CLI's real memory use per slot is still unmeasured (no API key in CI), so `mem_limit` may need raising above 1 GiB; the seed `ApiError` still exposes no response headers, so the UI cannot show a `Retry-After` countdown.

- **2026-09-16 (cutover, in progress)**:
  - **Done:**
    - Consent recorded (`cd4508d7`, `9747db4f`).
    - Prod compose, tunnel ingress and build scope landed (`a9dfb9e6`, `9e22d7e7`), and prod was promoted to `9e22d7e7`.
    - DNS: proxied CNAMEs for `academia.noctusai.com` and `agents.noctusai.com`.
    - Migrations: academia 001–009, agents 001–009, erp `046`, and core `045`.
    - Julia's agent rows exist for `noctusai` (`julia` = `f2cdaa2b-13e1-4acd-8d94-cf7dae0e3452`).
    - VPS `.env`: `APPROVAL_ASSERTION_SECRETS` generated on the host, plus explicit `PRODUCT_URL_ACADEMIA_DE_RECICLAGEM` / `PRODUCT_URL_AGENTS` overrides (the pattern would have produced `academia-de-reciclagem.noctusai.com`).
    - Core redeployed with the new CORS roster.
  - **academia is live:** the shell, bundle and deep link return 200, health is ok, unauthenticated API calls get 401, and the SSO preflight passes.
  - **Still owed:**
    - The agents container. It refuses to boot without `SOCIAL_WIRING_API_TOKEN`.
    - Minting `ACADEMIA_API_TOKEN` + `SOCIAL_WIRING_API_TOKEN` on the host and registering their hashes. The permission classifier blocked an agent from doing this, so the owner must run it.
    - `JULIA_ANTHROPIC_API_KEY`. The user asked to reuse the existing Anthropic key instead of a dedicated one (a deviation from §E.5), but no Anthropic key was found on the VPS, in the local `.env` files, or in the DB credential tables.
    - The sibling-history import (M2) and the G checks.
  - **Tool drift (wrong-tree family, N≥5):** `tunnel_config check` and `migrate_product` read the MCP server's stale primary checkout. The first reported `in_sync` while the live tunnel lacked both hosts; the second listed no agents `009`. Both were re-run pinned to a dev-tip tree. `spa_smoke` and `sso_cors_smoke` derive hosts from the slug pattern, so they cannot check a short-name host such as `academia`.

- **2026-09-17 (M2 import)**:
  - **Two defects blocked the import, both fixed at the root:**
    - The seed secret scanner flagged a lowercase code path (`backend/app/services/agent_runner`) in the sibling's `docs/SPEC.md` as a high-entropy token, so both the export and the prod importer refused the bundle. Fixed in `secrets_scan` (`dc0b0d7f`); a security review then closed a hex-after-`/` false negative the fix had opened, and named the real Stripe key prefixes (`0409dd7f`).
    - An untitled `## 2026-09-12` TIMELINE section mapped to `titulo=NULL`, and the RPC rolled the whole import back (23502, 0 rows). It now takes its title from the section's first line (`d02c9b7d`).
  - **Fake-vs-real drift, twice:** the fake store accepted NULLs Postgres refuses, and duplicated timeline events because it compared a date string with a `date`. Both are fixed (`d02c9b7d`, `04b6a15a`), with regression tests.
  - **How it ran:** an agent ran `run_import` inside the prod container for org `6dd73140…` as the platform owner. `POST /api/import` only accepts a signed-in admin, and the user asked the agent to execute. The container's rootfs is read-only, so the bundle went in over stdin.

## Retrospective (filled at first trigger fire)

*To be filled when T1–T6 fire.*

## Composes with

- `KB § GUIDES/absorb-seed-workspace.md` — the 10 gates this absorption follows.
- `KB § PATTERNS/devops/prod-exposure-consent.md` — M6 consent records.
- `KB § PATTERNS/backend/seed-fake-real-adapter.md` — `KnowledgeStore`, `AgentRuntime` shapes.
- `KB § PATTERNS/architect/products-consume-canonical-organs.md` — ChatWindow seams.
- `KB § PATTERNS/security/llm-bot-security.md` — Julia's hardened launch.
- `KB § PATTERNS/common/realtime-sse-bus.md` — agent event stream.

## File trail

- `products/academia-de-reciclagem/**` (scaffold)
- `products/core/backend/migrations/043_seed_academia_de_reciclagem_product.sql`
- `project-history/absorptions.ndjson`
- This doc.
