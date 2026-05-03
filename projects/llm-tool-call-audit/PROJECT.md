# llm-tool-call-audit — Project Document

> **This is a living document, not a rigid checklist.**
>
> **Write for a zero-context reader.** Inline context in §1, quote the user in §2, name files with paths in §5, pair every §7 Open Question with an evidence-backed recommendation, make §10 commands copy-paste ready.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** ✅ **CLOSED** 2026-05-03 — Phases 0-3 + 5 + 6 ✅; Phase 4 (wire-into-chatbot-framework) deferred until `projects/whatsapp-seed-absorption/` Phase 5 lands the LLM dispatcher that consumes the writer. Lib code + migration template + 2 KB docs shipped; first product consumer = imobi-scheduling-bot via the chatbot framework.
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Related docs:** `KB § 04-SHARED-LIBRARY.md § llm/`, `projects/whatsapp-seed-absorption/PROJECT.md` (depends on this for end-to-end completeness; preserves audit-row schema verbatim from sibling), sibling reference at `~/Documents/repository/NoctusAI/whatsapp-google-scheduling/app/services/openai/tools/registry.py`.
- **Project slug:** `llm-tool-call-audit` — cross-cutting seed-lib concern. Lives at `projects/<slug>/`.

---

## 1. Context & Purpose

Sibling's WhatsApp scheduling bot ships a `ToolCallAudit` model populated by `ToolRegistry.dispatch()` at `app/services/openai/tools/registry.py:37-87` (best-effort: audit failure does not break dispatch). Every LLM tool call captures: caller, tool name, arguments, result, error, duration_ms, started_at, correlation_id, gpt_call_id. Joinable by correlation_id + gpt_call_id, so an entire conversation's tool sequence is reconstructable.

We have **nothing equivalent** in `noctusai_lib.llm`. Tool calls our products make are unobservable — when a tool produces a wrong answer or fails, there's no trail. This is the highest-leverage observability gap for our AI features.

This project lifts the audit pattern into `noctusai_lib.domain.ai.tool_audit`, with the dispatch wrapper available as a lib helper any product can compose. The chatbot framework lift in `projects/whatsapp-seed-absorption/` depends on this for end-to-end completeness — the framework's LLM dispatcher accepts an optional `audit_writer` callable, and that callable is what this project ships.

---

## 2. Confirmed constraints

- **Highest-leverage observability** — analyst's framing accepted by user (item #1 in absorption priority list). *(Drives "land first" priority.)*
- **Best-effort design preserved** — sibling's pattern lets audit-row write fail silently (logged) without breaking dispatch. We preserve that — audit existing for visibility, not correctness. *(Drives §3 principle 2.)*
- **No retention TTL in v1** — sibling has no TTL on the audit table. Carry that limitation forward; document explicitly. Retention is a separate follow-up project once we have signal on table growth. *(§4 out-of-scope.)*

---

## 3. Design principles

1. **Audit is a side effect, not a guarantee.** Failure to write the audit row never blocks tool dispatch.
2. **Schema fidelity to sibling.** Field names, types, joinable key shape (correlation_id + tool-call-id) all match. *Why:* future migrations of sibling-style projects into our platform should round-trip without re-mapping.
3. **Audit is opt-in at the dispatcher level, default-on at the consumer level.** The lib provides `default_audit_writer(db)` which products wire. A product can pass a no-op for audit-disabled environments (local dev, certain test configs).
4. **One row per tool call attempt** — successful, failed, or "unknown tool" all generate rows. Silence is itself a signal worth absent rows in.

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

1. **Is the contract identical for every product?** YES.
2. **Is the data source product-specific?** NO — universal (every LLM-tool-using product writes to the same shape).
3. **Is the placement product-specific?** NO — `noctusai_lib/domain/ai/tool_audit.py`.
4. **Is the visibility / permission rule the same?** YES — uniform; per-product DB owns its rows.
5. **Does the seam already exist in seed?** PARTIAL — `noctusai_lib/domain/ai/` exists; `tool_audit.py` is new.
6. **Default-on or opt-in?** OPT-IN at the lib level (consumers wire); DEFAULT-ON at the consumer level (when a product wires LLM dispatch, it wires audit alongside by convention).

