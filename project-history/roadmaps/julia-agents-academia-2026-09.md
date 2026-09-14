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

- **M0: decisions + design** — two-product split, knowledge in the DB, lean agents home, isolation + hardening model, slice plan (this roadmap). ⬜
- **M1: contracts on `origin/dev`** — both products scaffolded and migration numbers reserved. Four contracts:
  - the academia API, with scopes and MCP descriptors
  - the agents API: conversations, messages, approvals, persona, agent list, SSE event vocabulary
  - the product-token scheme: scope names, `expires_at`, principal, audit shape, 401 vs 403
  - the social-wiring One Chat toggle contract

  Vendored `_kit` removed. ⬜
- **M2: academia knowledge product**
  - `KnowledgeStore` (Protocol + Fake + Pg + factory).
  - Append-only `kb_revisions` with provenance.
  - Code counters allocated under a row lock.
  - Sibling history imported from a bundle outside the repo, then verified (revision count + HEAD body hashes).
  - Scoped API and single-use approval assertions (H2).
  - KB / Decisions / Questions / Roadmap UI showing real data.
  - `mcp/academia` rebuilt as an HTTP client.

  ⬜
- **M3: seed uplift**
  - Product-token resolver + `require_scopes` + audit + expiry (N=3).
  - ChatWindow streaming / tool-card / approval seams.
  - Pilots green.

  ⬜
- **M4: agents product**
  - `AgentRuntime` Protocol (Claude SDK + Fake + factory) and the approval gate.
  - Hardened Julia launch.
  - Conversations with per-owner checks, persona (admin-only, model allowlist).
  - Agents list: Julia on/off; One Chat on/off through the social-wiring toggle API.
  - Julia works on academia only through scoped tools.
  - Isolation test suite green.

  ⬜
- **M5: social-wiring toggle API** — a scoped product-token endpoint that flips One Chat's existing auto-reply flag, with audit; no other change to the live product. Ships alone, behind `predeploy_check`. ⬜
- **M6: prod promote**
  - `academia-de-reciclagem` and `agents` public behind SSO.
  - Knowledge imported.
  - Julia usable in the browser.
  - One Chat toggle works from Agents.
  - `deploy_verify` + `spa_smoke` + `sso_cors_smoke` green.
  - Needs explicit user consent per slug.

  ⬜

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
