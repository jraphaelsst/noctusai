# lead-card-hub-2026-08 — the Lead/Cliente card as a shared, Trello-grade organ

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: user asked to "zoom in to social wiring", reported that funil cards show
> leads in **two different shapes** — *"both of them are true and contain different
> sets of information. I need both"* — and asked for the card to become the place
> that **centralizes everything about a Lead/Cliente**: documentation, annotations,
> tags, classifications, temperature, contracts. Explicit reference model: **Trello**
> (11 screenshots supplied 2026-08-07).
>
> **Decision: this roadmap ships the design record only. No product code yet.**
> All **17 decisions** below are user-ratified in the 2026-08-07 session, and **§7 is
> closed** — every open question was answered before anything was designed against
> it. The only thing left is **T0: the user says to start building.**
>
> **Scope ruling (user-ratified): the card hub is a SHARED ORGAN**, built in
> `noctusai_lib` + `@noctusai/lib` and consumed by **social-wiring** *and*
> **erp-imobiliario** — *"yes make it shareable"*. Building it inside
> `products/social-wiring/` would fork a primitive both products already share.
>
> 🔴 **Scope boundary (user-ratified 2026-08-07): social-wiring + erp-imobiliario
> ONLY.** *"let work only on social wiring and erp. Leave the other products."*
> A third forked Funil exists in `products/orbity` — found while fact-checking this
> document, recorded in §3, and **explicitly out of scope**.
>
> **Read order if you are picking this up cold:** §1 (what broke) → §2 (the
> measurement that changed the design) → §4 (the 17 decisions) → §5 (phases). §2 is
> the one that explains why everything else looks the way it does.

---

## 1 · Origin — the two shapes, explained

The user's report was precise and the cause is a single line of schema.

`social_wiring.negociacoes_venda` (migration `034_pipeline_funil_processos.sql`) is
the funil card. It carries **exactly one** origin:

```sql
CONSTRAINT negociacoes_venda_exactly_one_origin
  CHECK (num_nonnulls(lead_id, meta_ads_lead_id) = 1)
```

Two triggers feed it — `spawn_funil_card_on_lead` (on `social_wiring.leads`) and
`spawn_funil_card_on_meta_lead` (on `social_wiring.meta_ads_leads`). But the Meta
leadgen webhook writes **both** tables for the same human: it stores the raw Meta
record, then calls `ingest_meta_lead`
(`app/modules/meta_ads/services/leadgen_webhook_service.py:629`), which creates a
`leads` row.

**One person fires both triggers and gets two cards.** One renders through
`campanhaDetailSections` (form answers, campaign, ad/adset, platform); the other
through `leadDetailSections` (origem, corretor, empreendimento, região, follow-up,
status). Disjoint field sets, both true — exactly as reported.

### Measured on the live DB (2026-08-07)

| Measure | Value |
|---|---:|
| cards on the funil board | 1 193 |
| lead-origin cards | 1 068 |
| campaign-origin cards | 125 |
| `leads` ingested from Meta (`meta_lead_id IS NOT NULL`) | 1 066 |
| **duplicate pairs (same human, two cards)** | **125** |

Every campaign-origin card has a twin. The rate going forward is **100 %** — every
new Meta lead makes two cards.

The link already exists in the data (`leads.meta_lead_id`, migration 041) and
nothing in the pipeline reads it.

---

## 2 · The finding that changed the design: leads are **recurring**, not duplicated

Before choosing a de-duplication strategy, the lead base was measured rather than
assumed. It is not a duplicate-records problem.

| Measure | Value |
|---|---:|
| `leads` rows | 13 245 |
| rows with no contact at all | 397 |
| distinct phone numbers appearing **more than once** | 2 101 |
| excess rows attributable to repeat contact | 3 576 |
| ⇒ approximate distinct **people** | ~9 270 |

Sampled, the repeats look like this:

| phone | rows | names on those rows | origens |
|---|---:|---|---|
| `+5511996915253` | 23 | Ana Paula · Ana Paula Soares Franco · Paula · Paula Soares | SENSEYS form, SENSEYS |
| `+5511983287182` | 18 | Marinaldo · MARINALDO · Marinaldo Fontes · MARIVALDO | Imóvel Web, ZAP |
| `+5511943305562` | 13 | Dayane · DAY · Dayane e Sandra (mãe) · RETONO DAYANE | Instagram, SENSEYS, Site, Viva Real, ZAP |

