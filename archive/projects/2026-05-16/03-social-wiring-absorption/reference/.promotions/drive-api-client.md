---
slug: drive-api-client
origin:
  - products/youtube-crawler/backend/app/services/drive_api/
intended_noc_destination: noctusai_lib/integrations/google/drive/
layer_rationale: |
  Six-layer model: integration adapter — belongs in
  `noctusai_lib.integrations.google.drive/`, sibling to the
  `calendar/` and `routing/` adapters filed in the same session.
seed_first_analysis: |
  Q1 — Cross-product candidate? YES. Any product whose users have
  Drive content (PF for receipts, ERP for documents, daily-life for
  files) benefits from search/list/get.
  Q2 — Variance? None at the Protocol level. Tool surface (which
  prompts trigger the search) varies per product.
  Q3 — Existing seed coverage? None visible at session time.
  Q4 — Fake+Real? Yes — FakeDriveAdapter ships alongside.
  Q5 — Migration cost? Low. Same shape as calendar/.
  Q6 — Premature lift risk? Low. The reference repo
  (whatsapp-scheduling) didn't ship Drive — we built this fresh,
  modeled on the calendar package which is itself a port. Two
  consumers (this product's chatbot Drive tools + future products)
  pass the N=2 bar.
dependencies_on_other_additions:
  - google-integrations
promoted_on: not-yet
---

## Why this addition exists

User asked the chatbot "E o meu drive? Quantas casas tem registradas
la?" and the bot truthfully said it had no Drive search capability —
the only existing Drive surface was `inspect_drive_url` which is a
URL parser, not an API client.

Added the missing piece: a real Google Drive v3 read client (search,
list_recent, get_file). Reuses the same OAuth credential bundle the
calendar adapter wrote (scope widened to include `drive.readonly`),
so a single consent flow grants both Calendar and Drive.

## Integration notes for noc-side

When promoting:
1. Move `drive_api/` → `noctusai_lib/integrations/google/drive/`.
2. The OAuth credential bundle is shared with calendar — keep the
   `CALENDAR_PROVIDER` constant import from the calendar package, or
   generalize it into a shared `GOOGLE_OAUTH_PROVIDER` name once both
   live in noc.
3. The 3 chatbot tools (search_drive_files, list_recent_drive_files,
   get_drive_file) plus their intake handlers become part of the
   ChatbotIntake protocol surface alongside calendar + maps.
4. Consider adding write tools (drive.file scope) when the seed
   chatbot needs to attach files to events / upload reports / etc.
   Out of scope for v1.
