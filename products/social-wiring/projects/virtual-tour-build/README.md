# virtual-tour-build — our own specs for Tours Virtuais 360º

Build specs for **Tours Virtuais**, a 360º virtual-tour builder inside social-wiring: the team uploads equirectangular photos from a 360 camera, links the rooms with pins, publishes a link, and the visitor walks the imóvel and talks to us on WhatsApp or leaves a lead. These are OUR documents. **Specs only: no code and no migration is authorised yet** (the owner has not said "go all the way"; 2026-11-07).

The study of the reference app (Banib Conecta) is **private and lives outside git**: `~/Documents/repository/NoctusAI/_private-studies/banib/`. Where a doc here says `[private study: <name>]`, that is the file `<name>` in that folder (`specs/mechanisms.md`, `captures/xhr-2026-11-07/README.md`, `ui/ui-notes.md`, `specs/phone-to-360-implementation-options.md`). Vendor material never enters the repo (`KB § PATTERNS/common/app-reverse-engineering.md`).

## Scope

| v1 (this build) | Later (named phase, see `SLICES.md`) |
|---|---|
| Real estate only (`segmento='imobiliario'`); a tour attaches to an imóvel of the org | Construction (`obra`): project/area hierarchy, comments, versioning clones (P6) |
| Upload of 2:1 equirectangular photos from a 360 camera, in parallel, straight to private storage | Phone capture + stitching through the same `PanoramaSource` seam (P3) |
| One ingest path `ingest_equirect` → `web`, `thumb`, `preview` (blurred) variants | Privacy blur brush, HD variant for desktop, AI editing of panoramas through Edição de Fotos (P4) |
| Navigation by **pins** placed in both photos (two-pin gesture, arrival rule in `DECISIONS.md` D-T5) | Arrows/circles computed from a floor plan + floor plans + minimap (P2) |
| Info hotspots: text and link | Image and video hotspots (P4) |
| Always-visible WhatsApp button + optional lead form → the EXISTING lead pipeline | WhatsApp-click attribution rule in Julia's origin resolver; Julia sending tour links (P5) |
| Public **link** only, minimal visit record (count, duration, rooms seen, referrer host column ready) | Portal embed (iframe), per-portal links and stats, per-room dwell (P5) |
| Plan cap counted in **tours** (never photos per tour) | MP4 auto-video (P7) |
| Per-action saves with optimistic versions (no whole-document last-write-wins) | — |

## Layout

| Path | What |
|---|---|
| `DECISIONS.md` | Owner decisions (2026-11-07, binding) + our technical decisions marked **proposed** + the open owner questions. |
| `specs/sw-and-seed-map.md` | Where every piece maps in social-wiring and the seed today (imóvel, leads, roles, storage, access tiers, organs, viewer lib) and the seed verification. |
| `specs/data-model.md` | Tables, columns, RLS, access tier per table. |
| `specs/tour-api-contract.md` | Contract-first API: editor routes (tier `org`) and viewer routes (tier pending owner decision Q1). |
| `specs/ingest-pipeline.md` | Upload flow, `PanoramaSource` seam, `ingest_equirect`, variants, jobs. |
| `specs/screens.md` | Tour list, the 4-step editor (v1 adaptation), the public viewer. Mockups by `product-designer` are a required step before any FE slice. |
| `TEST-CHECKLIST.md` | Unit, contract, security, live checks. |
| `SLICES.md` | Phased, file-disjoint slice plan with effort estimates and their evidence. |

## Status

- 2026-11-07 — S4 synthesis written (this folder). Next: owner answers the open questions in `DECISIONS.md` § Open; `product-designer` mockups; then slices W1 (seed) can start once the owner says go.

## Sensitivity

No client names, no imóvel addresses, no visitor data, no panoramas in committed files. Fixtures are synthetic.
