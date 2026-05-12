# LLM Tool-Call Audit Rollout — Project Document

> **This is a living document, not a rigid checklist.** Revise phases as discovery happens.
> See `KB § PATTERNS/llm-tool-audit.md` for the audit primitive shape +
> `KB § 01-PHILOSOPHY.md § No silent errors` for why missing audit rows are silent debt.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11 (Phase 0 ✅ — discovery shipped by Engineer LLM-P0)
- **Status:** Phase 0 complete; Phase 1 ready (recipe + reference-adoption parity using media-scheduling as canonical)
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com) · Claude Opus 4.7
- **Related docs:**
  - `KB § PATTERNS/llm-tool-audit.md` — the audit primitive (`tool_call_audits` table, `AuditRecord`, `make_audit_writer`, LGPD redaction)
  - `seed/lib/backend/noctusai_lib/domain/ai/tool_audit.py` — canonical primitive
  - `seed/lib/backend/noctusai_lib/domain/ai/__init__.py` — `register_feature` / `consent_required` / `persist_output` (audit-adjacent)
  - `products/mailing/projects/mailing-wiring/PROJECT.md` §5.2.2 M-4 + §7 Q7 — originating mention
  - `KB § PATTERNS/accept-with-rationale.md § _safe_jsonable` — best-effort-by-contract entry (downstream BI consideration)
- **Project slug:** `llm-tool-audit-rollout`
- **Lives at:** `projects/llm-tool-audit-rollout/` (cross-product platform rollout)

---

## 1. Context & Purpose

The seed-lib ships an LLM tool-call audit primitive (`tool_call_audits` per-product table + `AuditRecord` + `make_audit_writer` + `_safe_jsonable`) per `KB § PATTERNS/llm-tool-audit.md`. The primitive is **best-effort by contract** (an audit-write failure must never break the user-facing tool dispatch) and ships with LGPD redaction hooks.

**Gap:** known LLM-calling products do NOT wire the audit writer:

- **mailing** — 7 LLM calls in `routers/ai.py` (via `ai_service` + `segmentation_service`) — Phase 0 audit `mailing-wiring` (2026-05-11) confirmed no `make_audit_writer` / `AuditRecord` integration. Recorded as M-4 in `products/mailing/projects/mailing-wiring/PROJECT.md`.
- **therapy** — Similar gap suspected (LLM calls in care plan + intake flows). Not yet audited.
- **ERP / personal-finance** — Similar gap suspected (LLM features for narrative + AI advisory). Not yet audited.

Each unaudited LLM call is a silent observability hole: no row in `tool_call_audits` means LGPD-relevant prompt + response data flows through the system without a query-able trail. The primitive exists; rollout is the gap.

**The win looks like:** every LLM tool-call in every product writes a row to its product-schema `tool_call_audits` table, with LGPD redaction applied per the registered feature, and the seed-lib `_safe_jsonable` fallback covers the unserializable edge cases without raising.

---

## 2. Confirmed constraints

To be captured during interrogation at Phase 0 kickoff. Provisional from mailing-wiring Q7 discussion:

- **Best-effort contract preserved** — audit writer must never break the user-facing tool dispatch (per `_safe_jsonable` accept-with-rationale entry).
- **LGPD redaction is per-feature** — each `register_feature(...)` call declares its own `redact_arguments` + `redact_result` lambdas. No global default beyond "log nothing structured" if redaction is unspecified.
- **Cross-product scope** — at least mailing + therapy + ERP + PF need audit-writer adoption. The N count drives recurrence-rule fire.

---

## 3. Design principles

1. **Seed-first.** Audit primitive lives in seed; per-product code is the registration + redaction + wiring only.
2. **No silent errors.** Each LLM call in each product either writes an audit row OR has an explicit `# accept-with-rationale: <reason>` inline pointer.
3. **LGPD-first.** Redaction wiring is required, not optional — the audit table holds personal-data-touching prompts.
4. **Per-product migration is mechanical.** The pattern is the same across all products; the rollout should follow a uniform recipe (Phase 1 ships the recipe, Phases 2+ apply it).

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every product?** YES — `make_audit_writer(db, table_class)` + `AuditRecord` + per-feature redaction. Uniform shape.
2. **Is the data source product-specific?** PARTIAL — the audit ROWS land in per-product `<schema>.tool_call_audits` tables (data is product-specific), but the writer + record shapes are uniform.
3. **Is the placement product-specific?** PARTIAL — registration happens in `app/services/ai_consent_features.py` per product; writer wiring happens wherever the LLM tool dispatch lives.
4. **Is the visibility / permission rule the same?** YES — RLS via service_role_bypass + org_id, uniform across products.
5. **Does the seam already exist in seed?** YES — fully shipped at `noctusai_lib.domain.ai.tool_audit`. Rollout = adoption, not seed-build.
6. **Default-on or opt-in?** DEFAULT-ON — every `register_feature` call SHOULD wire a `make_audit_writer`; opt-out only via explicit accept-with-rationale.

