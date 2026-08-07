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
> Every decision below is user-ratified in the 2026-08-07 session. Phase 1 begins on
> trigger **T1**.
>
> **Scope ruling (user-ratified): the card hub is a SHARED ORGAN**, built in
> `noctusai_lib` + `@noctusai/lib` and consumed by **social-wiring** *and*
> **erp-imobiliario**. User: *"yes make it shareable"*. Building it inside
> `products/social-wiring/` would fork a primitive both products already share.

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
| `cliente_field` | **default** → cards hang off `clientes` | **`None`** → cards hang off raw source rows |

**erp-imobiliario already builds person-cards.** social-wiring is the outlier: it is
the one product with no person layer, which is precisely the defect. The shared
organ is therefore *not* a new invention — it generalizes the model erp already
proved and back-fills the layer social-wiring lacks. Replication-to-seed symmetry
(`KB § PATTERNS/architect/project-execution.md`) says the right count of per-product
implementations is **zero**.

### 🔴 Naming trap — do not call it `clientes` in social-wiring

`social_wiring.clients` **already exists** and means something else entirely: agency
client *accounts* / brand owners, from migration 007 (`app/services/clients_service.py`,
compat view `mc_brand_owners`). The new person entity must not collide with it.

**Working name: `social_wiring.pessoas`.** Not user-ratified — flagged as an open
question (§7 Q1). Cheap to change before Phase 1 lands; expensive after.

### The seam

`PipelineConfig` is already configured by table **name**, which is exactly the seam
needed: each product names its own person table (`clientes` for erp, `pessoas` for
social-wiring) and the organ stays product-agnostic. No new seam invention required.

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

### Phase 1 — the person layer (the foundation; everything else attaches here)

- **P1.1** `pessoas` table + canonical identity key (E.164 phone / lowercased email),
  org-scoped RLS matching the rest of the schema.
- **P1.2** `pessoa_touches` — every `leads` row and every `meta_ads_leads` row
  becomes a touch. **Lossless: no source row is modified or deleted.**
- **P1.3** Identity resolution: auto-merge the 1 871 name-compatible groups; the
  223 + 7 land in a review queue. Merges recorded in a links table (**D3**, undoable).
- **P1.4** Repoint `negociacoes_venda` at `pessoa_id`; retire the
  `exactly_one_origin` CHECK. Backfill the 125 pairs into single cards, keeping the
  furthest-advanced stage.
- **P1.5** Active/inactive lifecycle (**D4**) — configurable silence threshold,
  **default 90 days** (assumption, §7 Q2), archive + manual restore, full history
  preserved on return.

**Checkpoint:** the board shows one card per human; nothing is lost; the review
queue is walkable.

### Phase 2 — the card organ shell

- **P2.1** Extract the card organ into `@noctusai/lib` + `noctusai_lib`: card face
  (colour strip, badge row) and two-pane detail, per the screenshots.
- **P2.2** The unified timeline (**D9**) — notes + system events + touches, in one
  chronological thread. `pipeline_movimentos` finally renders.
- **P2.3** Tags (**D6**) — colour + name, searchable, colour-blind mode, board filter.
- **P2.4** erp-imobiliario consumes the same organ against `clientes`. **This is the
  proof the organ is genuinely shared** and not a social-wiring feature in a shared
  folder.

**Checkpoint:** both products render the same card from the same code.

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
| **T1** | User ratifies this record and the open questions in §7 | Phase 1 |
| **T2** | Phase 1 checkpoint accepted — board shows one card per human | Phase 2 |
| **T3** | Phase 2 checkpoint accepted — **erp-imobiliario consuming the organ** | Phase 3 |
| **T4** | Phase 3 checkpoint accepted **and** the LGPD data-category intake is filed | Phase 4 |
| **T5** | Any phase ≥ 2 shipped (the component has a card to live on) | Phase 5 |

---

## 7 · Open questions — **must be answered before T1**

| # | Question | Assumption held meanwhile |
|---|---|---|
| **Q1** | What is the person entity called, given `social_wiring.clients` is taken? | `pessoas` |
| **Q2** | How many days of silence makes a person inactive? | 90, configurable in the UI |
| **Q3** | Can one person hold several negotiations over time (bought in 2024, negotiating again now)? Do closed ones stay on the card as history? | yes to both |
| **Q4** | Does the WhatsApp/DM half of the timeline (**D9**) embed the messages or link out to the existing chat pages? Embedding is a materially larger slice. | embed, read-only, in Phase 2 |

Q1–Q3 were raised in-session and not answered. Q4 was not raised; it is a real fork
inside a ratified decision and is flagged rather than guessed.

---

## 8 · Decision log

| Date | Entry |
|---|---|
| 2026-08-07 | Roadmap authored. Two-shapes cause traced to `034`'s `exactly_one_origin` CHECK + the double-trigger path through `ingest_meta_lead`. Live DB measured: 125 duplicate pairs, 100 % forward rate. |
| 2026-08-07 | **Design pivot:** lead base measured before choosing a merge strategy. 13 245 rows → ~9 270 people; 3 576 rows are repeat contact. Reframed from "de-duplicate" to "person + touches", which preserves every row. This reframe is the reason D1–D3 look the way they do. |
| 2026-08-07 | Match-safety quantified (1 871 compatible / 223 conflicting / 7 nameless). A real shared-number case found (`+5511974781330` → two distinct people), which is why blind phone-merge was rejected. |
| 2026-08-07 | Scope raised to shared organ on user instruction. Justified independently: erp already person-cards via `cliente_field`; social-wiring sets it to `None`. |
| 2026-08-07 | Naming trap recorded — `social_wiring.clients` is the agency-account table (migration 007), not people. |
