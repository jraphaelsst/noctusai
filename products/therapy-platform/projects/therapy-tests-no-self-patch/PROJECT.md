# Therapy Tests — No Self-Patch — Project Document

> **Resume here.** Pilot landed in `test_ai_pipeline_service.py` (43 → 0 self-monkeypatches). Remaining therapy-platform self-monkeypatch debt is 72 sites across 7 files (after pilot). This project picks up where Phase 1 of the parent triage left off.
>
> **Written for a zero-context reader.** If you pick this up cold: read §1 + §3 + §5 + §6 in that order.

- **Created:** 2026-04-28
- **Last updated:** 2026-04-28
- **Status:** ⏳ **PARTIAL — pilot landed, 72 sites remaining across 7 files.** Ready to resume.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Project slug:** `therapy-tests-no-self-patch` (subject=therapy-tests, intent=refactor)
- **Project location:** `products/therapy-platform/projects/therapy-tests-no-self-patch/` (single-product scope)
- **Related docs:**
  - **Parent triage:** `projects/keeper-warning-triage/PROJECT.md` §6 Phase 1 (this is the per-product follow-up)
  - **Playbook:** `KB § PATTERNS/testing.md § No self-monkeypatching — refactor playbook` (Pattern 1 = DI, Pattern 2 = boundary mock, Pattern 3 = seed real data)
  - **Memory:** `feedback_no_monkeypatching_in_tests.md` + `feedback_keeper_warning_triage.md`
  - **Pilot reference (closed at 0):** `products/therapy-platform/backend/tests/services/test_ai_pipeline_service.py` — canonical Pattern-1 (DI) example via `_PipelineHooks` dataclass + `_hooks(...)` factory.

---

## 1. Context & Purpose

The keeper detector `check_no_self_monkeypatch` flagged 115 self-monkeypatches across therapy-platform on 2026-04-28. The parent project `keeper-warning-triage` triaged these into per-product follow-ups; this is the therapy-platform follow-up.

**Pilot result (2026-04-28):** Path A from the parent triage shipped — `test_ai_pipeline_service.py` migrated end-to-end:
- Production `ai_pipeline.py` got `_PipelineHooks` dataclass (5 fields: `transcribe`, `summarize`, `regenerate_clinical_summary`, `longitudinal_clinical`, `longitudinal_patient`).
- All 3 pipeline functions (`process_session_end`, `on_observation_change`, `on_patient_note_change`) accept `hooks: _PipelineHooks | None = None`.
- All 17 tests in the file migrated from `patch.object(<our_module>, ...)` to a `_hooks(...)` factory. **17/17 pass.** Real consent guards execute end-to-end; revoked-feature paths verified via `hooks.<helper>.assert_not_awaited()`.
- **43 → 0 self-monkeypatches in that file.**

The playbook is now proven. This project applies the same patterns to the remaining 72 sites.

---

## 2. Confirmed constraints

- **Use the 3-pattern playbook from `KB § PATTERNS/testing.md`** — Pattern 1 (DI) for orchestrators, Pattern 2 (boundary mock) for service helpers calling external SDKs, Pattern 3 (seed real data) for guards / DB-bound logic.
- **No new `# self-patch-ok` annotations.** The escape hatch exists but per CLAUDE.md doctrine should be the genuine-impossible-case last resort.
- **Real consent guards must execute end-to-end** — same constraint as the pilot. Revoked-feature paths must verify via mock-introspection (`assert_not_awaited()` on the injected helper), not patch-assertion.
- **Severity ratchet** — when this project closes (therapy at 0), detector severity for therapy ratchets from `warning` to `high` per `KB § PATTERNS/testing.md § Severity ratchet`.

---

## 3. Inventory: 72 remaining sites across 7 files

| File | Sites | Likely pattern |
|---|---:|---|
| `tests/routers/test_messaging_router.py` | 40 | **Largest target.** Patches `app.routers.messaging.messaging_service.{send_message,list_conversations,find_or_create_conversation}`. Likely Pattern 1 (DI on the messaging-service helpers via a `MessagingHooks` dataclass) OR Pattern 2 (boundary mock at the Twilio/WhatsApp SDK level) — needs Phase 0 audit to pick. |
| `tests/routers/test_invitations_router.py` | 7 | Patches `app.routers.invitations.send_product_invitation_email` (audit/email side-effect). Pattern 2 (boundary mock at `noctusai_lib.email.send_*`) likely cleanest. |
| `tests/integration/test_e2e_flows.py` | 7 | Integration shape — likely Pattern 2 + Pattern 3 mix. |
| `tests/services/test_no_show_service.py` | 6 | Patches `commission_engine.process_no_show_charge`. Pattern 1 DI candidate (orchestrator-shaped service). |
| `tests/services/test_transcription_service.py` | 6 | Patches `transcribe_segment` (LLM boundary). Pattern 2 — swap to `noctusai_lib.llm.transcription` allowlisted target. |
| `tests/routers/test_reviews_router.py` | 2 | Small tail. |
| `tests/services/test_therapy_embedding_service.py` | 2 | Small tail. |
| `tests/services/test_email_service.py` | 2 | Small tail. |