Ana Paula was not imported 23 times. She **inquired** 23 times — different portals,
different months, probably different properties. Each row is a real, distinct event.
Deleting any of them destroys truth.

**This is the same phenomenon as the two card shapes, one layer down.** The
resolution is therefore the same for both:

> **A person is one card. Every lead row and every campaign submission is a TOUCH on
> that person's timeline.** Nothing is merged away; the board simply stops showing
> the same human twenty-three times.

### Match-safety, measured

| Groups of repeated phone | Count | Disposition |
|---|---:|---|
| names **compatible** (share a token — `Fatima`/`Fátima`/`Fátima Araujo`) | 1 871 | auto-merge |
| names **conflicting** (no shared token) | 223 | review queue |
| no name on any row | 7 | review queue |

The 223 are not all typos. `+5511974781330` carries both `Carmen Real Dias` **and**
`Luana Batista` — a genuinely shared number, two real people. **Blind auto-merge on
phone would fuse them**, which is why the review queue is not optional.

*(A looser measure — groups with any name-string variation at all, including case
and accents — returns 722. The 223 figure is the strict token-incompatibility
measure and is the one the review queue is sized against.)*

---

## 3 · Architecture — why this is a shared organ

`erp-imobiliario` and `social-wiring` already run the **same** pipeline primitive:
`noctusai_lib.domain.pipeline` + `@noctusai/lib`'s `PipelineBoard`, each declaring a
`PipelineConfig`.

| | erp-imobiliario | social-wiring |
|---|---|---|
| config | `app/services/pipelines.py` | `app/modules/pipeline/configs.py` |
| `cliente_field` | **default** → cards hang off `erp.clientes` (table verified to exist) | **`None`** → cards hang off raw source rows |

**erp-imobiliario already builds person-cards.** social-wiring is the outlier: it is
the one product with no person layer, which is precisely the defect. The shared
organ is therefore *not* a new invention — it generalizes the model erp already
proved and back-fills the layer social-wiring lacks. Replication-to-seed symmetry
(`KB § PATTERNS/architect/project-execution.md`) says the right count of per-product
implementations is **zero**.

### 🔴 Naming — RESOLVED 2026-08-07: the person is `clientes`; the incumbent becomes `marcas`

`social_wiring.clients` **already existed** and meant something else entirely: the
brand/profile owner an integration account belongs to (migration 007,
`app/services/clients_service.py`, compat view `mc_brand_owners`). Live contents —
two rows: `One Consultoria` (`kind='empresa'`) and `João Raphael`
(`kind='pessoa_fisica'`), i.e. the profiles whose Instagram / Facebook / WhatsApp /
YouTube accounts are connected.

The user wants the person entity to be called **`clientes`**, which is the right
word for it. So the incumbent is renamed.

**First proposal was `colaboradores` and it was rejected on a collision argument:**
Phase 3 invites the 28 corretores + admins as real noc users — *those* are the
actual colaboradores. Giving the brand-owner table that name would make one word
mean two different things one phase apart. The user accepted the objection and
chose **`marcas`**.

| | |
|---|---|
| person / lead entity (new) | `social_wiring.clientes` |
| brand-profile owner (renamed from `clients`) | `social_wiring.marcas` |

**Rename blast radius (measured):** 38 backend references, 17 frontend files, 34
files total. AST-first (libcst / ts-morph), never regex. Migration 007 already set
the precedent for this exact move (`mc_brand_owners` → `clients` behind a compat
view), so the same play applies: rename + compat view + migrate callers + drop the
view once no caller reads it.

### The seam

`PipelineConfig` is already configured by table **name**, which is exactly the seam
needed: each product names its own person table and the organ stays
product-agnostic. No new seam invention required.

After D14 **both** products land on the same name — `erp.clientes` and
`social_wiring.clientes` — so the seam is uniform in practice while remaining
configurable in principle. That is a convenience, **not** a licence to hardcode the
table name in the organ. See the third-consumer finding below.

### ⚠️ Found on contact: orbity is a third, forked Funil (out of scope, recorded)

