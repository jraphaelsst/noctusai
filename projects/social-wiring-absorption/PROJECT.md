# social-wiring Absorption — Project Document

> **Living document.** Revise phases, fold optimizations, keep §11 current. Zero-context reader: everything needed is inlined here — do not assume the originating conversation is available.

- **Created:** 2026-05-16
- **Last updated:** 2026-05-16
- **Status:** Design locked → Wave 0 ready
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com) · architect: Claude Opus 4.7
- **Related docs:** `KB § PATTERNS/whatsapp-chatbot-seed.md`, `KB § PATTERNS/seed-fake-real-adapter.md`, `KB § GUIDES/new-product.md`, `KB § PATTERNS/containerization.md`, root `SESSION-NOTES_*.md` (5 handoff notes), `OAUTH-PATTERNS-FOR-NOC.md`, `SEED-NEEDS-DEV-AUTH-AND-SQLITE.md`, and the in-home reference set at `projects/social-wiring-absorption/reference/` (promotion manifests + workspace docs copied in Wave 0). **This project is self-contained: all content is brought in-home; no durable doc references the originating workspace path — it is transient and the user retires it manually after absorption.**
- **Project slug:** `social-wiring-absorption` (cross-product / platform-infra → lives at `projects/social-wiring-absorption/`).

---

## 1. Context & Purpose

A sibling seed-workspace (`noctusai-youtube-crawler`) was used as a **functions development environment**: a place to build and live-validate a multi-channel media-wiring system against real external APIs, isolated from noc. It now contains a production-validated stack — surface-agnostic OpenAI chatbot (WhatsApp via WAHA **and** a platform `/chat` page), multimodal intake (audio→Whisper, image/video→vision, PDF→PyMuPDF), Google Calendar/Maps/Drive, Meta Facebook+Instagram Graph (read), YouTube upload, Vista CRM, a Fernet credential vault, conversation/message dedup, and a single-URL proxy/tunnel — plus **14 `.promotions/` manifests** that pre-map every piece to its noc seed destination.

This project absorbs that workspace into noc as **one new product, `social-wiring`** — a "media-wiring-into-one-place" CMS. In the same motion noc consolidates four in-home products into it and retires them:

| Product | Disposition | Why |
|---|---|---|
| `media-scheduling` | **Delete** (truly stale) | Empty scaffold; superseded 2026-05-11. |
| `youtube-crawler` (in-home) | **Delete** (truly stale) | Phase-1 only (thin OAuth wrapper); fully subsumed by social-wiring. |
| `mailing` | **Absorb → then delete** | Unique email-marketing platform; its domain moves *into* social-wiring as a module, then the standalone product is retired. |
| `imobi-scheduling` | **Absorb → then delete** | Unique real-estate scheduling bot; its domain moves *into* social-wiring as a module, then the standalone product is retired. |

The win: one consolidated, production-functional CMS product on noc's house single-container model; all the cross-product capabilities live in seed where every other product can consume them; the fragmented in-home products disappear; future separately-developed seed-workspaces ship pre-mapped for absorption.

---

## 2. Confirmed constraints