**Litmus — per-product code count this design requires:** [x] **1 line** — opt-in `audit_writer=default_audit_writer(db)` argument in the product's LLM dispatcher wiring. Acceptable.

**Phase plan implications:** §6 phases work in `noctusai_lib/domain/ai/` and `KB`. **No phase walks through products.**

---

## 4. Scope

**In scope:**

- `noctusai_lib/domain/ai/tool_audit.py` — `ToolCallAudit` SQLAlchemy model + `default_audit_writer(db)` factory + tests.
- DB migration template (Alembic-shaped) for products adopting it.
- Convention documentation in `KB § PATTERNS/llm-tool-audit.md`.
- Reference port of sibling's `ToolRegistry.dispatch()` shape into the chatbot framework lift's `llm_dispatcher.py` (the **call site** of the audit writer; the model + writer themselves live here).

**Out of scope (for now — with reason):**

- Retention TTL / archival — separate follow-up project once we have growth signal.
- Cross-product BI dashboards — needs a metrics sink architecture decision first.
- Audit query API / endpoints — products that need querying build them in their own routers; lib supplies the model.
- Correlation-ID propagation through the LLM call stack — already handled by `noctusai_lib/primitives/_correlation.py`; this project assumes it's working.

---

## 5. Architecture / Data Model

### 5.1 The there → here map

| There (`whatsapp-google-scheduling/`) | Here (`noctusai/seed/backend/lib/noctusai_lib/`) | Notes |
|---|---|---|
| `app/services/openai/tools/registry.py:ToolCallAudit` (SQLAlchemy model) | `domain/ai/tool_audit.py::ToolCallAudit` | Verbatim schema port. |
| `app/services/openai/tools/registry.py:dispatch()` (audit-row write side) | `domain/ai/tool_audit.py::default_audit_writer(db)` callable factory | Audit-write logic only; the dispatch loop itself lives in the chatbot framework's LLM dispatcher (`projects/whatsapp-seed-absorption/`). |
| Sibling's audit-row test coverage (`tests/test_tool_registry.py` if present) | `seed/backend/lib/tests/domain/ai/test_tool_audit.py` | Phase 0 confirms the test exists in sibling. |

### 5.2 Schema (verbatim from sibling, adapted to noctusai_lib idioms)

```python
# noctusai_lib/domain/ai/tool_audit.py (sketch)
class ToolCallAudit(Base):
    __tablename__ = "tool_call_audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    correlation_id: Mapped[str | None] = mapped_column(index=True)
    gpt_call_id: Mapped[str | None] = mapped_column(index=True)
    tool_name: Mapped[str]
    tool_call_id: Mapped[str | None]
    arguments: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None]
    status: Mapped[str]  # "success" | "failure" | "unknown_tool"
    duration_ms: Mapped[int]
    started_at: Mapped[datetime]
    user_id: Mapped[int | None] = mapped_column(index=True)
```

### 5.3 Writer contract

```python
# noctusai_lib/domain/ai/tool_audit.py (sketch)
def default_audit_writer(db: Session) -> AuditWriter:
    """Returns a callable an LLM dispatcher can hand a finished tool-call to."""
    def write(record: AuditRecord) -> None:
        try:
            row = ToolCallAudit(...from record...)
            db.add(row)
            db.commit()
        except Exception:
            logger.warning("Failed to persist tool audit row", exc_info=True)
            # best-effort — never raise to caller
    return write
```

The chatbot framework's `llm_dispatcher.py` accepts `audit_writer: AuditWriter | None = None`. When present, it calls `audit_writer(...)` after each tool dispatch.

---