---

## 6. Phase plan

### Phase 0 — Audit `test_messaging_router.py` (the 40-site file) ✅ (2026-04-28)
- [x] Read `test_messaging_router.py` + `app/routers/messaging.py` + `app/services/messaging_service.py`.
- [x] Mapped patch sites: all 40 target `app.routers.messaging.messaging_service.<helper>` (decorator-style `@patch("dotted.path", new_callable=AsyncMock)`).
- [x] Pattern decision: **Pattern 3 (seed real data via `MockSupabaseClient`)** — `messaging_service` helpers are DB-bound (query `conversation_participants`, check blocks, insert into `messages`/`conversations`); patching them neuters the auth/block/participant logic. Seeding tables exercises the real authorization path.
- [x] Ran absorption-search trio scoped to messaging surface — `send_message` recurs in ERP+therapy (different domains: ERP=WAHA/WhatsApp, therapy=in-app); accept-with-rationale, no absorption blocks the cleanup.
- [x] Pattern 3 proof-of-concept: refactored `test_start_conversation_with_self_fails` (1 site) — removed `@patch`, asserted real validation guard at `messaging_service.find_or_create_conversation` line 43 raises 400 for self-messaging. Test passes; keeper count 40→39 in file.

**Improvements:**
- The current tests assert *only* `mock_find.assert_called_once()` after patching — they verify the helper was CALLED, not what it DOES. Pattern 3 conversion strengthens every test by exercising real authorization/block-check/participant-validation logic. **This is exactly the rule's intent**: the patched test wasn't testing anything meaningful.
- Discovered the platform exception-handler shape during the proof-of-concept: HTTPException responses are wrapped as `{"error": {"code": ..., "message": ...}}` (not FastAPI default `{"detail": ...}`). Will need to use `body.get("error", {}).get("message", "")` in assertions throughout the file. **Recurrence rule trigger**: the `error.message` access pattern will recur 40+ times — could DRY via a helper `assert_error_message_contains(resp, expected)`.

### Phase 1 — Apply Pattern 3 to remaining 39 sites in `test_messaging_router.py` ⏳ ACTIVE (12/40 done, 28 remaining)
- [x] Site 1: `test_start_conversation_with_self_fails` (validation-only, no seed)
- [x] Site 2: `test_start_conversation_with_blocked_user_fails` (seed `user_blocks` row → real `_check_block` returns True → 403)
- [x] Sites 3-9: `TestListConversations.*` (7 sites — `test_list_conversations_patient`, `_therapist`, `_admin_sees_all`, `_clinic_admin`, `_unread_filter`, `_busca`, `_pagination`) — seed conversations + participants per role, real `list_conversations` exercises role-scoped filtering
- [x] Sites 10-11: `TestSendMessage` validation-failure paths — `test_send_message_non_participant_denied` (seed conv with OTHER user only) + `test_send_message_blocked_user_denied` (seed conv + participants + user_blocks)
- [ ] Site 12 (deferred): `TestSendMessage.test_send_text_message` happy path — **BLOCKED on MockSupabaseClient mock-infra gap** (see Improvements). Reverted to `@patch` for now with TODO marker citing the deferred follow-up.
- [ ] Sites 13-21: `TestGetMessages.*` (3 patches) + `TestMarkAsRead` (1) + `TestDeleteMessage.*` (3) + `TestReportMessage.*` (1) — should follow the same Pattern-3 shape with `messages` + `conversations` seed
- [ ] Sites 22-26: `TestArchiveConversation` (2) + `TestMuteConversation` (2) — seed conversation + user-participant; real handlers run UPDATE on participant flags
- [ ] Sites 27-32: `TestBlockUser` (3) + `TestUnblockUser` (3) — seed user_blocks; real handlers run INSERT/DELETE
- [ ] Sites 33-40: `TestUnreadCount` + edge cases — finish the remaining patches
- [ ] **Phase-end verification checklist**: file's 48 tests green + keeper count drops to ≤5 (the patched happy-path holdouts) + KB sync ✓
- [ ] File ONE bundled proposal capturing the pattern (e.g. `assert_error_message_contains` helper landed at N=4+ already this file)

