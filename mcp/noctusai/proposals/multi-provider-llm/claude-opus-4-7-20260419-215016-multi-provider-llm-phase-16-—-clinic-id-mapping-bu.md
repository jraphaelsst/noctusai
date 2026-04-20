# Proposal: Multi-provider LLM Phase 16 — Clinic-id mapping bundled improvements

**Agent:** claude-opus-4-7
**Origin:** project:multi-provider-llm:phase-16
**Generated:** 2026-04-19 21:50
**Severity:** low
**Effort:** low
**Affected products:** core, erp-imobiliario, therapy-platform, seed
**Status:** pending

---

## 1. Context

Phase 16 closed open question #1 by threading `clinic_id` through every Therapy AI service as `org_id`. `ai_pipeline._resolve_clinic_id` queries `therapist_profiles.clinic_id` once per pipeline and passes to all 4 sub-services. 3 pipeline entry points updated. 1 test mock signature fixed.

---

## 2. Situation

Wiring is correct but leaves three open items: `_resolve_clinic_id` runs separately in 3 entry points (same DB query thrice in short succession could easily be one `_session_context`), routers that call services directly (not via ai_pipeline) still don't pass clinic_id, and no realdb test covers the Tier 1 resolution path.

---

## 3. Proposed Solution

### 3.1 Linkage — why this solution fits this situation

Each bundled improvement tightens a boundary the Phase shipped loose. None block production — they clean up debt before it ossifies.

### 3.2 Application instructions

#### 1. DRY the pipeline context resolution

**Linkage:** process_session_end / on_observation_change / on_patient_note_change each call _resolve_clinic_id separately. One helper gives `{patient_id, therapist_id, clinic_id}` in one DB roundtrip.

**Steps:**
1. Write `_session_context(db, appointment_id_or_session_record_id)` returning a dataclass
2. Refactor the 3 entry points to call it

**Risks:** Low — same query batched

*Independent:* can be applied without other bundled improvements.

#### 2. Wire clinic_id in non-pipeline router callers

**Linkage:** `routers/attachments.py::process_attachment_with_ai` and `routers/therapy_matching.py::{embed_therapist, embed_patient}` still don't pass clinic_id. Tier 1 is bypassed for those paths today.

**Steps:**
1. Read `get_clinic_id_for_user(user)` in the route handlers
2. Pass to the service

**Risks:** Low — non-pipeline paths get the benefit too

*Independent:* can be applied without other bundled improvements.

#### 3. Realdb test covering Tier 1 clinic-scoped resolution

**Linkage:** Unit tests mock the lib — don't exercise the credential chain.

**Steps:**
1. Write `tests/realdb/test_llm_clinic_tier1.py`
2. Insert a clinic-scoped `org_settings.openai_api_key` row
3. Call `chat_completion(..., org_id=clinic_uuid)` and assert the key resolved correctly
4. Skip gracefully without SUPABASE_SERVICE_ROLE_KEY

**Risks:** Low — realdb tests already auto-skip

*Independent:* can be applied without other bundled improvements.

#### 4. Clean therapy_embedding_service.generate_embedding signature

**Linkage:** `api_key: Optional[str] = None` is unused since Phase 7. Now with `clinic_id` added, the signature has two dead/oddly-positioned params.

**Steps:**
1. Delete `api_key` positional param (grep: only internal callers)
2. Rename to `(text, *, clinic_id=None)`
3. Update the 2 internal call sites

**Risks:** Low — grep-verified unused

*Independent:* can be applied without other bundled improvements.

### 3.3 Seed APIs / shared lib involved

N/A — change is local to the product.

### 3.4 Risks before applying

Low — additive changes.

### 3.5 Alternatives considered

N/A — the situation dictates the fix.

---

## 4. Effects

When this is applied, these change:

- **Behavior:** Unchanged — improvements are structural.

---

## 5. Acceptance Criteria

- [ ] Fix applied to every affected product (not just the one that triggered detection)
- [ ] `python mcp/noctusai/cli.py --validate` shows 100/100 for the affected product(s)
- [ ] `python mcp/noctusai/cli.py --review --product core` files no new proposals for this issue
- [ ] Backend tests still pass for the affected product(s)
- [ ] If the change touched shared code, `python mcp/noctusai/cli.py --catalog` shows no new orphans or duplicate candidates
- [ ] Documentation updated KB-first, CLAUDE.md second (per `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md → Docs stay in sync`)
- [ ] Realdb test passes with a clinic-scoped key
- [ ] grep reveals no remaining `api_key` positional usage in therapy_embedding_service
