# Therapy Audio Lifecycle Schema Reconciliation — Project Document

> **Living document** — revise phases as work progresses.
> **Scaffolded 2026-04-22** from compliance-audit-reconciliation Phase 5 improvements bundle.
> **STATUS: PENDING USER INTERROGATION — do NOT execute before interrogating.**
> **Written for a zero-context reader.**

- **Created:** 2026-04-22
- **Last updated:** 2026-04-22
- **Status:** Filed pending interrogation. No phases designed yet.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Related docs:**
  - `projects/compliance-audit-reconciliation/PROJECT.md` § Phase 5 improvements — this project's origin.
  - `products/therapy-platform/backend/migrations/001_therapy_platform.sql` — `session_audio_segments` schema (has `video_room_id`, NOT `appointment_id`).
  - `products/therapy-platform/backend/app/services/session_service.py` — 20+ site silent-fail target.
  - `products/therapy-platform/backend/app/services/ai_pipeline.py:189-205` — reference for the "resolve video_rooms first" pattern (already fixed there in Phase 5).
- **Project slug:** `therapy-audio-lifecycle-schema-reconciliation`
- **Project location:** `products/therapy-platform/projects/therapy-audio-lifecycle-schema-reconciliation/` (single-product scope)

---

## 1. Context & Purpose

`therapy.session_audio_segments` has `video_room_id` but NO `appointment_id`, NO `recording_id`. Yet `session_service.py` uses `.eq("appointment_id", ...)` on this table at 20+ sites (start/pause/resume/end/reopen paths) and inserts rows with bogus `appointment_id` + `recording_id` keys. `transcription_service.py:108` and `session_journal.py:307` share the same pattern.

**Impact:** the mock test harness doesn't validate columns, so tests pass. Live DB either (a) 500s on inserts with unknown columns, or (b) silently drops them depending on PostgREST strictness. Either way, the session-audio lifecycle is broken in production — segments either fail to insert, or are orphaned from their parent appointment.

compliance-audit-reconciliation Phase 5 fixed ONE instance in `ai_pipeline.py:189` (retention update). This project addresses the system-wide pattern.

---

## 2. Confirmed constraints

_Interrogate the user before filling this section. Do NOT design Phase 1 before the answers below are locked._

---

## 3. Design principles

_TBD after interrogation._

---

## 4. Scope

**In scope:**
- Every `session_audio_segments` call site in the therapy backend that currently uses `appointment_id` or `recording_id` as if they were real columns.

**Out of scope:**
- Other tables with similar silent-fail patterns (file separately if found).
- Audio retention logic (owned by Phase 5 of compliance-audit-reconciliation — already shipped).
- Frontend changes (no frontend touches `session_audio_segments` directly).

---

## 5. Architecture / Data Model

Schema state verified 2026-04-22 via Supabase MCP:

| Table | Columns (live) |
|---|---|
| `session_audio_segments` | `id`, `video_room_id`, `segment_number`, `segment_type`, `audio_file_url`, `started_at`, `ended_at`, `transcription_text`, `is_transcribed`, `download_expires_at`, `created_at` |
| `video_rooms` | `id`, `appointment_id`, … |

Link chain: `appointments → video_rooms (1:1-ish) → session_audio_segments`.

### Files in scope

- `products/therapy-platform/backend/app/services/session_service.py:150-570`
- `products/therapy-platform/backend/app/services/transcription_service.py:106-160`
- `products/therapy-platform/backend/app/routers/session_journal.py:307`
- Tests: `tests/edge_cases/test_session_lifecycle.py`, `tests/services/test_*` that mock `session_audio_segments`.

---

## 6. Implementation phases

_Designed after §2 interrogation. Placeholder only._

- [ ] Phase 0 — Revalidate live-DB state; confirm the silent-fail pattern is still present.
- [ ] Phase 1 — Apply user's chosen reconciliation (denormalize OR refactor).
- [ ] Phase 2 — Regression tests + live-DB insert test (if `mock-supabase-schema-validation` has landed, use its column-aware mock).

---

## 7. Open questions

### Q1 (reconciliation pattern) — OPEN

**Question:** Two options:
- **A (denormalize):** add `appointment_id` as a column on `session_audio_segments` via a new migration; keep the direct `.eq("appointment_id", ...)` pattern. Pros: minimal code change. Cons: denormalization duplicates the `video_rooms.appointment_id` link.
- **B (refactor):** every call site resolves `video_rooms` first, then queries/inserts segments by `video_room_id`. Pros: respects the existing schema. Cons: 20+ site refactor; slightly chattier at runtime (1 extra SELECT per lifecycle op).

→ *Recommendation:* **B (refactor)**. `ai_pipeline.py:189` already landed this pattern in Phase 5 — consistency argument. Denormalization would also require backfill for any existing segments, which is riskier than the refactor given the feature isn't yet live.

### Q2 (test harness) — OPEN

**Question:** Should this project block on `mock-supabase-schema-validation` landing first (so the fix can be verified by a column-aware mock), or proceed without it (trust the refactor shape + manual live-DB test)?

→ *Recommendation:* proceed without the mock. The refactor pattern is concrete enough to audit by inspection; `mock-supabase-schema-validation` is itself blocked on user triage.

---

## 8. Dependencies & blockers

- **User decision on Q1** — hard gate for Phase 1.
- No conflicting in-flight projects (compliance-audit Phase 5 is closed).

---

## 9. Success criteria

- Every `.eq("appointment_id", ...)` on `session_audio_segments` replaced per Q1 choice.
- Every `.insert({... "appointment_id": ...})` / `{... "recording_id": ...}` on `session_audio_segments` cleaned.
- Therapy pytest baseline (1131 passing as of 2026-04-22) preserved with +N new silent-fail regression guards.

---

## 10. How to use this project

- Interrogate §7 Q1 + Q2 before designing Phase 1.
- Phase-by-phase cadence (execute one, pause, await "continue").

### Verification commands

```bash
cd products/therapy-platform/backend && /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest tests/ -q
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-04-22 | **Initial scaffold** — filed as Phase 5 follow-up from compliance-audit-reconciliation. Pending interrogation on Q1 (denormalize vs refactor). | Claude Opus 4.7 |
