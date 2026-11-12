# owner-kept-ideas-2026-11 — the 40 ideas the owner kept from the 10-12 → 11-11 chat sweep

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: a sweep of 74 owner sessions (10-12 → 11-11) found ideas the owner asked for that were missing, stalled or recorded-not-started; the owner ticked 40 to keep (triage artifact, collection `picks`, keep=true).
> Decision: **W0 (checks + filing) ships with this file; W1 dispatches 4 engineering slices; W2/W3 and the advisor items wait on the triggers below.** The owner delegated the sequencing ("go on with recommended path", 2026-11-12).

## Origin

Session 66 swept the owner's chats and published a triage page; the owner kept 40 rows (ids below are the page's ids; the local sweep report holds client data and stays out of git). Session b5 inherited the plan; this roadmap is the one home every kept item points to, so nothing is lost on `/clear`. Where an item already has a product roadmap, the row names it and that roadmap stays the source of depth.

## Trigger conditions (the "when")

| # | Trigger | Detection signal | Why it tips the balance |
|---|---|---|---|
| T1 | W1 landed | the 4 W1 slices are `landed` in the merge queue (`task_branch action=landed`) | W2 slices reuse W1's grants, notification switches and the owner number |
| T2 | Julia BASE→SDR→Julia template chain published | `agent-templates-2026-11` G-rows for the chain marked shipped | r02/r01/r04/r06/r07 build on the published chain |
| T3 | Owner says "go" on a W3 build | an owner message naming s04 or r22 | both are large builds the owner gates explicitly |
| T4 | Owner sends imovelweb details | owner message with imovelweb account / feed info (reminder set) | r10 cannot be designed without the account shape |
| T5 | Owner says "now" for the CRM guardian agent | owner answers the 13 interview questions (reminder set) | r33 is wanted "but not now" |
| T6 | Permutas discard reasons measured | ≥ 4 weeks of reason-coded discards on SW permutas matches | r23's decision is "N weeks of discard reasons, then decide" |

**Today's status**: none fired. W0 shipped; W1 is ready to dispatch.

> **Every slice carries TWO recipes, not one.** A *test-recipe* (green at the module boundary) is **not** a *verify-recipe* (proof against LIVE state). Empty verify = a positive claim that no live check is needed.

## Phase 1 — W0: checks + filing (SHIPPED)

