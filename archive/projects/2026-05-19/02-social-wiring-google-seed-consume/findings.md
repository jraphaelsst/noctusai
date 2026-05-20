# findings — social-wiring-google-seed-consume

> Durable findings ledger (5 categories). Append in-the-moment; synthesize at
> close. Symbol-first (AI scaffolding).

## Slips / errors

- (none yet)

## Mistakes (process)

- **Phase 0 audited the seed store READ path but not the WRITE path.** I (architect) confirmed `select("*")` ignores extra columns (read-safe) and called it "clean refactor, zero data migration" — but `SupabaseCredentialStore.put()` unconditionally injects a `metadata` column the absorbed `credentials` table lacks, and the seed `StoredCredential` lacks the 40-site denormalized `channel_id/title/scopes` fields. Caught by Wave-1 engineer's stop-before-improvise (recon-only, zero edits — correct). Lesson → a seed-consume Phase-0 audit MUST check the seed Real adapter's **write payload keys ∩ consumer DDL columns** AND **Protocol field set ⊇ consumer field reads**, both directions, not just the read path. Strengthens `feedback_verify_seed_ships_it`: "seed ships it" ⇒ "seed Real adapter is shape-compatible with THIS consumer's existing schema", bidirectional.

- **First branch created in the contended shared main tree.** `feat/social-wiring-google-seed-consume` was cut in the main working tree while a parallel `jraphaelsst` session was live-committing — a foreign commit (`a27843e2`) landed on it + `.git/index` mutated under us. Caught by the pre-work authorship sweep; recovered by re-basing to an isolated sibling worktree (`../noctusai-wt-sw-google`, branch `feat/sw-google-seed-consume`). Lesson → for any multi-phase refactor in a known-shared tree, create the isolated worktree FIRST, before branching in the shared tree.

## Lessons

- **Pre-commit-hook contention is real and the methodology already had the fix in-flight.** A parallel session's `a27843e2` fixed the exact bug (blanket `git add` of all KB-modified docs sweeping concurrent agents' edits) that the safety net flagged for us. Cherry-picked it (preserving authorship) so the whole program runs the corrected hook. Safety-net-fires = methodology-working; the fix already existed because another agent hit the same gap — convergent hardening.
- **Active hook is a symlink → main tree's `scripts/hooks/pre-commit`** (shared `$GIT_COMMON_DIR/hooks` across all worktrees). Worktree commits run whatever the *main tree* has checked out there — an inherent shared-tree coupling, not controllable from a worktree; do not try to clobber it (races other agents). Verify-don't-overwrite.
- **Credential compat proven by code-inspection of BOTH crypto paths > one live-row decrypt.** Reading seed `encrypted_tokens.encrypt` (plain Fernet, no envelope) + `token_store` (`json.loads(decrypt(...))`) vs social-wiring's `Fernet(json.dumps(...))` proved compat for *all* rows, not a sample. Stronger evidence, no DB/key access needed.
- **Verify-the-seed-ships-it refined a sub-agent assertion.** The Explore
  agent flagged youtube as a flat "seed-first violation, hand-rolled". Tree
  verification refined it: the seed ships the API layer *and* upload *and*
  the OAuth lifecycle (`security.oauth`) *and* the vault (`token_store`) — the
  fork is wider (full Google stack, ~2,357 LoC, N≥3) than the single-file
  flag. Codebase-is-source-of-truth caught an incomplete derived claim before
  it scoped the project.

## Interesting

