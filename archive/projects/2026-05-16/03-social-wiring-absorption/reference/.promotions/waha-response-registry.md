---
slug: waha-response-registry
origin: products/youtube-crawler/backend/app/services/waha_response_registry.py
intended_noc_destination: noctusai_lib/integrations/whatsapp/response_registry.py
layer_rationale: |
  Six-layer model: this is an `integration adapter side-car` —
  observability for the WAHA HTTP surface that records every distinct
  response shape we see, so schema drift across WAHA versions is
  detectable without re-engineering. Belongs adjacent to
  `noctusai_lib.integrations.whatsapp` (WAHA client + adapters live
  there per KB § PATTERNS/whatsapp-chatbot-seed.md).
seed_first_analysis: |
  Q1 — Cross-product candidate? YES. Every product that integrates
  WAHA (or any vendor with shape-variant responses) benefits from a
  registry that captures fingerprints + handling notes.
  Q2 — Variance across consumers? Schema fingerprint algorithm is
  vendor-neutral; the `source` + `direction` enums are WAHA-specific
  but pluggable.
  Q3 — Existing seed coverage? None.
  Q4 — Fake+Real shape? Real = persists to SQLite/Supabase; Fake =
  in-memory dict. Needed for unit tests that exercise WAHA error paths
  without polluting the dev DB.
  Q5 — Migration cost? Low — the helper is a single `record_waha_sample`
  function called from 4 callsites; schema migration already on SQLite.
  Q6 — Risk of premature seed lift? Medium — pattern is novel; let it
  bake at N=1 for one or two weeks before generalizing.
dependencies_on_other_additions: []
promoted_on: not-yet
---

## Why this addition exists

WAHA responses vary across versions and engines (WEBJS vs NOWEB) — the
session-status endpoint may return a session object, a bare status, or
a list. Hard-coding one envelope shape is fragile. The registry
captures every observed shape with a fingerprint + handling note so
future drift is visible (the operator can `SELECT * FROM
waha_response_samples` and see all variants).

Companion SQLite migration: `waha_response_samples` table in
`apply_sqlite_migrations.py`.

## Integration notes for noc-side

When promoting:

1. Move to `noctusai_lib/integrations/whatsapp/response_registry.py`.
2. Migration goes through `noctusai_lib`'s shared-schema mechanism (or
   stays per-product; one row per response-shape per product is fine).
3. Add a `FakeResponseRegistry` for tests — drop persistence, keep an
   in-memory dict keyed by fingerprint.
4. Consider lifting the schema-fingerprint helper into
   `noctusai_lib.observability` for non-WAHA vendor adapters (Vista,
   YouTube) that exhibit similar drift.
