# findings — meta-video-reels-publish (seed extension dispatch, Engineer F)

> Symbol-first per `KB § PATTERNS/doc-symbology.md`. Dispatch = seed-only
> (Phases 1+2+4). Phase 3 consumer wiring deliberately NOT done (gated +
> file-disjoint from Engineer E's concurrent `products/social-wiring/`).

## Errors
- ∅ functional. Baseline 65 meta tests green pre-edit; 107 green post (meta dir).

## Mistakes / slips
- **Harness overlay⊥worktree divergence (R6) hit HARD this session.** Every
  initial `Edit`/`Write` reported success ✅ but on-disk grep returned 0 — the
  worktree stayed clean (overlay-only). Caught by the §1a discipline: nuke-bytecode
  import test failed ⇒ `grep -c <marker> <file>` on true disk = 0 ⇒ re-authored
  ALL 5 src files + 2 docs via Bash (`libcst` for `.py`, Python `str.replace`+`ast.parse`
  for prose). Naive `git status` (clean) would have falsely passed. Proof = on-disk grep,
  never the Edit "success" message.
- libcst `add_field` helper iterated `ClassDef` not `ClassDef.body.body` → `IndentedBlock
  not iterable`. Fixed; ast.parse-gated every write.
- Heredoc `\n` escaping leaked a literal `\n` into the appended test block (first append
  attempt) → SyntaxError caught by ast.parse BEFORE the write (no partial file). Re-did via
  a temp block file + Python concat. Lesson: ast.parse-before-write is the net that made the
  failed attempt a no-op.

## Lessons
- **Worktree base was BEHIND not divergent.** HEAD `c72f7b3e` was a clean *ancestor*
  of `origin/dev` `977da6bd` (zero commits ahead) — a FF base, not a divergence.
  `git merge-base --is-ancestor HEAD origin/dev` distinguishes the two; rebased to the
  dev tip (the integration base) before working. A naive `HEAD==origin/dev` check would
  have false-STOPPED a fast-forward-able worktree.
- **No seed venv exists; `noctus.dev.pytest` is product-scoped.** Seed `noctusai_lib`
  is editable-installed (`-e seed/lib/backend`) and CI runs its tests from inside a
  product backend. For an isolated seed-only dispatch, a minimal `/tmp` venv
  (`httpx` + `fastapi` + `pydantic` + `pytest` + `libcst`) + `PYTHONPATH=seed/lib/backend`
  runs the meta suite — the meta module's heavy deps (google SDKs via `credential_resolvers`)
  are imported lazily inside the factory branch, so the suite never triggers them.
  Candidate methodology gap: a `noctus.dev.pytest_seed` (or `slug='seed'`) mode.

## Interesting
- Video publish is genuinely a different Graph contract: async resumable-upload +
  `status_code` poll (`IN_PROGRESS`→`FINISHED`|`ERROR`|`EXPIRED`) before `media_publish`.
  Modeled the poll as ONE shared `_meta_api.poll_media_status` helper (2 callers: IG Reel +
  FB video), `sleep`-injected for deterministic tests, hard-capped timeout (never blocks),
  typed `video_processing_timeout`. FB Reel uses the start→poll→finish `video_reels` phase
  flow; FB video uses `/videos` (synchronous unless an `IN_PROGRESS` container is returned).
- Open Question #2 resolved as the PROJECT.md recommended: unified `as_reel: bool` flag on
  `publish_facebook_video` (same endpoint family, one Protocol method).
- Gated-capability honesty preserved: Real raises `MetaGraphError(requires_app_review=True)`
  on the gated path; Fake = the "scope approved + transcode done" instant-ready path,
  `processing_duration_ms=0`.

## Knowledge (durable)
- `MediaProcessingStatus` value object (`creation_id` / `status_code` / `status` / `raw` +
  `is_finished` / `is_error`) is the open-taxonomy poll-state primitive — extend its
  status set, never force-fit.
- `processing_duration_ms` added (back-compat default `None`) to BOTH `PublishedMedia` and
  `PublishedPost` — `None` on the synchronous path, set on the async video/Reel path.
