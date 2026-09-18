# LGPD Awareness — Keeper Principle

> Brazilian General Data Protection Law (Lei Geral de Proteção de Dados Pessoais, Lei nº 13.709/2018) applies to every NoctusAI product — B2B CRM, clinical therapy, personal finance, daily-life tracker. This file is the **keeper principle** that injects LGPD-first thinking into every architecture decision.

---

## 1. The keeper principle

**Whenever code touches personal data, the LGPD lens is the first lens.** Functionality, performance, and UX are argued against an LGPD baseline — never around it. An architecture that works beautifully and violates LGPD is a broken architecture.

This is non-negotiable because:
- Therapy stores **clinical data** (sessões, prontuários, diagnoses) — "sensitive personal data" under Art. 11, the highest protection tier.
- ERP + PF store **financial data** (proposta values, salaries, investments) — personal data requiring a lawful basis per Art. 7.
- Core stores **authentication + identity** across products — any cross-product leak compounds risk.

A violation is not just a regulatory exposure (fines up to 2% of revenue, capped at R$ 50M per infraction). It's a breach of user trust that the platform cannot recover from silently.

---

## 2. What counts as "personal data" in this codebase

Anything that **identifies or could identify** a natural person, directly or through combination:

| Tier | Examples in this repo | Product |
|---|---|---|
| **Direct identifiers** | `users.email`, `users.name`, `cpf`, `telefone` | All |
| **Contextual** | `imoveis.observacoes`, `clientes.anotacoes`, `leads.nome` | ERP |
| **Financial** | `propostas.valor`, `comissoes.*`, `lancamentos.valor` | ERP, PF |
| **Clinical (Art. 11 — sensitive)** | `session_transcripts`, `session_summaries`, `journal_entries`, `mood_logs`, `clinical_records.*`, patient free text in any form | Therapy |
| **Health-adjacent** | `mood_logs`, `checkins` for wellness, `metas_saude` | Daily Life |
| **Behavioral** | `action_log.*` rows tied to a user | All |
| **Derived** | Embeddings computed over any of the above | All (via `noctusai_lib.llm`) |

The last row is the trap most commonly missed. An embedding of a patient's journal entry is still patient data — it's a mathematical transformation that retains semantic content.

---

## 3. The five questions (ask on every data-touching change)

Before shipping any code that reads, writes, transforms, stores, caches, logs, or transmits personal data:

1. **Basis.** What is the lawful basis (Art. 7)? Consent? Contract? Legitimate interest? Whichever it is, is it documented?
2. **Minimization.** Are we storing / transmitting only what's strictly required for the stated purpose? If we're sending 20 fields to an LLM when 3 would do, we're failing Art. 6.III.
3. **Destination.** Where is this data going? Our DB? A 3rd-party API (OpenAI, Anthropic, Gemini, Resend, WAHA)? A cache (Redis)? A log stream? Each hop needs to be deliberately chosen.
4. **Retention.** How long does this data persist? Is there a TTL? A deletion path on user request (Art. 18.VI)?
5. **Tenant isolation.** Is this data reachable across orgs/clinics that shouldn't share it? RLS policies must prove it — not just by convention.

If any answer is "I don't know" or "it depends", that's the moment to **flag it** (see §5).

---

## 4. Architectural anti-patterns (have bitten us before — or would)

- **Logging full request bodies** that include user fields. Redact or structured-log only IDs.
- **Caching deterministic LLM responses that contain user free text.** Therapy summaries and longitudinal analyses are flagged `cache=False` for this reason (Phase 8 of the LLM plan).
- **Shared embeddings across products.** Even if the vector is "just numbers", sharing an embedding built from clinical notes with a non-clinical product is a data leak. Cross-product data sharing is blocked until encryption is in place (see `project_lgpd_cross_product.md`).
- **PII in error messages.** Our `AppException` hierarchy returns user-facing Portuguese messages — they must never embed the raw data that caused the error (`"Usuário 'joao@example.com' já existe"` is a violation; `"Este e-mail já está em uso"` is not).
- **Unbounded retention.** Notifications, invitations, action logs, LLM response caches — every table needs an answer to "when does this data leave the database".
- **Single-tenant leakage via service-role clients.** `get_admin_client()` bypasses RLS. Any service-role query over a table that holds multi-org data needs an explicit `.eq("org_id", ...)` filter — the DB won't catch the omission.
- **Telemetry hitting 3rd-party services with user content.** Sentry scrubs PII by default, but custom `extra` context bypasses the scrubber. Never attach user-owned data to `sentry_sdk.capture_*` calls without sanitization.