**Litmus — per-product code count this design requires:** **~5 lines per product** (writer wiring in the LLM-dispatch entry + per-feature `redact_*` lambdas in `ai_consent_features.py`). Acceptable per the "product-specific data wiring around a seed-shaped container" litmus checkbox.

---

## 4. Scope

**In scope:**

- Audit-writer adoption in mailing (7 calls), therapy (TBD count), ERP (TBD count), PF (TBD count). Phase 0 confirms counts.
- Per-product `tool_call_audits` table migration (additive 002+ migration per product) if the table is not already created.
- Per-feature LGPD redaction wiring via `register_feature(..., redact_arguments=..., redact_result=...)`.
- Tests: each product gets a smoke test confirming the writer fires + a redaction unit test confirming sensitive fields are scrubbed.
- Methodology: a uniform recipe captured at `KB § PATTERNS/llm-tool-audit.md § Per-product rollout recipe`.

**Out of scope:**

- BI / dashboard surface on top of `tool_call_audits` (separate "audit observability" project).
- Backfill of historical LLM calls (no historical data exists; rows only appear after rollout).
- Cross-product `tool_call_audits` view (left for the BI surface project).
- The `_safe_jsonable` strict-mode flip (deferred per existing accept-with-rationale entry).

---

## 5. Architecture / Data Model

### 5.1 Seed-lib (already shipped, no work needed)

- `noctusai_lib.domain.ai.tool_audit.AuditRecord` — dataclass capturing one tool-call invocation
- `noctusai_lib.domain.ai.tool_audit.make_audit_writer(db, table_class)` — factory returning a coroutine for writing rows
- `noctusai_lib.domain.ai.tool_audit._safe_jsonable(value)` — best-effort coercion (per accept-with-rationale entry)

### 5.2 Per-product wiring (the rollout)

1. Confirm `tool_call_audits` table exists in product schema (add migration if not).
2. Add `make_audit_writer(...)` instantiation at app-startup (or per-request via dependency).
3. Wrap each LLM dispatch site with `audit_writer(record)` call (best-effort try/except inside the writer).
4. Add `redact_arguments=` + `redact_result=` to each `register_feature(...)` call.
5. Smoke test asserts a row lands in `tool_call_audits` after a feature invocation.
6. Redaction unit test asserts sensitive fields (emails, content bodies) are scrubbed.

---

## 6. Phase plan (revised post-Phase 0 — 2026-05-11)

- **Phase 0 — Discovery + cross-product gap audit.** ✅ **DONE 2026-05-11** (Engineer LLM-P0). Tabulated 7 products with LLM dispatch (mailing=7, therapy=4, erp=9, PF=3, daily-life=3, core=1, media-scheduling=1). Only media-scheduling has audit wiring (reference adopter). Zero products wire LGPD redaction. See §11 for the full table. **Improvements:** seed-lib should ship a `tool_call_audits.sql.template` (verified at `seed/lib/backend/noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template`) so per-product migrations call it via `noctusai_lib.sql` instead of inlining — pre-emptive lift since N=7 adopters guaranteed. Surfaced redaction-wiring N=0 across **all 35 `register_feature` calls** as the highest-impact gap (Q2 in §7 becomes mandatory).
- **Phase 1 — Recipe + reference-adoption parity** (reference = media-scheduling, already shipped). Document the per-product rollout in `KB § PATTERNS/llm-tool-audit.md § Per-product rollout recipe` using media-scheduling's `audit_hook.py` + `models/tool_call_audit.py` + migration block as the canonical shape. No new product wiring this phase — just lock in the recipe.
- **Phase 2 — ERP rollout** (highest LLM-site count = 9 + 10 `register_feature` calls, biggest single-product win; full `ai_service.py` already in one file = surgical wrap point).
- **Phase 3 — Mailing rollout** (7 LLM sites + 7 `register_feature` calls; mailing-wiring M-4 was the originating gap — close it next).
- **Phase 4 — Therapy + PF + daily-life + core combined rollout** (smaller — 4+3+3+1 sites, 2+3+3+1 features). Same recipe; can ship in one phase as a sweep.
- **Phase 5 — Final keeper + close.** Run keeper + `noctus.hound.scan` to confirm no remaining LLM dispatches lack audit wiring. File a detector follow-up (`check_llm_audit_wired` + `check_register_feature_has_redaction`) so the codification-pipeline closes the drift loop. adconnect + dev-team explicitly carved out (no LLM dispatch).