`products/orbity` also runs a Funil kanban — `frontend/src/pages/Funil.tsx`,
`app/services/crm_service.py` (*"leads CRUD, funil kanban grouping, stage moves,
activities, lead scoring"*). It does **not** consume the shared primitive:
`grep -rn "noctusai_lib.domain.pipeline\|PipelineConfig" products/orbity/backend/app`
returns nothing.

So the true count of funil-kanban implementations is **three**, of which two
consume the primitive and one forks it:

| product | funil substrate | consumes `noctusai_lib.domain.pipeline`? |
|---|---|---|
| erp-imobiliario | `app/services/pipelines.py` | ✅ |
| social-wiring | `app/modules/pipeline/configs.py` | ✅ |
| **orbity** | `app/services/crm_service.py` | ❌ **fork** |

N=3 would normally trip the recurrence rule (`CLAUDE.md` §1 · `KB §
PATTERNS/architect/project-execution.md`). It is pre-existing debt, discovered
while verifying a claim written for this roadmap — not caused by this work.

> 🔴 **USER RULING 2026-08-07 — scope is social-wiring + erp-imobiliario ONLY.**
> *"let work only on social wiring and erp. Leave the other products."*
> **Orbity is not to be touched** — not migrated, not refactored, not "while we're
> in there". It is recorded on this page so the finding is not lost and so nobody
> re-discovers it as news, and for **one** design consequence only:

**The one consequence:** the organ stays genuinely table-name-configurable rather
than hardcoding `clientes` just because both in-scope products now use that name.
That costs nothing and keeps the door open. Everything else about orbity is out of
scope by explicit instruction.

**No design decision in Phases 0–5 depends on orbity.** If it is never migrated,
nothing in this roadmap changes.

---

## 4 · Ratified decisions (2026-08-07 session)

| # | Decision | User's words / selection |
|---|---|---|
| D1 | **Funil card = a person. Processo card = a negotiation.** | *"while on the funil de vendas they are a person. When proposta is aceita and the client goes to the processos page, then it's gonna be a negotiation"* |
| D2 | **Matching: auto-merge on canonical phone/email where names are compatible; conflicts go to a review queue.** | user asked to be advised; recommendation accepted on the measured 89 %/11 % split |
| D3 | **The 125 existing pairs are merged, reversibly** (a links table records what folded into what, so a wrong merge can be split back). | as D2 |
| D4 | **Board shows active people only**; inactive fully accessible **and manually restorable**. | *"Only active people"* + *"i need to have access to inactive and i need to be able to revert if i need"* |
| D5 | **Documents get full LGPD handling** — org-scoped bucket + RLS, per-type retention, delete-on-request, access logging, size/type limits. | *"Full LGPD handling"* |
| D6 | **One tag system.** No separate "classification" concept — free-form, colour + name. | *"Same thing, one system"* |
| D7 | **Contracts: upload + status machine + e-signature.** | *"actually everything. Doc upload and the status and the possibility of e-sign"* |
| D8 | **Temperature ships now with a provisional formula** (recency of last touch + touch count), clearly labelled; the campaign-answer formula replaces it later. | *"Crude formula now"* + *"I want the temperature component on it already"* |
| D9 | **Timeline is one thread containing everything** — notes, system events, portal inquiries, campaign submissions, WhatsApp messages, Meta DMs. | *"Everything, one thread"* |
| D10 | **Corretores become real noc users**, invited through the existing invite flow; they get their own filtered board view, assignments and reminders. | *"They are the users i'll invite to the platform. The invite we fixed a while ago will be used to populate the platform with my corretores and adms"* |
| D11 | **Checklists: both** — each stage carries configurable requirements, and ad-hoc per-card checklists are still allowed. | *"Both"* |
| D12 | **The card is stage-aware in fields AND actions**, not just its checklist. Sections stay hidden until the card reaches the stage that needs them. Declarative stage schema — **not** a user-facing form builder. | selected "Fields and actions too" |
| D13 | **Built as a shared organ**, consumed by social-wiring and erp-imobiliario. | *"yes make it shareable"* |
| D14 | **The person entity is `clientes`.** The incumbent `clients` (brand-profile owners) is renamed **`marcas`**. `colaboradores` was proposed and withdrawn — it collides with the 28 real colaboradores D10 invites. | *"i wanna call them clientes. The clientes that already exists, let's call them colaboradores"* → after the collision objection, selected **Marcas** |
| D15 | **Conversations are embedded AND replyable from the card** — read and send WhatsApp / Meta DMs without leaving. | selected *"Embed and reply"* |
| D16 | **Inactivity threshold: 180 days**, configurable in the UI. | selected *"180 days, configurable"* |
| D17 | **A person accumulates negotiations over time; closed ones stay on the card as history** (bought in 2024, negotiating again now). | selected *"Yes, closed ones stay as history"* |

### The Trello → domain map (from the 11 supplied screenshots)

| Trello affordance | Card-hub equivalent | Substrate today |
|---|---|---|
| Título | nome da pessoa | ✓ exists |
| Etiquetas | tags, colour + name (D6) | build new |
| Descrição | observações | `leads.observacoes` ✓ |
| Datas + lembrete | follow-up date + reminder | `leads.follow_up_data` / `follow_up_nota` ✓ — **no reminder mechanism anywhere** |
| Anexo | documentos, LGPD (D5) | build new |
| Comentários e atividade | unified timeline (D9) | `pipeline_movimentos` records every stage move and **is rendered nowhere** |
| Membros | corretor responsável (D10) | `lead_corretores` = `(nome, nome_norm, cor, ativo)` — **no `user_id`** |
| Checklist | stage requirements + ad-hoc (D11) | build new |
| Card-face badges | due date, description, attachment count, checklist progress, comment count, temperature | build new |

The screenshots also fix concrete UI behaviour to reproduce: colour strip + badge
row on the card face; two-pane detail (content left, activity right); the
`+ Adicionar` popover; label search with a colour-blind mode; start/due/reminder/
recurring dates; multiple checklists each with a % progress bar; attachments with
type icon, thumbnail and per-file menu.

### Corretor → user migration is small

| Measure | Value |
|---|---:|
| corretores cadastrados (all active) | 28 |
| leads carrying a resolved `corretor_id` | 12 082 |
| leads with an unresolved `corretor_raw` | 10 |
| leads with no corretor | 1 153 |

`lead_corretores` gains a `user_id`; 28 invites go out; **all 12 082 historical
assignments survive untouched** because leads point at `lead_corretores.id`, never
at a name.

---

## 5 · Phases

> Each phase ends at a user-visible checkpoint. Nothing here is dispatched to
> engineers without the tech-lead integrating and live-probing first — a worktree
> being green is not the feature working (`KB § PATTERNS/common/self-branching-mode.md`).

### Phase 0 — free the name (**must land before Phase 1 opens**)

🔴 **Sequencing hazard.** Phase 1 creates `social_wiring.clientes` for people. If
the incumbent `clients` still means brand-owners at that moment, two tables named
for the same word are live simultaneously and every reader — human and agent —
has to guess which is which. **Phase 0 is not optional and cannot run in parallel
with Phase 1.**

**Verified table inventory (2026-08-07)** — three tables carry this name and only
one is in scope:

| table | what it holds | disposition |
|---|---|---|
| `social_wiring.clients` | brand-profile owners (2 rows) | → **`marcas`** (this phase) |
| `erp.clientes` | erp's people — already the person layer | **untouched**; already the right name |
| `orbity.clients` | orbity's own CRM clients | 🔴 **out of scope** (user ruling) |

- **P0.1** `social_wiring.clients` → `social_wiring.marcas` (**D14**), behind a compat
  view, following migration 007's own precedent (`mc_brand_owners` → `clients`).
- **P0.2** Migrate all callers AST-first — **38 backend references, 17 frontend
  files**, all within `products/social-wiring/`. libcst / ts-morph, never regex
  (`KB § PATTERNS/common/ast.md`).
- **P0.3** Drop the compat view only once no caller reads it. Verify by grep +
  a live probe, not by assumption.

**Checkpoint:** nothing **inside `products/social-wiring/`** says `clients` any
more, the app still works, and `social_wiring.clientes` is free to create.

⚠️ The checkpoint is scoped to social-wiring **deliberately**. A repo-wide "no
`clients` anywhere" check can never pass while `orbity.clients` exists, and chasing
it would breach the scope ruling in §3.

### Phase 1 — the person layer (the foundation; everything else attaches here)

- **P1.1** `clientes` table + canonical identity key (E.164 phone / lowercased
  email), org-scoped RLS matching the rest of the schema.
- **P1.2** `cliente_touches` — every `leads` row and every `meta_ads_leads` row
  becomes a touch. **Lossless: no source row is modified or deleted.**
- **P1.3** Identity resolution: auto-merge the 1 871 name-compatible groups; the
  223 + 7 land in a review queue. Merges recorded in a links table (**D3**, undoable).
- **P1.4** Repoint `negociacoes_venda` at `cliente_id`; retire the
  `exactly_one_origin` CHECK. Backfill the 125 pairs into single cards, keeping the
  furthest-advanced stage. **A cliente may hold many negociações (D17)** — the
  repoint is one-to-many from the start, not a one-to-one that has to be widened later.
- **P1.5** Active/inactive lifecycle (**D4**) — **180 days** of silence
  (**D16**), configurable in the UI; archive + manual restore; full history
  preserved on return.

**Checkpoint:** the board shows one card per human; nothing is lost; the review
queue is walkable.

### Phase 2 — the card organ shell

- **P2.1** Extract the card organ into `@noctusai/lib` + `noctusai_lib`: card face
  (colour strip, badge row) and two-pane detail, per the screenshots.
- **P2.2** The unified timeline (**D9**) — notes + system events + touches, in one
  chronological thread. `pipeline_movimentos` finally renders. **Conversations are
  deferred to Phase 2b** (see below); the timeline is built with a slot for them
  rather than being retro-fitted.
- **P2.3** Tags (**D6**) — colour + name, searchable, colour-blind mode, board filter.
- **P2.4** Negotiation history on the card (**D17**) — active plus closed, with
  outcome and date.
- **P2.5** erp-imobiliario consumes the same organ against its own `clientes`.
  **This is the proof the organ is genuinely shared** and not a social-wiring
  feature in a shared folder.

**Checkpoint:** both products render the same card from the same code.

### Phase 2b — conversations in the card (**split out because of its size**)

**D15 is the single largest slice in this roadmap** and it is not a rendering
change. "Embed and reply" pulls the outbound send path, connection state and
realtime into the organ: `whatsapp_outbound`, `whatsapp_realtime`,
`whatsapp_connection_store`, `whatsapp_identity`, `message_store` and the Meta DM
path (`meta_dms_router`). It also raises questions the read-only version never
has to answer — which connection sends when a person is reachable on two, what
happens when the session is down mid-reply, and how a failed send surfaces.

It is separated so Phase 2 can ship and be judged without waiting on it, **not**
because it is optional — the user chose it deliberately over both cheaper options.

- **P2b.1** Read path: real messages inline in the timeline, matched to the cliente
  by canonical phone — the same key Phase 1 builds identity on.
- **P2b.2** Send path from the card, reusing `whatsapp_outbound` — never a second
  send implementation.
- **P2b.3** Connection-state and delivery-failure states in the card UI. A send that
  silently does nothing is the no-silent-errors violation this phase is most exposed to.
- **P2b.4** Meta DMs on the same timeline.

**Checkpoint:** the whole relationship — inquiries, campaign answers, notes, stage
moves and the live conversation — is readable and answerable from one card.

### Phase 3 — people and process

- **P3.1** Corretor-as-user (**D10**): `lead_corretores.user_id`, the 28 invites,
  per-corretor filtered board view.
- **P3.2** Membros on the card — assignment, avatars, and the reminder path that
  currently does not exist anywhere.
- **P3.3** Stage-driven requirements + ad-hoc checklists (**D11**).
- **P3.4** Stage-aware fields and actions (**D12**) — declarative schema per stage.

**Checkpoint:** the card asks for different things in different columns, and the
right person is asked.

### Phase 4 — documents and contracts

- **P4.1** Document storage with **full LGPD** (**D5**) — bucket + object RLS,
  retention by document type, delete-on-request, access log, size/type limits.
  🔴 Requires a `noctus.dev.lgpd_flag` data-category intake before any RG/CPF lands.
- **P4.2** Contracts as an entity with a status machine (**D7**).
- **P4.3** E-signature. `erp-imobiliario` already ships `assinaturas` +
  `signature_provider` — **evaluate lifting it into the organ before rebuilding**
  (`noc-verify-seed` gate applies).

### Phase 5 — temperature

- **P5.1** The temperature component + the provisional formula (**D8**), labelled as
  provisional in the UI.
- **P5.2** *(deferred, no trigger)* the campaign-answer formula. The user explicitly
  deferred the formula, not the component.

---

## 6 · Triggers

| ID | Trigger | Fires |
|---|---|---|
| **T0** | 🟡 **PENDING** — user says to start building. §7 is closed; this is the only thing left. | Phase 0 |
| **T1** | Phase 0 checkpoint accepted — the name `clientes` is free | Phase 1 |
| **T2** | Phase 1 checkpoint accepted — board shows one card per human | Phase 2 |
| **T3** | Phase 2 checkpoint accepted — **erp-imobiliario consuming the organ** | Phase 3 |
| **T3b** | Phase 2 shipped; runs independently of Phase 3 | Phase 2b |
| **T4** | Phase 3 checkpoint accepted **and** the LGPD data-category intake is filed | Phase 4 |
| **T5** | Any phase ≥ 2 shipped (the component has a card to live on) | Phase 5 |

---

## 7 · Open questions — **ALL CLOSED 2026-08-07**

| # | Question | Resolution |
|---|---|---|
| **Q1** | What is the person entity called, given `social_wiring.clients` is taken? | **`clientes`** — and the incumbent is renamed **`marcas`**. See **D14** + §3. |
| **Q2** | How many days of silence makes a person inactive? | **180**, configurable (**D16**) |
| **Q3** | Can one person hold several negotiations over time? Do closed ones stay as history? | **Yes to both** (**D17**) |
| **Q4** | Does the WhatsApp/DM half of the timeline embed the messages or link out? | **Embed AND reply** (**D15**) — split into its own Phase 2b on size |

Q1–Q3 were raised in-session and initially passed over; Q4 was never raised by the
user — it was a fork discovered *inside* ratified decision D9 and surfaced rather
than guessed. All four were answered before any code was designed against them.

---

## 8 · Decision log

| Date | Entry |
|---|---|
| 2026-08-07 | Roadmap authored. Two-shapes cause traced to `034`'s `exactly_one_origin` CHECK + the double-trigger path through `ingest_meta_lead`. Live DB measured: 125 duplicate pairs, 100 % forward rate. |
| 2026-08-07 | **Design pivot:** lead base measured before choosing a merge strategy. 13 245 rows → ~9 270 people; 3 576 rows are repeat contact. Reframed from "de-duplicate" to "person + touches", which preserves every row. This reframe is the reason D1–D3 look the way they do. |
| 2026-08-07 | Match-safety quantified (1 871 compatible / 223 conflicting / 7 nameless). A real shared-number case found (`+5511974781330` → two distinct people), which is why blind phone-merge was rejected. |
| 2026-08-07 | Scope raised to shared organ on user instruction. Justified independently: erp already person-cards via `cliente_field`; social-wiring sets it to `None`. |
| 2026-08-07 | Naming trap recorded — `social_wiring.clients` is the brand-profile-owner table (migration 007), not people. |
| 2026-08-07 | **§7 closed — all four open questions answered.** Q1 naming, Q2 180d, Q3 multi-negotiation history, Q4 conversations. |
| 2026-08-07 | **`colaboradores` proposed for the renamed table and withdrawn.** The user's first instinct was to rename `clients` → `colaboradores`. Objected: D10 invites 28 corretores + admins as real users one phase later, and *those* are the colaboradores — one word, two meanings, one phase apart. Objection accepted; **`marcas`** chosen. Recorded because the near-miss is the reusable lesson: check a proposed name against what LATER phases will need to call things, not only against what exists today. |
| 2026-08-07 | **Phase 0 inserted.** Phase 1 creates `clientes`; if the incumbent still holds the word at that moment, two tables are live under one name. The rename is therefore a hard predecessor, not a parallel cleanup. |
| 2026-08-07 | **Phase 2b split out.** D15 ("embed and reply") is the largest slice here and pulls the outbound/realtime/connection stack into the organ. Separated so Phase 2 can ship and be judged without it — deliberately chosen by the user over both cheaper options, so it is deferred in sequencing only, never in scope. |
| 2026-08-07 | **A claim written into this document was wrong and was caught by verification.** A draft sentence asserted orbity "is the next consumer in line" for the pipeline primitive. Checked before committing: orbity does **not** consume it — it forks the mechanic in `crm_service.py`. Corrected, and the real finding (N=3 funil implementations, one forked) recorded in §3. The lesson is the cheap one: a plausible architectural claim about a product you have not opened is a guess, and a durable record is exactly where a guess does the most damage. |
| 2026-08-07 | **Scope boundary set by the user** after that finding: social-wiring + erp-imobiliario only; orbity explicitly not to be touched. Recorded at the top of the document, not only here, because a scope boundary read late is a scope boundary read after the work. |
| 2026-08-07 | **Table inventory verified against the live DB rather than inferred:** `erp.clientes`, `social_wiring.clients`, `orbity.clients`. Two consequences — erp already holds the target name (so Phase 2's erp consumption needs no rename), and Phase 0's checkpoint had to be scoped to `products/social-wiring/`, because a repo-wide "no `clients`" assertion can never pass while `orbity.clients` exists and is out of scope. A checkpoint that can never pass is a phase that can never close. |