---

## 5. The `noctus.dev.lgpd_flag` tool

When developing a feature that touches personal data and you're unsure whether an approach meets LGPD, **flag it**. The flag is a record, not a block — the code still ships. A future review picks up the flag as a checklist item before the feature can call itself "done".

```
# CLI
python mcp/noctusai/cli.py --lgpd-flag \
    --code-path "products/therapy-platform/backend/app/services/summary_service.py:85" \
    --concern "patient-transcript-in-prompt" \
    --reason "Full session transcript embedded in OpenAI prompt; request body logged at INFO level if debug flag on." \
    --mitigation "Redact patient-identifiable tokens before the LLM call; drop the request-body log."

# MCP tool
noctus.dev.lgpd_flag(
    code_path="...",
    concern="...",
    reason="...",
    mitigation="..."  # optional
)
```

**What it does:**
1. Appends a new checklist item to `LGPD-WARNINGS.md` at the repo root.
2. Prints a prominent user-facing notification (`⚠️ LGPD concern flagged: <concern>`).
3. Returns a structured dict with the warning details.

**What it does NOT do:**
- Block the commit.
- Fail any CI check.
- Edit the flagged code.

The file is a rolling log. Items are checkboxes (`- [ ]`). They get ticked when the concern is resolved — either the code was changed, or the concern was reviewed and dismissed with a rationale.

---

## 6. When to flag (non-exhaustive)

Call `noctus.dev.lgpd_flag` whenever you:

- Add a new table column that holds personal data (flag with the column's retention question).
- Send data to a 3rd-party API (OpenAI, Anthropic, Gemini, Resend, WAHA, Clickhouse, Sentry, …) — flag the destination + the data shape.
- Add or modify a cache (Redis, in-memory) that might hold personal data.
- Write to a log stream that could include request bodies.
- Use a service-role Supabase client on a multi-org table without an explicit tenant filter.
- Bypass RLS for any reason.
- Build an aggregation or analytics view that could allow re-identification.
- Touch clinical text in any way (Therapy prompts, summaries, embeddings, exports, search indexes).

"When in doubt, flag." A flagged concern with a solid mitigation review costs ~5 minutes; an unreviewed one that ships costs weeks.

---

## 7. Relation to existing rules

- **`project_lgpd_cross_product.md`** (memory) — blocks cross-product data sharing until encryption is in place. Still in force. The LGPD flag complements it; the block is the backstop.
- **`KNOWLEDGE-BASE/CONTEXT/backend/07-AUTH-SECURITY.md`** — auth + session security deep-dive.
- **`KNOWLEDGE-BASE/CONTEXT/PATTERNS/backend/database-rls.md`** — RLS policy templates. Every RLS design is an LGPD statement — re-read it when building one.
- **`CLAUDE.md` → "Keeper principles"** — this file is one of them.

---

## 8. Invariants (always true, regardless of phase)

- Clinical free text does not leave the Therapy product schema without a documented lawful basis.
- Response caches never cache a prompt that contains clinical free text (`cache=False` in every Therapy summary/longitudinal call).
- `get_admin_client()` on any multi-org table requires an explicit `.eq("org_id", …)` / `.eq("clinic_id", …)` filter.
- Pydantic models that surface user data define `model_config = ConfigDict(extra="forbid")` — no accidental leakage of internal columns.
- Every new migration with personal data columns ships with RLS enabled (`ENABLE ROW LEVEL SECURITY`) + a policy attached.
- Every 3rd-party data egress is listed in `LGPD-WARNINGS.md` with its mitigation.

## 9. Per-feature AI consent (X6 — Phase 19, 2026-04-26)

Platform-wide opt-in / opt-out for AI features that consume personal data. Backed by `public.ai_consent` (Core migration 012) + the `noctusai_lib.ai.consent` helpers + the user-facing `/api/me/consents` endpoints.

**Catalog registration.** Each product owns its catalog at `app/services/ai_consent_features.py` — module-level `register_feature(...)` calls populate the platform-wide registry as a side effect of import:

```python
# products/<X>/backend/app/services/ai_consent_features.py
from noctusai_lib.ai import register_feature

register_feature(
    "erp.lead_score",
    title="Pontuação de leads",
    rationale="Avalia perfis de clientes automaticamente para priorização da equipe.",
    product="erp",
    default_granted=False,    # opt-in by default
)
```

**The catalog gets loaded via the framework, not by import-for-side-effects** (consolidated 2026-04-28). Each product's `app/main.py` declares the path as a kwarg of `create_product_app(...)`:

```python
# products/<X>/backend/app/main.py
app = create_product_app(
    name="...",
    schema="...",
    settings=settings,
    routers=[...],
    consent_features="app.services.ai_consent_features",  # ← named seam
)
```

The framework calls `importlib.import_module(consent_features)` once per process at app construction. **This is the single named seam** — replaces the old `from app.services import ai_consent_features  # noqa: F401` boilerplate that lived in every product's `main.py`. Products without consent-gated AI features simply omit the kwarg (catalog stays empty; `is_granted` resolution rule 4 fails-closed for unknown features).

**Tests load the catalog automatically.** `noctusai_lib.testing.pytest_plugin` is auto-registered via the `pytest11` entry point in seed-lib's `pyproject.toml`. At pytest session start, the plugin probes for `app.main` and imports it (which triggers the framework's catalog load). Non-product test sessions (seed-lib, MCP) silently no-op because `app.main` doesn't resolve. **Zero per-product `tests/conftest.py` boilerplate** — no `from app.main import app` line, no `import app.services.ai_consent_features` line, nothing.

**Guard at every consent-gated entry — router layer preferred.** Two valid placements:

**(a) Router layer (preferred — consent-guard-rollout Phase 1, 2026-04-27).** `Depends(consent_required(feature_key))` resolves user_id + admin db at request time and raises `AIConsentRequired` (HTTP 412) before the handler body runs. **Services stay LGPD-agnostic — they don't know consent exists.** Wiring is automatic via `create_product_app(consent_gating=True)` (the default).

```python
from fastapi import APIRouter, Depends
from noctusai_lib.ai import consent_required

router = APIRouter()

@router.post("/api/ai/leads/{id}/follow-up-draft")
async def draft_follow_up(
    id: str,
    _consent: None = Depends(consent_required("erp.lead_score")),
    # ... other deps + body
):
    return await ai_service.draft_follow_up(id)  # service has no consent code
```

**(b) Service layer (fallback — when no clean router maps to a single feature key).** Keep the existing `await require(db, user_id, feature_key)` call:

```python
from noctusai_lib.ai import require as require_consent

async def score_lead(db, user_id, cliente_data, ...):
    await require_consent(db, user_id, "erp.lead_score")
    return await chat_completion(...)
```

Use (b) only when (a) doesn't fit — e.g., one router invokes multiple gated features behind a switch, or a scheduled job runs server-side without a request context.

**Feature key conventions.** `<product>.<feature>` (e.g. `erp.lead_score`, `pf.categorize`, `daily_life.note_extract`). Keep keys stable — they're a snapshot in audit trails.

**Resolution order** (in `is_granted`):
1. Catalog feature with `toggleable=False` → `True` (locked-on infrastructure; see § Visible-but-locked).
2. Stored decision row → use its `granted` boolean.
3. No stored row + catalog has the feature → use `default_granted`.
4. No stored row + feature unknown → `False` (fail-closed).