---

## 7. Open questions

**Q1 — Migration shape for `tool_call_audits` table.** Does each product own its own migration file, or does the seed-lib ship a SQL template (`noctusai_lib.sql.tool_call_audits_table(schema)`) that products invoke from their numbered migration?
- *Recommendation:* lift the migration template to seed-lib if N≥3 products need to add the table (recurrence rule). Otherwise inline per product.

**Q2 — Redaction defaults vs explicit-per-feature.** Should `register_feature(...)` require explicit `redact_*` args (TypeError if missing), or default to "log nothing structured" (current shape)?
- *Recommendation:* require explicit redaction args + add a `redact_passthrough()` helper for features that genuinely store no sensitive data — forces every feature author to think about LGPD. File as a seed-lib enhancement in Phase 1.

**Q3 — Audit row retention.** How long do `tool_call_audits` rows live? LGPD principle says "as long as the business reason justifies." For audit observability, 90 days is a common default.
- *Recommendation:* Phase 1 ships a per-product cron job (via `noctusai_lib.api.scheduler`) that prunes rows older than `audit_retention_days` (default 90). This is itself cross-product → seed-lib helper.

---

## 8. Risks / tradeoffs

- **Writer back-pressure.** If the audit DB is slow, every LLM call gets slower. Mitigation: writer is best-effort + non-blocking (already shipped — `_safe_jsonable` + async write).
- **LGPD redaction misses.** A feature author forgets to redact a sensitive field → personal data leaks into the audit table. Mitigation: Q2 (require explicit redaction args) + per-product redaction unit tests.
- **Rollout duration.** 4 products × ~5 lines each + tests + redaction = ~2-3 sessions. Acceptable.

---

## 9. Out of scope (reaffirm)

(See §4.)

---

## 10. Verification commands

```bash
# Per-product pytest (run after each product's rollout phase)
cd products/<slug>/backend && pytest tests/ -q -k audit

# Keeper rollup (after Phase 5)
python mcp/noctusai/cli.py --review --worktree-path "$PWD"

# Audit-writer detector (Phase 5 ships this)
python mcp/noctusai/cli.py --check-llm-audit-wired --worktree-path "$PWD"
```

---

## 11. Change log

- **2026-05-11 — Filed (Engineer MAI-P2)**. Surfaced as Q7 in `products/mailing/projects/mailing-wiring/PROJECT.md` Phase 0 (M-4 gap row); mailing-wiring scope excluded the rollout to keep the project focused. This project is the cross-product follow-up. Provisional design captured; Phase 0 discovery pending.

- **2026-05-11 — Phase 0 complete (Engineer LLM-P0 / LLM-AUDIT-DISCOVERY)**. Read-only cross-product gap audit shipped. Findings tabulated below.

### Phase 0 — Per-product gap audit ✅ (2026-05-11)

**Improvements:** none identified — discovery-only phase, no engineering churn. Findings tabulated into §6 Phase 1-5 plan (see table below); follow-up project filings deferred to per-phase close per parent project's standard execution.

LLM-dispatch site count includes direct `noctusai_lib.integrations.llm.chat_completion` calls. `digest_narrative()` (4 callers — mailing/PF/daily-life/core) wraps `chat_completion` internally and is counted once at the call-site, not at the wrapper. Embedding / transcription / vision calls (`generate_embedding` / `transcribe_audio` / `analyze_image`) excluded from the chat-completion count — they are separate LLM modalities that the audit primitive also covers but call sites are colocated.

| Product           | LLM-dispatch sites | `tool_call_audits` migration | `make_audit_writer` wired | LGPD redaction wired |
|-------------------|--------------------|------------------------------|---------------------------|----------------------|
| mailing           | 7 (chat) + 1 emb   | **missing**                  | **missing**               | **missing** (7 features) |
| therapy-platform  | 2 (chat) + 1 img + 1 audio + N emb | **missing**     | **missing**               | **missing** (2 features) |
| erp-imobiliario   | 9 (chat) + N emb + 3 direct-OpenAI HTTP | **missing** | **missing**         | **missing** (10 features) |
| personal-finance  | 3 (chat — incl. monthly_narrative_service via digest) | **missing** | **missing** | **missing** (3 features) |
| daily-life        | 3 (chat — incl. weekly_review_service via digest) | **missing** | **missing**   | **missing** (3 features) |
| adconnect         | **0** — no LLM use | n/a (carve-out)              | n/a                       | n/a (no consent file) |
| core              | 1 (chat — audit_digest_service via digest) | **missing**          | **missing**               | **missing** (1 feature) |
| **media-scheduling** | 1 (direct `OpenAI()` via agno worker) | **present** (002_initial_schema.sql L295-) | **present** (audit_hook.py + models/tool_call_audit.py + workers/conversation_worker.py L191) | **n/a** — no `register_feature` consent layer (worker-driven chatbot, no UI consent flow) |
| dev-team          | **0** — orchestrates external agno LLM calls, no direct dispatch | n/a (carve-out) | n/a            | n/a                  |

