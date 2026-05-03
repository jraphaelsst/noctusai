-- 009_session_audio_segments_recording_id.sql
--
-- Adds the missing `recording_id` column on `therapy.session_audio_segments`.
--
-- Why this migration exists. The `session_service.py` lifecycle paths
-- (start / pause / resume / end / auto_finalize / reopen) all attempted
-- `db.table("session_audio_segments").update({"recording_id": ...})`
-- against this table, but the column never existed in any of migrations
-- 001-008. PostgREST silently dropped the writes; subsequent reads of
-- `active_segment["recording_id"]` always returned None; every
-- `livekit_service.stop_recording(active_segment["recording_id"])` call
-- was a no-op for the lifetime of the feature.
--
-- Filed by `products/therapy-platform/projects/therapy-audio-lifecycle-schema-reconciliation/`
-- Phase 1b on 2026-05-03 after live-DB schema audit confirmed the column
-- gap. Companion to the Phase 1a `appointment_id` refactor (same project).
--
-- Pairs with the `therapy.session_audio_segments.video_room_id` link
-- chain (appointments → video_rooms → session_audio_segments). Nullable
-- because: (a) existing rows never had it persisted, (b) the LiveKit
-- start_recording call returns the id asynchronously inside the lifecycle
-- and segments are inserted before that resolves.

SET search_path = therapy, public;

ALTER TABLE therapy.session_audio_segments
    ADD COLUMN IF NOT EXISTS recording_id TEXT;

COMMENT ON COLUMN therapy.session_audio_segments.recording_id
    IS 'LiveKit egress recording id, set after start_recording resolves; '
       'used by stop_recording to cancel the egress at session-end. '
       'Nullable for back-compat with rows from before 2026-05-03.';
