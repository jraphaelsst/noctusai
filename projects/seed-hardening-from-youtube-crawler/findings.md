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
