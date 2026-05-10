# noctusai-lib-nfe-domain-absorption — Orchestration Findings

> Transcribed by the orchestrator post-merge per `KB § PATTERNS/branching-and-merging.md § 17.6.1` (return-as-text protocol). Engineer E returned the 5-category content as text in their report after the harness blocked their `findings.md` Write call.

## Errors encountered

None.

## Mistakes / slips

None observed. Architect's brief pre-resolved the major slip risk ("design-only at N=1, NOT premature absorption") in the framing.

## Lessons learned (durable rules)

- **L1 — N=1 absorption attempts are the canonical recurrence-rule slip.** Shape being canonical is necessary but not sufficient for lifting; the rule is N=2+ consumers, period. Catalog entry is the structurally-correct landing for an N=1 well-shaped module.
- **L2 — Pre-emptive PARKED follow-up project ≠ accept-with-rationale entry.** Discriminator is whether the second consumer already exists. N=1 with no second in flight → catalog entry. N=2 already-live → PARKED follow-up project (cf. `send-message-consolidation`). N=3+ → URGENT formalize project.
- **L3 — Architect-pre-resolved slip risks land deliverables clean.** Counter-framing the most likely slip in the brief ("absorption is NOT the deliverable; the catalog entry is") collapsed an entire decision branch the engineer would otherwise have walked.

## Interesting findings (surprises, discoveries)

- **I1 — AdConnect's `nfe_service.py` is single-file but canonical-shape-correct.** Single 444-line file at N=1; canonical seed reference (`google_calendar/`) splits the same surface across 5 files. Both are correct in their layers — single-consumer leaf modules stay single-file; the split happens AT lift time (parity with `whatsapp-seed-absorption`'s lift recipe).
- **I2 — The factory's `NotImplementedError` stubs ARE the design hook for N=2.** `make_nfe_provider` already lists `nfeio` and `enotas` as known future vendors. When N=2 lands, the lift project starts by replacing those stubs with the second consumer's real adapter — good forward-stub design.
- **I3 — DIMOB is XML-fiscal but a different domain entirely.** `dimob_service.py` + `xml_feeds.py` share `xml.etree.ElementTree` (stdlib) with a hypothetical NF-e parser, but DIMOB is yearly income-tax informational return and `xml_feeds.py` is property-listing XML — neither overlaps NF-e. **N=3 on a stdlib import is not recurrence**; recurrence is N≥2 on the same domain helper.
- **I4 — `nfe_service.py` was inaccessible** because adconnect-mvp-implementation hadn't been merged to main yet. Engineer used `git show adconnect-mvp-implementation:<path>` as workaround. Future briefs that depend on artifacts from a still-unmerged sibling branch should pre-flag the cross-branch dependency. **This finding contributed to the §14.2 prerequisite-merge formalize.**
- **I5 — `noctus.dev.archive` MCP tool failed** for cross-tree git mv (server resolves paths from noc, attempted to mv from worktree to noc/archive). Fell back to plain `mv` + git auto-detected the rename. Minor MCP gap; the tool could be hardened to detect worktrees. Reproduced again during orchestrator merge — confirmed N=2.

## Knowledge pieces (durable patterns)

- **K1 — Lift recipe for `noctusai_lib.integrations.nfe` (when N=2 fires).** Embedded in the catalog entry. Steps: create 5-file skeleton mirroring `google_calendar/`, refactor AdConnect's `nfe_service.py` to a thin re-export shim, wire second consumer to import from lib, move Fake-side + Protocol-contract tests to `seed/lib/backend/tests/test_integrations_nfe.py`, run AdConnect suite to confirm shim works, flip catalog entry to FORMALIZED.
- **K2 — Phase 0 audit grep recipe.** Three-layer N-count check: word-boundary grep + adjacent-domain grep + MCP recurrence scans. Covers the false-positive blind spots ("rejected" word collisions, stdlib-shared but different-domain collisions).
- **K3 — Catalog entry shape for "well-shaped N=1 module"** is now load-bearing across at least 2 active entries (Stripe webhook from `webhook-hmac-consolidation`, and this NF-e entry). Reusable template for the next single-consumer well-shaped vendor adapter.
- **K4 — Standing-duty `scan_within_product_helpers` flagged 19 within-product duplications** (e.g. `_resolve_org_id` x5 in adconnect routers, `get_resumo` x6 in erp services, `_get_service` x5 in mailing) — out of scope for this NF-e-focused project. Worth surfacing to the architect as candidates for either standalone follow-up projects or drive-by cleanup during touch passes. Not silently dropped.