- **Product name** — `social-wiring`. *(No longer "just a youtube crawler" — it is media-wiring-into-one-place. Rename on the way in.)*
- **Product is a CMS; cross-product funcs are seeded** — the chatbot, Google Calendar/Maps/Drive, Meta, email, multimodal, YouTube etc. land in `noctusai_lib`/`noctusai_seed` so EVERY product can consume them on demand; the *product* keeps its platform + frontend and is re-skinned to the CMS scope (per the new-product seeding rule: adapt the new product's frontend to its scope). *(The sibling repo was a funcs-dev environment by design.)*
- **4-product disposition** — delete the 2 truly-stale outright; absorb mailing + imobi-scheduling *into* social-wiring (their domains become modules of the new product), then retire the standalone products. *(User: "the other 2 not-stale become stale because they are inside the new product, not separate ones. make sure to doc everything correctly.")*
- **Seed reconciliation = FULL reconcile to sibling** — the sibling's adapters are live-validated; noc's existing seed adapters may not be. Where they diverge, **noc seed is rewritten to match the sibling's validated version** — even for already-seeded adapters (chatbot/calendar/maps/drive). Then existing noc consumers (therapy, PF, daily-life, ERP, core) are adapted to consume the reconciled seed correctly. *(User: "full reconcile to sibling… then adapt existing products to consume correctly the new brought-in funcs. As they are all noc-children code, we might not get into too much trouble.")*
- **Promotion-map automation** — the `.promotions/` + `PROMOTIONS.md` map the sibling carries is loved and must become **automatic**: whenever a separately-developed seed-workspace is created, the scaffolding system auto-creates and maintains an absorption map so a future noc absorption is already mapped + explained. Document as methodology. *(User explicitly requested; whether the sibling's map was hand-made or seed-generated is unknown — make it deterministic going forward.)*
- **Divergent-architecture rule** — an incoming product whose architecture differs from noc's house model (e.g. the sibling's 2-container backend+nginx+proxy) MUST be refactored to fit noc's single-container house model on absorption; new products inherit the house model so this won't recur, but the rule is documented for future different-architecture absorptions. *(User's earlier explicit ask.)*
- **No collisions / preserve others' work — CONSUMES the general methodology rule, does not redefine it.** The file-disjoint / worktree-base / parallel-agent-collision discipline is a **platform-wide dev rule** (CLAUDE.md §1 branching-first orchestration + `KB § PATTERNS/branching-and-merging.md` §16-§17 + memory `feedback_worktree_base_verification` / `feedback_parallel_agent_collision_protocol`). This project just applies it — it is NOT an absorption-specific rule. *(User: "the no collisions rule should be our methodology rule, not an absorption one… I feel like we have a duplicate or a misplaced rule." → reconciled in W5.5.)* Concrete application here: Wave-1 false-started with `isolation:worktree` (agent worktrees branch from `origin/main` 92b35d1, blind to the absorption branch's reference set + the untracked root notes; Engineer META correctly refused to fabricate). Correction applied: engineers run in the **master tree** on `feat/social-wiring-absorption` (sanctioned master-tree-parallel pattern), strictly file-disjoint by package, **ZERO engineer git ops** — architect stages + commits per package.
- **Container build paused** — the fleet docker build was stopped (no point building products about to be deleted/replaced). **Resume + refactor docker builds is the final phase, after absorption completes.** *(User: "after done with the absorption process, please refactor and continue the docker builds.")*
- **Bring ALL in-home; zero durable references to the originating workspace** — every needed artifact (code, promotion manifests, workspace docs) is copied into noc in Wave 0. No durable doc (this PROJECT.md, KB, CLAUDE.md, memory) references the originating workspace's path — it is transient. *(User: "please dont leave any references to sibling repo, bring ALL in-home." Direct application of the `durable-docs-self-contained` methodology rule.)*
- **User retires the originating workspace manually** — deleting it is NOT our action. We only sign off that everything useful is in-home. *(User: "I'm gonna delete that repo after absorbing it. But i'll do it manually, no need to do that for me." Completeness check still required per "check if we still have anything useful not yet set before deleting".)*
- **Document the absorption process as a durable playbook** — the repeatable "absorb a separately-developed seed-workspace into noc as a product" procedure is written as a KB guide + CLAUDE.md pointer + memory (Wave 5), so future agents know exactly how to do this. *(User: "doc the process of absorbing this new product… leave it explicit so other future agent know how to properly do this new product absorption task.")*
- **`SHARED.md` at noc root** — unrelated personal-blog draft, not part of this work. Left untouched; flagged for the user to remove at will.

---

## 3. Design principles

1. **The `.promotions/` manifests are the migration map.** The 14 manifests (in-home at `reference/.promotions/`) + the root `SESSION-NOTES_*.md` set + `OAUTH-PATTERNS-FOR-NOC.md` + `SEED-NEEDS-DEV-AUTH-AND-SQLITE.md` are the authoritative source for what lifts where. Reconcile against them; don't re-derive. *(Prefer "the set" over a count — hardcoded counts in living docs drift; W0.2 found the workspace's own `PROMOTIONS.md` index stale at 7-of-14, which is the evidence for the W5.2 auto-derive rule.)*
2. **Sibling-validated wins every conflict.** Default "seed is canonical" is *inverted for this absorption*: the sibling ran live against real OpenAI/Google/Meta/WAHA/Vista. Where noc seed diverges, noc bends.
3. **Seed gets Protocol+Fake+Real+factory, always.** Every IO module lifted lands in the canonical seed shape (`KB § PATTERNS/seed-fake-real-adapter.md`); no half-shipped Protocol-only or Fake-only.
4. **File-disjoint parallelism in the master tree.** Wave-based dispatch; each engineer owns a strictly disjoint package path **in the shared `feat/social-wiring-absorption` tree** (NOT a worktree — see §2 correction); engineers do ZERO git ops; the architect stages + commits per package and runs integration tests before opening the next wave.
7. **Integrations are independent seed modules; composition is a product/tool-layer concern.** Each integration (`youtube`, `vista`, `meta`, `whatsapp`, `google_*`, `media`…) is its OWN standalone seed module (Protocol+Fake+Real+factory). They are NEVER fused in seed. Cross-integration workflows — whatsapp+vista (chatbot looks up a Vista property then replies on WhatsApp), meta+vista, youtube+drive, etc. — are **orchestrated at the chatbot-tool / product layer** (Wave 2), composing the independent modules. Dispatch grouping (e.g. one engineer builds both `youtube/` and `vista/`) is an orchestration convenience only — the delivered modules stay separate. *(User: "make youtube AND vista features. not youtube+vista. They should be separate and orchestrated in that specific workflow. But we might have a meta+vista / whatsapp+vista…")*
5. **No deletion before green.** The 4 in-home products are deleted only after social-wiring + reconciled consumers are green. The originating workspace is the user's to delete manually — we only produce a completeness sign-off.
6. **Three-way doc sync for every new rule.** Methodology rules (promotion-map automation, divergent-arch refactor, full-reconcile precedent, the SEED-NEEDS seed fixes) land in KB + CLAUDE.md/topical + memory the same session they're decided.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every product?** YES for the cross-product capabilities (chatbot, WhatsApp, Google, Meta, multimodal, email, credential store, dev-auth, vite-build-arg, standalone-frontend degradation) — these are uniform integration contracts. NO only for the *product-specific domain logic* (mailing's campaign/automation engine, imobi's SchedulingEngine) which is correctly product-bounded inside social-wiring.
2. **Is the data source product-specific?** Mixed: the integrations are product-agnostic (seed); the consolidated domain data (campaigns, appointments, video catalog) is social-wiring-specific (product schema).
3. **Is the placement product-specific?** Integrations → seed (`noctusai_lib`/`noctusai_seed`). Domain modules + CMS UI → `products/social-wiring/`.
4. **Is the visibility / permission rule the same?** Seed integrations: uniform. Product domain: social-wiring RLS.
5. **Does the seam already exist in seed?** PARTIALLY — chatbot/whatsapp/calendar/maps/drive/llm/credential-resolver/oauth/vista seams exist (to be *reconciled* to sibling); Meta / YouTube-upload / PDF / video-keyframe / persistent-dedup / scope-discovery / response-registry / dev-auth+sqlite / vite-build-arg / standalone-frontend-degradation are **new seams**.
6. **Default-on or opt-in?** Integrations: opt-in per product (factory-selected, env-gated) — default Fake. dev-auth+sqlite: opt-in, hard-off in prod. vite-build-arg + standalone-frontend degradation: default-on (universally beneficial fixes).