| # | Title | Files | Status | Verify recipe |
|---|---|---|---|---|
| P1.1 | r15 check: one brand per org | — (prod query + git) | **shipped (answer: data yes, enforcement no)** | `select org_id from social_wiring.marcas group by 1 having count(*)>1` → 0 rows (5 marcas / 5 orgs, 2026-11-12); unique indexes on `marcas` are `(org_id,slug)` and `(org_id) WHERE is_primary` only; guard commits `26060405a4`, `6467b11fad`, `87b60482bb` are on local `feat/one-brand-per-org` only |
| P1.2 | q03 check: evaluation mode in the UI | — | **shipped (answer: yes)** | `products/agents/frontend/src/components/studio/ControlesCard.tsx:273-288` (switch on Julia's core, platform admin only), instance badge `:237`; prod `agents.agents` has the core row with `modo_avaliacao=true`, 1 evaluator. What 88c6815168 removed on 11-10 was the separate "fase de testes" switch, not evaluation mode |
| P1.3 | r17 check: owner phone fallback visible | — | **shipped (answer: yes, but two sources)** | agents nav "Configurações do agente" (`products/agents/frontend/src/App.tsx:73,107`, platform admin) → field `ConfiguracoesAgente.tsx:36`; prod `agents.runtime_settings.numero_fallback_atendimento` set 2026-11-11 16:16Z. NOT one source: core `public.notification_owner_recipients` (118) is a second owner-number list and has **0 active recipients** in prod, so owner WhatsApp notices currently have nobody to go to |
| P1.4 | r23 LGPD sign-off | EDIT `KNOWLEDGE-BASE/CONTEXT/PATTERNS/legal/lgpd-privacy-program.md` §4, §9 | **shipped (approved with 7 conditions)** | the 7 conditions are in §4 of that pattern; re-read before building P3.G |
| P1.5 | r15 promoted to KB | EDIT `KNOWLEDGE-BASE/CONTEXT/PATTERNS/backend/tenancy-license-gate.md` § One brand per org | **shipped** | — |
| P1.6 | Reminders r33, r10, r11 | memory `MEMORY-reminders.md` | **shipped** | the three lines show at session start |

**Behavior guarantee**: docs and memory only; no runtime change.

## Phase 2 — W1: four parallel engineering slices (DEFERRED — dispatch now, b5 owns)

| # | Items | Agent | Files (collision class) | Acceptance | Verify recipe |
|---|---|---|---|---|---|
| W1-A | s01 product-login mints the noc session (SSO S3) + s02 logout lands on the product's landing | backend-engineer + frontend-engineer pair, or product-engineer (Opus) | core SSO: `products/core/backend/app/**/sso*`, `products/core/frontend/src/**` login/SSO pages, seed FE logout redirect (`seed/lib/frontend/**/auth*`). Redo from `feat/sso-s3-central-login-v2` (local, 4 ahead / 658 behind; 19 files) on a fresh branch | logging into a product creates the core session too; product back-arrow ends the product session; logout from product X lands on X's landing; strict `== 401` auth tests | live: log in on agents, open core without a second login; log out on agents → agents landing |
| W1-B | s03 grants per product and org with personal tokens (+ r15 guard landing, see note) | backend-engineer (Opus) | `seed/lib/backend/noctusai_lib/api/**` tokens/grants, `products/agents/backend/**` consumption, SW grant sink; redo `feat/jl-s1-seed-tokens-grants` (30 files, 1234 behind); `feat/jl-s8-sw-grant-sink` (204 files) is too big to rebase: re-slice it into W2 | a token is scoped to (org, product); a call outside its grant → 403; migration numbers free; seed Fake+Real+factory | live: mint a personal token for org A/agents, call SW with it → 403, agents → 200 |
| W1-C | claim_next_job polling reduction (seed jobs organ) + polling backstop | backend-engineer | `seed/lib/backend/noctusai_lib/domain/jobs/{worker.py,wake.py}`, per-product worker wiring only where a cap is overridden, + keeper in `mcp/noctusai/tools/noctus/dev/compliance.py` (append-only; shared file, coordinate with W2-T) | prod `rpc/claim_next_job` ≤ ~6k/day (baseline 56,022 in the 24 h to 2026-11-12 12:00Z, ≈ 20 worker loops × 2,880 at the 30 s idle cap); in-process enqueue still picked up < 1 s; every cross-process producer listed with its worst-case pickup and either woken or accepted by the owner; seed test asserts call COUNT over N idle ticks; keeper refuses an unbounded read / fixed 1 s idle in a `run_forever` / `claim_gate` path | Supabase edge-log query `count(*) where event_message like '%claim_next_job%'` over 24 h after deploy |
| W1-D | notifications: r18 per-product + per-kind switches page, r08 opt-out-with-reason owner notice, r03 skill-scout notice (WhatsApp only), r17 owner number set once | product-engineer (mockup first, product-designer) | core: `products/core/frontend/src/pages/admin/AdminNotificacoes.tsx`, `products/core/backend/app/services/{notification_catalog_service,owner_recipients_service}.py`, seed `noctusai_lib.domain.notification_catalog`; agents `runtime_settings` fallback reads from the core owner number | the 117 catalog already has per-(product, kind) `enabled` — confirm the page exposes it for every product (only 2 products declare kinds today); new kinds `julia_opt_out` carries the reason, `skill_scout_novo_skill` WhatsApp-only; ONE owner number in core consumed by agents fallback; prod has ≥ 1 active owner recipient | live: toggle a kind off → `notification_sends` shows `suppressed`; trigger an opt-out in eval mode → owner WhatsApp shows the reason |

**Not in W1 (moved for the claim_next_job slice):** the tooling bundle W2-T (m01 model-name rule + agent `model:` keeper, m07 declared-but-unbuilt keeper, r14 build-vs-standard gate, the `noc-guard:primary-write` hook that times out and fails closed on read-only greps). It is file-disjoint from A, B and D; it shares `compliance.py` with W1-C, so run it as a 5th W1 slice only if a steward can serialize the two `compliance.py` appends; otherwise it heads W2.

## Phase 3 — W2 (DEFERRED — fires on T1; E also needs T2)

| # | Items | Home / depth | Notes |
|---|---|---|---|
| W2-T | m01, m07, r14, primary-write hook timeout | `KB § PATTERNS/common/gate-methodology-sync.md`; `KB § PATTERNS/backend/polling-request-budget.md` (models: Opus 5.5 / Sonnet 5.5 / Haiku 5.5 only) | r14 owner note: "gated, if not already; refine and increment it" — no build-vs-standard gate exists today (research-method.md only routes build-vs-buy to `architect`) |
| W2-E | r06 one Julia per company (agents per product per company), r07 outbound greeting (owner: NOT deterministic, the template was an example), r02 auto-refine eval loop (4 more evals), r04 owner-only chat on the agent details page, r01 creator chat in "Gerar com IA" | `agent-templates-2026-11.md`, `product-agents-platform-2026-10.md` | fires on T2 |
| W2-F | m13 Vista "observações internas" note on every Vista write, r09 property URL pattern per company (owner: keep as is for now), s06 price evaluator Phase 0 capture, r10 imovelweb intake + config UI (T4) | `social-wiring-imoveis-vista-2026-08.md`, `sw-price-evaluator-2026-10.md` | r10: research imovelweb on reliable sources (skill `noc-research`) and build a config UI |
| W2-G | r24 field sets per contract model selectable in the UI, r25 per-doc-type model routing + fallback + conciliation, r26 DPI fix (confirm or open), r23 permutas note→fields (T6 + the 7 LGPD conditions) | `sw-contract-reliability-2026-10.md`, `sw-drive-extraction-2026-09.md` | — |
| W2-H | s05 nosnolimiar clinical tools | spec `products/monica/projects/clinical-tools-build/` (product folder slug; the rename is in flight) | owner: start without waiting for the rename; the rename is in flight separately, so it stays in this slot |
| W2-S8 | `feat/jl-s8-sw-grant-sink` re-sliced on top of W1-B | `product-agents-platform-2026-10.md` | — |

## Phase 4 — W3 (DEFERRED — fires on T3)

| # | Items | Home |
|---|---|---|
| W3-1 | s04 CoreStudio Twin batch reels editor ("10 automated reels, 100") | `products/social-wiring/projects/core-studio-build/specs/twin-editor-design.md` |
| W3-2 | r22 360 tour builder inside SW | spec commit `d51014a43` |

## Advisor items (parallel to W1/W2, read-only)

| Item | Advisor / skill | Output |
|---|---|---|
| m02 Supabase edge/DB functions vs our FastAPI containers | `architect` | short ADR |
| r13 what "ready to use" means for a product | `product-manager` | KB new-product section, from the Assistant run |
| r19 WhatsApp-lines plan (multiple SW/WAHA instances) | `architect` + `integrations-engineer` | fold into the WhatsApp-lines project |
| r20 measure WAHA RAM per instance | `devops-engineer` | numbers in the WhatsApp-lines plan |
| m08 24 h browser-automation server on the VPS (owner: study past browser / Instagram runs first) | `architect` + `ops-steward` | exploratory study |
| m14 fold the Instagram performance research into `noc-ig-analysis` | skill `noc-ig-analysis` | skill update |
| m06 hygiene sweep + audit of what the contextualize tools actually consume | skill `noc-hygiene` | sweep report + deletions on a branch |

## Already handled (kept for the record)

- f01 Julia multi-info capture + similar-properties offer: `feat/agents-desejados-do-padrao` MERGED.
- f02 Supabase breaker: `feat/supabase-breaker` in the merge queue (b5).
- r32 Orbity white-label CRM: folded into `feat/roadmap-white-label-canons` (queued); the owner said more on systems and white-label in the Orbity session; ask it.
- r11 Julia "step 2" (deep documentation / legal depth after the basic qualification): explained to the owner 2026-11-12; reminder set; build home is `agent-templates-2026-11.md` after T2.
- r33 CRM guardian agent: wanted "but not now" (T5, reminder).

## Anti-goals

- ❌ Re-litigating dropped rows. The 22 unticked rows are dropped; they come back only if the owner raises them.
- ❌ Rebasing 1,000-commit-behind branches by force. Redo on a fresh branch off `origin/dev`, using the old branch as a reference.
- ❌ Deterministic outbound greeting (r07). Owner: "I don't want determinism, it was just an example."
- ❌ Copying the sweep report or any client data into git.

## Open questions

- **Q1**: r17 — should the core owner-recipients list (118) BE the one owner number, with the agents fallback reading it, or the reverse? Default in W1-D: core is the source (owner: "everywhere that uses it consumes from noc").
- **Q2**: W1-C — which cross-process producers need a wake channel (Redis pub/sub) vs accept up to the idle cap?

## Decision log

- **2026-11-12**: owner delegated ("go on with recommended path"): W0 + W1 go; s05 stays in W2 (rename in flight separately); legal-advisor LGPD sign-off for r23 runs now → approved with 7 conditions.
- **2026-11-12**: claim_next_job polling reduction added to W1 as W1-C; the tooling bundle moves to W2-T (or a 5th W1 slice if `compliance.py` appends can be serialized).

## Retrospective (filled at first trigger fire)

*To be filled when T1 fires.*

## Composes with

- `KB § PATTERNS/backend/polling-request-budget.md` — W1-C.
- `KB § PATTERNS/legal/lgpd-privacy-program.md` — r23 conditions.
- `KB § PATTERNS/backend/tenancy-license-gate.md` — r15.
- Roadmaps: `sso-identity-hardening-2026-10.md`, `product-agents-platform-2026-10.md`, `agent-templates-2026-11.md`, `sw-price-evaluator-2026-10.md`, `social-wiring-imoveis-vista-2026-08.md`, `sw-contract-reliability-2026-10.md`, `sw-drive-extraction-2026-09.md`.

## File trail

- This doc.
- `KNOWLEDGE-BASE/CONTEXT/PATTERNS/legal/lgpd-privacy-program.md` (§4 permutas paragraph, §9 OpenAI row).
- `KNOWLEDGE-BASE/CONTEXT/PATTERNS/backend/tenancy-license-gate.md` (§ One brand per org).