**Improvements (live capture, 2026-04-28):**
- Added `_seed_conversation_for_user(...)` + `_seed_block(...)` + `_assert_error_contains(...)` helpers at the top of the test file. Recurrence rule trip: if `_assert_error_contains` recurs at N=2+ across other product test files, **absorb into `noctusai_lib.testing.assert_error_contains(resp, expected)`** (already used 4× in this file alone — likely formalize candidate).
- **Real bug surfaced** by Pattern 3 conversion: `test_send_text_message` patched assertion was `data["content"] == "Olá, como você está?"` (a SAMPLE_MESSAGE constant) while the request sent `"Olá, tudo bem?"`. The patch hid the mismatch — Pattern 3 forces the real content through and surfaced it. Filed as deferred (blocked on mock-infra) but documented as a real correctness signal validating the rule's intent.
- **MockSupabaseClient mock-infra gap caught**: `db.table("messages").insert(msg_data).execute()` in production expects `result.data` to contain the inserted row, but the mock currently tracks inserts via `inserted_payloads` only — `execute()` returns an empty data response, breaking happy-path tests that read back the inserted row. **Recurrence will trip at N=2+** as we hit other products' insert-return paths. **File follow-up project: `mcp-mock-supabase-insert-returns-row`** to land a `MockRequestBuilder.insert(...)` that auto-generates an `id` + returns the payload in `result.data`. Would unlock all happy-path Pattern 3 conversions across the platform.

### Phase 2 — `test_invitations_router.py` 🅿️ DEFERRED
- [ ] Likely Pattern 2 (mock `noctusai_lib.email.send_invitation`) — the consent-rollout used a similar shape.
- [ ] 7 sites.

### Phase 3 — `test_e2e_flows.py` integration 🅿️ DEFERRED
- [ ] Hybrid Pattern 2 + 3.

### Phase 4 — Service tails (no_show, transcription, reviews, embedding, email) 🅿️ DEFERRED
- [ ] 16 sites total across 5 files.

### Phase 5 — Severity ratchet 🅿️ DEFERRED (pending all-zero)
- [ ] Therapy at 0 self-monkeypatches.
- [ ] Detector severity flipped to `high` for therapy product.
- [ ] Cleaner score signal — new violations block CI.

### Phase 6 — Project close 🅿️ DEFERRED
- [ ] Three-way doc sync.
- [ ] Folder delete on close.
- [ ] Update parent `keeper-warning-triage/PROJECT.md` Phase 1 to ✅.

---

## 10. How to use this project

```bash
# Quick state check — therapy self-monkeypatch count:
mcp/noctusai/.venv/bin/python -c "
import sys; sys.path.insert(0, 'mcp/noctusai')
from tools.compliance import check_all_products
_, issues = check_all_products()
mp = [i for i in issues if 'patches our own symbol' in i.get('issue','') and i.get('file','').startswith('products/therapy-platform/')]
print(f'therapy self-monkeypatch: {len(mp)}')"

# Per-file inventory:
mcp/noctusai/.venv/bin/python -c "
import sys, re; sys.path.insert(0, 'mcp/noctusai')
from tools.compliance import check_all_products
from collections import defaultdict
_, issues = check_all_products()
mp = [i for i in issues if 'patches our own symbol' in i.get('issue','') and i.get('file','').startswith('products/therapy-platform/')]
by_file = defaultdict(int)
for i in mp:
    by_file[i.get('file','').split(':',1)[0]] += 1
for f, n in sorted(by_file.items(), key=lambda x: -x[1]):
    print(f'  {n:3d}  {f}')"

# Run target file's tests after each refactor:
cd products/therapy-platform/backend && /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest tests/routers/test_messaging_router.py -q

# Absorption-search BEFORE refactoring (per CLAUDE.md standing duty 2026-04-28):
mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py --scan-helpers
mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py --scan-blocks
mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py --scan-service-lines
```

---

## 11. Change log

| Date | Change | Who |
|---|---|---|
| 2026-04-28 | **Project scaffolded** post-pilot. Pilot landed earlier same day in parent project: `test_ai_pipeline_service.py` migrated end-to-end (43 → 0). Playbook proven via Pattern-1 DI (`_PipelineHooks` dataclass). Inventory of remaining 72 sites across 7 files captured in §3 + §6. Phase 0 of `test_messaging_router.py` (40 sites — biggest tail) is the active phase. | Claude Opus 4.7 |