**Litmus — per-product code count:** the cross-product concern is **0 lines per consuming product** (factory inheritance). The only per-product code is social-wiring's own domain modules + CMS wiring (a product, by definition) and the *adaptation* of existing consumers to the reconciled seed (mechanical, seed-shaped).

**Phase plan implications:** §6 phases work in **seed** (Wave 1) then in **the one new product + mechanical consumer adaptation** (Waves 2-3). No "for each product, mount X" framing — the integrations are inherited from the factory, not replicated.

---

## 4. Scope

**In scope:**
- Bring all originating-workspace reference artifacts in-home (manifests + workspace docs → `projects/social-wiring-absorption/reference/`).
- Completeness audit (everything useful is mapped by a manifest/note and copied in-home, or surfaced) → produces the sign-off the user needs before manually deleting the workspace.
- Scaffold `social-wiring` via the seed factory (single-container house model).
- **Full-reconcile seed**: lift/upgrade every cross-product capability into `noctusai_lib`/`noctusai_seed` in Protocol+Fake+Real+factory shape, sibling-validated version winning conflicts. Includes the 14 manifests + the SEED-NEEDS fixes (dev-auth+sqlite, vite-supabase-build-arg, standalone-frontend-drift, single-url proxy/tunnel where still relevant under the house container model).
- Port sibling product functionality into `social-wiring` consuming the reconciled seed.
- Absorb `mailing` domain (campaigns/automations/segmentation/analytics/debrief) + `imobi-scheduling` domain (SchedulingEngine/appointment-lifecycle/LID-auth) into `social-wiring` as modules.
- CMS frontend adaptation (re-skin the new product frontend to its scope).
- Adapt remaining noc consumers (therapy, PF, daily-life, ERP, core) to the reconciled seed.
- Delete the 4 in-home products; sanitize all references (compose, start.sh, ports, KB, CLAUDE, core product-registration migration, seed tests).
- Methodology codification (three-way sync): the **absorption playbook** (repeatable process doc); promotion-map automation; divergent-arch refactor rule; full-reconcile precedent; SEED-NEEDS seed fixes documented.
- Refactor + resume docker builds for the new consolidated topology.
- Completeness sign-off so the user can manually retire the originating workspace.

**Out of scope (for now):**
- Meta *posting* / Instagram publish — sibling shipped read-only; write surface deferred (Meta App Review per scope). Adapter shaped to extend.
- TikTok integration — sibling explicitly deferred to a future branch; not in this absorption.
- Live re-validation against real external APIs — the sibling already validated live; noc-side re-validation is mocked-tests + smoke. Real-cred smoke is a post-absorption user step.

---

## 5. Architecture / Data Model