**Concrete file:line refs (top 5 per product, dispatch sites only):**

- **mailing** — `app/services/ai_service.py:55,100,138,190,245`; `app/services/segmentation_service.py:155`; `app/services/campaign_debrief_service.py:93` (via `digest_narrative`); `app/services/segmentation_service.py:215` (`generate_embedding`).
- **therapy-platform** — `app/services/summary_service.py:93`; `app/services/longitudinal_service.py:83`; `app/services/attachment_service.py:159` (`analyze_image`), `:172` (`transcribe_audio`); `app/services/transcription_service.py:68` (`transcribe_audio`).
- **erp-imobiliario** — `app/services/ai_service.py:83,140,223,316,409,497,561,649,725` (9 sites); `app/routers/configuracoes.py:32` + `app/services/matricula_service.py:54` + `app/services/certidoes_service.py:397` (3 direct-OpenAI HTTP calls — NOT going through seed `chat_completion`, so seed cache/budget/audit hooks bypassed; flag as a structural fork to fix in Phase 2).
- **personal-finance** — `app/services/ai_service.py:90,185`; `app/services/monthly_narrative_service.py:100` (via `digest_narrative`).
- **daily-life** — `app/services/ai_service.py:50`; `app/services/daily_brief_service.py:178`; `app/services/weekly_review_service.py:87` (via `digest_narrative`).
- **core** — `app/services/audit_digest_service.py:112` (via `digest_narrative`).
- **media-scheduling** — `app/workers/conversation_worker.py:323` (`OpenAI()` client construction; agent dispatches inside `_run_agent`). Audit row written at `:191` via `AuditRecord(...)` + `audit_hook.write(record)`.

**Carve-outs:**

- **adconnect** — no LLM dispatch in `products/adconnect/backend/app/`. No `ai_consent_features.py`. No `chat_completion` / `OpenAI` / `Anthropic` imports. Not in rollout scope.
- **dev-team** — no direct LLM dispatch; orchestrates external agno calls (which run in `dev_team/` engine, not in product backend). Agno's own telemetry covers tool-calls. Confirmed by absence of `chat_completion` import, no `ai_consent_features.py`, no `OpenAI()` construction. Not in rollout scope; revisit when agno bridges into product code paths.

**Three structural findings beyond the per-product gap table:**

1. **ERP has 3 direct-OpenAI HTTP calls (`httpx.post → api.openai.com/v1/chat/completions`)** bypassing the seed `chat_completion` wrapper — this dodges seed cache + budget + (future) audit. Fix at Phase 2: refactor to `chat_completion` before wiring the audit writer (otherwise audit coverage is structurally incomplete).
2. **Zero products wire `redact_arguments=` / `redact_result=` in any `register_feature` call** (35 calls total across 6 products checked). The seed primitive `_safe_jsonable` is a defensive fallback, not a redaction strategy — current state means **PII flows raw into prompts and (when the audit writer lands) into `tool_call_audits.arguments`/`result`**. This is the highest-impact LGPD gap surfaced. Phase 1 recipe MUST require explicit redaction args per `register_feature` call (Q2 in §7 becomes mandatory, not optional).
3. **`tool_call_audits` migration recurrence = 7** (every product that needs the table). The seed template at `seed/lib/backend/noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template` exists; per-product migrations should call it via a `noctusai_lib.sql` helper (consistent with `prelude(schema)` + `updated_at_trigger(table)` pattern). Q1 in §7 resolves to **yes, lift to seed-lib helper** — N=7 ≥ recurrence threshold.

**Recommended Phase ordering (post-Phase 0):**

1. Phase 1 — recipe + reference-adoption parity → **media-scheduling** (already shipped; just codify).
2. Phase 2 — **erp-imobiliario** (highest LLM-site count = 9 + 3 direct-HTTP refactor + 10 register_feature calls; biggest single-product win).
3. Phase 3 — **mailing** (7 sites + 7 features; closes the originating M-4 gap).
4. Phase 4 — **therapy + personal-finance + daily-life + core combined** (sweep; 4+3+3+1 sites, 2+3+3+1 features).
5. Phase 5 — keeper detectors (`check_llm_audit_wired` + `check_register_feature_has_redaction`) + close.