**Endpoints** (Core, user-scoped via RLS):
- `GET /api/me/consents` → `{items: [{key, title, rationale, product, default_granted, granted, decision_recorded, granted_at, revoked_at}], pending}`. `pending` powers the `LayoutEnrichment.aiBadge` "N consents pending" prompt.
- `PUT /api/me/consents/{feature_key} {granted: bool}` → upsert. Stores rationale snapshot + grant/revoke timestamp.

**Frontend UI — seed-mounted, zero per-product code (consent-ui-rollout Wave 4B, shipped 2026-04-28).** Every product gets the consent UI by virtue of calling `createProductApp(...)` — products write zero consent-UI code. The full chain:

- **Components** live in `seed/lib/frontend/src/design-system/ai/`: `<AIConsentToggles/>` (settings panel, grouped by product, "padrão" annotation when `!decision_recorded`, locked + "infraestrutura" pill when `!toggleable`), `<PendingConsentBadge/>` (compact nudge linking to `/settings/ai`, null-renders when nothing to nudge), plus the supporting `useConsents` + `useUpdateConsent` hooks.
- **Page hosting them** lives in `seed/framework/frontend/src/pages/ConsentSettingsPage.tsx` — title + LGPD-friendly intro paragraph (forward-only revocation explained inline) + `<AIConsentToggles/>`.
- **Route auto-injection** — `createProductApp` in `seed/framework/frontend/src/app.tsx` injects `<Route path="/settings/ai" element={<ConsentSettingsPage/>}/>` into both flat and role-based route trees BEFORE product-specific routes. Authenticated users of any role can manage their own consents.
- **Layout slot default** — `seed/framework/frontend/src/layout.tsx` resolves `enrichment.aiBadge !== undefined ? enrichment.aiBadge : <PendingConsentBadge/>`. Products pass `null` to explicitly opt out, or any React node to override (Wave 5's `<AIBadgeStack/>` composes multiple badges here).
- **Verification: per-product code count is ZERO.** Every product (mailing, ERP, daily-life, PF, core, therapy, adconnect, seed-reference) picks up `/settings/ai` + the pending badge automatically. Confirmed via cross-product `vite build` × 8 at Phase 2 close.

**LGPD audit trail.** `rationale_pt` is snapshotted on every grant so audit logs can prove what the user agreed to even after the catalog text changes. `granted_at` / `revoked_at` are kept across toggles (latest wins) for the same reason.

**Forward-only revocation (cross-product rule).** Revoking ANY consent (toggling a feature off) blocks **future** AI runs of that feature for the user only. It does NOT soft-delete, anonymize, or alter previously generated `ai_outputs` rows. Right-to-erasure is a separate LGPD Art. 18.VI workflow — the user (or a privileged admin acting on their behalf) explicitly requests deletion of past artifacts. Surfacing this distinction is part of the `<AIConsentToggles/>` UX (Wave 4B `consent-ui-rollout`): the revoke confirmation dialog must say "future runs only — past results are kept until you exercise erasure".

**Catalog inventory (consent-guard-rollout Wave 4A close, 2026-04-27).** 26 features across 7 products: ERP 10 (9 toggleable + `erp.embeddings` `toggleable=False`), Mailing 7, PF 3, Daily Life 3, Therapy 2, Core 1, AdConnect 0. Default postures: 19 `default_granted=True` (low/medium-risk org-internal text + aggregates + medium-risk lead/contact/transaction PII), 7 `default_granted=False` (Daily Life all-3 high-risk personal narratives + PF monthly_narrative + Therapy both-features Art. 11 clinical). The full per-feature registry lives in each product's `app/services/ai_consent_features.py` source-of-truth.

**Visible-but-locked features — billing transparency (consent-guard-rollout Phase 1, 2026-04-27).** Some AI features are infrastructure consumed silently by other features (e.g. `erp.embeddings` powers lead-matching + search-relevance). They can't be disabled without breaking dependent features — but **they ARE still registered in the catalog with `toggleable=False`** so users see what consumes their tokens. **The catalog serves two purposes simultaneously: LGPD transparency (what AI runs in your platform) AND billing transparency (what's burning your tokens).** Users are charged by token usage; they need to see what's consuming, even when they can't manage it manually.