**Seed targets (Wave 1 — disjoint packages):**
- `noctusai_lib/domain/chatbot/` — openai_orchestrator, message_store, response_registry, content-stats helper. (reconcile + extend)
- `noctusai_lib/integrations/whatsapp/` — WAHA reconcile, @lid 3-tier auth, vendor-URL rewrite, **persistent webhook dedup** (Redis SETNX + UNIQUE(provider_message_id)). (reconcile + extend)
- `noctusai_lib/integrations/google_calendar|google_maps|google_drive/` + `…/google/scopes/` — reconcile to sibling adapters; add scope auto-discovery + post-consent introspection. (reconcile + extend)
- `noctusai_lib/integrations/meta/` — **NEW** FB+IG read adapter (Protocol+Fake+OAuth+SystemUser+factory) + scope-discovery + `/api/meta/{status,scopes}`.
- `noctusai_lib/integrations/media/` + `…/llm/` — multimodal: audio/vision (reconcile) + **NEW** PDF→text (PyMuPDF) + video keyframe (ffmpeg) + refusal-retry helper.
- `noctusai_lib/integrations/youtube/` — extend query-only client with **upload** surface; Vista parity check.
- `noctusai_lib/security/token_store` (credential store → seed) + `noctusai_seed` dev-auth+sqlite + `seed/framework/frontend` vite-supabase-build-arg + `seed/lib/frontend` standalone-degradation (consents/notificacoes topology-aware).

**Product target (Wave 2):** `products/social-wiring/{backend,frontend}` — seed-factory app; modules: `media_wiring` (chatbot/intake/upload/CRM), `email_marketing` (from mailing), `scheduling` (from imobi); CMS frontend (nav: Dashboard · Agente/Chat · Vídeos · Upload · WhatsApp Conexão/Monitor · Campanhas · Automações · Agendamentos · Configurações · Equipe).

**Carry-forward (W0.2 flag):** `backend/WAHA_RESPONSE_FORMATS.md` lives ONLY in the workspace product tree (not copied to `reference/`, not manifest-covered). It MUST travel with Wave 1.E2 (whatsapp) / Wave 2 (product port) — the engineer reading the workspace product source carries it in. `scripts/sync_waha_webhook.sh` has no manifest → accept-with-rationale N=1, destination `templates/seed-workspace-docker/scripts/` (Wave 5).

**Consumer adaptation (Wave 3):** therapy/PF/daily-life/ERP/core — mechanical updates to match reconciled seed adapter signatures; pytest + vite build as oracle.

**Teardown (Wave 4):** remove `products/{media-scheduling,youtube-crawler,mailing,imobi-scheduling}`; scrub `docker-compose.yml`, `start.sh`, ports registry, `core/.../013_seed_media_scheduling_product.sql` + mailing/imobi product-registration rows, `KB § 02-LANDSCAPE.md`, CLAUDE pattern-adopter lists, seed test fixtures referencing the slugs, `accept-with-rationale.md` entries, `LGPD-WARNINGS.md` imobi entry (resolve or re-home).

---

## 6. Implementation phases (wave-structured for parallel dispatch)

> Waves gate on FF-merge of all prior-wave chunks. Engineers run in isolated worktrees off `origin/main`, file-disjoint. Architect maintains `findings.md`.

### Wave 0 — Foundation
- [x] W0.1 Originating workspace snapshot-committed (transient safety during the process; NOT a durable anchor — superseded by W0.2 bring-in-home).
- [x] W0.2 Bring-in-home + completeness audit ✅ — 40 artifacts copied to `reference/` + `reference/COMPLETENESS-AUDIT.md`; verdict **READY**; 12-item UNMAPPED-useful list captured; project now self-contained. 2 slips logged in findings.md.
- [x] W0.3 Scaffold `social-wiring` ✅ — 58 files at `products/social-wiring/`, core seed-row migration `032`, start.sh `social-wiring:Social Wiring:8011:8160`. **3 issues carried:** (a) README.md+MASTER-PROMPT.md LLM-rewrite failed → seed-template content remains, redo in Wave 2; (b) scaffold template emits `docker-compose.override.yml` registration = drift vs single-env containerization (removed) → fix in Wave 5/6 + doc-code-coherence finding; (c) ports 8011/8160 collide with imobi-scheduling until Wave 4 teardown frees them (transient, build paused).
- [x] W0.4 Author Wave-1 engineer briefs (master-tree, file-disjoint, zero engineer git ops).
- [x] W0.5 Bring validated product SOURCE in-home (195 files → `reference/source/`); project now fully workspace-independent.