## 6. Implementation phases

### Phase 0 — Audit before any code lands ✅ (executed 2026-05-03)

- [x] Read sibling's `app/services/openai/tools/registry.py` end-to-end. Confirm schema fields + write path. → **Done.** Pattern locked: `ToolRegistry.dispatch()` writes one row per call (success / failure / unknown_tool); audit failure logged + swallowed; sibling stores arguments/result as TEXT (JSON-stringified), uses `correlation_id + gpt_call_id + conversation_id + user_id` joinability. We use Postgres JSONB instead (native, indexable).
- [x] Identify whether sibling has dedicated tests for audit persistence. → **Yes.** `whatsapp-google-scheduling/tests/test_tool_call_audit.py` covers success, failure, unknown_tool, and audit-DB-failure paths. Ported the test shape into our lib tests.
- [x] Verify `noctusai_lib/domain/ai/` exists; confirm what's there. → **Exists** with `consent.py` + `outputs.py`. No collision; lib doesn't ship SQLAlchemy ORM models (per the cross-product LGPD block — products own their DB schemas). Adjusted Phase 1 scope: the lib ships `AuditRecord` dataclass + writer factory, products own the ORM model.
- [x] Check whether any product already has an ad-hoc tool-call log. → **No.** No product currently has `tool_call_audit*` / `ToolCallAudit` references (excluding `node_modules` matches in core/frontend).

**Improvements:**
- Sibling stores arguments/result as TEXT (JSON-stringified) for cross-DB portability (their stack supported SQLite for tests). We're Postgres-only via Supabase, so JSONB is the native fit. **Triage: refactor (applied)** — schema deviates from sibling's TEXT in favor of JSONB; documented in KB doc + migration template.
- The project doc Phase 1 sketch had the lib ship a SQLAlchemy ORM model directly. After Phase 0 audit of sibling `noctusai_lib/domain/ai/` we found existing modules (`consent.py`, `outputs.py`) keep ORM bindings out of the lib by design — products own DB. **Triage: refactor (applied)** — scope shifted to dataclass + writer factory + migration template; products define their own ORM class. Adoption boilerplate captured in KB doc §3.

### Phase 1 — Model + writer ✅ (executed 2026-05-03)

- [x] Create `seed/backend/lib/noctusai_lib/domain/ai/tool_audit.py` with `ToolCallAudit` model + `default_audit_writer(db)`. → **Adapted per Phase 0 audit:** ships `AuditRecord` dataclass + `AuditWriter` Callable type + `make_audit_writer(db, table_class)` factory + `_safe_jsonable` helper + `now_utc()` convenience. SQLAlchemy `Session` import is `TYPE_CHECKING`-guarded — lib doesn't require sqlalchemy at runtime/test time.
- [x] Provide `AuditRecord` dataclass (the in-memory record passed to the writer). → **Done.** Slots-true dataclass with `tool_name`, `status`, `duration_ms`, `started_at` required; everything else (correlation_id, gpt_call_id, tool_call_id, conversation_id, user_id, arguments, result, error) optional. `to_row_kwargs()` method handles the safe-jsonable round-trip.
- [x] Tests: success path + DB-failure path (must not raise) + unknown-tool path. → **Done.** 9 tests at `seed/backend/lib/tests/domain/ai/test_tool_audit.py`: round-trip, safe_jsonable variants (dict, None, Pydantic-like, repr fallback), success persists row, DB-failure logs WARNING + does NOT raise, unknown_tool path, now_utc returns aware datetime. All green: `pytest seed/backend/lib/tests/domain/ai/` = 9 passed.

