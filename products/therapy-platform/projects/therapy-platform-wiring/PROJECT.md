# Therapy-Platform Wiring — Project Document

> **This is a living document, not a rigid checklist.**
> As we build and learn, this project document evolves. Revise phases, fold in
> optimizations, update the Change Log. See
> `CLAUDE.md → Engineering Philosophy → Projects are living documents`.
>
> **Slug rationale (honest-scope check):** Originally discussed as
> `therapy-admin-console-gap` (intent=`gap`: narrow holes). Scope widened during
> interrogation to close every scaffolding gap across the whole `therapy-platform`
> product — admin **plus** therapist, patient, clinic, and public surfaces —
> which is an end-to-end *wiring* job, not a couple of gaps. Renamed per the
> naming convention in `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md §8`.

- **Created:** 2026-04-20
- **Last updated:** 2026-05-10 (Phase 2 ✅)
- **Status:** ⏳ **Phase 0 ✅ + Phase 1 ✅ + Phase 2 ✅ → awaiting "continue" before Phase 3.** Phase 2 added 8 admin endpoints (appointments, dashboard, suspend, financials summary/transactions/commissions GET+DELETE, plus the legacy-shape-compatible POST), wired the Dashboard frontend page, and shipped 45 new tests (37 router + 8 service). **Tests at last verification (2026-05-10):** 1212/1222 backend (10 pre-existing baseline failures from Supabase-client init when SUPABASE_URL is unset — none introduced by Phase 2); admin-surface 98/98 in isolation; `vite build` clean; keeper 0 issues. Per the project's pause-after-each-phase cadence, awaiting user signal before Phase 3 DTO normalization sweep.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com) · Claude Opus 4.7
- **Related docs:**
  - `CLAUDE.md § Engineering Philosophy` — behavioral rules, loaded every session
  - `KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md` — product surface inventory
  - `KNOWLEDGE-BASE/CONTEXT/backend/06-THERAPY.md` — therapy backend spec
  - `KNOWLEDGE-BASE/CONTEXT/frontend/04-THERAPY.md` — therapy frontend spec
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md` — cadence, naming, tests-with-code
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/proposals-and-improvements.md` — phase-end protocol
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/database-rls.md` — migration discipline
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/lgpd.md` — personal-data guardrails
  - `products/therapy-platform/MASTER-PROMPT.md` — the agent-facing product contract
- **Project slug:** `therapy-platform-wiring`

---

## 1. Context & Purpose

The `therapy-platform` product was shipped with a frontend that is substantially complete and a backend that is only partially wired. Multiple admin pages crash, 404, or 405. Several non-admin flows (therapist, patient, clinic) likely share the same class of defect: scaffolded UI hooks pointing at endpoints that are either missing, HTTP-method-mismatched, or returning raw DB rows instead of the DTO the frontend `types/` declares.

This was surfaced today (2026-04-20) by three admin-console reports from the user:

1. `/admin/terapeutas` crashed at `getInitials(t.nome)` because `nome` is undefined — backend returned raw `therapist_profiles` rows with no join to `auth.users`. *(Fixed ad-hoc in the same session — becomes Phase 1's reference pattern.)*
2. `/admin/agendamentos` toasts `[404] Not Found` — `GET /api/admin/appointments` is not defined in the backend router.
3. `/admin/financeiro` crashes with `A <Select.Item /> must have a value prop that is not an empty string` and toasts `[405] Method Not Allowed` — Radix Select misuse + `GET /api/admin/financials/commissions` is not routed (only the POST counterpart exists). *(Select fix applied ad-hoc — the 405 and sibling missing GETs fold into this project.)*

These three reports are symptoms of a product built with "frontend first, backend when needed" velocity — the common failure mode for a seed-inheriting product that grew faster than the platform around it. The purpose of this project is to **sweep every therapy-platform surface end-to-end, close every gap at the layer it belongs to (seed vs. product vs. schema), and land with tests and a clean build.** When this project finishes, any logged-in user of any role should be able to navigate any reachable page in the therapy-platform without a 4xx toast, a `TypeError` from a DTO mismatch, or a RLS surprise.

The win looks like: `vite build` clean, `pytest tests/` clean for backend, every `/admin/*` page loads real data in under one second with a 200, and the same goes for every `/therapist/*`, `/patient/*`, `/clinic/*`, and public route.

---

## 2. Confirmed constraints

User answers captured during interrogation (2026-04-20). **Future agents inherit the reasoning, not just the outcome.**

- **Scope breadth** — widest (A ⇒ B ⇒ C): fix known regressions, then sweep the admin console end-to-end, then close pre-existing scaffolding debt, then widen to the whole therapy-platform product (therapist/patient/clinic/public surfaces). *(Rules out a narrow "just appointments + financials" scope. Forces Phase 0 discovery to be rigorous — the rest of the project depends on a concrete gap inventory.)*
- **Display-name resolver** — absorb into seed (`noctusai_lib`), not inline per page. *(Rules out the per-row `get_user_by_id` pattern used in the ad-hoc therapists fix. Treat the ad-hoc fix as Phase 1's starting point and replace it once the shared helper ships.)*
- **Reject flow** — include the full wiring in this project (migration, service, list-endpoint status derivation, admin UI, test coverage). *(See §3 "Reject flow primer" for the current breakage and target state.)*
- **Tests** — always, per the three-layer discipline in `CONTEXT/PATTERNS/testing.md`. Not a per-phase decision. *(A phase without its tests is `⏳ (tests deferred)`, not `✅`.)*
- **Cadence** — phase-by-phase, pause after each, no auto-advance. The user will explicitly say "continue" / "do phase N" / "ram through 2-3" when bulk execution is wanted. *(Already documented in `project-execution.md §3`; verified during interrogation.)*
- **Seed sync** — patterns worth promoting mid-project (identity resolver, admin DTO-mapper helpers, reject-audit column scaffolding) land as **phase-end proposals** via `noctus.dev.file_proposal(project="therapy-platform-wiring", …)`. Reviewer triages separately; this project does not block waiting for seed promotion. *(Keeps this project shippable independently of seed maturation.)*
- **"The platform" in the widest-scope prompt** — interpreted as the `therapy-platform` product in full, not the whole NoctusAI multi-product repository. *(Other products are out of scope; seed touches are limited to the one identity-resolver capability and any other helpers discovered as genuinely generic.)*

---

## 3. Design principles

How we're approaching *this specific problem* on top of the platform-wide `CLAUDE.md` rules.

1. **Fix at the layer of the cause.** If two admin pages need `nome`/`email` from `auth.users`, the solution is a shared resolver — not two duplicated joins. Seed-absorption precedes duplication. The ad-hoc therapists fix applied this *inline*; Phase 1 consolidates.
2. **No band-aids.** We do not add `?? ''` guards to tolerate bad DTOs; we make the DTO correct at the backend boundary. The frontend consumes typed data or the endpoint is broken and Phase 0 catches it.
3. **LGPD-first on every personal-data endpoint.** Admin endpoints that aggregate patient/therapist data get a `noctus.dev.lgpd_flag` call the first time they touch identity/clinical/financial data in a new shape, per `CONTEXT/PATTERNS/lgpd.md`. The flag doesn't block — it puts the concern in the triage queue.
4. **Migrations and applied SQL stay in lockstep.** Every DDL we apply via `mcp__claude_ai_Supabase__apply_migration` lives first as `products/therapy-platform/backend/migrations/NNN_<name>.sql`. Schema drift is a rule violation, not a tradeoff.
5. **Tests land in the same phase as the code.** Three-layer discipline, no exceptions.
6. **Discovery is an artifact, not a vibe.** Phase 0 produces a checked-in gap table in this document. Phases 2-9 reference rows in that table — no phantom scope.

### Reject flow primer *(per constraint #3 — user asked for an explanation)*

**Current state today (2026-04-20):**

The therapy-platform models new therapists and new clinics as applications with a review lifecycle: `pendente → aprovado | rejeitado | suspenso`. The admin console's `/admin/terapeutas` and `/admin/clinicas` pages surface this as four tabs.

- `pendente`: user applied, no admin has acted.
- `aprovado`: admin clicked **Aprovar** → service sets `is_approved = true`. Works end-to-end.
- `rejeitado`: admin clicked **Rejeitar**, provided a reason → service is *supposed to* write the reason + actor + timestamp to the profile. **This is where the wiring is broken.**
- `suspenso`: previously approved, now deactivated → `is_active = false`. Works end-to-end.

**The break (caught during the admin-therapists fix earlier today):**

- `products/therapy-platform/backend/app/services/admin_service.py:84` writes `{"is_approved": False, "rejection_reason": reason}` to `therapist_profiles` / `clinics`.
- **No migration ever created the `rejection_reason` column.** Grep across `products/therapy-platform/backend/migrations/*.sql` returns zero hits.
- Therefore: clicking **Rejeitar** in the admin UI produces a Supabase error (undefined_column) → the request 500s. The UI never received a successful reject path.
- There is also no `rejected_at` / `rejected_by` — the audit trail (*who rejected this, and when?*) is missing entirely. LGPD and platform-admin accountability both want those fields.
- The admin list endpoint cannot derive `rejeitado` status because it has nothing to read from. The "Rejeitado" tab is empty in principle even if the above worked.
- The admin detail page has no "Rejection reason" surface — the admin clicking into a rejected profile cannot see the reason they (or a predecessor) gave.

**Target state after Phase 5:**

1. New migration `010_rejection_audit.sql` *(numbers 007/008/009 are taken — see §5.2)*:
   - Adds `rejection_reason TEXT, rejected_at TIMESTAMPTZ, rejected_by UUID REFERENCES auth.users(id)` to `therapy.therapist_profiles` and `therapy.clinics`.
   - RLS policies unchanged (the existing `service_role_bypass` + `platform_admin` select policies already cover reading these columns).
   - Applied via `mcp__claude_ai_Supabase__apply_migration` **after** the file is committed, per the "MCP migrations mirror the file" rule.
2. `reject_entity()` service updates:
   - Writes `rejection_reason`, `rejected_at = now()`, `rejected_by = admin_id`.
   - Idempotent re-reject overwrites the reason (latest reject wins) — audit trail remains via `audit_logs` if/when that's a separate concern.
3. `approve_entity()` service update:
   - Re-approval *clears* `rejection_reason`/`rejected_at`/`rejected_by` — we decided (§7) the audit trail lives in application logs, not in the profile row. The profile reflects *current* state; history goes to logs.
4. `_derive_therapist_status()` / `_derive_clinic_status()`:
   - Return `rejeitado` when `rejection_reason IS NOT NULL AND is_approved = false`.
5. List endpoint filter:
   - `status=rejeitado` query resolves to `.eq("is_approved", False).not_.is_("rejection_reason", "null")` — the "empty fallback" hack from the ad-hoc fix goes away.
6. Admin detail view:
   - `/admin/terapeutas/:id` and `/admin/clinicas/:id` render `rejection_reason`, `rejected_at`, and (resolved through the new identity resolver from Phase 1) the *name* of the admin who rejected.
7. Tests:
   - `pytest tests/routers/test_admin_router.py` — cover pendente→rejeitado, rejeitado→aprovado (re-approval clears), aprovado→suspenso→aprovado.
   - `pytest tests/services/test_admin_service.py` — direct service-layer coverage for the three reject-audit columns being written and cleared correctly.
   - Migration idempotency test (re-applying the migration is a no-op).

**Why include it in this project instead of deferring:**
The admin UI already *shows* a Rejeitar button and a Rejeitado tab. Leaving the reject flow broken means the widest-scope sweep (closing *every* gap) has a visible unfinished corner. Per the "No incomplete commits" rule, the admin surface is not `✅` until reject works.

---

## 4. Scope

**In scope:**

- Every `therapy-platform` backend endpoint that a frontend hook calls. The router surface as of the 2026-05-03 realignment audit has grown well beyond the original 2026-04-20 enumeration — Phase 0 covers all of: `/api/admin/*`, `/api/admin/financials/*`, `/api/clinic-financials/*`, `/api/therapists/*`, `/api/patients/*`, `/api/clinics/*`, `/api/appointments/*`, `/api/availability/*`, `/api/invoices/*`, `/api/reviews/*`, `/api/conversations/*` (messaging), `/api/longitudinal/*`, `/api/matching/*`, `/api/sessions/*`, `/api/wallets/*`, `/api/payments/*`, `/api/transactions/*`, `/api/refunds/*`, `/api/recurring/*`, `/api/consents/*`, `/api/lgpd/*`, `/api/anamnese/*`, `/api/attachments/*`, `/api/evolution-notes/*`, `/api/observations/*`, `/api/patient-notes/*`, `/api/treatment-plans/*`, `/api/homework/*`, `/api/mood/*`, `/api/crisis/*`, `/api/therapeutic-journal/*`, `/api/session-journal/*`, `/api/dashboard/*` (BI), `/api/rooms/*`, `/api/whatsapp-therapy/*`, `/api/support/*`, `/api/invitations/*`, `/api/auth/*`, `/api/settings/*`, and any others Phase 0 discovers. **The Phase 0 gap-table is per-router with role-tags** (admin/therapist/patient/clinic/public) so cross-cutting routers (e.g. `consents`, `lgpd`) get visited from every consumer angle without per-portal duplication.
- Every therapy-platform migration needed to support the above (notably the reject-audit migration; anything else Phase 0 discovers).
- The shared identity resolver in `seed/lib/backend/noctusai_lib/` (the one cross-product absorption this project is committing to).
- Frontend corrections required to consume corrected DTOs or fix pre-existing UI bugs uncovered during the sweep (Radix Select misuse, `Avatar` initial helpers, status-badge resolvers, etc.).
- Tests (unit + router + any integration paths) landing in the same phase as the code they cover.
- LGPD awareness: `noctus.dev.lgpd_flag` calls where new endpoints aggregate personal data in shapes not previously flagged.
- End-to-end verification: build + pytest + manual browser QA of the golden paths on every surface we touched.

**Out of scope (for now — with reason):**

- **Other products** (erp-imobiliario, core, adconnect, seed-the-template, etc.) — different projects, different slugs. *(This project is scoped to `therapy-platform`. Seed touches are limited to the identity-resolver helper per constraint #2.)*
- **UX redesigns** — if a page is ugly but works end-to-end, it stays. *(This is a wiring project, not a redesign.)*
- **New features** — no capability we aren't already carrying as scaffolded UI. If a hook points at `/api/admin/moderation-queue` and neither the backend nor a design exists, Phase 0 flags it and it becomes a separate future project. *(Avoid scope creep into fresh product work.)*
- **Payments / Stripe deep integration** beyond what's already scaffolded. Transactions, payouts, commissions exist — we wire the existing surface, not build new billing flows. *(Deeper billing work is a `-hardening` project on its own.)*
- **LiveKit / WebRTC depth** — we wire the session/video endpoints that exist. Real-time quality tuning, recording, or new RTC features are a separate project. *(Same reasoning.)*
- **Seed abstractions beyond the identity resolver** — if we spot another seed-worthy pattern (e.g., "admin DTO mapper"), we capture it in a phase-end proposal and let the reviewer schedule it as a separate seed project. *(Keeps this project shippable without waiting for seed maturation.)*
- **AI / transcription / clinical-summary pipelines** — only the wiring; model selection, prompt tuning, and pipeline restructuring are AI-expansion territory.

---

## 5. Architecture / Data Model

*Populated by Phase 0 in its entirety. This section starts with the shapes we already know from the interrogation; everything else lands as Phase 0's output.*

### 5.1 Shared identity resolver *(delivered by Phase 1)*

**Placement** — follows the 6-layer layout (`KB § PATTERNS/seed-lib-layout.md`) and the axis-swapped paths from commit `fc277e2` (2026-05-03). The resolver wraps the Supabase auth.admin SDK → it lives in `integrations/`, sibling to the existing `database.py`, `redis.py`, `email/`, `whatsapp/`, etc. Single-file shape (flat `.py`) is appropriate; promotes to a folder only if more identity providers join.

```
seed/lib/backend/noctusai_lib/integrations/
└── supabase_identity.py     # UserIdentity dataclass + fetch_user_identities()

seed/lib/backend/tests/integrations/
└── test_supabase_identity.py
```

```python
# seed/lib/backend/noctusai_lib/integrations/supabase_identity.py
@dataclass(frozen=True)
class UserIdentity:
    user_id: str
    nome: str = ""           # display name from user_metadata.{nome,full_name}
    email: str = ""          # empty string if auth lookup failed (never None — simpler downstream)
    foto_url: str | None = None

    @property
    def display_name(self) -> str:
        # Fallback chain: nome → email local-part → "Usuário"
        if self.nome:
            return self.nome
        if self.email and "@" in self.email:
            return self.email.split("@")[0]
        return "Usuário"


def fetch_user_identities(
    db: Any,                  # admin-scoped supabase client
    user_ids: Iterable[str],
) -> Dict[str, UserIdentity]:
    """Bulk resolve auth.users → UserIdentity, keyed by user_id.

    **Sync `def`, not `async def`** — supabase-py admin SDK is sync;
    wrapping in `async def` would block the event loop without yielding.
    Phase 1 decided: option (b) sequential `get_user_by_id` loop, sync
    on the request path (well under 1s at 10-100 IDs); benchmarking
    deferred until a slow page surfaces. See §11 Phase 1 entry.

    Missing IDs return UserIdentity with blank nome/email — callers get a
    deterministic shape for every requested ID.
    """
```

### 5.2 Reject-audit migration *(delivered by Phase 5)*

**Number:** `010`. As of the 2026-05-03 audit, migrations `007_clinical_data_privacy.sql`, `008_consent_retention.sql`, and `009_session_audio_segments_recording_id.sql` already exist. The next available slot is `010`. *(Phase 5 confirms the next free number at execution time — if other migrations land between now and then, bump accordingly.)*

`products/therapy-platform/backend/migrations/010_rejection_audit.sql`:

```sql
ALTER TABLE therapy.therapist_profiles
  ADD COLUMN IF NOT EXISTS rejection_reason TEXT,
  ADD COLUMN IF NOT EXISTS rejected_at      TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS rejected_by      UUID REFERENCES auth.users(id);

ALTER TABLE therapy.clinics
  ADD COLUMN IF NOT EXISTS rejection_reason TEXT,
  ADD COLUMN IF NOT EXISTS rejected_at      TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS rejected_by      UUID REFERENCES auth.users(id);

-- No RLS changes required: the existing platform_admin select policies cover
-- these columns, and the service_role_bypass policy covers writes from the
-- reject_entity service path.
```

### 5.3 Admin list DTO pattern

Every `/api/admin/<resource>` list endpoint returns `{ data: <Resource>[], pagination: { page, page_size, total, total_pages } }` where `<Resource>` exactly matches the frontend's `types/` declaration. No raw DB rows cross the HTTP boundary. Mappers live in `app/services/admin_service.py` (or a sibling file if they balloon).

**Pagination DTO destination:** invent locally in this product first, then **propose for seed promotion at the close of Phase 3** as `noctusai_lib/api/pagination.py` (verified absent from seed-lib at the 2026-05-03 audit). Phase 0 / Phase 3 confirm the recurrence count across products before the proposal lands; the project does not block waiting for the absorption.

### 5.4 Inventory *(populated 2026-05-03 by Phase 0)*

#### 5.4.1 Headline counts

| Surface | Count |
|---|---|
| Backend routers | 38 (`__init__.py` excluded; handoff-noted "39" included it) |
| Backend routes | 193 |
| Frontend hooks | 26 (all under `frontend/src/hooks/`) |
| Frontend pages with **direct** `useQuery`/`api.*` (bypassing hooks) | 4 (`pages/therapist/{Patients,Reviews}.tsx`, `pages/clinic/{Patients,Therapists}.tsx`) |
| Unique frontend → backend calls surveyed | ~143 |
| Gap rows (404 / 405 / path-mismatch / EN-PT-mismatch) | **~58** |
| Backend routers with response_model declared | **0 / 38** — all 193 routes return via `success_response()` / `paginated_response()` / `ok_response()` helpers; DTO contract is implicit |

#### 5.4.2 Systemic findings *(decided defaults are flagged in §7; design batch surfaces at end-of-Phase-0 to user)*

**Pattern A — Portuguese ↔ English path mismatches (cluster of ~30 calls × 8 routers).** Frontend uses English URLs; backend has 7 Portuguese path-prefixes that don't resolve. Pairs:

| Frontend (EN) | Backend (PT) |
|---|---|
| `/api/diary` | `/api/diario` |
| `/api/mood`, `/api/mood/analytics` | `/api/humor`, `/api/humor/analytics` |
| `/api/homework`, `/api/homework/:id/submit`, `/api/homework/:id/review` | `/api/tarefas`, `/api/tarefas/:id/submit`, `/api/tarefas/:id/review` |
| `/api/invoices` | `/api/recibos` |
| `/api/crisis-alerts`, `/api/crisis-alerts/:id/review` | `/api/alertas-crise`, `/api/alertas-crise/:id/revisar` |
| `/api/clinical/anamnese`, `/api/clinical/anamnese/:id` | `/api/anamnese`, `/api/anamnese/paciente/:id` *(also a path-shape mismatch beyond the EN/PT — see §7 design batch)* |
| `/api/clinical/evolution-notes` | `/api/evolucao` *(plus shape: backend uses `/paciente/:id` for list)* |
| `/api/clinical/treatment-plans` | `/api/planos-tratamento` *(plus shape)* |
| `/api/matching/results/:id` | `/api/matching/buscar/:id` *(EN→PT word swap, same intent)* |
| `/api/salas`, `/api/salas/reservas` | *(no frontend caller surveyed — orphan)* |

The backend is **mostly English** (30 of 38 routers); the 8 Portuguese routers are the outliers (`alertas-crise`, `diario`, `evolucao`, `humor`, `planos-tratamento`, `recibos`, `salas`, `tarefas` — `anamnese` kept aside as medically shared EN/PT term). Default recommendation: **rename the 8 PT backend routes to EN** to align with the majority and the frontend. Blast radius is contained — no external API consumers per `§4 scope > Out of scope`. Surfaced in §7 design batch (Q9).

**Pattern B — Admin namespace not split out (~6 calls).** Frontend assumes `/api/admin/*` for admin-scoped operations on shared resources; backend exposes those resources at their canonical paths and gates by role. Specifically:

| Frontend call | Backend reality |
|---|---|
| `GET /api/admin/reports`, `PATCH /api/admin/reports/:id` | `GET /api/support/reports`, `PATCH /api/support/reports/:id` |
| `GET /api/admin/reviews/flagged` | `GET /api/reviews/...` (no flagged-filter endpoint; dedicated flagged listing is missing) |
| `POST /api/admin/reviews/:id/{dismiss,hide}` | no equivalent (dismiss/hide moderation actions absent) |
| `GET /api/admin/blocks` | no equivalent |
| `GET /api/admin/support/conversations` | `GET /api/support/conversations` (admin role can read) |

**Pattern C — Admin detail endpoints missing (~3 calls × 3 resources = 9 calls).** Lists exist at `/api/admin/{therapists,clinics,patients}`; details (`/api/admin/.../:id`) all 404. Canonical detail endpoints DO exist at `/api/{therapists,clinics,patients}/:id` — admin pages can use those with role-gated authorization.

**Pattern D — Role-prefix paths in direct-fetch pages (4 calls).** Four pages use `useQuery` directly with `/api/{role}/*` URLs that have no backend mapping:

| Page | Direct fetch | Should route through |
|---|---|---|
| `pages/therapist/Patients.tsx` | `GET /api/therapist/patients` | hook over `GET /api/patients` (role-filtered) |
| `pages/therapist/Reviews.tsx` | `GET /api/therapist/reviews` | hook over `GET /api/reviews/therapist/:id` (or new aggregate) |
| `pages/clinic/Therapists.tsx` | `GET /api/clinic/therapists` | hook over `GET /api/clinics/:id/therapists` |
| `pages/clinic/Patients.tsx` | `GET /api/clinic/patients` | hook over `GET /api/patients` (role-filtered) |

**Pattern E — Implicit DTO contract.** **Zero of 193 backend routes declare `response_model`.** All shapes flow through `success_response(data)` / `paginated_response(data, page, …)` / `ok_response()` wrappers. Frontend `types/` carries the de-facto contract; the existing 38-file router test suite catches drift. Adding `response_model=PydanticDTO` across all 193 routes is a substantial sub-project. Default recommendation in §7 design batch: **defer to a follow-up project (`therapy-platform-dto-contract`); accept-with-rationale for this project**, with the gap table + tests as the operational contract.

**Pattern F — `require_role` recurrence inside this product (N=2 local + 1 seed = N=3).** Seed-lib carries a role-guard at `noctusai_lib.api.auth` (Phase 1 audit found the original `require_role` was broken — replaced with a `make_require_role(get_current_user, get_user_role)` factory matching the existing `make_get_current_user` pattern). Product has TWO local re-implementations:
- `app/dependencies.py:55` — `def require_role(*allowed_roles: str)` — used widely (admin, settings, others).
- `app/routers/settings.py:42` — `def _require_role(user, *allowed_roles: str)` — settings-only.

Per recurrence rule + absorption-search standing duty: **must formalize** = the seed will own the helper. Phase 1 absorbs both into `noctusai_lib.api.auth.make_require_role` (each product binds it once in `dependencies.py` as `require_role = make_require_role(get_current_user, get_user_role)`). No design Q.

**Pattern G — Path-shape mismatches inside the EN/PT cluster.** Independently of language, several frontend↔backend pairs disagree on URL shape:
- frontend `/api/clinical/anamnese/:id` vs. backend `/api/anamnese/paciente/:id` (different param semantics)
- frontend `/api/clinical/evolution-notes` (flat list) vs. backend `/api/evolucao/paciente/:id` (per-patient only)
- frontend `/api/matching/embed` (single endpoint) vs. backend `/api/matching/embed-{terapeuta,paciente}` (split by role)
- frontend `/api/settings/platform/ai-prompts/:type/history` vs. backend `/api/settings/platform/ai-prompts/history` (no `:type` segment)

These rename **with** the EN/PT alignment in Phase 3.

#### 5.4.3 Per-hook gap inventory

Format: `✅` = wired correctly; `❌` = gap (with status code + cause); empty hook entries omitted. Status codes: `404` (no backend route), `405` (verb mismatch), `path` (Pattern A/G — needs path-rename), `verb` (verb-only mismatch), `needs-audit` (shape unclear without test run).

**`hooks/useAdmin.ts` — admin (consumed by `pages/admin/*`)**
- ✅ OK: `GET /api/admin/{therapists,clinics,patients}`, `GET /api/admin/pending`, `POST /api/admin/approve/:type/:id`, `POST /api/admin/reject/:type/:id`
- ❌ 404: `GET /api/admin/dashboard`, `GET /api/admin/appointments`, `POST /api/admin/suspend/:type/:id`
- ❌ 404 (Pattern C — detail endpoints): `GET /api/admin/{therapists,clinics,patients}/:id`
- ❌ 404 (Pattern B — admin namespace): `GET /api/admin/reports`, `POST /api/admin/reports/:id/resolve`, `GET /api/admin/blocks`, `GET /api/admin/reviews/flagged`, `POST /api/admin/reviews/:id/{dismiss,hide}`, `GET /api/admin/support/conversations`

**`hooks/useAdminFinancials.ts` — admin**
- ✅ OK: `GET /api/admin/financials/wallets`, `GET /api/admin/financials/payouts`, `POST /api/admin/financials/payouts/:id/process`, `POST /api/admin/financials/commissions`
- ❌ 404 (known regressions): `GET /api/admin/financials/{summary,transactions}`, `DELETE /api/admin/financials/commissions/:id`
- ❌ 405 (known regression): `GET /api/admin/financials/commissions` *(only POST exists)*

**`hooks/useAppointments.ts` — multi:therapist+patient+clinic** — ✅ all 4 routes wired

**`hooks/useAvailability.ts` — therapist** — ✅ all 6 routes wired

**`hooks/useBi.ts` — therapist** — ✅ all 4 routes wired

**`hooks/useClinicalRecords.ts` — therapist**
- ❌ path (Pattern A + G): all 7 calls miss — `GET/POST/PATCH /api/clinical/anamnese*`, `GET/POST /api/clinical/treatment-plans`, `GET/POST /api/clinical/evolution-notes`. Backend at `/api/anamnese`, `/api/planos-tratamento`, `/api/evolucao` with different shapes.

**`hooks/useClinicFinancials.ts` — clinic** — ✅ all 3 routes wired

**`hooks/useConsents.ts` — therapist** — ✅ all 3 routes wired

**`hooks/useConversations.ts` — multi** — ✅ all 5 routes wired

**`hooks/useCrisis.ts` — therapist**
- ❌ path (Pattern A): `GET /api/crisis-alerts`, `POST /api/crisis-alerts/:id/review` → backend at `/api/alertas-crise` with `revisar`

**`hooks/useDiary.ts` — patient**
- ❌ path (Pattern A): all 4 calls (`GET/POST /api/diary`, `PATCH/DELETE /api/diary/:id`) → backend `/api/diario`

**`hooks/useHomework.ts` — multi:therapist+patient**
- ❌ path (Pattern A): all 4 calls → backend `/api/tarefas`

**`hooks/useInvoices.ts` — patient**
- ❌ path (Pattern A): `GET /api/invoices` → `/api/recibos`; `POST /api/invoices` → `POST /api/recibos/gerar` *(Pattern G shape too)*

**`hooks/useJournal.ts` — therapist** — ✅ all 11 routes wired

**`hooks/useLongitudinal.ts` — therapist** — ✅ all 4 routes wired

**`hooks/useMessages.ts` — multi** — ✅ all 8 routes wired (incl. `POST /api/attachments/upload` direct-fetch with custom token-refresh)

**`hooks/useMood.ts` — patient**
- ❌ path (Pattern A): all 3 calls → backend `/api/humor`

**`hooks/usePatientReviews.ts` — patient**
- ❌ 404: `GET /api/patient/reviews` (no equivalent — backend has `/api/reviews/{therapist,clinic}/:id` indexed the other way)
- ❌ 404: `DELETE /api/patient/reviews/:id` (no equivalent)
- ❌ path: `PATCH /api/patient/reviews/:id` → backend `PATCH /api/reviews/:id`

**`hooks/usePayments.ts` — patient** — ✅ all 4 routes wired

**`hooks/useRecurring.ts` — multi** — ✅ all 10 routes wired

**`hooks/useRefunds.ts` — patient** — ✅ all 3 routes wired

**`hooks/useSessions.ts` — multi** — ✅ all 8 routes wired

**`hooks/useSettings.ts` — multi** — ✅ 10/11 wired
- ❌ path (Pattern G): `GET /api/settings/platform/ai-prompts/:type/history` → backend `/api/settings/platform/ai-prompts/history` (no `:type` segment)

**`hooks/useTherapyMatching.ts` — patient**
- ❌ path (Pattern A): `GET /api/matching/results/:id` → `/api/matching/buscar/:id`
- ❌ 404 + shape: `POST /api/matching/embed` → backend has `/api/matching/embed-{terapeuta,paciente}` (split-by-role)

**`hooks/useTransactions.ts` — multi** — ✅ both routes wired

**`hooks/useWallet.ts` — multi** — ✅ all 4 routes wired

**Pages with direct fetch (Pattern D):** 4 calls in `pages/{therapist,clinic}/{Patients,Reviews,Therapists}.tsx`, all 404. Plan: extract to hooks during the relevant role-portal phase.

#### 5.4.4 Backend orphans (no surveyed frontend caller)

These backend routes have no frontend hook caller in the inventory. Some are consumed by un-surveyed pages (auth pages, public directory pages, AcceptInvite, PrivacyPolicy, Session room) and need a targeted page-walk during the public/auth Phase 9. Status `needs-audit` until then.

- `auth.py` — `POST /api/auth/{register/patient,register/therapist,register/clinic,login,google,forgot-password}`, `GET /api/auth/me` *(consumed by `Login.tsx` / `Register.tsx` / `ForgotPassword.tsx` / `SSOCallback.tsx` / `AcceptInvite.tsx` — Phase 9)*
- `attachments.py` — `GET /api/attachments/signed-url` *(consumed by Session.tsx or similar — needs Phase 6/7 audit)*
- `clinics.py` — `GET /api/clinics`, `GET /api/clinics/{settings,:id,:id/therapists}`, `PATCH /api/clinics/{settings,:id}`, `GET/PATCH /api/clinics/therapists/:id/config`, `POST /api/clinics/:id/invite` *(consumed by `ClinicDirectory.tsx`, `ClinicProfile.tsx`, clinic settings pages — Phase 6/8/9)*
- `invitations.py` — all 5 routes *(consumed by `AcceptInvite.tsx` and admin invitation flows — Phase 9)*
- `lgpd.py` — `POST /api/lgpd/{delete-my-data,delete-data/:type/:id,run-audio-retention}` *(consumed by patient settings + admin LGPD pages — Phase 7/2)*
- `reviews.py` — `POST /api/reviews`, `PATCH /api/reviews/:id`, `GET /api/reviews/{therapist,clinic}/:id`, `POST /api/reviews/clinic`, `POST /api/reviews/:id/{respond,flag}` *(consumed by `TherapistProfile.tsx`, `ClinicProfile.tsx`, therapist Reviews page — Phase 6/9)*
- `rooms.py` — all 5 routes *(consumed by clinic rooms management — Phase 8)*
- `support.py` — all 5 routes *(consumed by admin Support page + therapist/patient support — Phase 2 admin facade decision)*
- `therapists.py` — `GET /api/therapists`, `GET /api/therapists/:id`, `PATCH /api/therapists/:id` *(consumed by `TherapistDirectory.tsx`, `TherapistProfile.tsx`, therapist self-edit — Phase 6/9)*
- `patients.py` — `GET /api/patients`, `GET /api/patients/:id`, `PATCH /api/patients/:id` *(consumed via Pattern D direct-fetch in therapist/clinic pages — Phase 6/8 reroute)*
- `whatsapp_therapy.py` — all 5 routes *(consumed by therapist WhatsApp settings — Phase 6 audit)*
- `admin.py` — `POST /api/admin/{commissions,assign-patient}` *(orphan in hooks/, consumed by `pages/admin/{Financials,Patients}.tsx` direct? — Phase 2 audit)*

#### 5.4.5 Migration column gap

| Table | Missing columns | Code references | Target migration |
|---|---|---|---|
| `therapy.therapist_profiles` | `rejection_reason`, `rejected_at`, `rejected_by` | `admin_service.py:88,247,331` | `010_rejection_audit.sql` (Phase 5) |
| `therapy.clinics` | `rejection_reason`, `rejected_at`, `rejected_by` | **same code path** at `admin_service.py:84-92` runs against `clinics` when `entity_type="clinic"` — would fail with `undefined_column` if exercised; the empty-Rejected-tab hack at `:331-334` masks the throw | `010_rejection_audit.sql` (Phase 5) — **both tables** per §5.2 spec |

Verified absent in migrations 001–009. Migration 010 is the next free slot. **No other column gaps surfaced** across 44 tables and ~500+ column references in `app/services/*.py`.

#### 5.4.6 Should-use-seed candidates

Already widely adopted: `noctusai_lib.primitives.{responses,exceptions}`, `api.{middleware,scheduler,auth.{first_or_none,resolve_sso_role}}`, `domain.{action_log,ai,invitations}`, `integrations.{llm,email}`, `testing.*`, `logging_config`. Concrete absorption opportunities surfaced this Phase 0:

| Local helper | Replace with | Phase |
|---|---|---|
| `app/dependencies.py:55` `require_role()` (~product-wide use) | `noctusai_lib.api.auth.make_require_role` (factory; bound locally as `require_role = make_require_role(get_current_user, get_user_role)`) | Phase 1 (with identity resolver absorption) |
| `app/routers/settings.py:42` `_require_role(user, *roles)` (settings-local) | `Depends(require_role(...))` via the bound factory above | Phase 1 |
| `app/services/admin_service.py:252` `_fetch_user_identity(db, user_id)` (singular) | `noctusai_lib.integrations.supabase_identity.fetch_user_identities` *(bulk variant Phase 1 builds — covers this case via single-key)* | Phase 1 |

Pagination DTO (`{data, pagination: {page, page_size, total, total_pages}}`) — invent locally first per §5.3, propose for seed at Phase 3 close. Confirmed absent from `noctusai_lib.api/`.

#### 5.4.7 Deletion-candidate batch *(Q3 user decision: surface at end-of-Phase-0, one-line rationale per page, user approves/rejects in one sweep)*

**No deletion candidates surfaced.** Every admin / role page maps either to wired endpoints or to a gap row in §5.4.3 that this project's scope is to fix:

- `pages/admin/{Therapists,Clinics,Patients,Settings,Refunds,AIPrompts}.tsx` — wired ✅
- `pages/admin/{Appointments,Financials}.tsx` — known regressions, Phase 2 fixes
- `pages/admin/{TherapistDetail,ClinicDetail,PatientDetail}.tsx` — Pattern C, Phase 3 reroute
- `pages/admin/{Reviews,Moderation,Support,Dashboard}.tsx` — Pattern B, Phase 2/3 admin-facade work
- `pages/{therapist,patient,clinic}/*` — covered by Phases 6-8

If user has pages they actively want deleted (rather than wired), surface them in §7 Q-NEW-DEL.

#### 5.4.8 Test coverage

- 38 router test files (one per router) at `backend/tests/routers/test_*_router.py` ✅ — keeps DTO drift caught.
- Edge cases at `tests/edge_cases/` (data integrity, financial, messaging, scheduling, security, session_audio_segments_schema, session_lifecycle).
- Integration at `tests/integration/{test_e2e_flows,test_rls_clinical_privacy}.py`.
- Service tests at `tests/services/test_*.py`.
- ~~**Orphan finding:**~~ `tests/routers/test_notificacoes_router.py` was flagged as orphan but **resolved 2026-05-03 (false alarm)**: the router IS mounted, but by the `noctusai_seed` framework (cross-product notifications, seed-provided), not by the product `app/routers/*.py` tree. The test patches `noctusai_seed.database.DatabaseModule.{get_client,get_core_client,get_admin_client}` and exercises the seed-mounted `/api/notificacoes` endpoint. Test passes. **§5.4.8 caveat:** the inventory walks product routers only; seed-framework-mounted endpoints (notifications + any future cross-product seam) require a separate enumeration pass.

**Status discipline:** every phase that changes a router's response shape MUST keep that router's test file green. A phase ✅ requires the router's test file passes; new routes ship with new tests in the same phase per `KB § PATTERNS/testing.md`.

#### 5.4.9 Keeper review pass

`/Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python mcp/noctusai/cli.py --review --product therapy-platform` (run 2026-05-03):
- **Mode:** agent
- **Issues found:** 0
- **Proposals filed:** 0
- Result: clean keeper bill of health on therapy-platform — no compliance issues detected. The gap table above is the agent-authored signal for this project.

---

## 6. Implementation phases

Phases are **suggestive, not strict.** Reorder, split, merge, or discover new phases as work progresses. Phases 6-9 in particular are placeholders whose shape is decided by Phase 0's output.

**Phase status-icon convention** (see `CONTEXT/PATTERNS/project-execution.md §1`):

| Icon | Meaning |
|---|---|
| _(none)_ | Pending — not started |
| ⏳ | In progress / partially done |
| ✅ | Complete — every sub-task ticked |
| ❌ | Blocked or failed — see Change Log |

**Improvement capture happens during steps. Proposal authoring happens at end of phase.** One bundled proposal per phase, filed via `noctus.dev.file_proposal(project="therapy-platform-wiring", …)` → lands in `products/therapy-platform/projects/therapy-platform-wiring/proposals/`.

---

### Phase 0 — Discovery & inventory ✅ *(2026-05-03)*

Produces the concrete gap table in §5.4. Every subsequent phase references rows from this table — no phantom scope.

- [x] Enumerate every `api.get|post|put|patch|delete` call in `products/therapy-platform/frontend/src/hooks/` and `.../src/pages/`. Capture: URL, HTTP verb, caller hook/page, role-tag (admin/therapist/patient/clinic/public — derived from page-tree placement), expected response shape (from `types/`).
- [x] Enumerate every route decorator (`@router.get|post|put|patch|delete`) across **all 38 router files** in `products/therapy-platform/backend/app/routers/*.py` (corrected count: handoff said 39 but counted `__init__.py`; actual router count is 38). Capture: URL, HTTP verb, response shape (return value + `response_model` if set). Found: 193 routes total; **0/38 routers declare `response_model`** — all returns flow through `success_response()` / `paginated_response()` / `ok_response()` wrappers (Pattern E in §5.4.2).
- [x] Join the two lists → produce the **per-router gap table with role-tags** in §5.4. Status values populated: `OK`, `404`, `405`, `path` (Pattern A/G), `verb`, `needs-audit`. ~58 gap rows surfaced; Patterns A-G captured in §5.4.2.
- [x] Cross-reference every reference in services to a DB column against `products/therapy-platform/backend/migrations/001..009.sql`. Findings in §5.4.5: only `rejection_reason / rejected_at / rejected_by` missing — on **both** `therapist_profiles` AND `clinics` (the same `admin_service.py:84-92` reject path runs against either table; the empty-Rejected-tab hack at `:331-334` masks the second case). Migration 010 is the next free slot. **No other column gaps surfaced** across 44 tables / 500+ column references.
- [x] **Cross-cutting absorption check** vs. `seed/lib/backend/noctusai_lib/{primitives,config,testing,integrations,domain,api,security}/`. Findings in §5.4.6 — N=2 local `require_role` re-implementations duplicate the seed role-guard at `noctusai_lib.api.auth` (Phase 1 absorbs both via `make_require_role` factory; the original `require_role` was found broken and retired — see Phase 1 entry in §11); single-key `_fetch_user_identity` is the Phase-1 bulk-resolver-of-1 case.
- [x] Run keeper review pass — `/Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python mcp/noctusai/cli.py --review --product therapy-platform`. **0 issues, 0 proposals filed.** Captured in §5.4.9. *(Note: original sub-task said `cli.py --review products/therapy-platform` as a positional; actual CLI signature is `--review --product PRODUCT`. Sub-task corrected here.)*
- [x] **Rewrote Phases 2-9 below** based on the gap table. Phases 6-9 promoted from placeholders to concrete sub-tasks rooted in §5.4.3 per-hook gap rows + §5.4.4 backend orphans. **Deletion-candidate batch: empty** (per §5.4.7) — surfaced to user with one-line rationale per page; user approves/rejects in one sweep before Phase 1.
- [x] Log Phase 0 completion in §11.

**Deliverable produced:** §5.4 populated (5.4.1 counts → 5.4.9 keeper); phases 2-9 carry concrete work items rooted in §5.4.3 rows; design-batch surfaced in §7 (6 questions) for user sign-off before Phase 1 kickoff.

#### Phase 0 → §7 design-batch handoff

Six design questions surfaced from systemic findings (§5.4.2). All carry default recommendations; surface as one batch to user before Phase 1.
- §7 Q9 — Pattern A EN/PT alignment (rename 7 PT backend routers to EN). Default rec: **rename**.
- §7 Q10 — Pattern B admin namespace (admin facade vs. role-gated cross-resource). Default rec: **role-gated cross-resource for shared, keep `/api/admin/*` for admin-only operations**.
- §7 Q11 — Pattern C admin detail endpoints (refactor frontend to canonical `/api/{resource}/:id` paths). Default rec: **frontend-only refactor, no new admin detail routes**.
- §7 Q12 — Pattern D direct-fetch role-prefix pages (extract to hooks). Default rec: **extract to hooks during Phases 6/8**.
- §7 Q13 — Pattern E DTO contract (`response_model` rollout). Default rec: **defer to follow-up project `therapy-platform-dto-contract`; accept-with-rationale for this project**.
- §7 Q14 — Pattern F `require_role` consolidation. *No design Q* — Phase 1 absorbs into seed-lib via `make_require_role` factory, retire 2 local copies.

**Improvements:** none filed as a separate proposal. Captured inline in §5.4.2 Patterns A-G — the gap table itself is the Phase 0 artifact. Per `feedback_apply_inline_delete_proposals` and `feedback_auto_improvement` — improvements applied inline beat filed-then-deleted.

---

### Phase 1 — Shared identity resolver in `noctusai_lib.integrations.supabase_identity` ✅ *(2026-05-03)*

Seed absorption for the "I need `nome`/`email` from `auth.users` given a list of UUIDs" pattern. The ad-hoc admin-therapists fix (landed 2026-04-20 in `products/therapy-platform/backend/app/services/admin_service.py::_fetch_user_identity`, lines 252-282) was this phase's starting point — Phase 1 replaced it with the seed helper. **Plus Pattern F absorption:** factory-pattern fix for the broken seed `require_role` so products can use `make_require_role(get_current_user, get_user_role)` from seed-lib instead of re-implementing locally.

- [x] Design decided: **option (b) sequential get_user_by_id loop** — sync `def`, not `async def`. Rationale: supabase-py admin SDK is sync; wrapping in `async def` blocks event loop without yielding. Sequential at 10-100 IDs is well under 1s on the request path. Callers needing concurrency wrap with `asyncio.to_thread(...)`. Benchmarking deferred — current admin pages render fast enough; revisit if a slow page surfaces. *(§7 Q2 default rec.)*
- [x] Implemented `UserIdentity` dataclass + `fetch_user_identities()` + `fetch_user_identity()` (singular) at `seed/lib/backend/noctusai_lib/integrations/supabase_identity.py`. **Did NOT re-export from `integrations/__init__.py`** — followed the existing pattern used by sibling single-file integrations (`database.py`, `redis.py`); callers import from sub-module directly. Sub-package integrations like `email/`, `whatsapp/`, `vista/` re-export from their own `__init__.py`, but flat single-file integrations don't. Original Phase 1 sub-task said "re-export from `integrations/__init__.py`" — that instruction was based on the spec, not the existing repo pattern; deviated for consistency.
- [x] Unit tests at `seed/lib/backend/tests/integrations/test_supabase_identity.py` — **20 tests, 100% pass**. Coverage: happy path × full metadata, full_name alias for nome, avatar_url alias for foto_url, missing metadata, lookup error → empty shape, no_user response → empty shape, empty input, duplicate IDs deduplicated, falsy IDs skipped, non-string metadata coerced, non-string nome coerced, non-string foto_url null'd, single-user wrapper variants × 4. No `monkeypatch.setattr` of `our_module` — used `_FakeAdminAuth` / `_FakeClient` test doubles per `feedback_no_monkeypatching_in_tests`.
- [x] Updated `KNOWLEDGE-BASE/CONTEXT/04-SHARED-LIBRARY.md`:
  - New section `integrations/supabase_identity.py` with symbol table + sync-vs-async note + canonical usage example.
  - Updated `auth.py` table row: retired the broken `require_role` entry, added `make_require_role` (factory pattern matching `make_get_current_user`).
- [x] Replaced `admin_service.py::_fetch_user_identity` (32 lines deleted) with seed helper. **Bonus optimization:** the call site in `list_therapists_for_admin` was N+1 (one auth lookup per row in a loop). Refactored to bulk pre-fetch via `fetch_user_identities(db, user_ids)` then iterate the result map. `_therapist_row_to_dto` signature changed `identity: Dict[str, str]` → `identity: UserIdentity`; foto_url falls back from `UserIdentity.foto_url` to `row.get("photo_url")` so existing avatars keep rendering.
- [x] **Pattern F absorption (Q14 from §7).** Discovered the seed `require_role(get_user_role_fn, *roles)` was BROKEN (line 195 passed `_get_supabase_client=None` blindly → RuntimeError on first use; comment "overridden by product wrapper" was misleading — no override existed). Verified zero callers in the entire monorepo (only seed's docstring referenced it). **Replaced with factory pattern `make_require_role(get_current_user_fn, get_user_role_fn)`** matching the existing `make_get_current_user` shape. Product `dependencies.py` switched from local require_role implementation (lines 55-74, also dead code — no router imports it; admin routers use inline role-checking) to `require_role = make_require_role(get_current_user, get_user_role)`. **6 new seed-lib tests** for `make_require_role` (allows / multi-allows / rejects / propagates 401 / distinct deps per role-set / lists all allowed roles in 403 detail) — all pass.
- [x] **Re-ran tests.** `tests/routers/test_admin_router.py`: 38/38 ✅. Full `products/therapy-platform/backend/tests/`: **1143 passed, 0 failures**. `seed/lib/backend/tests/`: **448 passed, 0 failures** (includes 20 new identity tests + 6 new make_require_role tests). Frontend `npx vite build`: ✅ clean.
- [x] **Keeper review** post-change: `cli.py --review --product therapy-platform` → 0 issues, 0 proposals. KB sync: `bash scripts/verify-kb-sync.sh` → all pointers resolve, all KB docs indexed.
- [x] **Improvements captured inline (no separate proposal file per `feedback_apply_inline_delete_proposals`):**
  - **Seed-lib bug fix bonus:** broken `require_role` was upstream dead-code waiting to bite. Replaced with working factory; future products avoid the trap.
  - **N+1 → bulk:** `list_therapists_for_admin` was N+1; now does one bulk identity fetch. Same shape applies to upcoming admin list endpoints in Phase 2/3 (clinics, patients, appointments) — pre-fetch identities before the loop.
  - **Inline `_require_role` in `routers/settings.py:42` is signature-different** (takes `user`, returns `user.id`) and isn't a Depends-pattern factory. Different shape from `dependencies.py` `require_role`; refactoring to Depends-pattern requires changing 7 endpoint signatures in settings.py. **Deferred to Phase 4 (scaffolding-debt sweep).** Logged as a Phase 4 sub-task in the §11 Phase 1 entry.
  - **Settings.py:34 `_require_admin(user)` is the same shape as `_require_role(user, *roles)` — second helper to fold into Phase 4 Depends-pattern refactor.

---

### Phase 2 — Admin Tier A: known regressions ✅ *(2026-05-10)*

Fix every `404` and `405` row in the gap table. At minimum we already know:

- `GET /api/admin/appointments` — missing entirely (Appointments page).
- `GET /api/admin/financials/summary` — missing.
- `GET /api/admin/financials/transactions` — missing.
- `GET /api/admin/financials/commissions` — wrong verb (only POST exists).
- `DELETE /api/admin/financials/commissions/{id}` — missing.
- Any other rows Phase 0 classified `404` or `405`.

- [x] For each missing/wrong-verb endpoint: implement in `app/routers/*.py`, add a service-layer function in `app/services/*.py` (use the Phase 1 identity resolver for any display-name needs), return the DTO the frontend expects.
  - `admin.py`: `GET /api/admin/appointments`, `GET /api/admin/dashboard`, `POST /api/admin/suspend/{type}/{id}`.
  - `admin_financials.py`: `GET /api/admin/financials/summary`, `GET /api/admin/financials/transactions`, `GET /api/admin/financials/commissions`, `DELETE /api/admin/financials/commissions/{id}`. The existing `POST /api/admin/financials/commissions` now accepts BOTH the new frontend shape (`{global_rate_pct?, override?:{entity_type, entity_id, rate_pct}}`) and the legacy `{target_type, target_id, custom_commission_pct}` shape — `CommissionConfigRequest.model_post_init` normalizes legacy into `override` so existing tooling keeps working.
- [x] For Appointments: the DTO needs `patient_name`, `therapist_name`, `clinic_name` — Phase 1 resolver handles the first two; `clinic_name` joins `therapy.clinics`. Implemented in `admin_service.list_appointments_for_admin` with bulk `fetch_user_identities` + a new `_resolve_clinic_names` helper that does ONE `clinics.in_("id", …)` lookup per page (no N+1).
- [x] For Financials: `/summary` aggregates live — sums captured-transaction `gross_amount` + `platform_fee_amount` and `payouts.net_amount/amount` partitioned by `status`. Shape matches `AdminFinancialSummary` in `frontend/src/types/financial.ts`. No materialized view needed; the page reloads every 2 minutes (hook `staleTime`) so live aggregation is fine until volumes grow.
- [x] Router tests for every new/updated endpoint — status code + shape + auth boundary (admin vs. therapist vs. patient vs. unauthed). **37 new router tests** added across `tests/routers/test_admin_router.py` (`TestAdminAppointments`, `TestAdminDashboard`, `TestSuspendEntity`) and `tests/routers/test_admin_financials_router.py` (`TestFinancialSummary`, `TestListAllTransactions`, `TestGetCommissionConfig`, `TestSetCommissionConfig`, `TestDeleteCommissionOverride`).
- [x] Service unit tests for the non-trivial aggregation logic (`/summary` math, `/commissions` GET shape). New file `tests/services/test_admin_service.py` — 8 cases covering `list_appointments_for_admin` (DTO shape, null clinic_id, empty result), `admin_dashboard_metrics` (shape + revenue math), `suspend_entity` (success, invalid type, 404).
- [x] Wired the static `pages/admin/Dashboard.tsx` to the new `useAdminDashboard()` hook — page now renders live counts + revenue from `/api/admin/dashboard`.
- [ ] Manual QA: navigate `/admin/agendamentos` and `/admin/financeiro` in the browser; confirm zero toasts, data renders. *(Deferred to user — deploy drill required.)*
- [x] Run `python mcp/noctusai/cli.py --review --product therapy-platform` → **0 issues, 0 proposals**.
- [x] Capture **Improvements** (see §11 Phase 2 entry).

**Verification (2026-05-10):**
- `pytest tests/` from `products/therapy-platform/backend/`: **1212 passed, 14 skipped, 10 failed**. The 10 failures are pre-existing baseline noise (Supabase real-client constructed when SUPABASE_URL is unset in the local venv — same 10 fail on a fresh checkout of `main` before any Phase 2 work; documented in findings). Phase-2 surface: 45 new tests added, all green; the admin/admin_financials test files run 98/98 in isolation.
- `python mcp/noctusai/cli.py --review --product therapy-platform`: 0 issues, 0 proposals.
- `npx vite build` from `products/therapy-platform/frontend/`: clean (440 modules, 595 KB main chunk, 8.8s).

**Improvements / follow-ups (filed live during Phase 2):**
1. `admin_service.set_commission_override` (line ~135) writes to a `commission_overrides` table — but the migration creates `platform_commission_overrides`. The orphan POST `/api/admin/commissions` (Pattern G in §5.4.4) was already flagged for Phase 2 audit; the table name there is wrong. **Triage: refactor** — needs `commission_overrides` → `platform_commission_overrides` and `set_by` → `set_by_admin_id`. Deferred to Phase 4 (scaffolding-debt sweep) because the orphan endpoint is not consumed by any frontend hook surveyed in Phase 0; fixing the misnamed table can happen alongside the broader Phase 4 audit without blocking Phase 2 closure.
2. `MockSupabaseClient` does NOT apply `.eq()` / `.gte()` / `.lte()` predicates on SELECT reads — only on UPDATE/DELETE. This is documented behavior, but it's an N=2+ slip risk for service tests that assume aggregation filters work. *Suggested upstream:* either expose a `MockSelectBuilder._do_execute_with_predicates` opt-in or document the limitation prominently in `noctusai_lib/testing/__init__.py`. Triage: accept-with-rationale (production code's `.eq()` is still on the wire; tests just need to seed only the rows that match the production filter).

---

### Phase 3 — Admin Tier B: DTO normalization sweep

For every admin list endpoint the frontend calls, return the typed DTO. Raw DB rows do not cross the boundary.

At minimum: `/api/admin/clinics`, `/api/admin/patients`, `/api/admin/reports`, `/api/admin/reviews/flagged`, `/api/admin/blocks`, `/api/admin/support/conversations`. Phase 0 confirms the full list.

- [ ] For each endpoint: add/update a `_row_to_dto` mapper. Mirror the shape declared in `products/therapy-platform/frontend/src/types/`.
- [ ] Use Phase 1 identity resolver for every column where the DTO demands a display name/email that lives in `auth.users`.
- [ ] Accept the query filter the frontend already sends (status, busca, date ranges). Translate to DB predicates at the service layer.
- [ ] Add/update router tests per endpoint — auth boundary + happy path + one filter combination.
- [ ] Add/update service unit tests per mapper — covers the DTO contract directly without touching HTTP.
- [ ] Manual QA: walk each admin page, confirm data renders, tabs filter correctly.
- [ ] Run the keeper review pass.
- [ ] **Improvements** + phase proposal before ✅.

---

### Phase 4 — Admin Tier C: pre-existing scaffolding debt ⏳ (2 sub-tasks pre-delivered in Phase 1; 7 remain open)

Everything Phase 0 surfaced that Phases 2-3 didn't fold in. Likely candidates (confirmed by Phase 0):

- [ ] RLS hole audit across `therapy.*` admin-read paths. Compare the "who can select" policies against what the admin endpoints actually read.
- [ ] `search_path` hardening on any RPC that admin endpoints call.
- [ ] Migration drift: any column referenced in code but absent from `migrations/*.sql` that isn't the reject-audit set (that set is Phase 5).
- [ ] Missing admin-side tests — pages that had no router test at all before this project.
- [ ] Any admin endpoint that calls an N+1 pattern we didn't already collapse via Phase 1.
- [ ] `noctus.dev.lgpd_flag` calls on the new endpoints that aggregate personal data in novel shapes.
- [x] **Settings router refactor (Pattern F follow-up from Phase 1).** ✅ *(2026-05-03 — landed early, in same session as Phase 1 per user direction "deliver the deferred work").* `app/routers/settings.py` rewritten: 2 inline helpers (`_require_admin(user)`, `_require_role(user, *roles)`) deleted; 11 endpoints converted from `authorization: Optional[str] = Header(None)` + inline `await get_current_user + _require_X(user)` to `auth=Depends(require_role("..."))`. Imports cleaned (removed `Header`, `Optional`, `get_current_user`, `get_user_role`, `HTTPException` kept for clinic_id check; consolidated 6 inline `from app.dependencies import first_or_none` to a single top-level import). Tests `tests/routers/test_settings_router.py`: **26/26 green.** Full suite: **1143/1143 green.** `vite build`: clean. Same 403 behavior as before.
- [x] **Orphan test audit.** ✅ *(2026-05-03)* — **closed as no-action-needed (false alarm).** `tests/routers/test_notificacoes_router.py` docstring states "The notifications router is now provided by the noctusai_seed framework." It tests a seed-mounted `/api/notificacoes` endpoint via `noctusai_seed.database.DatabaseModule.{get_client,get_core_client,get_admin_client}` patches. Test passes (part of the 1143/1143). My §5.4.8 audit only walked product `app/routers/*.py`, missing seed-framework-mounted routers — false-positive flagging. **Updating §5.4.8** to note that "orphan" was a misread; the seed framework mounts cross-product routers (notifications) that the product test suite verifies.
- [ ] Keeper review + **Improvements** + phase proposal before ✅.

---

### Phase 5 — Reject flow wiring

End-to-end reject. See §3 "Reject flow primer" for the target shape.

- [ ] Confirm the next free migration number at execution time (was `010` as of the 2026-05-03 audit; bump if newer migrations have landed). Write `products/therapy-platform/backend/migrations/0NN_rejection_audit.sql` per §5.2. Commit with the migration file (do NOT apply yet).
- [ ] Apply via `mcp__claude_ai_Supabase__apply_migration` — migration file and applied state stay in lockstep.
- [ ] Update `reject_entity()` service: write `rejection_reason`, `rejected_at = now()`, `rejected_by = admin_id`. Idempotent re-reject.
- [ ] Update `approve_entity()` service: clear the three reject-audit columns on re-approval.
- [ ] Update `_derive_therapist_status()` / `_derive_clinic_status()` mappers (from Phase 1/2): return `rejeitado` when `rejection_reason IS NOT NULL AND is_approved = false`.
- [ ] Update admin list endpoints: `status=rejeitado` resolves to `.eq("is_approved", False).not_.is_("rejection_reason", "null")` — remove the "empty fallback" hack from the ad-hoc fix.
- [ ] Admin detail pages (`/admin/terapeutas/:id`, `/admin/clinicas/:id`): render `rejection_reason`, `rejected_at`, `rejected_by` (resolved to display name via Phase 1).
- [ ] Router tests: pendente→rejeitado with reason, rejeitado→aprovado clears audit columns, aprovado→suspenso→aprovado leaves audit columns clear.
- [ ] Service unit tests for `reject_entity` and `approve_entity` audit-column invariants.
- [ ] Migration idempotency test (re-applying is a no-op).
- [ ] `noctus.dev.lgpd_flag` call: rejection reasons may contain free-text about the applicant — acceptable under Art. 11 only with a retention policy. Flag for LGPD review even if the flag doesn't block.
- [ ] Manual QA: reject a pending therapist in the browser, verify the Rejeitado tab shows them with the reason, re-approve, verify they move back to Aprovado with audit columns cleared.
- [ ] Keeper review + **Improvements** + phase proposal before ✅.

---

### Phase 6 — Therapist portal wiring

Sub-tasks rooted in §5.4.3 therapist-tagged hooks + §5.4.4 backend orphans tagged for therapist consumption. Most therapist-facing hooks are already wired (✅ in §5.4.3); the work concentrates on Pattern-A path renames, Pattern-D direct-fetch extraction, and the therapist-side public-page audit.

- [ ] **6.a Pattern-D direct-fetch extraction (therapist surface).** Extract `pages/therapist/Patients.tsx` (`GET /api/therapist/patients` direct fetch) into a new `hooks/useTherapistPatients.ts` calling `GET /api/patients` with role-filtered query (or new aggregate endpoint if Phase 6.c reveals scope-specific filtering). Same shape for `pages/therapist/Reviews.tsx` (`GET /api/therapist/reviews` → `GET /api/reviews/therapist/:id` via `hooks/useTherapistReviews.ts` or extension to existing review hook).
- [ ] **6.b Pattern-A path renames affecting therapist surface** *(only if §7 Q9 default rec accepted).* Rename backend routes consumed by therapist hooks: `/api/alertas-crise` → `/api/crisis-alerts` (`useCrisis`), `/api/evolucao` → `/api/evolution-notes` (`useClinicalRecords`), `/api/tarefas` → `/api/homework` (`useHomework`), `/api/anamnese` → `/api/anamnese` (kept — anamnesis is medical-EN), with Pattern-G shape fixes. AST-rename via libcst per `KB § PATTERNS/ast.md` — never sed.
- [ ] **6.c Therapist-orphan backend audit.** For each backend route in §5.4.4 tagged "therapist consumer un-surveyed" (`whatsapp_therapy/*`, `availability` therapist-side variants, `attachments/signed-url`, `therapists` self-edit `PATCH /api/therapists/:id`), verify the consuming page (likely `pages/therapist/Settings.tsx`, `pages/therapist/AvailabilitySettings.tsx`, `pages/therapist/ClinicalRecords.tsx`). Confirm wiring or open a sub-row in the gap table.
- [ ] **6.d Therapist hook DTO normalization.** For each therapist-tagged hook flagged ✅ but consuming list endpoints, audit the DTO shape against `frontend/src/types/`. If the existing tests pass, status remains `OK`; if a manual browser walk reveals shape drift, file as `DTO-mismatch` and fix via service-layer mapper.
- [ ] **6.e Tests.** Router test coverage for new therapist-consuming routes (e.g. if Phase 6.b adds aggregate endpoints), DTO mapper unit tests, manual browser QA per `KB § PATTERNS/testing.md`.
- [ ] **6.f Phase-end.** Keeper review (`--review --product therapy-platform`) + `pytest tests/` green + `vite build` green + **Improvements** capture + phase-end proposal *(or `none identified` if nothing surfaced beyond §11)*.

---

### Phase 7 — Patient portal wiring

Sub-tasks rooted in §5.4.3 patient-tagged hooks. The patient surface has the **densest Pattern-A cluster**: `useDiary`, `useMood`, `useHomework`, `useInvoices` are all 100% PT/EN-mismatched, plus `useTherapyMatching` and `usePatientReviews` carry the bulk of the Pattern-A and 404 hits.

- [ ] **7.a Pattern-A path renames affecting patient surface** *(only if §7 Q9 default rec accepted).* Backend renames cascade: `/api/diario` → `/api/diary` (`useDiary` 4 calls), `/api/humor` → `/api/mood` (`useMood` 3 calls), `/api/tarefas` → `/api/homework` (`useHomework` 4 calls), `/api/recibos` → `/api/invoices` (`useInvoices` 1 call + Pattern-G `POST /gerar` shape fix), `/api/matching/buscar/:id` → `/api/matching/results/:id` (`useTherapyMatching`). AST-rename via libcst.
- [ ] **7.b `usePatientReviews` 404 trio.** New backend endpoint `GET /api/reviews/patient/:patient_id` (or `GET /api/patient/reviews` with role-filter from JWT — design call). Mirror shape `{data: PatientReview[], pending: PendingReview[]}` from `frontend/src/types/`. Add `DELETE /api/reviews/:id` (or `/api/patient/reviews/:id`) — backend currently has no review-deletion route. `PATCH /api/patient/reviews/:id` becomes `PATCH /api/reviews/:id` (path rename only).
- [ ] **7.c `useTherapyMatching.useEmbedProfile` 404.** Frontend calls `POST /api/matching/embed` (single endpoint); backend has `POST /api/matching/embed-{terapeuta,paciente}` (split-by-role). Decision: **unify to `POST /api/matching/embed` with `{role}` in body** vs. **frontend dispatches by role**. Default rec — unify backend, deprecate the split. Add a row to §7 Q-internal if user wants the other shape.
- [ ] **7.d Patient-orphan backend audit.** For backend orphans tagged `patient` (lgpd data-subject rights, cross-cutting consents from patient angle), verify consuming pages (likely `pages/patient/Settings.tsx`, `pages/patient/PaymentMethods.tsx`, `pages/patient/Journey.tsx`). Confirm wiring or open sub-row in gap table.
- [ ] **7.e LGPD walkthrough.** Patient is the most LGPD-sensitive surface — every personal-data endpoint (mood, diary, anamnese, longitudinal, payments, invoices) gets an `noctus.dev.lgpd_flag` if the new shape touches PII not previously flagged. Per `feedback_lgpd_first`.
- [ ] **7.f Tests.** Router tests for any new endpoints in 7.b/7.c, DTO mapper tests, manual browser QA.
- [ ] **7.g Phase-end.** Keeper + builds + tests green + **Improvements** + proposal.

---

### Phase 8 — Clinic portal wiring

Sub-tasks rooted in §5.4.3 clinic-tagged hooks. Clinic surface is the **most-wired** of the three role portals: `useClinicFinancials` is fully ✅; the gap is concentrated in 2 direct-fetch pages (Pattern D) + the orphan `clinics.py` endpoints.

- [ ] **8.a Pattern-D direct-fetch extraction (clinic surface).** Extract `pages/clinic/Patients.tsx` (`GET /api/clinic/patients` direct fetch) into `hooks/useClinicPatients.ts` calling `GET /api/patients` with clinic-id filter from JWT. Extract `pages/clinic/Therapists.tsx` (`GET /api/clinic/therapists` direct fetch) into `hooks/useClinicTherapists.ts` calling `GET /api/clinics/:id/therapists` (which already exists per backend inventory).
- [ ] **8.b Clinic-orphan backend audit.** For backend orphans tagged `clinic` (`clinics.py` settings + branding endpoints, `clinics.py` therapist-config endpoints, `rooms.py` full surface, `clinic_financials.py` confirmed wired), verify consuming pages (likely `pages/clinic/{Settings,LLMPreferences}.tsx`, possibly a rooms management page). Confirm wiring or open sub-row.
- [ ] **8.c `dashboard_bi` clinic-side audit.** `useBi.ts` is therapist-tagged in §5.4.3 but the BI dashboard may also feed clinic-admin. Verify whether `pages/clinic/Dashboard.tsx` consumes `/api/bi/*` and whether the role-gating allows clinic-admin to read aggregated clinic data.
- [ ] **8.d Clinic settings / branding DTO normalization.** `useSettings.useClinicBranding` returns `unknown`; type the DTO via `frontend/src/types/` and the backend service mapper. Same for `usePlatformSettings` (admin-consumed).
- [ ] **8.e Tests.** Router tests, DTO tests, manual browser QA for Patients + Therapists + Settings + Dashboard + Financials per role.
- [ ] **8.f Phase-end.** Keeper + builds + tests green + **Improvements** + proposal.

---

### Phase 9 — Public surfaces + auth wiring

Sub-tasks rooted in §5.4.4 backend orphans tagged for `auth.py` + `invitations.py` + `lgpd.py` public-side + the public directory pages (`Login`, `Register`, `ForgotPassword`, `SSOCallback`, `AcceptInvite`, `ClinicDirectory`, `TherapistDirectory`, `Landing`, `PrivacyPolicy`, `TermsOfUse`).

- [ ] **9.a Auth surface walkthrough.** Each `auth.py` endpoint (`POST /api/auth/{register/patient,register/therapist,register/clinic,login,google,forgot-password}`, `GET /api/auth/me`) gets a survey: confirm consuming page, confirm wiring, manual browser QA. Status: `needs-audit` until walked. Special attention to `POST /api/auth/google` (SSO callback shape).
- [ ] **9.b Invitations surface.** `invitations.py` 5 routes (`POST /`, `GET /accept/validate`, `POST /accept`, `GET /`, `DELETE /:id`). Verify `AcceptInvite.tsx` consumes `accept/validate` + `accept` correctly; admin invitation list/cancel hits `GET /` + `DELETE /:id`.
- [ ] **9.c Public directory walkthrough.** `ClinicDirectory.tsx` consumes `GET /api/clinics` + `GET /api/clinics/:id`; `TherapistDirectory.tsx` consumes `GET /api/therapists` + `GET /api/therapists/:id`. Confirm response shape, RLS gating (public-readable subset only), and DTO match.
- [ ] **9.d LGPD public-data-subject endpoints.** `POST /api/lgpd/delete-my-data` is logged-in-only; verify `POST /api/lgpd/delete-data/:type/:id` admin path is gated. Public LGPD pages (`PrivacyPolicy.tsx`, `TermsOfUse.tsx`) are static — no API surface.
- [ ] **9.e Public landing.** `Landing.tsx` — confirm whether it's static or fetches anything (e.g. live therapist count). If static, no work. If fetches, audit endpoint + caching.
- [ ] **9.f SSO callback.** `SSOCallback.tsx` walks the OAuth flow; verify `POST /api/auth/google` returns the JWT + role correctly, and that `resolve_sso_role` + `get_sso_context` (already imported from `noctusai_lib.api.auth`) handle the role correctly.
- [ ] **9.g Tests.** Router tests for new endpoints, integration tests for the auth flows, manual browser QA per public route.
- [ ] **9.h Phase-end.** Keeper + builds + tests green + **Improvements** + proposal.

---

### Phase 10 — End-to-end verification

- [ ] `cd products/therapy-platform/frontend && npx vite build` — clean.
- [ ] `cd products/therapy-platform/backend && python -m pytest tests/ -q` — full suite green.
- [ ] `cd seed/lib/backend && python -m pytest tests/` — seed tests green (identity resolver, anything else Phase 1 touched).
- [ ] `cd mcp/noctusai && python -m pytest tests/` — MCP toolkit tests green.
- [ ] `python mcp/noctusai/cli.py --review products/therapy-platform` — final keeper pass; triage any remaining proposals.
- [ ] Manual browser QA of the golden path per surface: admin, therapist, patient, clinic, public. Record any regressions in §11 and either fix inline or open a follow-up project.
- [ ] Update `products/therapy-platform/MASTER-PROMPT.md` with any contract changes (new shared helpers, new DTO conventions, reject-flow semantics).
- [ ] Update `KNOWLEDGE-BASE/CONTEXT/backend/06-THERAPY.md` and `frontend/04-THERAPY.md` to reflect current state.
- [ ] Run `python scripts/update-kb-counts.py` and `bash scripts/verify-kb-sync.sh`.
- [ ] Final **Improvements** block + phase proposal + Change Log entry before ✅.

---

## 7. Open questions

Unresolved items. Each tagged with *when it needs an answer* and *who answers*.

1. ~~**Should `rejection_reason` be retained after re-approval?**~~ *(Phase 5.)* — **DECIDED 2026-05-03 (parent-batch Phase 3.a §7 round):** No — clear `rejection_reason` on re-approval; audit trail lives in logs. User quote: *"yes"* (confirmed default). Re-approval reverses the rejection; retaining the reason on the live row creates ambiguity. Decided by: user.
2. **`fetch_user_identities` implementation choice — list_users walk vs. parallel get_user_by_id vs. direct `auth.users` SELECT?** *(Phase 1.)* — Decide by benchmarking on a realistic page (100 IDs). User confirmed 2026-05-03: *"go on with recommendations"*. Decided by: Claude during Phase 1, with the chosen implementation + benchmark numbers logged in the Phase 1 Improvements block.
3. ~~**Does Phase 0 discover any admin page that should simply be deleted rather than wired?**~~ *(Phase 0.)* — **DECIDED 2026-05-03 (parent-batch Phase 3.a §7 round):** Surface deletion candidates as a batch at end-of-Phase-0 with a one-line rationale per page; user approves/rejects in one sweep (no per-page interruption). User quote: *"good call"*. Decided by: user (process), Claude (per-page proposals).
4. **Are there therapy-platform surfaces that don't route through Vite at all?** *(Phase 0.)* — If there's e.g. a standalone marketing site, it's out of scope for this project. User confirmed 2026-05-03: *"go on with recommendations"*. Decided by: Claude during Phase 0, flagged to user if ambiguous.
5. ~~**LGPD stance on rejection reasons (free-text may contain applicant PII).**~~ *(Phase 5.)* — **DECIDED 2026-05-03 (parent-batch Phase 3.a §7 round):** 90-day retention post-rejection, then null-out `rejection_reason` via a scheduled job. **PLUS** explicit `noctus.dev.lgpd_flag` call at rule-creation time per `feedback_lgpd_first` (aligns with consent-retention pattern in migration 008). User quote: *"let's go with your option, 90 dias then flag lgpd"*. Decided by: user.
6. ~~**Does the identity resolver belong under `noctusai_lib.identity/` or `noctusai_lib.auth/`?**~~ — **RESOLVED 2026-05-03 (audit):** placement is `noctusai_lib/integrations/supabase_identity.py` per the 6-layer layout decision tree (`KB § PATTERNS/seed-lib-layout.md`). Wraps the Supabase auth.admin SDK → integrations layer. Single-file shape (flat `.py`), promotes to a folder if more identity providers join. Naming follows the integrations vendor-naming convention (e.g. `whatsapp/`, `vista/`, `google_calendar/`).
7. **Avatar fallback chain** — today the Therapists page uses initials from `nome`. If `nome` comes out empty (e.g. user signed up with only an email), what do we show? Email-local-part? A generic silhouette? User confirmed 2026-05-03: *"go on with recommendations"*. Decided by: Claude during Phase 2, design-logged in Improvements.
8. **Pagination DTO destination — invent locally first or land in seed-lib upfront?** *(Phase 0/3.)* — **DECIDED 2026-05-03 (audit):** invent locally in this product first, then propose for seed promotion at Phase 3 close as `noctusai_lib/api/pagination.py`. Verified absent from seed-lib at audit time. Keeps Phase 1's "one absorption" constraint intact and lets Phase 0/3 confirm cross-product recurrence before the absorption lands. Decided by: user.

### Design batch from Phase 0 discovery *(surfaced 2026-05-03 from systemic findings §5.4.2 — all decided same day)*

9. ~~**Pattern A — EN/PT path alignment.**~~ *(Phases 2/3/6/7.)* — **DECIDED 2026-05-03 (default rec accepted):** Rename the 8 PT backend routers to EN (`alertas-crise→crisis-alerts`, `evolucao→evolution-notes`, `tarefas→homework`, `recibos→invoices`, `humor→mood`, `salas→rooms`, `diario→diary`, `planos-tratamento→treatment-plans`) using libcst AST rename per `KB § PATTERNS/ast.md`. Lands during Phase 3 DTO sweep. Blast radius: 8 routers, ~35 routes, ~30 frontend hooks. No external API consumers per `§4 Out of scope`. User quote: *"go on with your recommendations"*.

10. ~~**Pattern B — Admin namespace shape.**~~ *(Phases 2/3.)* — **DECIDED 2026-05-03 (default rec accepted):** Role-gate canonical endpoints (`/api/support/reports`, `/api/reviews/flagged`, etc.); add `/api/blocks` + `/api/reviews/:id/{dismiss,hide}` where missing. Keep `/api/admin/*` only for admin-only operations (approve/reject/list-pending/dashboard/appointments/financials). Reduces backend-surface drift; matches the `/api/admin/financials` pattern. User quote: *"go on with your recommendations"*.

11. ~~**Pattern C — Admin detail endpoints.**~~ *(Phase 3.)* — **DECIDED 2026-05-03 (default rec accepted):** Frontend-only refactor — `useAdminTherapist` etc. call canonical `/api/{therapists,clinics,patients}/:id` with admin-role JWT (backend already permits admin role). No new backend routes; three frontend hooks updated. User quote: *"go on with your recommendations"*.

12. ~~**Pattern D — Direct-fetch role-prefix pages.**~~ *(Phases 6/8.)* — **DECIDED 2026-05-03 (default rec accepted):** Extract 4 pages into hooks; call canonical un-prefixed endpoints with role-filter from JWT. No new backend routes. Lands in Phases 6/8. User quote: *"go on with your recommendations"*.

13. ~~**Pattern E — DTO contract via `response_model`.**~~ *(Project-level scope decision.)* — **DECIDED 2026-05-03 (default rec accepted):** Defer to follow-up project `therapy-platform-dto-contract`; **accept-with-rationale for THIS project**, with the gap table + 38 router test files as the operational contract. Phase 10 success criterion "every admin list endpoint returns the typed DTO declared in `frontend/src/types/`" upheld via mappers, not `response_model`. Accept-with-rationale entry filed at end of Phase 10. User quote: *"go on with your recommendations"*.

14. ~~**Pattern F — `require_role` consolidation.**~~ *(Phase 1.)* — **APPLIED at Phase 1 (no design Q):** Phase 1 absorbs `app/dependencies.py:55` `require_role()` and `app/routers/settings.py:42` `_require_role()` into `noctusai_lib.api.auth.make_require_role` (factory; product binds it once in `dependencies.py` as `require_role = make_require_role(get_current_user, get_user_role)`). The original `require_role` was found broken pre-absorption and retired in the same phase — see §11 Phase 1 entry. N=3 recurrence (1 seed + 2 local) → formalize per absorption-search rule. No user signal needed.

---

## 8. Dependencies & blockers

- **Supabase MCP access** — already granted via blanket approval (`feedback_supa_mcp_proactive`). Used for Phase 5 migration application and Phase 0 schema inspection.
- **`auth.admin` API access from the admin-client path** — Phase 1 depends on this. Already used elsewhere in the codebase (`auth_service.py`), no new access needed.
- **Baseline test stability** — every phase re-runs the prior phase's tests. A phase that destabilizes a previously-green test suite is a regression, not a normal revision.
- **Admin test fixtures may need updating** — once DTO shapes change, the mock `SAMPLE_*` fixtures in `tests/routers/test_admin_router.py` need to reflect the new shape. Track this inline per phase.

---

## 9. Success criteria

- **0 `404`s, 0 `405`s on every navigable URL** for a logged-in user with each role (admin, therapist, patient, clinic-admin) across the therapy-platform frontend. Verified manually in Phase 10.
- **Every admin list endpoint** returns the typed DTO declared in `products/therapy-platform/frontend/src/types/` (no raw DB rows cross the boundary).
- **Reject flow works end-to-end**: a pending therapist can be rejected with a reason, appears in the Rejeitado tab with the reason visible on the detail page, and can be re-approved back into Aprovado.
- **`pytest products/therapy-platform/backend/tests/` is green.**
- **`npx vite build` is green** for the therapy-platform frontend.
- **`improvements.md` populated** for every completed phase, regenerated by `noctus.dev.improvements` after each tick.
- **One phase-end proposal landed in `products/therapy-platform/projects/therapy-platform-wiring/proposals/`** for every phase with meaningful observations (or a one-line `**Improvements:** none identified.` when genuinely nothing was learned).
- **No new LGPD warnings opened without a planned resolution** — any `noctus.dev.lgpd_flag` call added during this project has either been resolved by the project's end or has a follow-up project named in `LGPD-WARNINGS.md`.
- **KB is in sync**: `bash scripts/verify-kb-sync.sh` and `python scripts/update-kb-counts.py --check` both pass after the project closes.

---

## 10. How to use this project

- **Single source of truth for progress.** Update as work progresses.
- **Live-tick tasks as they complete.** Flip `- [ ]` → `- [x]` immediately and save. Don't batch. The user watches this file as a live dashboard.
- **Phase-by-phase cadence.** Execute exactly one phase, then pause and wait for the user to say "continue" / "next phase" / "do phase N". Do **not** auto-advance. User overrides with explicit throughput instructions ("ram through 2-3", "run all admin phases").
- **Revise phases when reality diverges.** If Phase 0 discovers the gap set is smaller or larger than estimated, rewrite Phases 2-9 accordingly and log the revision in §11.
- **Commit project changes with the code.** The PROJECT.md evolves in the same commit as the phase's implementation.
- **Interrogate before designing revised phases.** If a phase needs a scope call, ask the user — don't assume.

### Verification commands *(run at end of every phase, not just Phase 10)*

```bash
# Frontend build (any phase that touches frontend)
cd products/therapy-platform/frontend && npx vite build

# Backend tests (every phase)
cd products/therapy-platform/backend && \
  /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest tests/ -q

# Seed tests (Phase 1 and any phase that touches seed)
cd seed/lib/backend && \
  /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest tests/

# MCP tests (only if the MCP toolkit was touched)
cd mcp/noctusai && \
  /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest tests/

# Keeper review pass (after every phase)
python mcp/noctusai/cli.py --review products/therapy-platform

# Regenerate the retrospective (after every ticked phase header)
python mcp/noctusai/cli.py --improvements products/therapy-platform/projects/therapy-platform-wiring/PROJECT.md
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Phase 2 ✅ — Admin Tier A regressions cleared.** 8 new admin endpoints landed: `GET /api/admin/appointments` (DTO with `patient_name` / `therapist_name` / `clinic_name` via Phase 1 bulk identity resolver + new `_resolve_clinic_names` helper — no N+1), `GET /api/admin/dashboard` (pending counts + sessions_today + total_revenue / platform_fees aggregates), `POST /api/admin/suspend/{type}/{id}` (mirror of `approve_entity`, sets `is_active=False`), `GET /api/admin/financials/summary` (4 headline metrics matching `AdminFinancialSummary`), `GET /api/admin/financials/transactions` (paginated with status + date_start/date_end), `GET /api/admin/financials/commissions` (returns `{global_rate_pct, overrides[]}` with `entity_name` resolved via the Phase 1 resolver for therapists and a clinic-name `.in_()` lookup for clinics), `DELETE /api/admin/financials/commissions/{id}` (with 404 guard). The existing `POST /api/admin/financials/commissions` was extended to accept BOTH the new frontend shape (`{global_rate_pct?, override?:{entity_type, entity_id, rate_pct}}`) AND the legacy `{target_type, target_id, custom_commission_pct}` shape — `CommissionConfigRequest.model_post_init` normalizes legacy into `override` so existing tooling keeps working (legacy tests in `test_admin_financials_router.py::TestSetCommissionOverride` still green). New `CommissionOverrideInput` + `CommissionConfigRequest` schemas in `app/schemas/financial.py`. Service additions in `admin_service.py`: `list_appointments_for_admin`, `_appointment_row_to_dto`, `_resolve_clinic_names`, `admin_dashboard_metrics`, `suspend_entity`. **Frontend wiring:** `pages/admin/Dashboard.tsx` was a static placeholder — now consumes `useAdminDashboard()` with live counts + currency-formatted revenue. **Test additions:** 37 new router tests in `test_admin_router.py` (TestAdminAppointments × 6, TestAdminDashboard × 3, TestSuspendEntity × 6) and `test_admin_financials_router.py` (TestFinancialSummary × 3, TestListAllTransactions × 5, TestGetCommissionConfig × 4, TestSetCommissionConfig × 6, TestDeleteCommissionOverride × 4) plus 8 service tests in new `tests/services/test_admin_service.py` (`list_appointments_for_admin` × 3, `admin_dashboard_metrics` × 1, `suspend_entity` × 4). All 45 new tests green. **Verification:** therapy-platform backend `pytest tests/` = 1212/1222 (10 pre-existing baseline failures from Supabase real-client init when `SUPABASE_URL` is unset in the local venv — same 10 fail in isolation against a fresh checkout of `main` before any Phase 2 work; documented in `findings.md`). admin-surface in isolation = 98/98. `npx vite build` from frontend = clean (440 modules, 8.8s). `python mcp/noctusai/cli.py --review --product therapy-platform` = 0 issues, 0 proposals. **Phase 2 improvements (filed live):** (1) `admin_service.set_commission_override` writes to `commission_overrides` but the migration creates `platform_commission_overrides` — orphan POST `/api/admin/commissions` already flagged for Phase 2 audit; table name + `set_by` → `set_by_admin_id` deferred to Phase 4 because the orphan endpoint is not consumed by any frontend hook surveyed in Phase 0. (2) `MockSupabaseClient` does NOT apply `.eq()` / `.gte()` / `.lte()` predicates on SELECT reads (only on UPDATE/DELETE) — accept-with-rationale (tests seed only matching rows; production filter is still on the wire). **Status:** Phase 2 closed; awaiting user "continue" before Phase 3 DTO normalization sweep. | Claude Opus 4.7 (1M context) |
| 2026-04-20 | Initial project drafted from `templates/PROJECT-TEMPLATE.md` after interrogation of the user. Slug renamed `therapy-admin-console-gap` → `therapy-platform-wiring` to honor the scope widening captured in §2. Methodology docs updated with §8 slug-naming convention and §9 tests-land-with-implementation note. | Claude Opus 4.7 |
| 2026-04-20 | Project folder relocated from `projects/therapy-platform-wiring/` to `products/therapy-platform/projects/therapy-platform-wiring/` as part of the scope-scoped-projects architecture change (single-product scope lives under the product). Methodology docs updated to codify the two-location rule (`PATTERNS/project-execution.md §1`). MCP `proposals.py::_find_project_dir` resolver updated to search both locations. | Claude Opus 4.7 |
| 2026-05-03 | **§7 round closed — parent-batch `main-core-migrations-batch` Phase 3.a.** All 8 §7 items now decided. **User decisions (3):** Q1 reject-reason cleared on re-approval (*"yes"*); Q3 page-deletion candidates surfaced as one batch at end-of-Phase-0 with one-line rationale per page (*"good call"*); Q5 LGPD retention 90 days + explicit `noctus.dev.lgpd_flag` at rule-creation per `feedback_lgpd_first` (*"let's go with your option, 90 dias then flag lgpd"*). **Default recommendations accepted (4):** Q2/Q4/Q7 stand as Claude-decides-during-execution per the user's *"go on with recommendations"*. **Already-resolved by drift-audit (2):** Q6 (identity-resolver placement = `noctusai_lib/integrations/supabase_identity.py`) and Q8 (pagination DTO local-first). **Scope confirmed:** widest A⇒B⇒C — fix known regressions → admin sweep → close pre-existing scaffolding debt → widen to whole product (no narrowing requested). **Status:** 📋 Phase 0 ready — awaiting "continue" from user before Phase 0 discovery starts per the project's pause-after-each-phase cadence. | Claude Opus 4.7 |
| 2026-05-03 | **Phase 1 bonus delivery — 2 Phase 4 sub-tasks landed early (settings.py refactor + notificacoes audit).** Phase 4 itself remains open with 7 unticked sub-tasks (RLS audit, search_path hardening, migration drift, missing admin tests, N+1 audit, LGPD flags, keeper review/proposal); only the 2 easy wins from Phase 1's surface were folded forward this session. User direction: *"please deliver the deferred work. then commit and push your work"*. **Two Phase 4 sub-tasks delivered, not full Phase 4 close.** (1) **`app/routers/settings.py` rewritten**: 2 inline helpers (`_require_admin(user)` line 34, `_require_role(user, *roles)` line 42) deleted. 11 endpoints converted from `authorization: Optional[str] = Header(None)` + manual `await get_current_user + _require_X(user)` pattern to `auth=Depends(require_role("..."))` factory pattern (binding from Phase 1). Endpoints: GET/PATCH `/platform`, GET/PATCH `/platform/ai-prompts`, GET `/platform/ai-prompts/history`, GET/PATCH `/therapist`, GET/PATCH `/clinic/branding`, GET/PATCH `/patient`. Imports cleaned: removed `Header`, `Optional`, `get_current_user`, `get_user_role`; consolidated 6 inline `from app.dependencies import first_or_none` to a single top-level import. Same 403 behavior as before — only signatures shifted. (2) **`tests/routers/test_notificacoes_router.py` orphan audit closed as no-action-needed (false alarm)**: docstring states "The notifications router is now provided by the noctusai_seed framework"; test patches `noctusai_seed.database.DatabaseModule.{get_client,get_core_client,get_admin_client}` and exercises seed-mounted `/api/notificacoes` endpoint. Test was passing all along (part of 1143/1143). My §5.4.8 audit only walked product `app/routers/*.py` and missed seed-framework-mounted routers. §5.4.8 note updated with the caveat. **Verification:** `tests/routers/test_settings_router.py` = 26/26 ✅; full therapy backend `pytest tests/` = 1143/1143 ✅; frontend `npx vite build` clean. Phase 4 sub-tasks in §6 ticked ✅. **Note:** Phase 4 itself is not closed — RLS audit, search_path hardening, migration drift, missing admin tests, N+1 audit, LGPD flags, plus other scaffolding-debt items remain Phase 4 scope. The 2 sub-tasks delivered here were the easy wins from Phase 1's surface; the full Phase 4 sweep stays for after Phase 2/3. **Status:** awaiting user "continue" before Phase 2 known-regressions sweep. | Claude Opus 4.7 |
| 2026-05-03 | **Phase 1 ✅ — Shared identity resolver + Pattern F require_role consolidation.** Shipped (a) `seed/lib/backend/noctusai_lib/integrations/supabase_identity.py` with `UserIdentity` dataclass + `fetch_user_identities()` (bulk) + `fetch_user_identity()` (singular). 20 unit tests green covering happy path, alias fallbacks, error → empty-shape contract, dedupe, falsy-skip, and defensive non-string coercion. Sync `def` (not `async def`) — supabase-py admin SDK is sync; documented in module docstring + KB catalog. Did NOT re-export from `integrations/__init__.py` — followed the existing repo pattern for flat single-file integrations (`database.py`, `redis.py`); deviated from the original Phase 1 sub-task spec for consistency. (b) **Seed-lib bug discovered + fixed:** `noctusai_lib.api.auth.require_role` was broken at line 195 (`_get_supabase_client=None` blindly → RuntimeError). Verified zero callers monorepo-wide; replaced with `make_require_role(get_current_user_fn, get_user_role_fn)` factory matching the `make_get_current_user` pattern. 6 new tests cover allow / multi-allow / reject / 401-propagation / distinct-deps / 403-detail-formatting. (c) Therapy-platform absorption: `admin_service.py::_fetch_user_identity` (32 lines) deleted + replaced with seed import; `_therapist_row_to_dto` signature changed to `UserIdentity`; foto_url falls back from auth metadata → row's `photo_url` column for compat. **Bonus N+1 → bulk** at `list_therapists_for_admin`: was one auth lookup per row in a loop; now bulk pre-fetch via `fetch_user_identities(db, user_ids)` then iterate the result map. (d) `dependencies.py` switched from local `require_role` (lines 55-74, dead code — no router imports it) to `require_role = make_require_role(get_current_user, get_user_role)`. (e) Updated `KNOWLEDGE-BASE/CONTEXT/04-SHARED-LIBRARY.md` with new `integrations/supabase_identity.py` section + retired/replaced `require_role` row in `auth.py` table. **Verification:** therapy-platform backend `pytest tests/` = 1143/1143 ✅; seed-lib backend `pytest tests/` = 448/448 ✅ (incl. 26 new); therapy-platform frontend `npx vite build` clean; keeper review pass = 0 issues, 0 proposals; `verify-kb-sync.sh` clean. **Improvements (inline, no proposal file per `feedback_apply_inline_delete_proposals`):** N+1 → bulk pattern propagates to upcoming admin list endpoints in Phase 2/3 (clinics, patients, appointments — pre-fetch identities before the loop, same shape). **Deferred to Phase 4:** `app/routers/settings.py` carries 2 inline role-check helpers (`_require_admin(user)`, `_require_role(user, *roles)`) signature-different from the Depends-pattern factory; refactoring 11 endpoints to use `Depends(require_role(...))` is scaffolding-debt scope, added as a Phase 4 sub-task. **Also Phase 4:** orphan `tests/routers/test_notificacoes_router.py` (no matching router file) flagged for audit. **Status:** awaiting user "continue" before Phase 2 known-regressions sweep. | Claude Opus 4.7 |
| 2026-05-03 | **Phase 0 ✅ — Discovery + inventory complete.** Parallel-agent enumeration (4 Explore agents) produced: backend route inventory (38 routers, 193 routes, **0/38 declare `response_model`** — DTO contract is implicit via `success_response()` / `paginated_response()` wrappers), frontend api-call inventory (~143 unique calls across 26 hooks + 4 direct-fetch pages), migration column cross-reference (44 tables, ~500+ column refs, **0 unexpected gaps** — only `rejection_reason × {therapist_profiles, clinics}` flagged for Phase 5), seed-lib export catalog (7 layers). Join surfaced **~58 gap rows + 7 systemic patterns**: Pattern A (~30 calls × 8 PT backend routers don't match EN frontend), Pattern B (admin namespace not split), Pattern C (admin detail endpoints missing), Pattern D (4 direct-fetch pages bypass hooks), Pattern E (193 routes have no `response_model`), Pattern F (`require_role` N=3 — 1 seed + 2 local), Pattern G (intra-cluster path-shape mismatches). §5.4 populated (5.4.1 counts → 5.4.9 keeper); Phases 6-9 promoted from placeholders to concrete sub-tasks rooted in §5.4.3 rows; §7 design batch surfaced (Q9-Q14). **Q3 deletion-candidate batch: empty** — every admin/role page maps to a wired endpoint or a §5.4.3 gap row this project's scope fixes; user invited to surface deletion candidates in §7 Q-NEW-DEL if any exist beyond the inventory. **Keeper review pass clean:** `cli.py --review --product therapy-platform` returns 0 issues, 0 proposals filed (corrected CLI signature: `--review --product PRODUCT`, not `--review <path>` — original Phase 0 sub-task instruction had stale syntax). **Improvements applied inline** (no separate proposal file per `feedback_apply_inline_delete_proposals` + `feedback_auto_improvement`): require_role recurrence flagged for Phase 1 absorption; orphan `tests/routers/test_notificacoes_router.py` flagged for Phase 4 audit; `clinics` table added to migration 010 scope (the `admin_service.py:84-92` reject path runs against either table — clinic-side fails today silently masked by the empty-Rejected hack). **Status:** ⏳ Phase 0 ✅ → awaiting user sign-off on §7 Q9-Q13 design batch before Phase 1 kickoff (Q14 = no design Q, Phase 1 absorbs). Per child cadence: pause until "continue". | Claude Opus 4.7 |
| 2026-05-03 | **Project-doc inconsistency cleanup pass.** Two prior agents flagged 4 drifts between project narrative and shipped state; resolved this session. **(1)** Unresolved `git stash pop` conflict markers at the header status block + §11 Phase-1-bonus row removed; kept the "Phase 4 deferred-work pre-delivered" framing (matches the §6 Phase 4 ticked sub-tasks and the §11 Phase 1 entry's "Deferred to Phase 4" note). **(2)** §5.1 code sketch flipped from `async def fetch_user_identities` → sync `def`, dropped the (a)/(b)/(c) "Phase 1 decides" implementation-choice block, and pointed forward to the §11 Phase 1 entry for the decision (option (b) sequential, sync, benchmarking deferred). Also tightened the `display_name` fallback to the actual code's behavior (`"@" in self.email` guard, not bare `split("@")[0]`). **(3)** §5.4.6 absorption-table rows + §5.4.2 Pattern F write-up + §6 Phase 0 sub-task + §7 Q14 — all four pointers to `noctusai_lib.api.auth.require_role` updated to `noctusai_lib.api.auth.make_require_role` (factory; bound product-side as `require_role = make_require_role(get_current_user, get_user_role)`). The original `require_role` was retired by Phase 1 — historical narrative in the §11 Phase 1 entry left intact. **(4)** Header status-block test counts refreshed from the Phase-1-close snapshot (1143/448) to the current verified state (1177/485 at 2026-05-03 cleanup re-run); the historical Phase-1-close numbers stay in the §11 Phase 1 entry as the snapshot at that time. Verification: therapy-platform backend `pytest tests/` = 1177/1177 ✅; seed-lib backend `pytest tests/` = 485/485 ✅; no `<<<<`/`====`/`>>>>` markers remain. **Status:** unchanged — awaiting user "continue" before Phase 2. | Claude Opus 4.7 |
| 2026-05-03 | **Drift-realignment audit before Phase 0 kicks off — pilot-care expansion-on-invalidation.** 13 days of repo evolution between draft (2026-04-20) and execution (2026-05-03), 17 commits to therapy-platform / seed-lib, plus the seed axis-swap (`fc277e2`). Audit findings + revisions applied: **(a) seed paths** — already updated by the parallel agent's bulk sed when commit `fc277e2` swapped `seed/{backend,frontend}/{lib,framework}` → `seed/{lib,framework}/{backend,frontend}`. **(b) reject migration number** — `007` → `010` (007/008/009 are now `clinical_data_privacy`, `consent_retention`, `session_audio_segments_recording_id`). §3 / §5.2 / Phase 5 updated; Phase 5 sub-task carries an "confirm next free at execution time" caveat. **(c) identity-resolver placement** — moved from top-level `noctusai_lib/identity/` to `noctusai_lib/integrations/supabase_identity.py` per the 6-layer layout decision tree (`KB § PATTERNS/seed-lib-layout.md`); §5.1 + Phase 1 + §7 Q6 updated. Tests now in `seed/lib/backend/tests/integrations/test_supabase_identity.py`. **(d) scope expansion** — §4 router list expanded from ~12 to ~39 routers actually present (consents, lgpd, whatsapp_therapy, crisis, mood, homework, journals, treatment_plans, attachments, evolution_notes, observations, patient_notes, recurring, refunds, transactions, dashboard_bi, etc.). Phase 0 sub-task names all 39 routers; Phases 6-9 "likely scope" lines expanded to fold in cross-cutting routers per role. **(e) gap-table shape** — per-router with role-tags (admin/therapist/patient/clinic/public), so cross-cutting routers get a row per consumer angle without per-portal duplication. §5.4 + Phase 0 deliverable updated. **(f) pagination DTO** — invent locally first; propose for seed at Phase 3 close as `noctusai_lib/api/pagination.py` (verified absent from seed-lib `api/`). §5.3 + new §7 Q8. **(g) absorption-search:** Phase 0 gains a "should-use-seed" cross-cutting check sub-task — given the substantial seed-lib growth (`domain/{scheduling,digest,ai,conversation}`, `integrations/{whatsapp,google_calendar,google_maps,llm,vista,email}`, `security/`), Phase 0 verifies for each new router/service whether seed-lib already covers a need that would otherwise be invented locally. **What's still valid (no rewrite needed):** §1, §2 constraints, §3 reject-flow target state, §6 Phase 2 known regressions (all confirmed still missing — no `/api/admin/appointments` route; `admin_financials.py` exposes only `/`, `/wallets`, POST `/commissions`, `/payouts`, POST `/payouts/{id}/process`), §9 success criteria. **What's still pending in code:** identity resolver was never absorbed (ad-hoc `_fetch_user_identity` intact at `admin_service.py:252`); `rejection_reason` column was never migrated (Rejeitado tab early-returns `[], 0` at `admin_service.py:331-334` as the explicit hack). | Claude Opus 4.7 |
