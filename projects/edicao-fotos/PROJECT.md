# Edição de Fotos — AI photo editing for real estate

> **Status:** Wave 1 (seed organs) SHIPPED to `dev` @ `ce5538dc`, 2026-09-16.
> Waves 2-4 not started. No engine, no product module, no migrations applied.
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

Also inherited from `origin/dev` (not collisions — already landed, and Wave 1 builds on
them): `primitives/exceptions.py` (`HTTPException.headers` no longer dropped fleet-wide,
so `Retry-After` survives — relevant to the OpenAI 429 retry path), `config/csv_settings.py`
(new), `security/secrets_scan.py` (new), and `seed/lib/frontend/src/api.ts`
(`ApiError.code` now also reads a flat `{detail, code}` body — relevant to §0 of the
contract's error envelope).

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
`products/core/backend/migrations/045_academia_agents_live_scope.sql` is **already
on `origin/dev`** (verified at `7e5f5ad6`). It is a HELD file — written but applied to
no database — belonging to `noctusai-36`'s consent-gated julia/academia cutover, and
it flips `academia-de-reciclagem` + `agents` to `deploy_scope='live'`.

**Renumber Core 045/046 → 046/047.**

> 🔴 **Methodology note — this is why the primary checkout is not the source of truth.**
> The first audit pass read `products/core/backend/migrations/` from the primary
> checkout, which sits on a local `dev` that is **12 commits behind `origin/dev`**, and
> concluded "next free is 045". That matched the plan document, so nothing looked wrong.
> Both were stale in the same direction. Always number against `origin/dev` — or better,
> against the merged tip at write time.

Downstream: `deploy/fleet/build-scope.txt` is derived from `ativo=true AND
deploy_scope='live'` (`mcp/noctusai/tools/noctus/dev/build_scope.py:111`), so the build
set grows by two slugs when 045 is applied.

### C4 — billing is far less greenfield than the spec implies 🟡
Spec §8 reads as if platform billing is new. Core already ships
`routers/{billing,plans,subscriptions,licenses,entitlements,onboarding}.py` and
`services/{billing_service,stripe_service}.py` — ~1,600 lines against the real Stripe
SDK. The plan knows this ("billing refactored onto the seed payments module"); the
spec does not, and anyone sizing Wave 2 from the spec will under-size it by a lot.
Refactoring **live billing** onto a brand-new seed organ is the highest-blast-radius
slice in the project and is absent from the plan's §8 Risks.

### C5 — Vista gallery read: ✅ RESOLVED 2026-09-16 (and the plan was wrong)
"Pull photos from a Vista imóvel" is one of three v1 photo sources. It **works**, and
needs no new credential.

**The approved plan said:** add `list_imovel_fotos()` reading a *"nested `fotos` group
on `/imoveis/listar`"*. That is wrong on **both** the relation name and the method, and
would have failed at build time with a misleading 400.

Live-probed — sandbox first (`sandbox-rest.vistahost.com.br`, key published in Vista's
own docs), then production read-only:

| probe | result |
|---|---|
| `{"fotos":[…]}` on `/imoveis/listar` | `400` — *identical shape to a bogus relation* (control `{"naoExiste":["Xyz"]}` errors the same way) |
| `{"Foto":[…]}` on `/imoveis/listar` | `400 "A tabela Foto não está disponível **para este método**"` — table real, method wrong |
| `{"Foto":[…]}` on **`/imoveis/detalhes`** | ✅ `200` |
| `GET /imoveis/fotos` | `405` — write-only, confirms `vista.md:346` |

**Production, `CA2830`, with the ERP's existing key (`…644c`): 28 photos.**

Consequences:
1. ✅ The Vista photo source **ships in v1**. Route `POST /lotes/{id}/vista` is unblocked.
2. ✅ **`VISTA_PHOTOS_API_KEY` is NOT needed for reads** — one owner-consent gate drops
   off the critical path entirely. The `…bced` portal key is required only for photo
   *writes* (Phase 2), which v1 does not do.
3. ⚠️ **The payload is a DICT keyed by photo code, not a list** — the same shape trap as
   `Corretor`. The adapter must `list(d.values())`; indexing `[0]` yields a key string.
4. Entry keys: `Codigo`, `Foto` (full URL), `FotoPequena`, `Destaque` (`"Sim"` on exactly
   one), `Tipo`, `Descricao`. `FotoDestaque` on `listar` is a *cover* field, not a gallery.
5. `KB § INTEGRATIONS/vista.md` documented the wrong name and method; corrected in this
   branch (drift-fix-on-contact).

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

### C8 — "Econômico" has no viable model 🔴 (found at Wave 1 verification)
`supports_batch` ships as a real field on `ModelEntry`, and the contract's
`capacidades.economico_disponivel` lock keys off it. But **no catalog row sets it
`True`** — verified against the built catalog: 32 rows, `batch-capable: []`.

Cause, and it is the correct behaviour: the spec says `gpt-image-2` and older support
the Batch API at 50% off, but publishes **no per-1M-token rate** for them. S2 refused to
fabricate one and filed `NOC-REMEDIATE[llm-model-unpriced]` instead — right call, since
an invented price would silently corrupt every cost record and margin figure.

Consequence: **Econômico is permanently blocked for every org**, so the speed-mode
toggle, the 50%-discount path, and the `fotos.poll_openai_batch` job are all v1 dead
code. The two priced models (`gpt-image-2.5-sunburst` / `-flare`) are `supports_batch=False`
by verified fact, not omission.

Resolution is an owner decision, and it is cheap either way:
1. **Supply `gpt-image-2`'s pricing** → add the row, Econômico ships.
2. **Cut Econômico from v1** → drop the toggle, the batch job, and the lock from the
   contract; re-add when a batch-capable model is priced.

Until one is chosen, do NOT build the Econômico half of the pipeline — it cannot be
exercised end-to-end, so it would ship untested by construction.

### C9 — 🔴 DO NOT APPLY Core 045, and do not trust a tree you did not name
**Core 045 is on the prod branch but deliberately UNAPPLIED.** It belongs to
`noctusai-36`'s cutover. `deploy/fleet/build-scope.txt` derives from
`ativo=true AND deploy_scope='live'`, so applying 045 early makes build-scope list two
slugs that have no compose service — **breaking the next build for every product,
including this one**. Confirmed by `noctusai-cd` 2026-09-16. Leave it alone.

**The wrong-tree family (N=3 in one night).** A repo with 47 worktrees makes "which tree
am I acting on?" a live hazard, and it bit three different surfaces the same night:

| # | surface | failure | cost |
|---|---|---|---|
| 1 | `noctus.dev.branch_pointer` | **writes** to the MCP server's tree, not the calling worktree (it is the only tool in its family with no `worktree_path` param) | stray commit `996c64c2` on primary `dev` |
| 2 | `noctus.dev.predeploy_check` | **measures** the primary tree and returned **GREEN** against a 40-commits-behind state | a false "ready to deploy" |
| 3 | hand-written `git --git-dir=<primary>/.git … origin/dev..HEAD` run from inside a worktree | **reads** the wrong tree — `HEAD` resolves to the primary's branch | a 170-file diff that looked like a rogue slice; truth was 6 files |

**Rule.** This is `CLAUDE.md` §1 *verdict-channel integrity* — "the exit code you read must
belong to what you are judging" — one axis over: **the TREE you read must belong to what
you are judging.** #2 is the dangerous variant: a deploy gate returning GREEN from the
wrong tree is a false-green on the one check whose entire job is to be trustworthy.

**Practice, until the tools carry `worktree_path`:** never pass `--git-dir` to inspect a
worktree — `cd` into it and let git resolve its own context; and before trusting any
gate's verdict, confirm which tree produced it. `noctusai-cd` owns the incident filing.

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

## 4b · Wave 1 — shipped 2026-09-16 (`dev` @ `ce5538dc`)

Seven seed slices, built in parallel worktrees off `7e5f5ad6`, merged to one tip, and
gated on the MERGED result — not seven per-branch greens.

| slice | organ | independent verification |
|---|---|---|
| S1 | `domain/jobs` hardened + `migrations/jobs.sql.template` | `retry_policy.py` byte-identical (blob `513f182a`) — its 3 live consumers untouched |
| S2 | `integrations/llm` + image-edit catalog | pricing exact: $4.00 back-compat, $38 image-only, $43 mixed |
| S3 | `primitives/image_sizing` + `integrations/imaging` | GPS strip proven on a real EXIF fixture; `gps_stripped` False on a GPS-less control |
| S4 | `integrations/fx` (BCB PTAX) | 33 tests in 0.05s (offline by proof); `Decimal`; no `LLM_USD_TO_BRL` fallback |
| S5 | `integrations/payments` + `domain/payments` | `products/core/` zero bytes touched; duplicate-webhook no-op proven |
| S6 | `domain/permissions` + `api/auth/platform` | strict `== 401`; org-admin→platform gate denied (the escalation trap) |
| S7 | `integrations/vista.list_imovel_fotos` | verified against the REAL production wire shape |

**Merged-tip gates:** seed lib **4469 passed / 1 skipped / 0 failed** · seed framework
**203 passed** · `verify-kb-sync` · `check-claude-md-router` · `check-seed-declared-imports`
· `check-seed-test-root-ci-coverage` — all clean.

**Integration conflicts, all additive keep-both** (`backend-engineer.md` owns_kb +
`INDEX.md` + `pyproject.toml`). Three slices designed as file-disjoint were textually
coupled by the `owns_kb` gate and a shared dependency list — *file-disjoint is not
effect-disjoint*, and this is the cheap version of that lesson.

**New seed dependencies reaching prod at the NEXT promote** (they change a build input
for every product): `Pillow`, `pillow-heif` (S3), `stripe` (S5). Whoever runs that
promote will see them in the rebuild set.

## 4c · 🔴 Blockers for Wave 2+ — none are solvable by an agent

1. **The OpenAI account has no credits.** Every cache refresh this session returned
   `429 — "You have no credits remaining"`. This is not a side issue: the entire product
   is four OpenAI steps (edit · evaluate · guide · rule-propose). **Nothing downstream of
   Wave 1 can be exercised end-to-end until this is resolved**, including the smoke run
   the plan gates release on.
2. **C8 — Econômico has no batch-capable model** (§C8). Supply `gpt-image-2` pricing, or
   cut Econômico from v1. Unbuilt deliberately: it cannot be exercised, so it would ship
   untested by construction.
3. **Migrations are owner-gated.** SW starts at **119** (114-118 applied to prod
   2026-09-16); Core at **046/047** (045 is taken and must stay unapplied — §C9).
4. **Secrets** — Stripe live, Asaas production, OpenAI. `VISTA_PHOTOS_API_KEY` is NO
   LONGER needed (§C5).
5. **Release shape** (§C7) — recommendation stands: R1 = engine + review + zip, R2 =
   billing. Wave 2 refactors *live* billing with real customers; pairing it with a new
   AI pipeline doubles the blast radius for no validation benefit.

## 4d · Leftovers

- **8 worktrees not torn down** (`ef-s1..s7`, `ef-wave1-integration`, `edicao-fotos-contract`).
  Deliberate: `task_branch action=cleanup` pushes a salvage pointer, which cancels an
  in-flight CI run. Tear down after the `dev` run is green.
- `NOC-REMEDIATE[llm-usage-image-columns]` — `SupabaseUsageSink` can't write the new
  image-token columns yet. That migration is the one that must become the **seed template**
  (§C2, N=3), not a fourth hand-copy.
- `NOC-REMEDIATE[llm-model-unpriced]` — `gpt-image-2` (see C8).
- `mcp/noctusai/tests/test_llm_providers.py` is effectively frozen to edits: a pre-existing
  unannotated self-monkeypatch at line ~356 makes the guard refuse any edit to the file.
  Annotate or rewire before a later slice needs to touch it.
- N=2 triage: a fake-core-client shim duplicated across two auth test files.

## 5 · Owner-consent gates (from the approved plan §7, unchanged)

None of these can be satisfied by an agent:

1. Applying Core 046/047 and SW migrations (numbers TBD at write time).
2. Supplying `VISTA_PHOTOS_API_KEY`, OpenAI, Stripe **live**, Asaas **production** secrets.
3. Enabling billing automations.
4. Prod deploy.
5. Flipping any page from `desenvolvimento` to `producao`.
6. Spending on the real smoke run.

## 6 · Next actions

1. ~~Resolve C5~~ ✅ done 2026-09-16 — gallery reads via `Foto` on `/imoveis/detalhes`.
2. Apply C1–C3 to the plan document before opening Wave 1 worktrees.
3. SW migrations 114–118 are **taken and land with the in-flight prod promote**
   (114 termos · 115 matrícula ato detalhes · 116 certidões situação · 117
   identidade+settings · 118 imóvel documentos) — confirmed by `noctusai-cd`
   2026-09-16. **SW 119 is the correct next free number**; re-verify after the
   promote lands. Only the *Core* number needed renumbering (C3).
4. Wait for `noctusai-cd` / `noctusai-36` to land their prod promote — dev is moving.
5. Author the API contract (`EDICAO-FOTOS-CONTRACT.md`), then open Wave 1.
