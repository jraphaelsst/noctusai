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

## 5. The `noctusai_lgpd_flag` tool

When developing a feature that touches personal data and you're unsure whether an approach meets LGPD, **flag it**. The flag is a record, not a block — the code still ships. A future review picks up the flag as a checklist item before the feature can call itself "done".

```
# CLI
python mcp/noctusai/cli.py --lgpd-flag \
    --code-path "products/therapy-platform/backend/app/services/summary_service.py:85" \
    --concern "patient-transcript-in-prompt" \
    --reason "Full session transcript embedded in OpenAI prompt; request body logged at INFO level if debug flag on." \
    --mitigation "Redact patient-identifiable tokens before the LLM call; drop the request-body log."

# MCP tool
noctusai_lgpd_flag(
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

Call `noctusai_lgpd_flag` whenever you:

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
- **`KNOWLEDGE-BASE/CONTEXT/PATTERNS/database-rls.md`** — RLS policy templates. Every RLS design is an LGPD statement — re-read it when building one.
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

**Reference implementation:** `products/therapy-platform/backend/app/services/ai_pipeline.py` — `_notify_therapist_ai_skipped(...)` helper + `try/except AIConsentRequired` blocks around each AI step in `process_session_end`, `on_observation_change`, `on_patient_note_change`. Tests in `tests/services/test_ai_pipeline_service.py § TestPatientConsentGuards` show the granted-path autouse fixture pattern + per-test selective-revoke pattern.
