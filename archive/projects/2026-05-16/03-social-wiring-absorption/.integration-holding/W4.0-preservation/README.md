# W4.0 — RISK-A preservation snapshot (pre-deletion, social-wiring-absorption Wave 4)

> Created 2026-05-16 by Engineer **W4-EXEC** BEFORE the irreversible Wave-4 product deletions.
> This directory is **in-noc** (under `projects/social-wiring-absorption/.integration-holding/`),
> survives the `products/{mailing,youtube-crawler,imobi-scheduling}` deletion, and is NOT under
> `archive/` (so it is not subject to the archive-trim policy while this project is open).
> Ledger disposition recorded: `project-history/ledger.ndjson` slug
> `social-wiring-absorption-wave4-teardown` (append-only, +1 line).

## Why this exists

The W0.2 audit covered only the **originating sibling workspace**, not in-noc product subtrees.
Deleting `products/{mailing,youtube-crawler}/` would have destroyed unique noc-internal project
history that is **not** in `project-history/ledger.ndjson`. `noctus.dev.archive` was NOT used
because it performs `git mv` (this engineer operates under a ZERO-git-ops brief; the architect
commits in hazard-grouped commits) — the manifest's RISK-A explicitly authorizes the
ledger-record alternative. To preserve the *substance* (not merely a disposition line), the
content is snapshotted verbatim here and the disposition is ledger-recorded.

## Contents + disposition

| Snapshot | Source (deleted in Wave 4) | Disposition |
|---|---|---|
| `mailing-wiring__PROJECT.md` (468 lines, byte-verified) | `products/mailing/projects/mailing-wiring/PROJECT.md` | Phases 0-2 ✅; **Phases 3-5 PENDING (incomplete)**. Durable Phase-0/2 substance already lives in `KB § PATTERNS/accept-with-rationale.md` → "Entries from `mailing-wiring` Phase 2" (4 entries, re-pathed to `social-wiring/email_marketing` by W4.4). Phases 3-5 design **superseded** by the Wave-2 absorption of mailing → `products/social-wiring/app/modules/email_marketing/`. Not previously ledgered → now ledgered + snapshotted. |
| `youtube-crawler-domain-implementation__PROJECT.md` (361 lines, byte-verified) | `products/youtube-crawler/projects/youtube-crawler-domain-implementation/PROJECT.md` | "Design draft — needs user interrogation before Phase 1"; **never executed**; fully superseded by `social-wiring`. Low value; preserved verbatim + ledger retirement note. |
| `mailing-proposals-eval-20260419-014952/` (5 files, 32 KB) | `products/mailing/proposals/evaluations/20260419-014952-mailing/` | Closed proposal-evaluation set (LLM-comparison "remove product-level health.py"). Low value; preserved verbatim for completeness. |

## LGPD security sub-gate — `LGPD-WARNINGS.md:18` (HAZARD-4) — RESOLVED, not dropped

The imobi-scheduling entry warned: `oauth_credentials` stores **plaintext** Google OAuth
refresh+access tokens at
`products/imobi-scheduling/backend/app/services/calendar.py:SupabaseCalendarCredentialResolver`.

**Re-verification (2026-05-16) against the absorbed code in `products/social-wiring/`:**

- `products/social-wiring/backend/migrations/001_social-wiring.sql:84-93` —
  `social_wiring.credentials.encrypted_tokens TEXT NOT NULL -- Fernet-encrypted JSON`;
  explicit comment: *"Plaintext never lives in the DB; the encryption key lives in .env
  (ENCRYPTION_KEY) so DB compromise alone cannot recover the refresh token."*
- `products/social-wiring/backend/app/services/calendar/oauth_adapter.py` +
  `.../calendar/__init__.py` — the absorbed Calendar OAuth path consumes
  `app.services.credential_store.CredentialStore` (Fernet-encrypted rows), NOT a
  plaintext-token resolver.

**Conclusion:** the plaintext-credential vulnerability described in the warning **did NOT carry
forward** into the absorbed scheduling code. The absorption itself (Wave-2 credential_store
bridge architecture) is the mitigation the original entry's *Mitigation* block called for
("Mid-term: file `seed/lib crypto envelope helper`… so the resolver can encrypt/decrypt
refresh_token transparently"). The entry is therefore **RESOLVED with a dated fact**, not
silently dropped and not path-deleted. The `LGPD-WARNINGS.md:18` rewrite (W4.4) strikes the
open checkbox to resolved and re-anchors the dated fact; the durable record survives here + in
the ledger. (Route-through `noctus.dev.lgpd_flag` was NOT needed — the resolution is
unambiguous from the migration + adapter source, not a judgment call.)
