-- 032_media_creation_post_score.sql — persist the Método Audience audit result.
--
-- Project: media-creation-methodology (2026-07-26). The new "Avaliar post"
-- action (POST /api/media-creation/posts/{id}/score) audits a finished post
-- against the 8-criteria rubric and returns {score, verdict, strengths,
-- corrections, criteria, rationale}. Persist it so the verdict survives reload.
--
-- Forward-only + idempotent (ADD COLUMN IF NOT EXISTS), additive + NULLable →
-- zero impact on existing rows. Matches the 002+ convention (never edits 001).

ALTER TABLE social_wiring.mc_posts
    ADD COLUMN IF NOT EXISTS score JSONB;
