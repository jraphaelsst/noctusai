# P Studio — absorption + prod promotion · roadmap (2026-08)

> **Product.** `products/p-studio/` — ERP for a real-estate photography/AV
> production studio. Built OUTSIDE noc, in the sibling workspace
> `cadu/p-studio/`, and absorbed 2026-08-13. Project doc:
> `projects/p-studio-absorption-rollout/PROJECT.md`.
>
> **Status convention** (`KB § PATTERNS/common/roadmap-tracking.md`): a milestone
> bullet is annotated ✅ **only once genuinely reached**. `M4` is the
> prod-promotion milestone that `deploy/consent/p-studio.prod.yml` must
> reference — it is marked when the promotion is actually ready, never in
> order to satisfy the gate that reads it.

---

## Origin

P Studio's financeiro module was wired to Asaas in the sibling workspace and
proven end-to-end against the real Postgres and the real Asaas API: it issues a
boleto, reconciles the payment, and settles the lançamento. One gap survived,
and it is not closable on `localhost`: **the Asaas webhook can only be delivered
to a public URL**, so the real envelope has never passed through the route. Every
test body was hand-built from the documented format.

Closing that gap needs a public URL. A public URL needs the product to be a
first-class noc product — catalog, container, ingress, consent. Hence an
absorption roadmap rather than "point a tunnel at localhost", which would have
captured the envelope and left the entire absorption debt standing.

---

## Milestones

- **M1: Phase 0 audit + source in-home** — structural audit of the sibling
  workspace (tree, deps, env, DB/auth wiring, migrations, suite, platform
  coupling); worktree isolated off `origin/dev`; source copied to
  `products/p-studio/` minus secrets/venv/node_modules; roster row + ports
  8014/8180 reserved. Three keepers fired on the import and each found real
  debt: `check_override_is_range` (exact `react-router` pin — a fleet-wide
  freeze, since the seed copies `overrides` into 12 products),
  `check_dependabot_product_coverage` (product invisible to Dependabot),
  `check_ci_test_matrix_coverage` (absent from both test matrices). All fixed
  at the source. → ✅ **reached 2026-08-13** (`d4a354a0`).

- **M2: house-shape reshape** — backend on the seed factory
  (`create_product_app`, schema `p_studio`, port 8014, `ErroProvedor` handler
  preserved); frontend on the seed vite factory (same-origin API base, port
  8180); one container per `KB § PATTERNS/devops/containerization.md § 12a`
  (`FROM noctus-seed-*-base`, `serve_spa` / `SERVE_SPA_DIR`, no nginx, no
  proxy sidecar). Suite green in the new home at the ratified baseline.
  → ✅ **reached 2026-08-13** (`2b75f465`, `2e4f58cc`, `dbb66c05`, `17933bdb`).
  Ratified baseline: **330 backend** (1 skipped, 9 `ao_vivo` deselected) +
  **116 frontend** / 6 files; `tsc` and `vite build` exit 0. The Phase-0
  audit's "~311 + ~116" were static estimates; these are measured.

  Three things this milestone turned up that the plan did not anticipate:
  (a) moving to `create_product_app()` silently changed every HTTPException
  envelope from `{"detail"}` to the seed's `{"error":{"code","message"}}`,
  so every backend error in the UI would have kept failing correctly while
  quietly ceasing to say why — caught only because slice A surfaced the
  change instead of fixing its own tests around it; (b) `--propagate`
  skipped p-studio in silence and exited 0, because propagate.py carried a
  hand-maintained slug list whose stated justification (parity with two
  shell scripts) referred to scripts that no longer exist; (c) regenerating
  the fleet's containers corrected orbity's OCI image title, which had been
  publishing as `noctus-seed`.

