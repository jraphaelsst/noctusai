# Edição de Fotos — AI photo editing for real estate

> **Status:** S0 — contract only. No engine code written. Not started.
> **Base:** `7e5f5ad6` (origin/dev at 2026-09-16).
> **Spec:** `../../genesis vision/README.md` (sibling, spec-only — no code).
> **Approved plan:** `~/.claude/plans/hey-claude-i-need-gentle-spring.md` (2026-09-15).
> **Shape:** seed organs + a social-wiring module. NOT a new `products/<slug>/`.

---

## 1 · What this is

An image-editing feature for the Brazilian real-estate market. A corretor uploads a
batch of property photos; the AI edits them to a company standard; the corretor
reviews each photo (✓ / ✗ with a required comment) and downloads a `.zip` of the
approved ones. Around it: a global reference pool, an AI-written style guide, a
per-agency learning loop, a dashboard, and subscription billing.

**Phase 1 (this project)** ships the engine as **seed organs** consumed by a
social-wiring module `app/modules/edicao_fotos/`. **Phase 2** rebuilds the engine
in an external app using the seed as reference — so seed organs carry **no
Social-Wiring coupling**.

## 2 · Why this is not an absorption and not a new product

`noc-absorb-product` folds an externally-developed *seed-workspace* into noc. The
Genesis Vision sibling contains **one README and zero code** — there is nothing to
absorb. And both the spec (§2) and the approved plan place Phase 1 **inside
social-wiring** as a module. Scaffolding `products/edicao-fotos/` would contradict
the approved plan and fork the seed.

Governing skills: `noc-contract-first` → `noc-verify-seed` → `noc-branch-dispatch`.

## 3 · Corrections to the approved plan (verified against the tree, 2026-09-16)

The plan is accurate on most counts — Core next-free was 045, `VISTA_PHOTOS_API_KEY`
absent, `corretor` a real seed role, `org_type` present, `ModelKind` lacking
`image_edit`, `image_gen` Gemini-only, `_MAX_BODY_PATH_OVERRIDES` present, p-studio
carrying the Asaas providers to lift, and no Pillow anywhere. The following are
**wrong or stale** and must be applied before Wave 1 opens.

### C1 — `domain/jobs` is NOT unconsumed 🔴
The plan states *"nothing consumes `Job`/`Worker` today, so the contract is free to
change."* True for `Job` / `Worker` / `JobRepository`. **False for `retry_policy`**,
which has three live consumers:

- `products/social-wiring/backend/app/modules/portal_leads/services/forward_service.py:34`
- `products/social-wiring/backend/app/modules/scheduling/retry.py:41`
- `seed/lib/backend/noctusai_lib/integrations/outbound_webhook/__init__.py:37` — **a seed organ**

Slice S1 explicitly changes `mark_failed` to honour `RetryPolicy`. S1 therefore
carries a three-consumer blast radius including seed-on-seed coupling, and is a
SEED-BE collision class — not the free-to-break slice the plan assumes.

### C2 — `llm_usage` would be the third hand-copy → DRY rule fires 🔴
Already exists per-product at `products/erp-imobiliario/backend/migrations/020_llm_usage.sql`
and `products/therapy-platform/backend/migrations/006_llm_usage.sql`. A third copy in
social-wiring makes N=3, and `CLAUDE.md` §1 says N=3+ **MUST** formalize. It must ship
as a seed migration template (the `domain/ai/migrations/tool_call_audits.sql.template`
shape), not a third copy — especially since the plan *widens* the schema (image tokens,
`model_version`, `batch`), which would silently drift the two existing copies.

### C3 — Core migration 045 is already taken 🔴
Session `noctusai-36` is applying **core 045** as part of a consent-gated
julia/academia fleet cutover, confirmed by direct message 2026-09-16. Its claim is
older and about to land. **Renumber Core 045/046 → 046/047**, and re-verify against
the merged tip at write time rather than trusting any number in the plan document.

### C4 — billing is far less greenfield than the spec implies 🟡
Spec §8 reads as if platform billing is new. Core already ships
`routers/{billing,plans,subscriptions,licenses,entitlements,onboarding}.py` and
`services/{billing_service,stripe_service}.py` — ~1,600 lines against the real Stripe
SDK. The plan knows this ("billing refactored onto the seed payments module"); the
spec does not, and anyone sizing Wave 2 from the spec will under-size it by a lot.
Refactoring **live billing** onto a brand-new seed organ is the highest-blast-radius
slice in the project and is absent from the plan's §8 Risks.

### C5 — Vista gallery read is still unproven, and is a v1 hard dependency 🔴
"Pull photos from a Vista imóvel" is one of three v1 photo sources. Evidence as of
2026-09-16:

- `KB § INTEGRATIONS/vista.md:346` — `GET /imoveis/fotos` returns **405**
  (`Allow: POST, PUT, DELETE`). The route is **write-only**. There is no GET read.
- `vista.md:101` documents a nested `fotos` group on `/imoveis/listar`
  (`Foto`, `FotoPequena`, `Destaque`, `Tipo`, `Descricao`) — **per public docs**.
- `vista.md:398` — tenant calibration (2026-05) says `FotoDestaque` is *the only
  photo field this tenant exposes*.
- Live read-only probe of `CA2830` with our key (`…644c`) on 2026-09-16 returned
  **`FotoDestaque` only** — a single cover photo, no `fotos` group. (The existing
  adapter does not request the nested group, so this bounds the *current path*, not
  the *capability*.)
- `vista.md:883` — the `…bced` portal key is a superset of ours in both directions.

**Open:** whether `fields: [{"fotos": [...]}]` on `/imoveis/listar` returns the full
gallery, and on which key. This needs a raw probe the current MCP adapter cannot
issue. **It is the first task of the Vista slice and it gates a v1 feature** — if it
fails on both keys, the Vista photo source is dead and v1 degrades to computer-upload.

### C6 — cost exposure is unbounded in v1 🟡
At $30 / 1M output image tokens, 100-photo batches, no per-org cap, the dashboard is
a rear-view mirror. `seed/lib/backend/noctusai_lib/integrations/quota/`
(Protocol + factory + Redis + in-memory) already exists and nothing in the plan
consumes it. Wire it in Wave 1, not later.

### C7 — release shape 🟡
social-wiring is `ativo=true`, `deploy_scope='live'` (core migration 042), so this
lands in a **live** product. Combined with the spec's "everything ships as one
release" — editing + review + zip + dashboard + billing together — the blast radius
is large. Recommend splitting: **R1** = engine + review + zip (seed organs + SW
module, no billing); **R2** = billing. R1 alone satisfies Phase 1's stated purpose
of validating the idea.

## 4 · Vista integration facts (from `noctusai-c3`, 2026-09-16)

Relevant to Phase 2 (write-back) and to the probe design:

- `POST /imoveis/fotos` — `imovel` is a **top-level query param**; payload is
  `cadastro={"fields":{...}}`; body empty.
- Vista **pulls** the image from a URL you supply. You never send bytes — a publisher
  needs a publicly reachable image host, not a multipart client.
- `fields` is a **keyed object** (`foto1`/`foto2`/`foto3`). A JSON array is rejected.
  base64 is rejected. URL only.
- A failed fetch returns **207** per-photo and creates nothing.
- 🔴 Vista returns **401 for missing parameters as well as for permission denial**.
  Discriminate on the **message**, never the status.
- Permission split: `…644c` (ours) **denied** photo write; `…bced` (Quinto Andar
  portal) **permitted**, and also reads full owner PII.
- Sandbox `sandbox-rest.vistahost.com.br` (key published in Vista's own docs) carries
  the identical write surface — work out payloads there, never against the live CRM.

> ⚠️ The 401-means-two-things rule interacts with `CLAUDE.md` §1 *"Auth tests: assert
> strict `== 401`"*. That rule is about **our** routes. A Vista-facing adapter must
> discriminate on message; do not let the keeper's shape push a status-only read into
> the adapter.

## 5 · Owner-consent gates (from the approved plan §7, unchanged)

None of these can be satisfied by an agent:

1. Applying Core 046/047 and SW migrations (numbers TBD at write time).
2. Supplying `VISTA_PHOTOS_API_KEY`, OpenAI, Stripe **live**, Asaas **production** secrets.
3. Enabling billing automations.
4. Prod deploy.
5. Flipping any page from `desenvolvimento` to `producao`.
6. Spending on the real smoke run.

## 6 · Next actions

1. Resolve C5 with a read-only gallery probe (sandbox first, then production read).
2. Apply C1–C3 to the plan document before opening Wave 1 worktrees.
3. SW migrations 114–118 are **taken and land with the in-flight prod promote**
   (114 termos · 115 matrícula ato detalhes · 116 certidões situação · 117
   identidade+settings · 118 imóvel documentos) — confirmed by `noctusai-cd`
   2026-09-16. **SW 119 is the correct next free number**; re-verify after the
   promote lands. Only the *Core* number needed renumbering (C3).
4. Wait for `noctusai-cd` / `noctusai-36` to land their prod promote — dev is moving.
5. Author the API contract (`EDICAO-FOTOS-CONTRACT.md`), then open Wave 1.