Behavior:
- `register_feature(..., toggleable=False)` marks a feature as locked-on.
- `is_granted` short-circuits to `True` for non-toggleable (regardless of any stored decision row).
- `consent_required(...)` (the FastAPI dep) passes silently for non-toggleable features — same as if the user had granted.
- `upsert_decision` defensively raises `MandatoryFeatureCannotBeToggled` (HTTP 403) — the PUT `/api/me/consents/{key}` router pre-checks this and returns the same 403 with a PT-BR explanation.
- `pending_count` excludes non-toggleable features (no decision is needed, so they don't sit in the LayoutEnrichment.aiBadge "N consents pending" prompt).
- Frontend `<AIConsentToggles/>` (Wave 4B `consent-ui-rollout`) reads `item.toggleable` and renders the toggle as disabled, with the rationale text explaining why the feature is required infrastructure.

When to use `toggleable=False`:
- The feature is consumed by other features that ARE user-toggleable (revoking the infra would silently break the toggleable features).
- The feature has no direct user-facing surface — it runs in the background as part of another feature's work.
- Disabling individually would mislead the user about what they can opt out of (better to be honest: "this is infrastructure, here's what it does").

**Inaugural adopter:** `erp.embeddings` (consumed by lead-matching + search-relevance). Default for all other catalog entries: `toggleable=True`.

### Therapy clinical AI — patient consent + skip-and-notify (therapy-consent-guard-wiring 2026-04-27)

Therapy ships the platform's first **service-layer-only** guards because clinical AI runs from `BackgroundTasks` after the session-end request returns 200, not as a request handler. The router-level `consent_required(...)` dep doesn't fit — the request that triggers AI (PATCH `/sessoes/{id}/encerrar`) is a session-state mutation, not the AI itself, and 412-ing it would block the session record from being created.

**Three load-bearing rules locked in 2026-04-27:**

1. **Patient consent gates clinical AI, not therapist consent.** Per LGPD Art. 11, the patient is the data subject — their clinical text enters the LLM, so their grant is what matters. The pipeline has both `patient_id` and `therapist_id` in scope; only `patient_id` flows into `await require(db, patient_id, "therapy.<feature>")`. Therapist convenience (one consent vs N patients) does not override LGPD posture.

2. **Skip-and-notify, not hard-block.** When patient hasn't granted, the session record / audio archive / observations are **still created** — only the AI narrative steps are skipped. A `notifications` row (`type="ai_skipped_consent"`) is filed for the therapist with PT-BR explanation + link to the session. The therapist learns the AI was skipped, can ask the patient to grant, then re-trigger via an explicit "regenerate AI" action (out of scope; file as follow-up if needed). The session itself is never blocked by missing consent.

3. **Lightweight structured log, not a new audit table.** Each AI step emits `logger.info("ai.consent.processed feature=... patient=... session_record=... granted=<bool> [(skipped)]", ...)` whether AI ran or was skipped. The structured log line (already shipped to the standard log destination) meets the immediate audit-trail need. A dedicated `ai_processing_log` table would be its own follow-up project — keep scope tight.

**Forward-only revocation.** Revoking `therapy.session_summary` or `therapy.longitudinal_narrative` does NOT soft-delete past `ai_outputs` rows. Right-to-erasure is a separate workflow (LGPD Art. 18.VI) where the patient explicitly requests deletion.

## 10. Public-registry documents ARE personal data (matrícula-imóvel, 2026-09)

A certidão de matrícula, a certidão de casamento, a CND — any document a cartório or public body issues about a REAL asset, a marriage, a debt — still NAMES a natural person, with CPF, estado civil, cônjuge, regime de bens. "It's public" answers *who can request the document from the source*, not *what our system must do once it holds a copy*. Both facts are true at once:

- migration `075_imovel_dados_cartorio.sql` shipped `imovel_documentos` with the reasoning "a matrícula is a public registry document about a PROPERTY, not a person" — and gave it no `categoria_lgpd`, no access log, no retention clock;
- migration `109_matricula_estruturada.sql` reversed that: once the contract flow started keeping and re-opening these PDFs routinely, "public registry" stopped being a reason to skip logging WHO read a document that also happens to carry someone's CPF.

**The lesson generalizes past matrículas.** A document being a public record NEVER exempts it from the LGPD posture (§2–§3 above) — it only changes the *lawful basis* (Art. 7 V — cumprimento de obrigação legal/regulatória — rather than Art. 7 I consent), never the *obligation to log access and set a retention window*.

**Retention and access-log decisions are made TOGETHER, not staggered.** Migration 079 (`documento_retencao_politicas`) explicitly excluded the imóvel surface for the SAME reason 075 gave it no log: "offering a retention control with nothing logging its use would be a lying UI." Shipping the log (109) without also giving the surface a retention clock (111, two migrations later) leaves exactly that lying-UI window open — a surface that is LOGGED but has no ANSWER to "how long do we keep this". When a review finds one half missing, the fix ships both halves in the same change, or explicitly defers the second half with a named migration/ticket, never silently.

**Readings derived from the document inherit its posture (migration 115).** Party names/CPFs, creditor and instrument read OUT of a matrícula act (`matricula_ato_detalhes`) are the same personal data as the text: a route returning them without the text logs `detalhes_view` in `imovel_documento_acessos` (as 111 logs `text_view`), and `purgar_texto_expirado` deletes them with the transcription — retention follows the `imovel` surface, never outlives the source.

**LGPD flag filed for this class:** matrícula transcription text (CPF, estado civil, cônjuge of every owner in the chain of title) — basis Art. 7 V (cumprimento de obrigação legal, corretor de imóveis) + Art. 7 IX (legítimo interesse — evidenciar o negócio), retention per the `documento_retencao_politicas` "imovel" surface (§2 above), LLM transcription of the CPF-bearing PDF is itself a processing operation under Art. 5º X. See `noctus.dev.lgpd_flag` output for `app/modules/matriculas/service.py::processar_extracao`.

**Reference implementation:** `products/therapy-platform/backend/app/services/ai_pipeline.py` — `_notify_therapist_ai_skipped(...)` helper + `try/except AIConsentRequired` blocks around each AI step in `process_session_end`, `on_observation_change`, `on_patient_note_change`. Tests in `tests/services/test_ai_pipeline_service.py § TestPatientConsentGuards` show the granted-path autouse fixture pattern + per-test selective-revoke pattern.

## 11. Withheld-then-activated identity documents (rg/cpf, social-wiring, 2026-09)

A data category can be **built, wired end-to-end, and deliberately not turned on** — migration `057_card_hub_documentos.sql` seeded `cliente_documento_tipos.rg`/`.cpf` with `ativo = false` explicitly *because* the intake below had not been filed yet, not because the code was incomplete. `identidade_extracao_service.TIPOS_EXTRAIVEIS` already listed both types the whole time; the single `ativo` gate at upload (`documentos_service._require_tipo_documento`) was the only thing stopping either from ever reaching storage or the extraction pipeline. **The register entry for a withheld category belongs here, filed BEFORE the flip, so the activation migration only ever needs to point at it — never re-derive it.**

**Register entry:**

| Field | Value |
|---|---|
| Data category | `identidade` — RG number, CPF number, and (when the same document states them) nome oficial / data de nascimento / estado civil. Direct personal identifiers, Art. 5 I/II. |
| Purpose | Civil qualification (qualificação civil) of the parties on the Promessa de Compra e Venda — the F5 contract generator (`card_hub/contrato_gerador`) requires it before a contract is `pronto`. |
| Retention | 1825 days (5 years) — the SAME window every other `cliente_documento_tipos` row already carries (migration 057); the activation migration does not touch `retencao_dias`. |
| Legal basis | Art. 7 V — execução de contrato do qual o titular é parte, ou de procedimentos preliminares relacionados a ele (the qualificação civil clause the contract generator gates on). |
| Access logging | `cliente_documento_acessos`, already wired — `acao` in `view` / `extract` / `delete` (migration 057/068), unchanged by activation. |
| Owner decision | User, 2026-09-16 (roadmap `social-wiring-contract-automation-2026-09.md`, question Q-identity-docs). |

## 12. Public storage buckets bypass RLS entirely (erp-certidoes leak, 2026-09-17)

`erp-certidoes` — 102 objects, 21MB of certidões carrying CPF, full names,
and debt/restriction findings — and `erp-geral` were declared `public =
true` in `products/erp-imobiliario/backend/migrations/001_erp_
imobiliario.sql` + `011_storage_buckets.sql`. Anyone with (or able to
guess/enumerate) an object URL could fetch a certidão fully
unauthenticated — no auth header, no session, nothing.

**🔴 The keeper-principle lesson: "RLS is enabled" is a FACT about the
table, not a GUARANTEE about the data.** `storage.objects` had RLS enabled
with 17 policies — org-scoped, correctly written, the same pattern this
file's own §2–§3 lens would have approved. They gave **zero** protection,
because Supabase Storage serves a **public** bucket's objects via the
`/object/public/{bucket}/{path}` route, and that route does not evaluate
`storage.objects` RLS **at all** — only `/object/authenticated/...` and
`/object/sign/...` do. The LGPD keeper lens (§1) is "does this architecture
protect personal data", not "is RLS turned on somewhere near this data" —
the bucket's `public` flag is a SEPARATE gate the RLS policies cannot see
past, in either direction. A reviewer who checked "RLS enabled? yes, 17
policies, org-scoped, looks right" and stopped there would have signed off
on the leak.

**The generalization.** Any storage layer with more than one access
route — public URL, signed URL, authenticated RLS-checked read — has to be
audited on EVERY route, not the route the reviewer happens to think of
first. A single wrong flag on the BUCKET (not a row, not a policy) silently
overrides every RLS policy on every OBJECT in it. This is the storage
analogue of `check_status_pagina_role_parity`'s lesson
(`KB § PATTERNS/frontend/status-pagina-dev-visibility.md`) — a filter
upstream of RLS (there: the SELECT policy predicate; here: the bucket's
own `public` column) can make correctly-written downstream RLS
irrelevant.

**Fix + gate — owner directive: NO exception, ever, not even with
explicit permission.** Live buckets flipped private 2026-09-17. Forward
migration `048_storage_no_public_buckets.sql` codifies it (001/011 stay
immutable — see `KB § PATTERNS/backend/database-rls.md § Storage buckets —
never public` for the full mechanism). Two-legged gate, both blocking,
neither skippable, neither with an override: static
`noctus.dev.compliance.check_storage_bucket_public` (pre-commit) + live
`noctus.dev.check_storage_no_public_buckets` (wired into
`predeploy_check`). This is the ONE keeper on the platform explicitly
carrying no allowlist / suppression marker / accept-with-rationale escape
hatch — a public bucket is never the correct answer, so there is no
rationale that could make one acceptable.

**LGPD flag filed for this class:** certidão PDFs (CPF, nome completo,
débitos/restrições) held in `erp-certidoes` — basis Art. 7 V (cumprimento
de obrigação legal/regulatória, due-diligence imobiliária), retention per
the certidões feature's own lifecycle (deleted with the consulta —
`app/routers/certidoes.py::excluir_consulta` /
`_delete_storage_files`), access now exclusively via short-TTL signed URL
minted at read time — never a persisted or public link. See
`KB § PATTERNS/backend/database-rls.md § Storage buckets — never public`
for the canonical pattern.

**Activation ships as data, never as code.** `119_cliente_identidade_ativacao.sql` is a single `UPDATE ... SET ativo = true WHERE tipo_documento IN ('rg', 'cpf')` — no `CREATE TABLE`, no `ALTER TABLE`, no new CHECK. The lesson generalizes: when a category is withheld pending an intake, wire everything downstream of the gate FIRST (extraction, retention, access log) and leave literally one boolean for the activation migration to flip once the register entry above exists — a withheld category with unfinished downstream wiring would make "flip the flag" the wrong migration to write.