- **M3: validation** — the `KB § GUIDES/production-deploy.md § 0.1` gate that
  `dev_validated: true` attests to. → ✅ **reached 2026-08-16.**

  The container leg, which was the open one, closed against a real running
  image (`ghcr.io/jraphaelsst/noctus-p-studio:dev`, single container, port
  8014):

  | probe | result |
  |---|---|
  | container health | **healthy** at 45s |
  | `GET /api/health` | **200** `{"status":"ok","version":"0.1.0","product":"P Studio","startup_hook_error":null}` |
  | `GET /` (SPA) | **200**, real HTML — `serve_spa` serves the built bundle from the same port as the API |
  | `GET /api/clientes` unauthenticated | **401** strict |
  | `POST /api/integracoes/asaas/webhook` with no `asaas-access-token` | **503** — see below |

  **On the 503.** The project's Fase-2 check said "must answer 401 without
  the header". With `ASAAS_WEBHOOK_TOKEN` empty the route answers 503
  instead, and that is deliberate: `integracoes_router.py:41` — *"503 e não
  401: o problema é nosso, não de quem chamou."* It fails **closed**. The
  property the check actually protects — no anonymous write is ever
  accepted — holds. So the gate was reworded to name the real danger
  condition (**200**), with 503 expected before the token is configured and
  401 after. A gate that fires on "not exactly 401" would have blocked on
  correct fail-closed behavior.

  Superseded record of the earlier blocked state, kept deliberately:

  Green:
  - `predeploy_check p-studio` → **ready, exit 0, 7/7** (framework_deps ·
    frontend_build · backend_tests · deploy_local_gitignored ·
    prod_config_parity · required_prod_env_present · cors_roster_complete).
  - p-studio backend **330 passed** / 1 skipped / 9 deselected; frontend
    **116** / 6 files; `tsc` + `vite build` exit 0.
  - `--propagate both --check` → **in-sync** across the whole fleet, zero
    stale — the derive change did not disturb the other 11 products.
  - `test_propagate.py` 10 passed · `test_container_shape.py` 11 passed.

  Blocked:
  - **Container build + healthy + functional probe on `localhost:8014`.**
    Docker Desktop is not running on the host (`docker info` cannot reach
    the daemon socket). This is the leg that distinguishes "tests green"
    from "the image actually serves", per
    `KB § PATTERNS/devops/containerization.md § 12b` — it cannot be
    substituted with more test runs, and claiming M3 without it would make
    `dev_validated: true` a false attestation.

  Not blocked, but the user's:
  - Migration `004` (url_base → the house port) is **written and committed
    but NOT applied** — the live-database write was refused by the
    permission layer. One idempotent UPDATE.

- **M4: prod promote** — `p-studio.noctusai.com`. Registers the three
  prod-exposure surfaces (`deploy/fleet/docker-compose.prod.yml` ·
  `deploy/tunnel/ingress.yml` · `deploy/fleet/build-scope.txt`). Gated on the
  user's consent per `KB § PATTERNS/devops/prod-exposure-consent.md`. → ⬜

  **Authorization status.** The user typed the canonical phrase — *"I authorize
  p-studio to be published to production."* — in-session on **2026-08-13**. That
  is the decision, and it is durable in the harness transcript. The record
  `deploy/consent/p-studio.prod.yml` is **not yet written**, because its
  `consent_ref` must resolve to a ✅ milestone and `dev_validated: true` must
  attest to a validation that has not run yet. Marking M4 ✅ now, to satisfy the
  gate that reads M4, would be the exact shape the gate exists to prevent.
  Authorization is obtained; readiness is not. They are different legs.

- **M5: real webhook envelope captured** — the reason the roadmap exists.
  Register the **sandbox** webhook, pay a sandbox charge, capture the real body
  to `tests/fixtures/asaas/webhook_liquidada.json` with `_procedencia`, replay
  it offline, confirm `provedor_eventos.efeito='recebido'` and no duplicate row
  on re-delivery. Closes `cadu/_INTEGRACOES_BANCARIAS/03-ASAAS.md § 6`. → ⬜

---

## Trigger conditions

- **T1 — M4 unblocks** when M3 is green *and* the consent record's four legs can
  all be honestly satisfied. Signal: `predeploy_check p-studio` returns `ready`
  **and** M3 is annotated ✅ on its line above.
- **T2 — production Asaas key** replaces sandbox only after M5 has captured the
  envelope *and* the user decides to bill for real. Signal: the user says so.
  This moves real money (real boleto, real fee, real payer) and is not an
  engineering call.
