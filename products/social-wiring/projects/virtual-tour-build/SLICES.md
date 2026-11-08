# Slice plan — Tours Virtuais

Gate: nothing below starts until the owner says go and answers the blocking question Q1 (`DECISIONS.md`). FE slices also wait for the `product-designer` mockups.

## Evidence used for the estimates (opened 2026-11-07)

- Edição de Fotos, the closest sibling (upload → private bucket → worker → signed URLs → review UI): product module `app/modules/edicao_fotos` ≈ 4.1 k lines of Python, FE pages `pages/edicao-fotos` ≈ 3.9 k lines, seed organ `domain/photo_editing` ≈ 7.6 k lines; history 2026-09-16 → 2026-11-06 (16+ commits) — but it also carries an AI edit pipeline, cost ledger, curators and notifications that tours do not need.
- Seed surfaces consumed as-is: storage, imaging resize, jobs, turnstile, job-polling, `@dnd-kit` (`specs/sw-and-seed-map.md`).
- Lead path is three existing calls (`olx_ingest_service.ingest_olx_lead` precedent); no new lead machinery.

Estimates are engineer-days of focused work including tests, excluding review/CI queue time.

## Waves (file-disjoint inside each wave)

| Wave | Slice | Owner agent | Files (disjoint) | Depends on | Estimate |
|---|---|---|---|---|---|
| W0 | Mockups: list, 4-step editor, viewer (mobile first) | `product-designer` | none in repo | owner answers Q2/Q3/Q7 | 2–3 d |
| W1 | **S1** seed `integrations/panorama` + imaging extension (crop, blur, read_xmp, roll) | `engineer-seed` | `seed/lib/backend/noctusai_lib/integrations/panorama/**`, `…/integrations/imaging/**`, their tests | — | 3–4 d |
| W1 | **S2** seed storage `signed_upload_url` (Protocol, Fake, Local, Supabase) | `engineer-seed` | `seed/lib/backend/noctusai_lib/integrations/storage/**`, its tests | — | 1 d |
| W1 | **S3** seed FE organ `PanoramaViewer` (PSV v5, markers, tour links, arrival, autorotate, gyroscope, LQIP, WebGL fallback) + licence/bundle check | `frontend-engineer` | `seed/lib/frontend/src/panorama/**`, seed lib `package.json` | — | 4–6 d |
| W2 | **S4** sw migration + editor API + ingest job handlers + quota seam | `backend-engineer` | `products/social-wiring/backend/migrations/<NNN>_tours_virtuais.sql`, `app/modules/tours_virtuais/{deps,schemas,errors}.py`, `…/services/{tours,fotos,conexoes,pontos,quota,ingest_job}.py`, `…/routers/editor.py`, tests | S1, S2, Q4–Q6 | 6–8 d |
| W3 | **S5** viewer API (manifest, visits, leads) + `tour-virtual` lead source + limiter + Turnstile wiring | `backend-engineer` | `app/modules/tours_virtuais/routers/publico.py`, `…/services/{manifesto,visitas,leads_tour}.py`, `app/modules/leads/seed_data.py` (one row), tests | S4 merged, **Q1**, Q3 | 3–4 d |
| W3 | **S6** FE list + editor (4 steps) + `ImovelDetalhes` panel + nav leaf | `frontend-engineer` | `frontend/src/pages/tours/**` (except viewer), `nav/navGroups.ts`, `pages/ImovelDetalhes.tsx` panel, `App.tsx` route | S3, S4 contract, W0 | 8–12 d |
| W4 | **S7** public viewer page `/t/:token` | `frontend-engineer` | `frontend/src/pages/tours/publico/**`, `App.tsx` `publicRoutes` entry | S3, S5, W0 | 3–4 d |
| W4 | **S8** e2e + live checklist + predeploy + `spa_smoke` deep link | `test-engineer` | `frontend/e2e/tours*.spec.ts`, `backend/tests/modules/tours_virtuais/test_e2e_*` | S5–S7 | 2 d |

`App.tsx` is touched by S6 and S7: S7 lands after S6 (or the route lines are added by S6 with S7 only filling the page) — the one coupling to watch.

**Total ≈ 32–44 engineer-days; ≈ 3–4 weeks wall clock** with the waves run in parallel. Biggest uncertainty: S6 (editor UX of the two-pin gesture) and S3 (viewer on low-end Android). The `migration_replay` + access-tier keepers will gate S4; the merge queue judges each wave on the merged tree.

## Later phases (named destinations for everything v1 leaves out)

| Phase | Scope | Notes |
|---|---|---|
| P2 | Floor plans, photo placement, arrows/circles computed from the plan, minimap | `tour_plantas`; placement columns on `tour_fotos` |
| P3 | Phone capture + stitching (`PhoneStitchSource`) | plan and estimates in `[private study: specs/phone-to-360-implementation-options.md]` §6.3 (spike 1.5–3 weeks, MVP 5–8 weeks) |
| P4 | Image/video hotspots, privacy blur brush, HD desktop variant, rectilinear thumbs, panoramas through Edição de Fotos | |
| P5 | Portal embed (iframe), per-portal links (`tour_links.canal`), referrer stats, per-room dwell, WhatsApp-click attribution rule in `julia_origem_service`, Julia sending the tour link | after the ImovelWeb / Viva Real integrations exist |
| P6 | Construction segment (`obra`): project/area, comments, versioning clones | after the real-estate app is validated (D-O1) |
| P7 | MP4 auto-video | |