### Wave 1 — Full seed reconcile ✅ (master-tree parallel; 7 engineers; 1430 lib + 75 framework tests green)
- [x] W1.E1 chatbot orchestrator+message_store+response_registry+content_stats → `noctusai_lib/domain/chatbot/` (72; commit `11eb9d5`)
- [x] W1.E2 whatsapp @lid+vendor-URL-rewrite+SETNX dedup+response_registry → `noctusai_lib/integrations/whatsapp/` (93; `5b3bd07`)
- [x] W1.E3 google scope-discovery + Drive-read; Calendar/Maps already validated (no-op) → `google_*` (112; `56b2d32`+`ef5d42f`)
- [x] W1.E4 Meta FB/IG read adapter [NEW] + dual-auth + scopes → `noctusai_lib/integrations/meta/` (40; `77613f4`)
- [x] W1.E5 multimodal media + PDF/video-keyframe + refusal-retry → `noctusai_lib/integrations/{media,llm}/` (38; `8e0b27d`)
- [x] W1.E6 YouTube upload surface + Vista Fake/factory (INDEPENDENT modules) → `youtube/` + `vista/` (51; `b941623`)
- [x] W1.E7 token_store + dev-auth(flag-gated) + frontend topology/auth-ready → `security/`+`noctusai_seed/`+`seed/.../frontend` (110; `dafc38b`)
- Integration: held shared deltas committed (`a77602c`); full-suite oracle green (2 non-W1 failures categorized in findings → Wave 2/test-infra).

### Wave 2 — Port social-wiring product ⏳ (depends W1)
- [x] W2.1 ✅ base media-wiring backend (`1808b99`) — 10 routers/21 services/4 adapter subpkgs/5 schemas; single `001` (ref 002-008 folded); **MODULES registration seam** (`MODULES: list[Callable[[],ModuleRegistration]]`; migration markers `-- W2.2/W2.3 tables — ADD BELOW`); 69/70 router+integ (1 = scaffold team-e2e seed-drift `[A]`). Fixed W0.3 scaffold conftest over-substitution.
- [ ] W2.2 Absorb `mailing` → `app/modules/email_marketing/` (in flight) — consumes seed digest/llm; returns register()+migration-SQL+MODULES-line as text.
- [ ] W2.3 Absorb `imobi-scheduling` → `app/modules/scheduling/` (in flight) — consumes seed scheduling/chatbot/whatsapp/google; returns register()+migration-SQL+MODULES-line as text.
- [x] W2.4 ✅ CMS frontend (`<commit in W2.4>`) — 7 pages/7 hooks/components, CMS nav, apiBase house-model, README/MASTER-PROMPT rewritten, package.json name fixed; unblocked by DEP-B seed-frontend WA hooks.
- [ ] ~~W2.5~~ → **W2.5b** (re-scoped; W2.5 correctly blocked: Wave-1 reconciled seed to a resolver architecture contract-incompatible with the validated workspace consumers). **Architect decision:** `credential_store.py` stays product-local (N=1); build 3 product-side bridge adapters (Calendar/Meta resolver + Drive reader) + routing `settings→api_key` shim; consume seed factories through bridges; behavior-preserving (in flight). Seed follow-up (N≥2): `get_*_adapter` lack a `credential_store=` convenience path → seed-improvement follow-up project. W5.7(a) extended: verify-seed-ships-it must assert factory-SIGNATURE-compat for the named consumer, not just same-name.
- Architect integration (post W2.2/W2.3/W2.5 FF): splice the two migration SQL blocks under their `001` markers; append the 2 MODULES register lines in `main.py`; merge any `requirements.txt` deltas — all returned-as-text by the engineers (shared-file deltas held, Wave-1 pattern).

