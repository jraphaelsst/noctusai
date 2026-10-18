# Instagram content analysis — post mode and profile mode

**The rule.** An Instagram analysis follows one order: **extract everything first**, then transcribe, then analyse, then report. The report gives value the owner can act on (what to make next, and why). A summary of the post is not enough. The procedure lives in skill `noc-ig-analysis`, and this file holds the depth: endpoints, failure modes, the analysis vocabulary, and the run history.

**Why.** Before this skill existed, the same procedure was rebuilt by hand four times between 2026-09-21 and 2026-10-18, each run rediscovering the same traps: logged-out caps, 429s, signed-URL filtering, the DASH-format rejection, transcription quotas. Under `repetitive-task-skill-codification.md`, N≥2 means it becomes a skill.

## 1 · Extraction surface (logged-in tab, in-page `fetch`)

| Need | Endpoint | Notes |
|---|---|---|
| Shortcode → media id | base64url alphabet `A-Za-z0-9-_`, BigInt over the first 11 chars | `IG.toId` |
| Post metrics, caption, DASH | `GET /api/v1/media/<id>/info/` with header `X-IG-App-ID: 936619743392459` | reliable, ~1 req/s fine |
| Comments | `GET /api/v1/media/<id>/comments/?can_support_threading=true&permalink_enabled=false`, paginated with `min_id=next_min_id` | includes `preview_child_comments` |
| Replies | `GET /api/v1/media/<id>/comments/<pk>/child_comments/`, paginated with `max_id=next_max_child_cursor` | dedupe by pk |
| Profile reel list | the `/<user>/reels/` grid DOM, **accumulated while scrolling** (the grid is virtualized) | `web_profile_info`, `users/<id>/info` and `clips/user` return 429 or HTML |
| Logged-out fallback | the `og:description` meta (likes, comments, caption head) | no comments beyond about 15 |

Output-filter constraints: never return CDN URLs or query strings, and render exports as `<article><pre>` read through `get_page_text`. `coauthor_producers` is blocked ("Sensitive key"), so read coauthors from the caption.

## 2 · Media and transcription

- DASH manifest → `AdaptationSet[contentType=audio]` (about 57 kbps) or the lowest video rep. The page fetches it into a blob and triggers `<a download>`. **Each batch of downloads needs owner consent.**
- The platform transcription API (`noctus.transcription.*`, core; contract `products/core/projects/transcription-api/CONTRACT.md` §3) rejects fragmented MP4 with `415 formato_invalido`, so convert to mono 16 kHz mp3 first.
  - Caps per caller: **20 submissions per rolling hour, 3 in flight, 180 min per 24 h**, POST 10/min. 50 reels therefore take ≥2.5 h. `noctus.transcription.batch` keeps within these caps and can resume.
  - A killed client leaves its jobs **in flight** on the server, still holding slots. Don't resubmit what is already queued.
- Faster for 30+ reels: run local faster-whisper (sibling repo `knowledge-extractor/backend/.venv`, model `mobiuslabsgmbh/faster-whisper-large-v3-turbo` int8, `cpu_threads=4`, `nice`) at the same time, in reverse order, writing to the same `<stem>.txt` dir (claim with a `.local.lock`).
- LGPD: this is third-party voice. Delete the raw audio once it's transcribed, and use the result to study structure only (`LGPD-WARNINGS.md`, Biblioteca de virais entry).

## 3 · Analysis vocabulary — reuse the platform's, don't invent one

Profile mode classifies each reel with the **same taxonomy the social-wiring Biblioteca de virais classifier uses**, so a study's output can feed `geracao` directly:
- **Formats** `FORMATOS_VIDEO` (15) and **attention triggers** `GATILHOS` (7): `products/social-wiring/backend/app/modules/media_creation/geracao_taxonomias.py`.
- **Gancho** (literal opening line) and **blueprint** (the gancho with `{{SLUG}}` research-variable slots from `pesquisa_variables.CLASSIFIABLE`): prompt `…/prompts/biblioteca_classificador.py`, with the pure parser `parse_classificador_output`.
- On top of the platform schema, the study adds the **beat sequence** (the order of the moves), the **thesis formula** (e.g. "existe uma diferença entre X e Y"), the **CTA type** (keyword-DM / question / save / share / link-in-bio), and plays normalised by the profile's median.

Post mode needs a risk scan first: suicide, self-harm or acute distress goes at the top, noting whether it got a reply. Then owner/circle/audience split, theme classification by hand-reading (regex tallies are noisy at ≤300 comments), top-liked comments, reply coverage, tag/share counts, and audience questions turned into pautas.

## 4 · Report shape

A pt-BR HTML artifact in the IG-report series identity. Profile mode adds the two-axis family chart, one card per structure (beat rail + real hook + taxonomy + blueprint), signature devices, the funnel timeline, "o que não copiar" and a Biblioteca-ready table (olive and lamp tokens, Archivo / Source Serif 4 / IBM Plex Mono / Instrument Serif, the on-screen hook rendered as white boxes). No usernames. One post is analysed on its own unless the owner asks for comparisons. The report always closes with a method-and-limits section.

## 5 · Runs

| Date | Target | Artifact |
|---|---|---|
| 2026-09-21 | Mônica reel (viral "Ninguém prepara uma mãe") | "O Reel dos 4 Mil" |
| 2026-09-28 | Mônica carousel DdxRjYEiZTF | "O Carrossel da Travessia" |
| 2026-09-30 | Gilson, 88 posts (profile) | "A Fórmula Gilson" |
| 2026-10-18 | Mônica × Isa collab reel DenRejRJTJN | "O Reel das Duas" |
| 2026-10-18 | @lisianecattani, 50 reels (profile) | "A Fórmula Lisiane" (skill born here) |

**Lessons from the Lisiane run** (the first run under the skill):
- Ranking on plays alone misled. 8 of the 12 reels above 40k plays had <1% likes per play (launch window + 5 s loops), so two axes are mandatory.
- Local Whisper finished 50 reels in about 40 min. The API batch was stopped after its in-flight slots stayed occupied for about 15 min.
- The grid is virtualized: one end-of-scroll read returned 20 of 64 codes.
