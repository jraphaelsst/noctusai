# Test checklist — Tours Virtuais v1

Synthetic fixtures only (generated 2:1 gradients from `FakePanoramaSource`, a few real CC0 equirects stored in the test tree under a size budget). No client panoramas in the repo.

## Seed (S1–S3)
- [ ] `ingest_equirect` on 8192×4096, 4096×2048, 6000×3000 and a 3:2 image: variant sizes, JPEG validity, `proporcao_ok` true/false, no EXIF in any variant.
- [ ] GPano XMP start view read (heading 90° ⇒ yaw π/2); missing XMP ⇒ 0/0.
- [ ] Refusals: > max pixels ⇒ `imagem_grande_demais` before full decode; corrupt bytes ⇒ `decodificacao_falhou`; GIF/HEIC ⇒ `formato_invalido`.
- [ ] `roll_horizontal` by Δyaw keeps a marker pixel at yaw+Δ.
- [ ] Fake/Real parity: same Protocol tests run against Fake and Real imaging + panorama sources.
- [ ] `signed_upload_url`: Fake/Local/Supabase return `{url, method, headers, expires_at}`; Supabase adapter test against the client double, no monkeypatching of our own seams.
- [ ] `PanoramaViewer` (vitest): renders markers from props, emits `onPlace(yaw,pitch)` in edit mode, applies `chegada` on navigation, autorotate stops on interaction and with reduced motion, WebGL-missing fallback renders the gallery.
- [ ] `noctus.dev.check_framework_deps` green fleet-wide after the viewer dependency lands.

## social-wiring backend (S4–S5)
- [ ] Migration replay (`noctus.dev.migration_replay`) green twice (idempotent); `check_access_tier_tables --paths <migration>` green (tier comments, REVOKEs, no browser grant on `tour_links`/`tour_visitas`); `check_storage_bucket_public` green (bucket private).
- [ ] RLS: a member of org B cannot SELECT org A's tours/photos/pairs (replay probe); anon reads nothing.
- [ ] Every editor route: unauthenticated ⇒ strictly `== 401`; other org's id ⇒ 404 (never 403 leaking existence).
- [ ] Versioning: two PATCHes with the same `versao` ⇒ first 200, second 409 with `atual`; reorder with a stale tour version ⇒ 409; reorder with a different id set ⇒ 422.
- [ ] Pair invariants: `foto_a_id < foto_b_id` enforced; duplicate pair ⇒ 409; pair across tours refused by trigger; deleting a photo removes its pairs and info points.
- [ ] Arrival maths: `chegada.yaw = normalise(pin_destino.yaw + π)`, pitch 0; flag ⇒ target start view; values in (−π, π].
- [ ] Upload flow: F1 creates rows + signed URLs; F2 without the object ⇒ 409 `arquivo_ausente`; F2 twice ⇒ one job (dedupe); stale job no-op; sweep removes 24 h-old `aguardando_envio`.
- [ ] Quota: at `limite` E2 and E8 ⇒ 402; removed tours not counted; null limit ⇒ unlimited.
- [ ] `segmento='obra'` and `navegacao_modo` ≠ pins ⇒ 422.
- [ ] Viewer V1: unknown, revoked, unpublished, removed ⇒ identical 404 bodies; published ⇒ manifest has no org id, user id, version, storage path or other token; only `pronta` photos; links to non-ready photos dropped.
- [ ] Unpublish then V1 within the cache window ⇒ 404 after ≤ 60 s; rotate link ⇒ old token 404 at once.
- [ ] V2/V3: referrer stored as host only; no IP/UA stored (column inventory test); V3 monotonic; V3 for a visit of another token ⇒ 404.
- [ ] V4: honeypot filled ⇒ 201 without creating a lead (silent to the bot, logged as `honeypot` metric); Turnstile fail ⇒ 403; `consentimento=false` ⇒ 422; success ⇒ one `leads` row with source `tour-virtual` and the tour's `codigo_imovel`, `lead_novo` notice fired once, visit linked.
- [ ] Rate limits on every `/api/public/tours/*` route (keeper requires a limiter on public routes).
- [ ] `assert_schema_clean` / `assert_tier_contract` cover the new routes once the product adopts them.

## social-wiring frontend (S6–S7)
- [ ] Contract tests assert the E*/V* shapes from `specs/tour-api-contract.md`, never a private mock shape.
- [ ] Parallel uploads: 6 files ⇒ at most 3 PUTs in flight; one failure does not stop the others; cancel aborts.
- [ ] Panoramas never pass through `prepareImageForUpload`.
- [ ] 409 handling: the screen shows the server's row and the message; no silent retry.
- [ ] Viewer: WhatsApp button visible in every state that has a tour; beacon sent on `pagehide`; gyroscope permission requested only on tap.

## Live (owner, after deploy)
- [ ] Shoot one imóvel with the office's 360 camera, upload 10+ photos from a laptop and 3 from a phone on 4G.
- [ ] Link rooms, publish, open the link on iPhone and Android, walk every pin, check arrival direction.
- [ ] WhatsApp button opens the right number with the pre-filled message; a lead from the form appears in Leads with source "Tour virtual" and the right imóvel.
- [ ] Unpublish ⇒ the link shows "indisponível" within a minute; republish ⇒ works again.
- [ ] `noctus.dev.predeploy_check social-wiring` ready; `noctus.dev.spa_smoke` with deep link `/t/<token>`.
