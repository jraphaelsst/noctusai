# social-wiring-drive-projection-enrichment — Project Document

> **Filed 2026-05-19** as the named destination for the Phase-5 Drive API deferral.
> The full field-by-field projection gap is documented authoritatively in
> `products/social-wiring/backend/app/services/drive_api/__init__.py` (the
> module docstring is the canonical gap-spec; do not duplicate it here).
> Same `absorbed-product-seed-shape-seam` pattern, projection-mismatch axis;
> sibling of the `seed-google-drive-projection-enrichment` work the engineer
> SW-P5 routed.

- **Status:** Filed (gap-spec captured; ready for in-flight resolution as part of `social-wiring-google-seed-consume` Phase 6a OR as a standalone follow-up if scope shifts)
- **Owner / stakeholders:** joaoraphaelsst · architect
- **Slug:** `social-wiring-drive-projection-enrichment` — intent: `expansion` (seed Protocol enrichment + consumer migration)
- **Related docs:** `products/social-wiring/backend/app/services/drive_api/__init__.py` (canonical gap-spec) · `KB § PATTERNS/absorbed-product-seed-shape-seam.md` (pattern body, projection-axis worked examples — youtube `_build_service` retention + this) · sibling `seed-youtube-read-projection-enrichment` (same pattern, youtube integration) · sibling `social-wiring-meta-seed-consume` (same pattern, Meta integration) · `KB § INTEGRATIONS/google.md` (consume-side reference)

## 1. Context & Purpose

Phase 5 of `social-wiring-google-seed-consume` migrated Calendar fully but deferred Drive: the seed `noctusai_lib.integrations.google_drive.DriveReader` Protocol projects a strictly narrower field set than the chatbot UI consumes (`parents`/`owners`/`icon_link`/`is_folder`/`raw` on hits; decoded `text`/`bytes_read`/`raw_mime` + PDF-text extraction on file content; naming deltas `id`/`file_id`, `modified_time:str`/`modified_at:datetime`; async-only Protocol vs sync FastAPI handlers). Migrating without enrichment would silently degrade the chatbot UI — anti-pattern per `KB § PATTERNS/absorbed-product-seed-shape-seam.md`. This project enriches the seed first, then collapses the product Drive surface to a thin re-export (as Calendar did).

## 2. Confirmed constraints

- **Seed-first.** Enrich seed `noctusai_lib.integrations.google_drive` Protocol+Fake+Real+factory **back-compat-defaulted** (today's narrow shape preserved as the default; richer shape opt-in via a new method or a `full=True` flag — design-call at Phase 0). Defaults = no observable change for current consumers. Pilot-gate verified no-op.
- **Sibling parity.** Mirror the youtube projection-enrichment work (`seed-youtube-read-projection-enrichment`): same pattern, just a different integration. Could be dispatched in parallel with that one (file-disjoint at `seed/integrations/{youtube,google_drive}/`).

## 3a. Seed-first analysis

Canonical body: `KB § PATTERNS/absorbed-product-seed-shape-seam.md` — this is the projection-axis variant (N=2: youtube `_build_service` + this drive). Same back-compat-defaulted seam recipe.

## 6. Implementation phases (suggested)

- **Phase 0** — read the canonical gap-spec at `drive_api/__init__.py`; map every consumer site (start with the engineer's enumeration: `whatsapp_intake_service.{search_drive_files,list_recent_drive_files,get_drive_file,query_drive_sheet,read_drive_file}` + the SA/OAuth adapter methods). Decide sync facade approach (async seed + `asyncio.to_thread` bridge, or sync facade method on seed).
- **Phase 1** — `[F]` seed Protocol+Fake+Real enrichment (back-compat-defaulted: existing `DriveSearchHit`/`DriveFileContent` unchanged; add `DriveSearchHitFull`/`DriveFileContentFull` OR additive optional fields on existing types — design at Phase 0).
- **Phase 2** — consumer migration: collapse `products/social-wiring/backend/app/services/drive_api/*` to a thin seam re-exporting from seed (target shape: ~150 LoC like calendar's, down from 773 LoC). `git rm` the fork modules.
- **Phase 3** — full verify (social-wiring 383 baseline; seed full; mcp/google; mcp/noctusai); MASTER-PROMPT row update if applicable.

## 9. Success criteria

- Seed `DriveReader` Protocol projects the field set social-wiring needs (parents/owners/etc.); Fake mirrors; Real wraps the same `drive.files().list/get` calls.
- `services/drive_api/*` collapses to thin re-export (~150 LoC; matches calendar's shape).
- All consumer sites (5 in `whatsapp_intake_service`) read `.metadata` / projected fields directly from seed value objects (no product mappers needed).
- Pilot gate green (additive-with-defaults provably no-op for non-social-wiring consumers).

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-19 | Filed at Phase-5 close of `social-wiring-google-seed-consume`. Engineer SW-P5 captured the field-by-field gap in `drive_api/__init__.py` (canonical spec). Same pattern as `seed-youtube-read-projection-enrichment` — could be dispatched in parallel (file-disjoint at seed). | Claude (architect) |
