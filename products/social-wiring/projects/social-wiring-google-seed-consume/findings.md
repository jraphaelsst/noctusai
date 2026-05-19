# findings — social-wiring-google-seed-consume

> Durable findings ledger (5 categories). Append in-the-moment; synthesize at
> close. Symbol-first (AI scaffolding).

## Slips / errors

- (none yet)

## Mistakes (process)

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

- The seed `oauth/google_provider.py` docstring **self-documents** that it was
  formalized to cure "the hand-rolled … oauth_adapter's refresh logic" — the
  seam was born from this exact drift class. The fork persisted because the
  Wave-1..4 absorption lifted the seed code but never refactored the consumer
  (R1/R5 absorption-debt shape: code lifted, consume side not migrated).
- Credential-table compat is verbatim: social-wiring's `credentials` DDL
  comment "Fernet-encrypted JSON" == the seed `SupabaseCredentialStore`
  docstring expectation. Clean refactor, not a data migration — the
  scope-blowup risk evaporated on inspection (estimate-off-evidence paid off).

## Knowledge / methodology routed

- **Seed gap → formalize (Phase 0):** `noctusai_lib.security.oauth.oauth_router`
  hardcodes `prefix="/api/oauth"`. An absorbed product with OAuth redirect URIs
  already registered in Google Cloud Console (here `/api/youtube/oauth/callback`,
  `/api/calendar/oauth/callback`) **cannot move them** without orphaning every
  existing consent. The seed seam needs a `prefix=`/`callback_path=` override.
  This is the canonical "absorbed product carries pre-registered external OAuth
  URIs" need — recurs on every OAuth-bearing absorption. Routed to Phase 2 as a
  pilot-gated `[F]` seed change (not a product shim).
- Candidate recurrence pattern: **absorbed product lifts seed code but skips
  consumer-refactor** → the seam exists, the fork persists, MASTER-PROMPT
  falsely claims "consumed". Sibling of R1 (`absorption-ships-consume-docs`).
  If this recurs on the next absorption, route to codification (a keeper that
  flags `googleapiclient`/raw-oauth in a product whose MASTER-PROMPT claims
  the seed seam is consumed). Logged here; not yet s2 (N=1 as a *named*
  pattern — watch the next absorption).
