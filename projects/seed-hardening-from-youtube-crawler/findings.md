# findings.md — seed-hardening-from-youtube-crawler

Append-in-the-moment file for slips / errors / lessons / surprises / interesting discoveries during this project. Five standard categories. Synthesized at project close into a curated knowledge artifact (per `feedback_knowledge_tracking.md`).

---

## Errors / Mistakes / Slips

- **2026-05-04 (architect, Phase 0 prep):** Asked user permission to commit at phase gate. Slip: the no-auto-commit rule was *retired* 2026-05-03 — "DO commit at phase gates without asking" is the rule. Fixed by amending `MEMORY.md` index entry to flip the framing ("DEFAULT IS commit at gates" instead of "default never; carve-outs:..."). Pre-existing memory file content was already correct — the index hook was the misleading line.

## Lessons

- **2026-05-04 (Phase 1.1):** Pre-existing email-module tests use `monkeypatch.setattr(digest_module, "_post_to_resend", ...)` which patches our own internal function name — the no-monkeypatch rule's exact anti-pattern. The module pre-dates the rule (2026-04-25). New SMTP tests patch at `smtplib.SMTP` / `SMTP_SSL` boundary directly (external-service carve-out), which is correct. Lesson: when extending a flat-shape module, tests inherit pre-rule patterns by gravity unless explicitly broken; called out in §findings instead of fixing in-scope.

## Interesting findings

- **2026-05-04 (Phase 0 §3a):** All five "from the critique" Batch-A items pointed at seed gaps that were either *missing entirely* (encrypted_tokens, youtube) or *half-shipped* (email is Resend-only). Architect-side observations (jobs primitive, storage, quota, scaffold polish) compose with them — together they form a coherent "youtube-crawler dependency surface" that lifts cleanly as a single project.

## Knowledge pieces

- **2026-05-04:** SMTP via stdlib `smtplib` (sync) wraps cleanly with `asyncio.to_thread` to preserve the `async def send_digest(...)` signature without adding `aiosmtplib` as a dependency. Multipart/alternative is `MIMEMultipart("alternative")` + plain `MIMEText` then html `MIMEText` (order matters — most preferred renderer LAST, per RFC 2046).
- **2026-05-04:** SMTP security modes that matter: `ssl` (port 465, implicit TLS, `smtplib.SMTP_SSL`), `starttls` (port 587, explicit upgrade, `smtplib.SMTP` + `.starttls()`), `none` (port 25, plain — only useful for `aiosmtpd` test servers). Default `starttls` covers ~all modern providers.

## Surprises

- **2026-05-04 (Phase 0 commit):** Pre-commit hook caught a §6-vs-§11 inconsistency in `projects/seed-shadow-purge-helper-lift/PROJECT.md` — Phase 5 header says ✅ but the last sub-task "Final-commit + branch-push (next)" stayed unticked even though commit `f46f76a` on origin/main IS that final commit. Fixed as a drive-by tick (one character) with note pointing at the landing commit. Lesson: phase-close discipline needs to tick the literal LAST sub-task AFTER the commit lands, not before — but agents flip the header pre-commit so the hook only catches it when something else triggers a check. Methodology suggestion (deferred): the post-commit hook (or a new one) could auto-tick "Final-commit + branch-push" sub-tasks when they appear in §6 of the project just committed.

- **2026-05-04 (Phase 1.3, Engineer B):** Brief asked the test file at `seed/lib/backend/tests/test_youtube_integration.py` (top-level), but the existing convention places integration tests under `tests/integrations/<integration>/{test_fake_adapter.py,test_real_adapters.py}` (see `google_calendar`, `google_maps`, `whatsapp`). Followed the brief's literal path because it was explicit and the file is self-contained — but flagged here as a deferred follow-up: relocate to `tests/integrations/youtube/{test_fake.py,test_real.py}` for parity with siblings, or split into two files. Trivial mv + import path stays the same; not blocking.

## Lessons

- **2026-05-04 (Phase 1.3, Engineer B):** The Protocol docstring's quota math says "~2 units per page of 50 videos" for `list_channel_videos`. The actual cost on a fresh client is **3 units** (1 channels.list + 1 playlistItems.list + 1 videos.list); the "~2" assumes the caller has cached `uploads_playlist_id` from a prior `get_channel` call. Real client returns `quota_units_consumed=3` for the un-cached first call, `2` would require an in-client cache. Documented the asymmetry inline in `real.py` (`list_channel_videos`); cache enhancement is a future item. The Fake mirrors the API contract (charges 2/page) since it has no channels.list step inside `list_channel_videos` — the seed's documented `get_channel` (1) + per-page (2) is what tests assert against.

## Knowledge pieces

- **2026-05-04 (Phase 1.3):** YouTube Data API v3 quota costs (relevant subset):
  - `channels.list` = 1 unit (any combination of `part`).
  - `playlistItems.list` = 1 unit per page (max 50 items).
  - `videos.list` = 1 unit per call regardless of how many comma-joined ids (up to 50 in batch).
  - `search.list` = **100 units** per page (50 max items). 1% of daily quota per call.
  - Default daily quota = 10,000 units → ~100 search calls OR ~5,000 channel-video pages.
  - The auto-managed "uploads" playlist id appears on `channels.list?part=contentDetails` as `contentDetails.relatedPlaylists.uploads`.

- **2026-05-04 (Phase 1.3):** ISO-8601 durations from YouTube (`contentDetails.duration`) only use the H/M/S subset of the spec (no D/W/M for video durations) → simple state-machine parser is enough; no `isodate` dep needed. Fallback to 0 on parse failure with WARN log keeps a malformed entry from poisoning a whole list.

- **2026-05-04 (Phase 1.3):** YouTube emits `publishedAt` as RFC 3339 with a literal `Z` suffix. Python <3.11 chokes on `Z`; replace with `+00:00` before `datetime.fromisoformat`. Tested on Python 3.11 (works either way) but the replace stays for portability.