- **Patch-return dispatch model worked across the worktree-isolation hazard.**
  Engineer SW-P1 (harness worktree) returned the change as a `git diff` written
  to `/tmp/*.patch` (deliverable artifact, not a `.md`); architect applied it in
  the gate-green sibling worktree, fresh-eyes-reviewed, and **independently
  re-ran** the test suite (not trusting the engineer's claim). Sidesteps
  `feedback_worktree_isolation_base_and_overlay` (no cross-worktree salvage /
  overlay-divergence). Reusable for the remaining phases under this contended-tree
  situation. NOTE: the prose patch did not transmit in the first return — needed
  a SendMessage continuation to dump it to a file. Lesson: brief engineers to
  write the patch to a tmp file from the start, not inline in the return.
- Plan/brief referenced `_row_to_stored` as pre-existing; it was not (shipped
  `get()` inlined construction). Engineer extracted it (the assumed shape). A
  spec can hallucinate a helper name that "should" exist — engineer rebuilt to
  the intent, not the literal. Surfaced so the plan prose is now accurate.

- The seed `oauth/google_provider.py` docstring **self-documents** that it was
  formalized to cure "the hand-rolled … oauth_adapter's refresh logic" — the
  seam was born from this exact drift class. The fork persisted because the
  Wave-1..4 absorption lifted the seed code but never refactored the consumer
  (R1/R5 absorption-debt shape: code lifted, consume side not migrated).
- Credential-table compat is verbatim: social-wiring's `credentials` DDL
  comment "Fernet-encrypted JSON" == the seed `SupabaseCredentialStore`
  docstring expectation. Clean refactor, not a data migration — the
  scope-blowup risk evaporated on inspection (estimate-off-evidence paid off).

## Knowledge / methodology routed (cont.)

- **Documented `--no-verify` carve-out (this commit, loud — NOT silent).** The
  pre-commit hook invoked from a sibling worktree resolves `settings.REPO_ROOT`
  to the **main tree** (`feedback_mcp_path_constants_from_settings` class), so
  it validates the contended main tree's **stale residue** copy of this
  PROJECT.md, not the correct worktree file. The real invariant
  (`check_phase_state_consistency` scoped to the worktree) was proven **GREEN
  (0 issues)** out-of-band before committing. This is a known-mis-scoped-gate
  carve-out (safety-net mis-fire), user-approved, ¬ a silent workaround — the
  fractional-phase bug it first caught IS fixed (integer renumber).
- **Structural friction stack (lesson):** contended main tree → manual sibling
  worktree → repo tooling hardwired to main `REPO_ROOT` → gate validates wrong
  tree + stale-residue shared landmine. Lesson: a manual sibling worktree
  fights repo tooling that assumes the canonical checkout path; the
  harness-managed `.claude/worktrees/` (engineer dispatch) or a clean main tree
  is the friction-free path. Architect doc-commits in a mispathed sibling
  worktree are a known cost.
- **Tooling gap (codification candidate, N=1 but deterministic):**
  `check_phase_state_consistency` `_PHASE_HEADER_RE = ^### Phase\s+(\d+)\b`
  silently coerces `Phase 0.5`→`0`. Fix options: (a) convention forbids
  fractional phases (doc + a `check_*`), or (b) regex `\d+(?:\.\d+)?` + numeric
  sort. Routed to phase_learnings + surfaced to user.

## Knowledge / methodology routed

- **Seed gap → formalize (Phase 0):** `noctusai_lib.security.oauth.oauth_router`
  hardcodes `prefix="/api/oauth"`. An absorbed product with OAuth redirect URIs
  already registered in Google Cloud Console (here `/api/youtube/oauth/callback`,
  `/api/calendar/oauth/callback`) **cannot move them** without orphaning every
  existing consent. The seed seam needs a `prefix=`/`callback_path=` override.
  This is the canonical "absorbed product carries pre-registered external OAuth
  URIs" need — recurs on every OAuth-bearing absorption. Routed to Phase 2 as a
  pilot-gated `[F]` seed change (not a product shim).
- **Codification candidate (N≥2 — surfaced loudly):** a `check_*` keeper that
  diffs a **seed-store/adapter write-payload key set vs the consuming product's
  migration DDL columns** (and Protocol field set vs consumer field reads). The
  `MockRequestBuilder` never validates columns ⇒ schema-shape divergence is a
  systemic false-green blind spot (N≥2 with `feedback_structural_refactor_grep_blindspot`
  + `feedback_verify_seed_ships_it`). Routed to phase_learnings + surfaced to
  architect/user. Not built now (own thread; s2 memory candidate). Interim
  mitigation already baked into Phase 1 (payload⊆columns contract assertion).
- Candidate recurrence pattern: **absorbed product lifts seed code but skips
  consumer-refactor** → the seam exists, the fork persists, MASTER-PROMPT
  falsely claims "consumed". Sibling of R1 (`absorption-ships-consume-docs`).
  If this recurs on the next absorption, route to codification (a keeper that
  flags `googleapiclient`/raw-oauth in a product whose MASTER-PROMPT claims
  the seed seam is consumed). Logged here; not yet s2 (N=1 as a *named*
  pattern — watch the next absorption).
