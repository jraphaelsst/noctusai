# findings — social-wiring-google-seed-consume

> Durable findings ledger (5 categories). Append in-the-moment; synthesize at
> close. Symbol-first (AI scaffolding).

## Slips / errors

- (none yet)

## Mistakes (process)

- (none yet)

## Lessons

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

- Candidate recurrence pattern: **absorbed product lifts seed code but skips
  consumer-refactor** → the seam exists, the fork persists, MASTER-PROMPT
  falsely claims "consumed". Sibling of R1 (`absorption-ships-consume-docs`).
  If this recurs on the next absorption, route to codification (a keeper that
  flags `googleapiclient`/raw-oauth in a product whose MASTER-PROMPT claims
  the seed seam is consumed). Logged here; not yet s2 (N=1 as a *named*
  pattern — watch the next absorption).