### Wave 3 — Adapt PILOT consumers to reconciled seed ✅ (depends W1; parallels W2)
> **Pilot-products-first cadence** (NEW platform rule, [[feedback_pilot_products_first]]): seed ripples prove on 3 canonical pilots — `erp-imobiliario` · `therapy-platform` · `social-wiring` — + `core` (control-plane, always-in). Non-pilots are NOT adapted per-change; they extend in Wave 3b only after pilots are green. *(User: "use erp, therapy and social wiring as canonical pilots… instead of working on every product at the same time. It's consuming time and tokens.")* PF/daily-life Wave-3 engineers were stopped + their partial edits reset to pristine the moment this rule landed.
### Wave 3 status ✅ — 3 pilots green + DEP-A structural root fix landed (`4b6c6c2`); zero reconcile-induced breakage confirmed platform-wide.
- [x] W3.1 therapy-platform (pilot) — 1381 passed / 0 fail consuming reconciled seed (with conftest-helper neutralized); zero files changed (correctly surfaced the seed bug, didn't bandaid). Frontend tsc: pre-existing supabase-js skew (not W1).
- [x] W3.4 erp-imobiliario (pilot) — 1899 passed, tsc clean; Vista Fake/factory + PyMuPDF additive-safe; conftest framework-fallback applied (commit `c16bfae`); 21 residual = pre-existing fixture drift.
- [x] W3.5 core (control-plane) — 531 passed; **CORS root-fixed** (registry-derived assertion, no frozen literal) + config conftest re-register; 39 CORS tests green (was 13 fail) (commit `c9e1abb`). CORS-8140 = `b91043f` media-scheduling removal, NOT W0.3.
- [x] DEP-A ✅ (`4b6c6c2`) — `purge_shadowing_editable_finders` per-package-root aware; daily-life/PF/ERP/core collect clean with ZERO workaround (228/625/1954/540, 0 err); 8/8 helper tests. Root = combination (W1.E7 2026-05-11 generalization × seed/{lib,framework} axis-swap); structural fix is trigger-agnostic. Therapy now collects natively (no PYTHONPATH crutch). The ERP/core/W3.5-config conftest call-site workarounds are now harmless no-ops → **follow-up: post-FF mechanical cleanup chunk** to remove them (file-disjoint; accept-with-rationale until then).
- Deferred follow-up (surfaced, not silent): `@supabase/supabase-js` version-lockstep across seed-frontend + all product frontends (pre-existing skew, cross-cutting) → W5.7 / separate follow-up.

### Wave 3b — Extend to non-pilots (GATED on Wave 3 pilots green; mechanical by then)
- [ ] personal-finance · daily-life · adconnect · dev-team (+ any other survivors) — apply the now-de-risked adaptation shape proven on the pilots. Deferred by the pilot-first rule (named destination, NOT a silent skip). Confirmed-safe signal: Wave-1 seed changes were additive-only exports → PF showed zero reconcile-induced breakage (baseline failures pre-existing).

### Wave 4 — Teardown (depends W2+W3 green)
- [ ] W4.1 Delete 4 products · W4.2 sanitize compose/start.sh/ports · W4.3 core product-registration migration · W4.4 KB/CLAUDE/seed-test/accept-with-rationale/LGPD-WARNINGS scrub.

### Wave 5 — Methodology codification (three-way sync; parallels W2-W4)
- [ ] W5.1 **Absorption playbook** — author `KB § GUIDES/absorb-seed-workspace.md` (repeatable end-to-end procedure: snapshot → bring-in-home → completeness audit → scaffold → full-reconcile waves → port → consumer-adapt → teardown → container-refactor → user-gated workspace retirement) + CLAUDE.md §3 routing pointer + memory entry + MEMORY.md index. The explicit how-to for future agents.
- [ ] W5.2 Promotion-map automation in seed-workspace scaffolding (KB + CLAUDE.md + memory + the scaffolding code/template that auto-emits `.promotions/` + `PROMOTIONS.md`).
- [ ] W5.3 Divergent-arch → house-container refactor rule (KB + CLAUDE.md + memory).
- [ ] W5.4 Full-reconcile-to-validated-source precedent + SEED-NEEDS fixes documented (KB + memory; accept-with-rationale where judgment-bound).
- [ ] W5.5 **Dedupe + amend the EXISTING general parallel-dev rule (NOT a new absorption rule).** The user flagged a likely duplicate/misplaced rule. (a) Audit the overlapping memory entries — `feedback_worktree_base_verification`, `feedback_parallel_agent_collision_protocol`, `feedback_branching_first_orchestration`, `feedback_wave_dispatch_and_pause_on_dependency` — + KB §16/§17 + the CLAUDE.md §1 bullets; identify the duplicate/misplaced one and consolidate. (b) Amend the canonical worktree-base rule (three-way sync: KB §16.7 + CLAUDE.md + memory) to additionally cover **uncommitted/branch-only authoritative inputs are invisible to `isolation:worktree` (branches from origin/main)** → pre-dispatch the inputs must be committed-to-base OR master-tree-parallel OR inlined. This is platform-wide dev methodology; absorption only consumes it. Recurrence with the existing worktree-base entry → formalize.
- [ ] W5.6 Improvement-queue (scout) — bundled proposal in `proposals/`; route #1 stale-PROMOTIONS→W5.2, #2 scaffold-override-drift→doc-code-coherence (W2+), #3 `safely_run` dispatch helper (N=6) + #4 `dependencies.py` boilerplate (N=7-8)→Wave 3 disjoint (exclude the 4 doomed products), re-run `noctus.seed.report` after W1 FF to re-baseline.
- [x] W5.8 ✅ **Pilot-products-first refactor cadence** — three-way sync DONE (`9c55eec`): KB § PATTERNS/project-execution.md § 2.12 (new) + CLAUDE.md §1 bullet + memory `feedback_pilot_products_first` + MEMORY.md index. s3 complete; s4 advisory-keeper candidate → W5.9. Wave-3b "extend after pilots green" to fold into the W5.1 absorption playbook.
- [x] W5.9a/W5.7a ✅ keeper codification (`e9b7b4f`) — `check_seed_export_membership` (W5.7a) + `check_hardcoded_product_slug_set` (W5.9a) shipped to compliance.py + colocated tests (22/22) + KB §4.6/§4.7 + testing.md + 06-AGENTS + memory (`feedback_seed_export_membership_keeper`, `feedback_hardcoded_product_slug_set_keeper`) + MEMORY.md (s4 three-way complete). Calibrated live FPs 685→0 (lesson: import-surface detectors need a live-tree FP sweep, not just tests-as-spec). 1 live true-positive = `test_per_product_cors_sentinel.py:61` → W4 teardown re-homes/derives it.
- [ ] W5.9-rest: (b) tool-code-coherence — a tool that moves a package root must update its guards same-change (axis-swap × `purge_shadowing_editable_finders`); (c) `@supabase/supabase-js` version-lockstep follow-up project (W3.1).
- [ ] W5.7-rest: (b) `check_dockerfile_vite_supabase_args` keeper (E7) — s4; (c) `seed-sqlite-dev-backend` follow-up project (E7); (d) `VistaClientProtocol` follow-up (E6) — extended by W2.5 to *factory-signature-compat* (verify-seed-ships-it must assert the signature the named consumer needs, not just same-name); (e) `compute_content_stats` N=2 dedup at Wave-2 integration; (f) N=2 imobi seed-lift triage (retry_call/PII-redactor/conv-rate-limiter/anomaly/supabase-audit-writer — recurrence vs email_marketing's audit).

### Wave 6 — Containerization resume
- [ ] W6.1 Refactor docker/compose/start.sh for the new consolidated topology (4 products gone, social-wiring in).
- [ ] W6.2 Resume the fleet build; verify house single-container model green.

### Wave 7 — Completeness sign-off (NOT a deletion step)
- [ ] W7.1 Final completeness re-check vs W0.2: assert every useful artifact is in-home + every manifest absorbed → W7.2 deliver an explicit "safe to delete the workspace" sign-off to the user. **The user deletes the originating workspace manually — we never do.**

---

## 6a. Continuous tracks (run every wave — user-directed)

**Improvements engine (parallel, collision-free).** Every wave runs the noc hygiene/absorption scanners (`noctus.hound.scan`, `noctus.dev.improvements`, `noctus.seed.report`, the absorption-search sextet, recurrence scans) over the surface that wave touched. Rule to avoid conflicts: **in-scope improvements are applied inline by the engineer who owns that file** (absorption-search standing duty — they already hold the worktree); **cross-cutting improvements are queued by a read-only improvement-scout and dispatched as their own file-disjoint chunks in the next wave where nothing else touches those files**. Never dispatch an improvement-implementer onto files an active engineer holds. The scout produces a prioritized, parallelizable queue in `findings.md` (Interesting/discovered) + files one bundled proposal per wave.

**Autonomous throughput (user override of the §10 phase-pause default).** User directive: "keep building until done." The architect does NOT pause for "continue" between waves. Progression is automatic on **FF-merge of all prior-wave chunks**. Hard stops remain ONLY for: (a) irreversible/destructive actions without a green precondition (Wave 4 deletions gate on W2+W3 green), (b) security/LGPD, (c) a genuine ambiguity that changes direction (ask, don't guess). Everything else proceeds wave-to-wave on completion notifications.

## 7. Open questions

1. **social-wiring as one mega-product vs. modular sub-domains** — recommendation: one product, three internal modules (`media_wiring`, `email_marketing`, `scheduling`) with clear package boundaries; revisit if the product becomes unwieldy. Decided-by: user, before Wave 2; default proceeds modular-in-one-product.
2. **Single-URL proxy/tunnel manifest under the house container model** — the house model already serves SPA+API on one port + ships profile-gated `<slug>-tunnel`; the sibling's separate `proxy/nginx.conf` is largely redundant. Recommendation: fold only the still-relevant bits (SPA fallback already covered by `serve_spa`), drop the standalone proxy. Decide during W1.E7 / W6.
3. **mailing/imobi live DB data** — absorption is code+schema; any production data migration is out of scope unless the user flags a live tenant. To-discover before W4.

---

## 8. Dependencies & blockers

- Wave 1 FF-merge gates Waves 2 & 3. Wave 2+3 green gates Wave 4. W0.2 gates W7.
- `noctus.dev.scaffold_product` must produce a house-container, seed-factory skeleton (W0.3).
- W0.2 brought manifests+notes in-home but NOT the validated source — W1.E1 proved a true reconcile/port needs the source. **Resolved by W0.5** (195-file validated source tree in-home at `reference/source/`). From W0.5 onward the project is genuinely workspace-independent; no later wave reads the originating workspace.
- Pre-commit KB-sync hook will block on dangling pointers when the 4 products are scrubbed (Wave 4) — KB/CLAUDE updates must land in the same commits.

---

## 9. Success criteria

- `social-wiring` is a seed-factory, single-container product, real-world functional (chatbot multichannel + integrations + email-marketing + scheduling), backend pytest + `vite build` green.
- All cross-product capabilities live in seed in Protocol+Fake+Real+factory shape; `noctus.hound.scan` shows no new absorption debt.
- therapy/PF/daily-life/ERP/core green against the reconciled seed.
- The 4 products are gone with zero dangling references (`verify-kb-sync.sh` + pytest + vite builds pass repo-wide).
- Methodology rules three-way-synced; seed-workspace scaffolding auto-emits an absorption map.
- Fleet docker build green on the new topology.
- Sibling repo retired only after the completeness gate; snapshot branch retained.

---

## 10. How to use this plan

- Single source of truth. Live-tick `- [ ]`→`- [x]` as work completes; flip phase headers per the icon convention.
- Wave-gated, not phase-paused: dispatch a wave's engineers in one tool-use turn (true parallelism); the architect FF-merges and gates the next wave. The user thinks-with the architect while engineers build.
- Engineers stage + return notes; architect reviews diff, commits per chunk, FF-merges. Commit only own work.
- Revise when understanding changes; commit plan changes with code.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-16 | Recon (3 Explore agents + 8 handoff notes) + 3-question interrogation; originating workspace snapshot-committed (transient); PROJECT.md drafted; wave structure locked | Claude Opus 4.7 |
| 2026-05-16 | Folded 3 follow-up constraints: bring ALL in-home + zero durable workspace-path refs; user retires workspace manually (sign-off only, no deletion by us); author a durable absorption playbook (W5.1) for future agents | Claude Opus 4.7 |
| 2026-05-16 | W0.1+W0.2 ✅ — 40 artifacts in-home, project self-contained, completeness verdict READY; architect fixes applied (count→set phrasing; WAHA_RESPONSE_FORMATS carry-forward flagged for W1.E2/W2) | Claude Opus 4.7 |
| 2026-05-16 | **Wave 1 ✅** — 7 engineers, master-tree parallel, 1430 lib + 75 framework tests green; per-package commits `11eb9d5`/`5b3bd07`/`56b2d32`+`ef5d42f`/`77613f4`/`8e0b27d`/`b941623`/`dafc38b` + integration `a77602c`. W0.5 source-in-home (`71b9dab`). 13 suite failures categorized: 12 pre-existing test-infra (noctusai_seed exec_module shadow, not W1), 1 W0.3-scaffold CORS side-effect (`localhost:8140` dropped → Wave 2/4). Wave-1 cross-engineer lessons → findings + W5.7. | Claude Opus 4.7 |
| 2026-05-16 | **Wave 3 ✅** — DEP-A `4b6c6c2` (per-package-root structural fix; daily-life/PF/ERP/core collect clean ZERO workaround) + DEP-B `da50d94` (seed-frontend WA hooks; Conexao/Monitor unblocked; W5.7a N=2). 3 pilots green, zero reconcile breakage platform-wide. Diagnosis final: combination (W1.E7 generalization × axis-swap), structurally fixed. Cleanup follow-up: remove now-redundant conftest workarounds post-FF. | Claude Opus 4.7 |
| 2026-05-16 | **Wave 3 pilots ⏳→evidence-green** — ERP `c16bfae` (1899) · core `c9e1abb` (531 + CORS root-fix, 39 green) · therapy (1381, zero files, surfaced seed bug). All 3 pilots: ZERO reconcile-induced breakage → Wave-1 backward-compat + pilot-first VALIDATED. Converged diagnosis (git-S): conftest fails = pre-existing axis-swap helper defect (not W0.3/W1.E7); CORS-8140 = `b91043f`; supabase-js skew separate. DEP-A (conftest-helper root) + DEP-B (seed-frontend WA hooks) dispatched. W5.9 added. | Claude Opus 4.7 |
| 2026-05-16 | **NEW rule: pilot-products-first** (user) — seed ripples prove on erp+therapy+social-wiring+core only; non-pilots → Wave 3b after pilots green. Wave 3 re-scoped mid-flight: stopped W3.2(PF)/W3.3(daily-life), reset their partial edits; therapy/ERP/core continue + W2.1/W2.4. Memory `feedback_pilot_products_first` + MEMORY.md written (s2); W5.8 = KB+CLAUDE three-way + advisory keeper. | Claude Opus 4.7 |
| 2026-05-16 | W0.3 ✅ scaffold (branch `feat/social-wiring-absorption` off origin/main); 3 issues carried (README/MASTER rewrite, override-drift, port overlap). Added §6a Continuous tracks: Improvements engine (collision-free) + Autonomous throughput (user override). | Claude Opus 4.7 |
| 2026-05-16 | Wave-1 false start: `isolation:worktree` branches from origin/main → engineers blind to branch-only/untracked inputs (META hard-stopped, correct; 6 others stopped clean, no commits). Correction: master-tree-parallel, no engineer git ops. Brought 9 root handoff notes in-home (committed, self-contained). Added principle 7 (integrations independent; combos orchestrated at product layer). Scout queue transcribed → findings + W5.5/W5.6. | Claude Opus 4.7 |