**Improvements:**
- `_safe_jsonable` falls through `json.dumps(default=str)` so Pydantic models / dataclasses / Decimals round-trip through JSON cleanly. Non-serializable values (circular refs, etc.) wrap as `{"_repr": repr(value)}` with a debug log — audit row still lands. Caught a subtle case during testing: a default-str fallback returns a string (Pydantic-like → `"Sentinel(value=42)"`), which the test now asserts is acceptable. **Triage: accept-with-rationale** — best-effort means we trade structural fidelity for "row always lands"; documented.
- The lib ships ZERO SQLAlchemy imports at runtime (TYPE_CHECKING-guarded). Tests run without sqlalchemy in the venv (which our MCP venv lacks today). **Triage: refactor (applied)** — keeps lib portable across deployment environments + matches the existing `noctusai_lib.domain.*` style.

### Phase 2 — Migration template ✅ (executed 2026-05-03)

- [x] Provide `noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template`. → **Done.** Postgres / Supabase-native: `JSONB` for arguments/result, `TIMESTAMPTZ` for started_at, `BIGSERIAL` PK, indexes on correlation_id / (user_id, started_at) / tool_name / status / (conversation_id, started_at). `{{SCHEMA_NAME}}` placeholder per `KB § PATTERNS/database-rls.md`. RLS scaffold commented for products to enable + tune. `archived_at` column commented out (retention TTL = `projects/llm-audit-retention/` future hook).
- [x] Document the migration mirroring rule (`KB § PATTERNS/database-rls.md`). → Adoption flow documented in `KB § PATTERNS/llm-tool-audit.md § 3a` (apply via Supabase MCP) — the database-rls.md rule reference is in the template header.

**Improvements:**
- Added a `status` column (`success`/`failure`/`unknown_tool`) with its own index. Sibling didn't have this — they parsed the `error` field for status. Indexed status is much faster for error-rate dashboards (`SELECT status, count(*) GROUP BY status`). **Triage: refactor (applied)** — schema improvement over sibling.
- Added `(conversation_id, started_at)` composite index for per-conversation reconstruction queries. Sibling has only `correlation_id` indexed; conversation reconstruction would be a sequential scan. **Triage: refactor (applied)**.

### Phase 3 — KB pattern doc ✅ (executed 2026-05-03)

- [x] Write `KB § PATTERNS/llm-tool-audit.md`. → **Done.** 8 sections: why-audit (§1), schema (§2), wiring at consumer side incl. ORM model + dispatcher example (§3), status semantics (§4), LGPD redaction at consumer (§5), common queries (§6), what-this-is-NOT (§7), adoption checklist (§8). Cross-references `llm-bot-security.md` for the defense layer.
- [x] Add to `KB § INDEX.md`. → **Done.** Layout tree + Patterns table both updated.
- [x] Add `CLAUDE.md §2 Map` pointer. → **Done.** Patterns list gains a depth pointer line.

**Improvements:**
- The KB doc includes 4 worked SQL queries (per-user 24h trail, failure-rate-per-tool weekly, conversation reconstruction, log-join via correlation_id). Worked queries are quoted-runnable in the BI surface that surfaces in Phase 4 wiring. **Triage: refactor (applied)** — saves consumer projects from re-deriving them.
- Adoption checklist (§8) is a tickable for any product wiring the audit. **Triage: accept-with-rationale** — checklists are where adoption errors get caught early.

### Phase 4 — Wire into chatbot framework ⏳ **DEFERRED**

GATED ON: `projects/whatsapp-seed-absorption/` Phase 5 (the chatbot framework's `llm_dispatcher.py` lands there; that's the call site of `make_audit_writer`).