- **T3 — Banco do Brasil adapter** starts when the cobrança convênio is active.
  Signal: user confirms the bank agreement. Lead time is the bank's, not
  engineering's. Design is already proven compatible — the `ProvedorCobranca`
  Protocol means it is an adapter swap, not a refactor.
- **T4 — canonical-organ refactor** (frontend consumes `@noctusai/lib` instead
  of the local 22-primitive `ui.tsx`) starts once the product is live and
  stable. Signal: M4 ✅ + one week of prod uptime with no rollback.
- **T5 — `check_fake_db_fidelity` keeper** gets built at N=3. Currently N=2 —
  see Open questions.

---

## Anti-goals — explicitly NOT doing these

- **Not** adapting p-studio to consume canonical seed organs in this roadmap.
  The absorption ports and containerizes; the organ swap is T4. Mixing them
  makes a large diff where a reviewable one was available, and the container
  gate is what unblocks everything else.
- **Not** rewiring `org_id` from env to the JWT/session. The product is
  single-tenant by construction today (`settings.org_id` stamps INSERTs; RLS
  `org_id = public.current_org_id()` authorizes). It is a genuine mismatch with
  the multi-tenant platform and it is filed, not fixed here.
- **Not** wiring Core SSO. Login stays local Supabase email/password until a
  dedicated slice.
- **Not** editing `products/p-studio/backend/migrations/**`. All three are
  already applied to the live shared Supabase (`nyplttplcoyiiqjrvtiw`). Defects
  found in them get **forward** migrations, never in-place edits — an edited
  applied migration lies about what ran.
- **Not** pointing a tunnel at a local `uvicorn` to grab the envelope. It would
  close M5 and leave M1–M4 undone forever.
- **Not** simulating the envelope from documentation and calling § 6 covered.
  That is precisely the lie the replay suite is capable of telling.

---

## Open questions

1. **Does the real Asaas envelope match the documented `{"id","event","payment":{…}}` shape?**
   Unknown by construction — it is what M5 exists to answer. `interpretar_evento`
   in `app/providers/asaas.py` is the translation point if it diverges. No
   guess recorded here on purpose.

2. ~~**`/api/health` response body.**~~ **Resolved 2026-08-13.** The seed's
   router returns `{"status","version","product","startup_hook_error"}` with
   `product` as the display name, not the slug. The **criterion moved, not the
   route**: re-declaring a local `/api/health` would shadow the seed's in one
   product and fork a fleet-wide contract for cosmetics. `PROJECT.md § 9`
   updated to the real body.

3. **FakeDB fidelity — N=2, one short of MUST-formalize.** Twice in the sibling
   workspace a test fake more permissive than Postgres hid a real bug: first the
   UNIQUE constraint (the fake accepted duplicates, so the webhook "deduplicated"
   against a store that accepted everything), then UUID typing (the fake compared
   strings in Python and returned "not found"; Postgres *raises* 22P02, and the
   event parked in the retry queue forever). At N=3 this is a
   `check_fake_db_fidelity` keeper (T5). Logged as triage, not acted on — the
   recurrence rule is N=2 → triage, N=3+ → MUST formalize.

4. **Disposition of `cadu/p-studio/`.** Recommendation: archive with a pointer
   to `products/p-studio/`. Two live copies of one product is the most reliable
   way for a fix to land in the wrong one. **We never delete the originating
   workspace — the deliverable is the "safe to delete" sign-off** (Gate 9).

5. **`dev_validated` under a dormant dev fleet.** The dev fleet has been dormant
   since 2026-08-11, so "dev-fleet-validated" cannot mean what it meant for igig
   on 2026-08-09. M3 defines the substitute explicitly (local container healthy +
   `predeploy_check` + functional probe). Worth confirming this is the intended
   reading of `§ 0.1` post-dormancy rather than an agent's convenient
   reinterpretation.

---

## Known hazards carried in from the sibling workspace

Recorded here because they are live, not hypothetical:

- ~~**Migration 002 seeds `admin@pstudio.local` / `senha123`**~~ — **checked
  against the live database 2026-08-14, and it is NOT live.**
  `SELECT encrypted_password = crypt('senha123', encrypted_password)` returns
  **false** for that user. The migration FILE does hash `senha123`
  (`002:90`), so a re-run would introduce the weak credential — but what
  actually ran set something else, exactly as `PROJECT.md § 5` claimed. Two
  corrections fall out: (a) the Phase-0 read that called this a live
  vulnerability was wrong — it read the file and inferred the database;
  (b) **the file is not a faithful record of what ran**, which is the more
  durable hazard. Do not re-run 002 against this project, and do not trust
  it as a description of live state. Rotating the password remains the
  user's, per `PROJECT.md § 4`.

- ~~`url_base = 'http://localhost:5176'` is a localhost URL in a shared
  platform table~~ — **also mischaracterized.** Every one of the 13 catalog
  rows carries `http://localhost:<port>`, including the four products
  serving production today (`erp-imobiliario`, `igig`, `orbity`,
  `social-wiring`). `url_base` is therefore **not** the public-routing
  field; public routing is `PRODUCT_URL_*` in `.env`
  (`https://{slug}.noctusai.com`, managed by
  `noctus.dev.ensure_product_url_roster`). p-studio's row is anomalous only
  in carrying its **old Vite port** (5176) where the fleet convention is the
  **backend** port. Forward migration `004` aligns it to 8014. This was a
  convention drift, not a production leak.

  > Recorded rather than quietly amended, because both errors share one
  > cause: reading a file and reporting it as the state of the world.
  > `KB § 01-PHILOSOPHY.md` — the codebase is the source of truth for
  > *solutions*; for *live state*, the live system is.

- **`p-studio` was ALREADY `ativo=true, deploy_scope='live'`** in the catalog
  before this project touched anything (set when 002 ran). §7-Q3's decision
  matched what was already there; no catalog write was needed for it.
- **`cadu/p-studio/backend/.env` holds a PRODUCTION Asaas key** (`$aact_prod_…`,
  issues real boletos with real fees) plus a `SUPABASE_SERVICE_ROLE_KEY`. It was
  excluded from the absorption copy. Production env vars are provisioned through
  the platform secret path.
- **The webhook answers 200 to almost everything, deliberately.** Asaas halts
  its delivery queue after **15 consecutive non-2xx** responses and only resumes
  on manual reactivation in the panel. One poisoned event returning 500 would
  cost the reconciliation of every other payment. `p_studio.provedor_eventos`
  **is** the retry queue, drained by `POST /api/integracoes/reprocessar`. An
  agent who does not know this will "fix" the design.
- **Verify 401-before-registering.** The webhook must answer **401** without the
  `asaas-access-token` header. If the deployed route answers 200, then
  `ASAAS_WEBHOOK_TOKEN` did not reach the environment and an anonymous write
  route is live. Stop and fix before touching the Asaas panel.

---

## Decision log

- **2026-08-13** — Absorb rather than tunnel. A tunnel to `localhost` would
  capture the envelope and leave the product outside the catalog, undeployed and
  un-SSO'd; the debt would outlive the "solution".
- **2026-08-13** — `deploy_scope: live`. The dev fleet is dormant and the whole
  point is a public URL, so `dev` is a parking state that cannot serve this
  goal.
- **2026-08-13** — Organ-consumption refactor deferred to T4, not folded into
  the absorption. Rationale in Anti-goals.
- **2026-08-13** — User authorized prod publication with the canonical phrase.
  Consent record deferred to T1 rather than written immediately, because two of
  its four legs (`consent_ref` → ✅ milestone, `dev_validated: true`) cannot yet
  be satisfied honestly. Recording the reasoning so a later reader does not
  mistake the delay for a missing decision.

---

## Retrospective

_Filled at T1 fire._

---

## Composes with

- `KB § GUIDES/absorb-seed-workspace.md` — the 10 gates this roadmap walks.
- `KB § PATTERNS/devops/prod-exposure-consent.md` — the M4 gate.
- `KB § PATTERNS/devops/containerization.md § 12a` — divergent-arch → house model.
- `KB § PATTERNS/architect/product-working-scope.md` — `ativo` + `deploy_scope`.
- `KB § PATTERNS/devops/dev-fleet-dormant.md` — why M3 substitutes for dev-fleet validation.
- `KB § PATTERNS/common/roadmap-tracking.md` — the milestone/✅ convention.
