# AI Expansion — Project Document

> **Living document.** Revise phases, fold in optimizations, update the Change Log as work progresses. Flip `- [ ]` → `- [x]` live. Interrogate the user before revising scope.

- **Created:** 2026-04-19
- **Last updated:** 2026-04-19
- **Status:** Phase 1 atlas + §5a Pattern Catalog shipped (enriched with lessons from ERP Metas build-out). Phase 2 (user triage) pending user review. Recommend triaging **by pattern** (P1–P6) rather than by opportunity — one pattern unlocks many rows.
- **Owner / stakeholders:** @jraphaelsst
- **Related docs:**
  - `task.md` (Multi-Provider LLM Platform — Phases 1–10 — produced the lib/framework this project builds on)
  - `KNOWLEDGE-BASE/CONTEXT/04-SHARED-LIBRARY.md` § `llm/`
  - `KNOWLEDGE-BASE/CONTEXT/backend/05-AI-FEATURES.md`
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/lgpd.md`
  - `KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md` (product roster)
- **Project slug:** `ai-expansion` (phase proposals land in `mcp/noctusai/proposals/ai-expansion/`)

---

## 1. Context & Purpose

The multi-provider LLM lib (`noctusai_lib.llm`) shipped in `task.md` made AI access a **seed-inherited feature**: any product gets `chat_completion`, `generate_embedding`, `transcribe_audio`, `analyze_image` with zero wiring. Before the lib, only two products had AI (ERP + Therapy) because each integration cost a credential resolver, a client wrapper, and a fallback path. After the lib, the marginal cost of adding AI to a product is writing the service method itself — everything below it is framework.

That changes the question from *"can we afford AI here?"* to *"what would it actually improve for the user?"* This project audits every product in the platform — Core, ERP, PF, Therapy, Daily Life, Mailing, AdConnect — and catalogues concrete AI opportunities grounded in each product's real UX. The atlas in §5 is the first deliverable; the user then triages it in Phase 2; Phases 3+ ship the winners product-by-product.

Today only ERP + Therapy call the lib. Core, PF, Daily Life, Mailing, AdConnect have **zero** AI integrations. This project closes that gap without shipping features for features' sake.

---

## 2. Confirmed constraints

- **Seed-first lib access** — every new AI feature calls `noctusai_lib.llm.*`. No per-product SDK use, no raw `httpx`, no provider-specific code outside `seed/backend/lib/noctusai_lib/llm/providers/`. *(CLAUDE.md rule; already enforced by the lib migration.)*
- **LGPD-first triage** — every opportunity is tagged `lgpd: low | med | high`. `high` opportunities require `noctusai_lgpd_flag` + a documented basis before implementation; `med` may require pre-redaction; `low` ships normally. *(Memory: LGPD-first keeper principle.)*
- **UX-first, not tech-first** — an opportunity only enters the atlas if it answers: *what does the end-user see differently?* Pure backend-optimization AI (e.g. "LLM re-ranks our DB query") is deferred unless it surfaces as user-visible behavior. *(Avoids AI-for-AI's-sake.)*
- **Product owners triage their own atlas** — the user triages Core + personal products; product champions (when they exist) triage domain products. Scope of Phase 2. *(Memory: planners interrogate first.)*
- **Effort-sized per opportunity** — S (≤ 1 day), M (2–5 days), L (> 1 week). Lets the user stack-rank on impact/effort. *(Pragmatic sizing, not estimation theater.)*
- **Streaming is deferred** — the lib doesn't expose `stream=True` yet (task.md §4 Out of scope). Features that require streaming UX (ChatGPT-style chat) are flagged `needs: streaming` and queued after the lib adds support.
- **Response cache must be on for cacheable flows** — anything with `temperature=0` deterministic output should opt in to the Phase 8 response cache to control cost. Clinical/PII flows remain `cache=False`. *(Memory: LGPD hard rule + task.md Phase 8.)*
- **Frontend selector is Phase 10 of task.md** — opportunities that need the org admin to pick a provider/model must wait on `task.md` Phase 10 landing. *(Dependency noted in §8.)*

---

## 3. Design principles

1. **One UX improvement per opportunity.** Don't bundle. "Auto-categorize + export + explain" is three opportunities in one, and buries the LGPD triage.
2. **Degrade gracefully.** Every AI feature has a non-AI fallback — the old UX. `LLMNotConfigured` doesn't crash the page, it falls back to the manual flow.
3. **Explain before automating.** First ship AI as a *suggestion* the user accepts/rejects. Only after the accept rate is high do we move to automatic application.
4. **Cache aggressively where LGPD allows.** Shared corpus lookups (e.g. "explain a Brazilian tax concept") should cache platform-wide; per-org custom prompts must use unique namespaces or `prompt_version`.
5. **Pin the default model at the lib level, override at the service level.** Don't scatter model strings. One constant per service at most.
6. **Show provenance.** User-visible AI output includes a subtle "AI-generated · review" label with a way to flag bad output. Gathers training signal; satisfies LGPD transparency.
7. **No new observability until needed.** Log counts of calls + token estimates where the lib already exposes them. Don't build a usage dashboard until cost becomes the question.

---

## 4. Scope

**In scope:**
- Audit all 7 live products (Core + ERP + PF + Therapy + Daily Life + Mailing) **plus** scaffolded AdConnect for AI opportunities that improve user experience.
- Per opportunity: short description, user-visible change, lib entry point, LGPD tag, effort, dependency notes.
- Triage session output → priority list per product.
- Implementation phases per triaged opportunity (each ≥ M effort gets its own phase; S opportunities can batch).
- Updating `KNOWLEDGE-BASE/CONTEXT/backend/05-AI-FEATURES.md` as new features ship.

**Out of scope (deferred):**
- Streaming-based features — wait for lib support.
- Fine-tuning / custom models per org — wait for a real business case.
- Per-org usage dashboards / token billing — wait for cost pressure.
- Voice-first UX (wake word, dictation, full-duplex) — wait for lib audio streaming + latency work.
- Training a proprietary model — explicitly no.

---

## 5. AI Opportunity Atlas

The matrix below is **the** Phase 1 deliverable. Tags:

| Field | Values |
|---|---|
| Lib | `chat` / `embed` / `audio` / `vision` / `mixed` |
| LGPD | `low` (no PII) / `med` (PII but not sensitive) / `high` (Art. 11 or equivalent) |
| Effort | `S` (≤1d) / `M` (2–5d) / `L` (>1wk) |
| Needs | `selector-ui` (depends on task.md Phase 10) / `streaming` (lib future work) / `org-keys` (needs bring-your-own-key) / `—` |

---

### Core (NoctusAI platform)

Core owns auth, orgs, billing, licenses, SSO, admin. The user-facing audience is **org admins and platform admins**, not end-users, so UX wins concentrate on onboarding, operational friction, and support.

| # | Opportunity | User-visible change | Lib | LGPD | Effort | Needs |
|---|---|---|---|---|---|---|
| C1 | **Onboarding wizard with AI-filled defaults** | After the admin names the org and picks a plan, AI suggests initial team structure, license split, and which products to activate based on industry/size inputs. Admin accepts or edits. | chat | low | M | — |
| C2 | **Audit log narrative digest** | Weekly email / dashboard card that turns the `audit_logs` stream into a one-paragraph English summary ("3 team invites sent, 2 licenses upgraded, 1 unusual login from São Paulo at 03:12"). | chat | med | M | — |
| C3 | **Support-style Q&A over platform docs + org state** | A `?` button in Core UI opens a side drawer where the admin asks "how do I move a user between orgs?" — the answer pulls from `KNOWLEDGE-BASE/` + the admin's own org settings. | mixed (embed + chat) | med | L | streaming (ideal UX), org-keys |
| C4 | **Invoice explain** | On the billing page, each line item has a "why?" link that generates a plain-Portuguese explanation of the charge (pro-ration, upgrade diff, metered item). | chat | low | S | — |
| C5 | **Anomalous-login flag** | Login history page surfaces sessions the LLM flags as unusual (new country, impossible travel). Admin confirms or marks as "expected". | chat | med | M | — |
| C6 | **License-allocation copilot** | On the licenses page, a "suggest allocation" button proposes who gets which product license based on their role + recent activity in each product. | chat | med | M | — |
| C7 | **Org setup health check** | A diagnostic panel that reviews the org's current configuration (SSO status, team structure, seat utilization) and produces a checklist of improvements. | chat | low | S | — |

---

### ERP — `erp-imobiliario` (real estate CRM)

Already uses AI for: description gen, lead scoring, price suggestion, embeddings. Expansion targets daily broker workflows.

| # | Opportunity | User-visible change | Lib | LGPD | Effort | Needs |
|---|---|---|---|---|---|---|
| E1 | **Contract clause extractor** | On a `contratos/` or `matricula/` upload, AI extracts key clauses (parties, price, vencimento, penalties) into a structured sidebar. Broker confirms; data populates the property record. | chat | med | M | — |
| E2 | **WhatsApp intent classifier** | Each inbound WhatsApp message is classified (pergunta sobre imóvel / agendamento / objeção de preço / reclamação) with a suggested template reply. Broker picks one-click. | chat | med | M | — |
| E3 | **Comparable market analysis narrative** | Property listing page shows a "Análise de mercado" card: comparable recently-sold/listed properties + a short paragraph explaining price positioning. | chat | low | M | — |
| E4 | **Client follow-up draft** | On a stalled lead (no activity > 14 days), AI drafts a personalized re-engagement WhatsApp/email using the lead's history. | chat | med | S | — |
| E5 | **Voice note → structured log** | Broker hits record on the client card, speaks in Portuguese, AI transcribes + summarizes into "interação" fields (tipo, próximo passo, imóvel mencionado). | audio + chat | med | M | — |
| E6 | **Certidão OCR + summary** | Uploaded certidões (imobiliária, negativas) get OCR'd + summarized: "ônus reais: 2, impeditivos: 0, vencimento: 2026-05-10". Broker confirms. | vision + chat | med | M | — |
| E7 | **Metas AI coach** | On the Metas page, each salesperson sees one AI-generated coaching tip per week: "você está 12% abaixo do ritmo; 3 leads no estágio negociação precisam follow-up". | chat | low | S | — |
| E8 | **Property photo compliance check** | On upload, vision model flags photos missing (fachada, sala, cozinha, banheiro) or with issues (blurry, low-light, watermark). | vision | low | S | — |
| E9 | **Listing translation (PT → EN/ES)** | Property pages have a "versão em inglês/espanhol" tab auto-generated for international clients. | chat | low | S | — |
| E10 | **Semantic search refinement** | Search bar accepts natural queries ("apartamento perto de praia, 3 quartos, até 800k"); lib generates embedding → pgvector search. | embed | low | M | — |

---

### PF — `personal-finance`

Tracks accounts, transactions, budgets, portfolios, watchlists. Audience: individual users. Wins are comprehension + reduced data entry.

| # | Opportunity | User-visible change | Lib | LGPD | Effort | Needs |
|---|---|---|---|---|---|---|
| P1 | **Transaction auto-categorization** | Imported transactions arrive with a proposed category (Mercado, Transporte, Saúde). User confirms; the confirm becomes training signal stored per-user. | chat | med | M | — |
| P2 | **Monthly financial narrative** | Dashboard card: "Em março você gastou 12% mais que fevereiro, principalmente em restaurantes (+R$ 340). Sua meta de emergência fechou em 87%." | chat | med | S | — |
| P3 | **Recurring expense detection** | Scans the last 90 days; surfaces "você paga Netflix + Spotify + HBO — R$ 98/mês; considere consolidar". | chat | med | S | — |
| P4 | **Receipt OCR → transaction** | Camera upload on mobile: AI extracts valor, data, estabelecimento, categoria; pre-fills a transaction form. | vision | med | M | — |
| P5 | **Watchlist thesis generator** | On a watched ticker, AI summarizes recent news + fundamentals into a 2-paragraph "por que acompanhar" note. | chat | low | M | org-keys (cost per user) |
| P6 | **Goal-progress coaching** | On the Metas page (PF has these too), each goal shows a short AI-generated "o que fazer esta semana" micro-plan. | chat | med | S | — |
| P7 | **DIRPF helper** | February–April window: AI walks the user through which transactions need to go in the DIRPF, which categories map to which fichas. | chat | high (tax ID + financial) | L | — |
| P8 | **Portfolio rebalancing suggestion** | On the carteira page, AI compares current allocation vs stated target and suggests specific trades to close the gap. | chat | med | M | — |

---

### Therapy — `therapy-platform`

Already uses AI for: session summaries, longitudinal aggregation, transcription (Whisper), attachment analysis (Vision), embeddings. All clinical text is Art. 11 sensitive. `cache=False` everywhere.

| # | Opportunity | User-visible change | Lib | LGPD | Effort | Needs |
|---|---|---|---|---|---|---|
| T1 | **Homework suggester** | After a session, therapist sees 3 suggested homework tasks grounded in the session transcript + patient history. Picks 0–3, edits, assigns. | chat | high | M | — |
| T2 | **Session preparation brief** | 15 min before an appointment, therapist opens the case and sees a "desde a última sessão" brief: last summary + any journal entries + homework completion. | chat | high | M | — |
| T3 | **Crisis keyword detection** | During transcription of session audio (if therapist opts in), a background pass flags phrases suggesting self-harm / crisis; notifies therapist end-of-session. | audio + chat | high | L | — |
| T4 | **Progress visualization narrative** | On the patient's longitudinal view, AI produces a 3-month narrative: "o paciente apresentou redução em X, aumento em Y". Used for clinician BI, never shared with patient without clinician approval. | chat | high | M | — |
| T5 | **Clinic admin dashboard — aggregate insights** | Clinic owners see de-identified aggregates: "70% dos pacientes reportaram melhora" — generated from clinical summaries with strict de-ID guardrails. | chat | high | L | — |
| T6 | **Patient messaging draft** | Therapist composing an out-of-session message gets a "sugerir redação" button that drafts a response in the therapist's tone, grounded in recent case notes. | chat | high | M | — |
| T7 | **Appointment prep reminders (patient-side)** | 24 hr before session, patient gets a "prepare-se" prompt with 2–3 reflection questions personalized to recent themes. Consent-gated. | chat | high | M | — |

---

### Daily Life — `daily-life`

Tasks, goals, habits, schedule, notes. Audience: individual users, overlap with PF user base.

| # | Opportunity | User-visible change | Lib | LGPD | Effort | Needs |
|---|---|---|---|---|---|---|
| D1 | **Daily brief** | Morning card summarizing the day: "5 tasks dues, 2 habits pending, 1 event at 14h, você completou 83% do plano de ontem". | chat | med | S | — |
| D2 | **Goal → tasks decomposition** | User creates a goal ("aprender inglês nos próximos 3 meses"); AI proposes a task breakdown with weekly milestones. Edit-then-accept. | chat | low | M | — |
| D3 | **Schedule optimizer** | "Optimize minha semana" button: AI suggests time-blocked placement for incomplete tasks based on their due date, estimated effort, and user's stated peak hours. | chat | med | M | — |
| D4 | **Note-to-task extraction** | On a long note, a "extract tasks" button pulls action items out ("- [ ] buy milk, - [ ] call mom") as proper task records. | chat | low | S | — |
| D5 | **Journal pattern / sentiment** | Over any window, AI produces a gentle summary of themes + sentiment trend. Not therapy — labeled as reflection, not diagnosis. | chat | high | M | — |
| D6 | **Weekly review coach** | Friday afternoon prompt: AI walks user through a structured weekly review (wins, misses, next week). | chat | med | M | — |
| D7 | **Habit-streak story** | When a habit hits a milestone (30d streak), AI writes a short celebration note specific to the habit. Mild gamification. | chat | low | S | — |

---

### Mailing — `mailing`

Contacts, lists, templates, campaigns, automations. Audience: org marketers.

| # | Opportunity | User-visible change | Lib | LGPD | Effort | Needs |
|---|---|---|---|---|---|---|
| M1 | **Subject line generator** | On a draft campaign, "gerar assunto" produces 3–5 options labeled by tone (urgência, curiosidade, direto). Variants feed A/B. | chat | low | S | — |
| M2 | **Template content draft** | "Escreva um email sobre X" → HTML-ready template (fills an existing responsive layout). | chat | low | M | — |
| M3 | **Audience segmentation suggestion** | On a list, AI clusters contacts and proposes 2–3 segments with names ("reengajáveis 90d", "clientes ativos"). Uses embeddings over engagement + tag data. | embed + chat | med | M | — |
| M4 | **Campaign debrief** | Post-send, "gerar relatório" produces a plain-Portuguese narrative of open rate, clicks, winners/losers of A/B variants. | chat | low | S | — |
| M5 | **Re-engagement copy variants** | For an "inactive" segment, AI generates 3 different re-engagement emails (different tones). Marketer picks. | chat | low | S | — |
| M6 | **Spam/deliverability content review** | Before send, AI flags risky phrasing, missing unsubscribe, link-heavy bodies. | chat | low | S | — |
| M7 | **Multilingual translation** | One-click PT → EN/ES/FR for international campaigns, preserves template HTML. | chat | low | S | — |

---

### AdConnect — `adconnect/` *(scaffolded; not yet migrated)*

B2B marketplace. Opportunities listed for completeness; implementation blocked on migration + schema.

| # | Opportunity | User-visible change | Lib | LGPD | Effort | Needs |
|---|---|---|---|---|---|---|
| A1 | **Listing description generator** | Seller uploads product specs → AI writes marketing copy. | chat | low | S | AdConnect impl |
| A2 | **Auto-tagging / categorization** | AI suggests category + tags for a listing from its description + image. | mixed | low | M | AdConnect impl |
| A3 | **Buyer–seller matchmaker** | Based on buyer's interests + seller's inventory, AI surfaces high-fit matches. | embed + chat | med | M | AdConnect impl |
| A4 | **Negotiation copilot** | Chat assistant helps seller respond to a buyer's offer with 3 template replies (aceitar, contraproposta, recusar). | chat | med | M | AdConnect impl |

---

### Cross-cutting opportunities (not tied to one product)

| # | Opportunity | User-visible change | Lib | LGPD | Effort | Needs |
|---|---|---|---|---|---|---|
| X1 | **Cross-product global search** | A single search that spans ERP + PF + Daily Life + Mailing (per org's licensed products), embedding-backed. | embed + chat | med | L | selector-ui |
| X2 | **Consolidated AI settings panel** | In Core, a single page lets the org admin enable/disable AI per product per feature + view token estimates. | chat | low | M | selector-ui (task.md Phase 10) |
| X3 | **AI output rating widget** | Every AI-generated string in any product has a 👍 / 👎 button that persists to a `ai_feedback` table. Feeds prompt iteration. | — | med | S | — |
| X4 | **Usage-aware cost guardrails** | Now that `noctusai_lib.llm.usage.UsageSink` records per-org tokens + cost, expose per-org monthly budgets with soft-warn at 80% and hard-stop at 100%. Admin sees a live spend/month in Core; agent sees a gentle banner when their org is approaching the limit. | chat | low | M | task.md Phase 15 DB sink |
| X5 | **AI decision audit trail** | Store `(user, prompt_hash, response_hash, operation, timestamp, accepted_yes_no)` for every AI-generated suggestion the user accepts/rejects. Not the prompt or response content — just hashes + outcome. Enables "show me every AI decision that shaped my workflow". | — | med | M | X3 (feedback widget) |
| X6 | **Per-feature AI consent panel** | In user settings, a per-user toggle for every AI feature their org has enabled. Defaults to opt-in with explicit Portuguese rationale per feature. LGPD gold standard — proves informed consent. | — | low | M | X2 (settings panel) |
| X7 | **Contextual AI indicator pattern** | Drop a small `<AIIndicator refType refId />` on any entity page that auto-hides when no AI output exists, auto-shows score/label when one does. Proven pattern in ERP `MetaEventoIndicator` — generalize to: ERP ativos AI matches, Therapy session records AI summaries, PF transactions AI category, Daily Life tasks AI breakdown, Mailing campaigns AI performance note. | chat | med | S (per wire-up) | — |
| X8 | **Milestone/threshold notification pattern** | The `trg_meta_milestone` pattern in ERP (trigger on event INSERT → computes %, compares to last-notified threshold, dispatches via `/api/notificacoes`) generalizes to any AI threshold: PF category-overrun alert, Therapy crisis-keyword cross, Daily Life habit streak celebration, Mailing deliverability drop alert. One pattern, N specific instances. | chat + trigger | med | S (per instance) | — |

---

## 5a. Pattern Catalog (discovered while shipping the Metas domain)

The ERP Metas build-out produced reusable scaffolding that every AI feature in §5 should lean on. Don't invent new patterns for each row — lift these.

### P1 — Contextual indicator on source pages
**Where it lives:** `products/erp-imobiliario/frontend/src/components/MetaEventoIndicator.tsx` + `GET /api/metas/meta-eventos?referencia_tipo=&referencia_id=`.

**What it does:** A small badge/chip that silently fetches `{ referencia_tipo, referencia_id }`-keyed data, auto-hides when empty, auto-shows score + chip when present. Three-line drop-in on any entity page.

**Applies to:** every `X7`-tagged opportunity. Also most per-product rows that output a per-entity score: E2 (WhatsApp intent), E6 (certidões summary), E8 (photo compliance), T3 (crisis detection), M3 (segment assignment), A1 (listing tags).

**Cost to generalize:** rename to `<AIIndicator refType refId />`, replace the backend fetch with `useAIOutputFor(refType, refId)`, promote to `@noctusai/lib/design-system`.

### P2 — Milestone / threshold notification trigger
**Where it lives:** migration `019_metas_milestones.sql` (ERP) — a table `(org_id, ref_id, threshold, notified_at)` + a function `fn_check_milestone()` + an `AFTER INSERT` trigger that reads current progress, dedups against the table, and inserts a `public.notificacoes` row.

**What it does:** at DB level, detects a threshold cross once — regardless of how many inserts produce the crossing — and fires exactly one notification. No cron, no polling, no race condition.

**Applies to:** X8 generalization. Also specific rows: P1 (PF budget overrun), D7 (Daily Life streak), T3 (Therapy crisis keyword cross), M6 (Mailing deliverability drop).

**Cost to generalize:** extract the SQL pattern into a template generator — one migration file per (event table, threshold array, notification tipo).

### P3 — Biweekly / scheduled digest email
**Where it lives:** `products/erp-imobiliario/backend/app/services/metas_digest_service.py` + `POST /api/metas/digest/{periodo_id}?recipient=`.

**What it does:** builds HTML + plain-text digest from a period's aggregated data, delivers via Resend using the existing 3-tier credential chain, dry-runs when no key configured. Scheduled externally (n8n cron hits the endpoint).

**Applies to:** C2 (Core audit-log narrative), T4 (Therapy longitudinal digest), P2 (PF monthly narrative), D6 (Daily Life weekly review), M4 (Mailing campaign debrief). All are "summary email on cadence".

**Cost to generalize:** lift the `_render_html` / `_render_text` split into a shared `noctusai_lib.email.digest` helper + a tiny `<Digest>` renderer SDK.

### P4 — Layout-enrichment injection
**Where it lives:** ERP `hooks/useLayoutEnrichment.ts` — reads the agent's current rank and appends it to `roleLabel` so every page's header shows `"Corretor · #3"` with zero per-page plumbing.

**What it does:** inject any AI-derived scalar (unread count, status badge, recent-decision summary) into the global Header without touching individual pages.

**Applies to:** C3 (Core support-chat "2 pending suggestions"), T1 (Therapy "homework due"), D1 (Daily Life "today's brief"), X4 (budget watermark), X6 (pending consent).

**Cost to generalize:** formalize a `LayoutEnrichment.aiBadge?: string | React.ReactNode` field in the framework.

### P5 — Idempotent seed script for AI demo data
**Where it lives:** `products/erp-imobiliario/backend/scripts/seed_metas_teams.py`.

**What it does:** insert-if-absent sample rows for a target `--org-id`, idempotent on re-run, standalone (no app server), uses service-role key.

**Applies to:** every AI feature that needs demo/pilot data before real user traffic arrives. A product onboarding agency with no history can run one script to populate "plausible" AI examples so the UX doesn't start empty.

**Cost to generalize:** nothing — copy the script per AI feature.

### P6 — Gamification primitives (`RankBadge`, `ScorePill`, `ProgressRing`)
**Where it lives:** `seed/frontend/lib/src/design-system/gamification/` — exported from `@noctusai/lib/design-system`.

**What it does:** renders threshold-colored visual feedback for any score. Accepts `{good, warn}` thresholds. Works for any kind of AI score (confidence %, match strength, risk level).

**Applies to:** every row in §5 that produces a score. Confidence labels on classifier outputs (E2, M3), match strengths on semantic search (E10, P5 watchlist), progress indicators on goal-breakdown (D2).

**Cost to generalize:** zero — already shared.

---

## 6. Implementation phases

### Phase 1 — Opportunity Atlas ✅ (this document, §5 above)

- [x] Audit all 7 live products + AdConnect scaffold
- [x] Per-product opportunity list with LGPD / effort / dependency tags
- [x] Cross-cutting opportunities surfaced (X1–X3 at first; enriched to X1–X8 after Metas build-out)
- [x] **§5a Pattern Catalog added** after shipping the ERP Metas consolidation round — 6 reusable patterns (P1–P6) that generalize across most of the atlas

**Improvements:**
- The atlas reads each product's `services/` directory but doesn't consult the actual UI — some opportunities may misread what the user actually sees. Next iteration: cross-reference with `frontend/src/pages/` per product and trim anything that doesn't match an existing page or planned page.
- LGPD tags are rule-of-thumb from the KB rule, not individually traced. Items tagged `high` all need the formal 5-question LGPD review before they leave triage.
- Effort sizing is gut-feel. **First calibration point in from the Metas build-out**: "add a contextual indicator to a page" is realistically **S (<1d)** when the lib + `<AIIndicator/>` pattern exist, not the M tag I'd use without the pattern. Re-tag accordingly when triaging §5 items that are "indicator on a page" or "small notification" shapes — they're mostly S.
- **New grouping axis for triage**: instead of per-opportunity triage, **group opportunities by the pattern they need** (P1–P6). Building pattern P1 once unlocks ~10 §5 rows. Makes Phase 2 easier: pick 1–2 patterns to harden, then most of the atlas falls as low-effort follow-ups.

### Phase 2 — User triage 🔲 *(blocked on user)*

- [ ] User reviews §5, per product, and marks each opportunity: `go` / `defer` / `no`
- [ ] For `go` items, user picks priority rank and any scope edits
- [ ] Output: a prioritized list pinned into §6 as Phase 3+ (one phase per opportunity for M/L, batch S's per product)

### Phase 3+ — Per-opportunity implementation

*To be generated from Phase 2's output. Template per phase:*

```
### Phase N — <product><opp-code> <short-title>
- [ ] Service layer using noctusai_lib.llm.<entry>
- [ ] Router endpoint(s)
- [ ] Frontend: <page/component> + hook
- [ ] Tests (FakeProvider for unit, integration where cheap)
- [ ] LGPD flag if tag = high
- [ ] Docs: add to 05-AI-FEATURES.md + product MASTER-PROMPT.md
- [ ] (if cacheable) enable response cache
```

---

## 7. Open questions

1. **Prioritization axis** — impact first, effort first, or product-by-product? *Needs answer before Phase 2.*
2. **AdConnect timing** — hold all AdConnect opportunities until migration, or spec them now so migration + AI land together? *Needs answer in Phase 2.*
3. **Streaming dependency** — should we invest in lib streaming (adds task.md Phase 11) before Phase 3, or ship non-streaming versions first? *Decide after Phase 2 — only relevant if `needs: streaming` opportunities land in the priority top-5.*
4. **Per-product prompt versioning** — each opportunity's prompt needs a version tag for the response cache. Where does it live: constant in the service, DB row, or git-tagged file? *Decide during Phase 3 first implementation.*
5. **LGPD review gating** — `high`-tagged items need formal review before implementation. Who approves? *Needs answer before the first `high` item enters a phase.*

---

## 8. Dependencies & blockers

- **~~`task.md` Phase 10 (frontend LLM selector + API Keys UI)~~** — **resolved** (shipped).
- **AdConnect migration** — blocks A1–A4.
- **~~`noctusai_lib.llm` streaming support~~** — **resolved** (`task.md` Phase 12 shipped streaming). Any `needs: streaming` opportunity (C3) is now unblocked.
- **~~Redis deployed~~** — **resolved** for the dev path (in-memory backend + real Redis backend via `REDIS_URL` env, task.md Phase 11). Production still needs a Redis instance running; that's an ops task not a code task.
- **LGPD approval flow** — before `high` items ship, the project needs a documented approval channel (whose sign-off, recorded where). Still open.
- **Pattern infrastructure** — P1 (`<AIIndicator/>` + backend read endpoint) + P2 (milestone trigger template) + P3 (digest service template) should be built first as shared scaffolding. They unlock multiple §5 rows as low-effort follow-ups. *(New blocker added after §5a Pattern Catalog.)*
- **~~Token accounting DB sink~~** — **resolved in-memory**; X4 (cost guardrails) needs the Supabase-backed sink + admin aggregate endpoint to ship. Tracked in `task.md` Phase 15 deferrals.

---

## 9. Success criteria

- Every live product has **≥ 1 shipped AI feature** (or a documented "no — here's why" for the product).
- Zero AI code bypasses `noctusai_lib.llm` (grep-checked in CI with the existing patterns).
- Every `high`-LGPD feature has a corresponding `LGPD-WARNINGS.md` entry with mitigation status.
- Each shipped feature has a graceful non-AI fallback path (tested).
- `KNOWLEDGE-BASE/CONTEXT/backend/05-AI-FEATURES.md` covers every shipped AI feature with prompt, model, LGPD tag, and cache posture.

---

## 10. How to use this document

- **Phase 2 is a user action** — this project document cannot advance without your triage. Treat §5 as a menu, mark each row, and Phase 3+ will be generated from your marks.
- **Phase 3+ cadence is one phase per opportunity (M/L) or one phase per batch (S's per product).** Phase-by-phase default applies: one phase, pause, continue.
- **Atlas is evolvable.** If you think of something not listed, add a row to §5 with a new code and re-run the triage for that row.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-04-19 | Initial atlas drafted after surveying all 7 live products + AdConnect scaffold. 48 opportunities catalogued across 8 products + 3 cross-cutting. Phase 1 ticked; Phase 2 (user triage) pending. | Claude |
| 2026-04-19 | **Enriched from Metas build-out.** Added **5 new cross-cutting opportunities** (X4 cost guardrails, X5 decision audit trail, X6 per-feature consent, X7 contextual indicator pattern, X8 milestone-threshold pattern). Added **§5a Pattern Catalog** with 6 reusable patterns (P1 contextual indicator, P2 threshold-cross trigger, P3 scheduled digest, P4 layout-enrichment injection, P5 idempotent seed script, P6 gamification primitives) — each with a pointer to the concrete Metas implementation that proves them out. Updated Phase 1 improvements with first effort-calibration data point ("indicator on a page" = S, not M). Updated §8 dependencies to mark streaming/cache/UI-selector as **resolved** (task.md Phases 10/11/12 shipped) and added "pattern infrastructure" as the new high-leverage blocker. | Claude |