This project ships the lib code + migration template + KB doc + adoption checklist. The wire-up itself happens INSIDE the chatbot framework lift, where the dispatcher is built. Pulling it forward into this project would either (a) prematurely create the dispatcher (out of this project's scope) or (b) wire against a stub that vanishes when the real one lands — both are wrong shapes.

**When to resume:** when `projects/whatsapp-seed-absorption/` Phase 5 starts, that project's §6 adopts:
1. `from noctusai_lib.domain.ai.tool_audit import AuditRecord, make_audit_writer, now_utc`
2. Wires `audit_writer` parameter into the dispatcher signature.
3. Calls `audit_writer(AuditRecord(...))` after each dispatch — see `KB § PATTERNS/llm-tool-audit.md § 3c` for the exact shape.

- [ ] *(carried to `projects/whatsapp-seed-absorption/` Phase 5)* Coordinate the chatbot framework's `llm_dispatcher.py` to accept `audit_writer: AuditWriter | None = None` and call it after each dispatch.
- [ ] *(carried)* Verify end-to-end: framework Phase 5 tests use the audit writer and audit rows appear.

### Phase 5 — LLM-bot-security KB pattern doc ✅ (executed 2026-05-03)

- [x] Write `KB § PATTERNS/llm-bot-security.md`. → **Done.** Sections: threat model (§1), defense trio — output sanitization + Pydantic-arg validation + rate-limit (§2), confidence thresholds + confirm-then-execute (§3), prompt-injection mitigation — instruction sandboxing + allowlists + output review (§4), baseline checklist (§5), cross-references (§6). Folds the entire sibling `security-hardening` planning artifact into one durable doc.
- [x] Add to `KB § INDEX.md`. Add `CLAUDE.md §2 Map` pointer. → **Done.**
- [x] Cross-reference from `KB § PATTERNS/llm-tool-audit.md`. → **Done.** llm-tool-audit.md § Cross-references points at llm-bot-security.md; llm-bot-security.md §6 points back at llm-tool-audit.md (audit = observation; security = defense).
- [x] First consumers: `projects/imobi-scheduling-bot-creation/` Phase 9 + future bot products use this checklist. → **Captured.** Section §5 names `imobi-scheduling-bot-creation` Phase 9 as the first consumer.

**Improvements:**
- Folded sibling's "security-hardening" planning artifact ENTIRELY into one doc. The sibling's plan was scattered across multiple `.md` files; this consolidates it into a single durable reference that survives sibling deletion. **Triage: accept-with-rationale** — single-doc fold is right shape for a checklist-style rule; KB structure favors one substantive doc over five thin ones.
- The §3 confirm-then-execute pattern surfaces as a strong default for ANY destructive LLM tool, not just scheduling. Captured as the platform default; products override only if they have a clear UX reason. **Triage: accept-with-rationale** — recurrence rule applies if 3+ products override (revisit then).

### Phase 6 — Final verification ✅ (executed 2026-05-03)

- [x] `pytest seed/backend/lib/tests/domain/ai/` — **9 passed, 0 failed**.
- [x] `bash scripts/verify-kb-sync.sh` — **green** (3 new KB docs landed: `llm-tool-audit.md`, `llm-bot-security.md`, INDEX.md updated).
- [x] Three-way sync confirmed. KB ↔ CLAUDE.md ↔ memory: KB has 2 new pattern docs; CLAUDE.md §2 Map has 2 new depth pointers; **memory** does NOT need new entries (per memory rule "Code patterns, conventions, architecture — these can be derived by reading the current project state, not stored in memory"). Existing memory `feedback_lgpd_first.md` already covers the LGPD redaction angle.

**Improvements:**
- Total project surface: 1 lib module (`tool_audit.py`, 175 lines), 1 migration template (~70 lines), 2 KB pattern docs (~250 + ~190 lines), 9 tests. Ratio of doc to code is ~3:1 — reflects the "this is a foundational primitive every future bot uses" framing. **Triage: accept-with-rationale** — the doc cost is upfront; downstream consumers (imobi-scheduling-bot-creation, future bots) avoid re-deriving the schema + wiring + LGPD posture.
- Phase 4 carved out cleanly into `whatsapp-seed-absorption` Phase 5 with the exact import line + wiring shape pre-documented in `KB § PATTERNS/llm-tool-audit.md § 3c`. When that project picks it up, integration is mechanical. **Triage: accept-with-rationale** — clean handoff is what good cross-project carve-outs look like.

---

## 7. Open questions

All open questions resolved 2026-05-03 in batch §7 round (`projects/absorbed-projects-batch/PROJECT.md` Phase 1.a):

1. ~~**Single shared `tool_call_audits` table per product, or namespaced?**~~ → **Decided: per-product table** (recommendation accepted). Each product's DB owns its rows; cross-product BI is a future concern. Aligns with cross-product LGPD block.
2. ~~**Retention default in the migration template?**~~ → **Decided: none in v1**, include commented-out `archived_at` column + index hint so future TTL is cheap. (Default carried.)
3. ~~**LGPD implications with `arguments`/`result` JSON storing PII?**~~ → **Decided: products handling Art. 11 sensitive data (clinical text in therapy) MUST redact those fields before passing to the dispatcher.** Document the pattern in Phase 3 KB doc. Use `noctusai_lgpd_flag(...)` if uncertain. (Default carried.)
4. ~~**Data retention follow-up?**~~ → **Decided: no automatic TTL in v1**; products opt in via a follow-up. File `projects/llm-audit-retention/` once second product consumer surfaces. Imobi-scheduling proposes 90-day raw + permanent aggregated — decision lives in `projects/imobi-scheduling-bot-creation/` §7 Q5. (Default carried.)
5. ~~**GPT confidence thresholds?**~~ → **Decided: out of scope here** — confidence belongs in the LLM dispatcher (chatbot framework), not the audit. Capture pattern in `KB § PATTERNS/llm-bot-security.md` (§6 Phase 5 here). Implementation lives in consumer products. (Default carried.)
6. ~~**Provider-payload audit?**~~ → **Decided: separate concern** — raw provider payloads deserve their own `webhook_events`-style table at consumer level, with its own retention. Not bundled with tool-call audit. Lib does NOT ship a model for this; consumers define their own per-provider shape. (Default carried.)

---

## 8. Dependencies & blockers

- **`projects/whatsapp-seed-absorption/` Phase 5** — its `llm_dispatcher.py` is the first consumer of `default_audit_writer`. Coordinate so the writer interface is set before that phase lands.
- **No infrastructure dependency** — DB is whatever the consuming product uses.

---

## 9. Success criteria

- [ ] `noctusai_lib/domain/ai/tool_audit.py` exists with model + writer + tests.
- [ ] Migration template exists.
- [ ] `KB § PATTERNS/llm-tool-audit.md` exists, indexed, pointed-to from CLAUDE.md.
- [ ] First consumer (chatbot framework lift) wires `default_audit_writer` and rows persist in tests.
- [ ] `KB § PATTERNS/llm-bot-security.md` exists, indexed, pointed-to from CLAUDE.md.

---

## 10. How to use this plan

```bash
# Sibling reference
cat ~/Documents/repository/NoctusAI/whatsapp-google-scheduling/app/services/openai/tools/registry.py

# Lib + tests
pytest seed/backend/lib/tests/domain/ai/

# KB sync
bash scripts/verify-kb-sync.sh
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | Initial project drafted; user confirmed priority #1 (highest observability ROI). | claude-opus-4-7 |
| 2026-05-03 | Added §7 Q4 noting sibling's `provider-payload-audit` and `data-retention` ideas as future-work hooks (raw integration payloads + retention TTL). Captured here as open questions rather than separate projects so the lessons aren't lost when sibling folder is deleted. | claude-opus-4-7 |
| 2026-05-03 | **§7 round closed** (batch Phase 1.a). Decision: per-product `tool_call_audits` table (Q1, user-confirmed). Q2-Q6 accepted at recommended defaults (no v1 TTL, Art. 11 redaction at dispatcher, confidence out-of-scope, provider-payload separate concern). Project status flipped to ⏳ EXECUTING — Phase 0 begins after MCP-server-expansion closes (per user-reordered tier sequence: MCP → LLM-audit → finish). | claude-opus-4-7 |
| 2026-05-03 | **Project CLOSED.** Phases 0-3 + 5 + 6 ✅ shipped; Phase 4 (wire-into-chatbot-framework) deferred to `projects/whatsapp-seed-absorption/` Phase 5 with exact import + wiring shape pre-documented in `KB § PATTERNS/llm-tool-audit.md § 3c`. **Concrete deliverables**: (1) `seed/backend/lib/noctusai_lib/domain/ai/tool_audit.py` (175 lines) — `AuditRecord` dataclass + `AuditWriter` Callable type + `make_audit_writer(db, table_class)` factory + `_safe_jsonable` helper + `now_utc()`. SQLAlchemy `Session` is `TYPE_CHECKING`-guarded — lib has zero runtime sqlalchemy imports. (2) Migration template at `noctusai_lib/domain/ai/migrations/tool_call_audits.sql.template` — Postgres-native JSONB, 5 indexes (correlation_id / (user_id, started_at) / tool_name / status / (conversation_id, started_at)), `archived_at` retention column commented for v2. (3) 9 tests at `seed/backend/lib/tests/domain/ai/test_tool_audit.py` covering success / DB-failure / unknown-tool / Pydantic-like / circular-ref / empty paths. (4) `KB § PATTERNS/llm-tool-audit.md` (NEW, 8 sections + 4 worked SQL queries + adoption checklist). (5) `KB § PATTERNS/llm-bot-security.md` (NEW, 6 sections — defense trio, confidence thresholds, prompt-injection mitigation, baseline checklist, folded entire sibling `security-hardening` planning artifact). (6) `KB § INDEX.md` + `CLAUDE.md §2 Map` updated. **Schema improvements over sibling**: indexed `status` column (sibling parsed `error` for status); `(conversation_id, started_at)` composite index for fast per-conversation reconstruction; Postgres JSONB instead of TEXT (sibling stored JSON-stringified for SQLite portability). | claude-opus-4-7 |

---

## 12. No-leftovers constraint

The sibling repo (`~/Documents/repository/NoctusAI/whatsapp-google-scheduling/`) WILL BE DELETED by the user once the absorption batch completes:

- **All sibling-path references in this PROJECT.md are execution-scoped** — vanish when this project closes.
- **`KB § PATTERNS/llm-tool-audit.md` references our lib only**, not sibling paths.
- **`noctusai_lib/domain/ai/tool_audit.py` is freshly authored** on the schema we agreed; sibling is design-reference, not runtime dep.
- **Tests stand alone** against our lib.

### Future-work hooks captured from sibling (so the ideas survive the deletion)

The following sibling planning artifacts are NOT separate projects — they're recorded here so we don't lose them:

- **`provider-payload-audit`** — store raw provider payloads (WAHA, OpenAI, Calendar) alongside normalized records, indexed for replay-driven debugging. Pairs with retention. *Future hook:* `noctusai_lib/domain/ai/provider_payload_audit.py` companion to `tool_audit.py` once a consumer needs replay.
- **`data-retention`** — nightly job for conversation message + summary + audit retention; LGPD compliance. *Future hook:* `noctusai_lib/domain/ai/retention.py` once the first consumer's table grows or legal review fires.
- **`gpt-confidence-thresholds`** — confidence scores on extracted fields; ask follow-up or escalate if below threshold. *Future hook:* extension to the chatbot framework's `llm_dispatcher.py`.
| 2026-05-03 | Added §12 No-leftovers constraint. Folded sibling `provider-payload-audit` idea — raw provider payloads (WAHA, OpenAI, Google) get their own `webhook_events` table at consumer level, separate from `tool_call_audits` (different lifecycle, different retention). Folded sibling `data-retention` idea as Open Question #4. Folded sibling `gpt-confidence-thresholds` idea as Open Question #5. Folded sibling `security-hardening` LLM-output sanitization + tool-arg validation patterns into new §6 Phase 5 (KB doc). | claude-opus-4-7 |
