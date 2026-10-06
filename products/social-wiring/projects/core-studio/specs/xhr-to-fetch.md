# CoreStudio — read-only XHRs still to fetch

Precise list of **read-only GET** endpoints whose responses we still need to finish mapping content and mechanisms (2026-10-06). Every entry was checked against the page scripts: none mutates state, triggers AI generation, spends credits or deletes. Run them in the owner's logged-in browser with `Accept: application/json` and `X-Requested-With: XMLHttpRequest` (some controllers only answer JSON with these headers — `profile-viral-search` is one).

Base: `https://corestudio.ai/dashboard/user`. IDs below come from the crawl. Save each response under `captures/xhr-2026-10-06/<name>.json` and **redact before committing** (`access_token`, `_token`, CSRF, any `eyJ…`).

## A · Do NOT call (GETs that mutate or generate)

These are GET routes in CoreStudio but change data or spend AI: `headlines/reprocess/{id}` (re-runs a batch), `headlines/delete/{id}`, `headlines/favorites/delete/{id}`, `roadmaps/delete/{id}`, `cores/custom/delete/{id}`, `cores/remove/{id}`, `profile/integrations/delete`, `searches/viral/topics/approve/{id}`, `searches/viral/topics/reject/{id}`, `searches/viral/topics/remove/{id}`, `searches/remove/{id}`. Also avoid any page that loads `headlines.js` more than needed: it fires `POST headlines/generate-sugeridas-day` on load (Dashboard, `/headlines?who=…`, Favoritas). All POSTs are excluded, including Livewire.

## B · Priority 1 — reveals the intelligence

| # | GET | Params / ids | Why |
| --- | --- | --- | --- |
| 1 | `/headlines/suggested/view/{id}` | 201775, 201774, 201760 (any 3 of the dashboard ids 201755–201775) | Returns `payload_headline_old_1`, `callback_headline_old_1`, `payload_headline`, `headline`: the stored **prompt payloads of both passes**. Likely the real headline prompts, with no credit spent. |
| 2 | `/library/result/{id}` | structures cited in chat: 124680, 124688, 124672, 127980, 149271, 147303, 152098, 157372; the 5 unexplained ids 124684, 124700, 147089, 147091, 148727; 2 top library virals 105038, 135319 | Full viral JSON: transcript, hook headline, niches, professions, formats, `is_core`, `eng_reversa_search_id`. Shows what a "structure" is made of; explains the 5 ids not found in the allow-listed profiles. |
| 3 | `/searches/profile-viral-search/{searchId}` | 1735 (elias.maman), 1702 (psifernandosegredo), 1640, 1761, 1545, 1457 | Precomputed research extraction per profile: which variables, phrase vs hook sentence, per viral. Ties research items to structures. |
| 4 | `/headlines/profiles` | — | Profile list with `is_structure`: which profiles have structures; size of the structure-bearing set. |
| 5 | `/library/videos` | `profile=elias.maman`; `profile=psifernandosegredo&format_video=10`; `views_min=1000000` | Picker JSON (`title`, `description`, `format_name`, `transcription_text`): a second viral shape; check whether `title`/`description` hold the extracted headline/structure. |
| 6 | `/cores/brain-status/{coreId}` | 3081, 8, 9, 14, 3741, 4191, 4192 | Brain state contract (`brain_status`, `validation_status`, `responses[{question_id, status, rejection_reason}]`) for answered, empty and custom brains. |
| 7 | `/headlines/view/{id}` | batch ids from the `headlines/list` table (a read-only DataTables POST; owner shows 0 generated, so likely nothing to fetch) | `headline_preview`, `payload`, `params`, `structure_count`, `headline_count` of a form batch. Skip if there are none. |

## C · Priority 2 — completes the content map

| # | GET | Params / ids | Why |
| --- | --- | --- | --- |
| 8 | `/searches/variables/items` | `type=avatar`, `type=especialista` | Full research items (≈110 approved + 160 pending on 2026-10-05) with `eng_reversa_result_id`; source virals of the auto-suggested items. |
| 9 | `/searches/approved-profiles` | — | The 485 approved profiles with niche/profession tags and thumbnails: corpus coverage by niche. |
| 10 | `/searches/approved-profiles-viral-topics` | — | Which profiles support viral-topic extraction; compare with #9. |
| 11 | `/searches/viral-data/{topicId}` | 442798, 442794, 442789 | The virals behind a viral topic (topic ↔ video link). |
| 12 | `/searches/user-variables-viral-data/{itemId}` | 2–3 pending item ids from #8 | Unused by the UI; check whether it returns the source virals of a research item. |
| 13 | `/headlines/suggested/get/{id}` | 201775, 201755 | Suggested headline + roteiro fields as the edit modal reads them. |
| 14 | `/roadmaps/reversa/show/{id}` | 201775 | Roteiro attached to a suggested headline (`eng_reversa_headlines` save target). |
| 15 | `/headlines/suggested/advanced-roadmap/show/{id}` | `?headline_id=201775` | `roadmap_advanced`, `search_text`, `use_article`, `roadmap_source` for a suggested headline (may be empty). |
| 16 | `/roadmaps/view/{id}` | 41429 (41428 already captured) | Second roteiro: `params`, `payload`, `search_text`, feedback. |
| 17 | `/profile/instagram/posts/all` | — | All imported posts with the `selected` flag: size of the import window and the purpose of the dormant 60-post selection. |
| 18 | `/profile/instagram` (page) | `?page=2`, `?page=19` | Oldest imported posts → import window rule. |
| 19 | `/library` (page) | `?view_all=1`; `?view_all=1&core=1`; `?view_all=1&viral_result_id=124684` | Unfiltered corpus size (page count); whether the Core filter applies for non-staff; direct card for an unexplained id. |
| 20 | `/library/profiles` | `profile=a`, `profile=elias` | Profile search with `video_count` per profile. |
| 21 | `/cores/edit/{coreId}` (page) | 3741, 4191, 4192 | Custom-brain editor HTML and content structure (inventory has headings only). |
| 22 | `/headlines` (page) | `?who=viral` | The Assuntos Virais form variant as rendered for the owner. **Caution:** this page loads `headlines.js`, which fires `POST headlines/generate-sugeridas-day` (see §A); fetch only if the owner accepts that side effect (the 2026-10-06 crawl already loaded such pages). |

## D · Priority 3 — shapes only

| # | GET | Why |
| --- | --- | --- |
| 23 | `/my-library/requests` | Request list shape (`status`, `notes`). |
| 24 | `/my-library/check-profile?profile=@elias.maman&social=instagram` | Status vocabulary (`in_library`…). |
| 25 | `/library/workspaces` | Workspace list used by the Biblioteca wizard. |
| 26 | `/profile/get-niches-professions` | Targeting shape (already known from the profile page). |
| 27 | `/notifications` | Notification payload (`title, body, link, icon, type, status`). |
| 28 | `/twin/api/credits` | Credit packages and `has_payment_method` (billing data; optional). |

## E · Not fetchable read-only

Job-status GETs need a job id that only a mutating call creates: `searches/add-items-job/{id}`, `searches/extract-profile-status/{id}`, `cores/youtube/status/{id}`, `headlines/status/{id}` (works for an existing batch only), `roadmaps/check-status/{id}`. Livewire chat actions (`searchMentions`, `searchMyResearch`, `searchMyCerebro`, `loadToolDetail`) are POSTs to `/livewire/update`; the "Trace da IA" drawer (system prompts per chat message) needs a click on an existing assistant message and is the other prompt source if #1 comes back empty.
