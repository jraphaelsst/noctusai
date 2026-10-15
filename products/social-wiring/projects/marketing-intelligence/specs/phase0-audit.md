# Phase-0 audit — building SIMEC, Central Editorial and AR3 in social-wiring

Architect agent, read-only, 2026-10-15. Paths are relative to the repo root. Verify a path still exists before relying on it.

**Bottom line.** About 60% of the hard part already ships. social-wiring collects Instagram data every day (catalog, per-post insights, profile insights) through the seed's Instagram Login adapter (Protocol + Fake + Real + factory). So SIMEC-Instagram is mostly a calculation and presentation layer over data we already have. Missing:
- Comment collection on Instagram Login (neither the adapter nor the scope covers it).
- TikTok (nothing exists).
- Per-marca access control inside one org (RLS only separates orgs).
- The SIMEC calculator, decision log, reports and the AR3 tree.

The Central Editorial is **not a new module**: its commands map onto Criação de Mídia (Pesquisa, Segundo Cérebro, Roteiros, Legenda, Esteira, Chat).

## 1 · What already exists

| Need | Where | State |
|---|---|---|
| Instagram insights client | `seed/lib/backend/noctusai_lib/integrations/meta/instagram_login_adapter.py`; metric catalog `meta/instagram_insights.py` (an unreturned metric is stored as `None` + `unsupported`, never 0) | Full |
| Instagram daily collection | `products/social-wiring/backend/app/modules/instagram/` (`sync_service.py` 90-day window, `scheduler.py` cron `30 5 * * *`, `repository.py`, `metrics.py`); tables `ig_media`, `ig_media_snapshots`, `ig_profile_snapshots` (migration 208); FE `components/instagram/*` | Full, in prod |
| Instagram comments | `seed/.../meta/oauth_adapter.py` `list_instagram_comments` + reply/hide/delete; `backend/app/routers/meta_comments_router.py` | **Facebook Login only.** Missing on Instagram Login: no adapter method, and `instagram_business_manage_comments` is not in `IG_BUSINESS_LOGIN_SCOPES` (`backend/app/services/integration_providers.py`) |
| TikTok | none; seed reserves `integrations/tiktok/` (`seed/.../meta/__init__.py`) | Absent |
| Template for a new platform | `seed/.../integrations/youtube/{protocol,fake,real,factory,types}.py` + `products/social-wiring/backend/app/modules/youtube/` | Full |
| Scheduling | `seed/.../api/scheduler.py`, `backend/app/services/sync_lease.py`, `snapshot_runs.py`, `seed/.../domain/jobs/` | Full |
| Alerts | `backend/app/services/notification_service.py`, `seed/.../domain/notifications.py`. A failed sync only reaches logs and a `snapshot_runs` error row today | Plumbing exists; nothing alerts on a failed sync |
| Reports + email | `seed/.../domain/digest/` (`BaseDigestService`), `seed/.../integrations/email/` | Full |
| LLM | `seed/.../integrations/llm/`, `seed/.../domain/ai/`, AI-output audit tables (migration 239) | Full |
| Embeddings | `seed/.../integrations/llm/embeddings.py`; pgvector already used (migration 101) | Full |
| Per-profile separation | `social_wiring.marcas` (all three people's marcas in **one org**), `integration_accounts.marca_id`; RLS is org-only | **Half**: per-marca filtering only in the service layer |
| Competitor tracking | `cs_perfis_monitorados` (migration 229): Business Discovery, LGPD sweep | Full; reuse for "Inteligência competitiva" |
| Approval workflow | `seed/.../domain/editorial/` (draft → review → published) | Full in seed, no consumer yet |

## 2 · Collecting SIMEC's metrics ourselves

**How the workbook computes things (must match):**
- Ratios: Instagram divides by reach, TikTok by views.
- "Total interações" stays blank unless all 4 counts are present.
- Validation states: `INCOMPLETO`, `DATA INVÁLIDA`, `FORA DA JANELA` (7d = days 7–10; 30d = days 30–35), `DUPLICADO`, `OK`.
- The panel is the simple mean of rates over the posts that have the metric, with a sample count per rate.
- A blank is never 0.

**Instagram (DADOS columns):**
- ✅ Already stored or derivable: date, ID/link, format, topic (caption or `cs_posts.titulo`), the 7d/30d/current windows (from the daily snapshots), views, reach, likes, comments, shares, saves, average watch time (Reels), skip rate (Reels), profile followers, visits and link taps.
- ⚠️ Attributed followers: FEED and STORY only, so blank for Reels (correct under the "blank ≠ 0" rule).
- ❌ Video duration: not on IG Media; probe the file (ffprobe) or take it from `cs_posts`.
- ❌ Retention curve and exact "views above 3 s": not in the Graph API. Mark them unavailable; skip rate is the proxy and must be labelled as such.

**Comment window:** the "50 most recent posts" limit is Metricool's, not Meta's. `GET /{ig-media}/comments` works on any media in the catalog: collect daily, diff on the comment ID, keep our own bank. The `comments` webhook is an option later.

**Scopes and App Review:**
- `instagram_business_manage_comments` must be added to `IG_BUSINESS_LOGIN_SCOPES`, and every account reconnects.
- The three founders can be added as roles on the Meta app, so Standard Access is enough.
- **Clients** need Advanced Access (App Review + Business Verification).

**TikTok:** needs the **Business API** with a **TikTok Business account** per profile, plus TikTok developer-app approval. The Display API has no watch time, completion rate or traffic source. Field names below come from third-party connector docs; verify them against TikTok's official reference.
- Business API: `average_time_watched`, `full_video_watched_rate`, `impression_sources`, plus a comments endpoint.
- Unconfirmed: favorites, attributed followers.

## 3 · Module split

**Seed (bone):**
- **B1** `noctusai_lib/integrations/tiktok/`: Protocol, Fake, Real (Business API), factory; copy the youtube shape.
- **B2** comments Protocol + Real + Fake on `meta/instagram_login_adapter.py` (list comments, list replies, reply, hide).
- **B3** `noctusai_lib/domain/content_performance/`: pure, no IO. Windows, validation states, per-platform derived ratios, mean-of-rates with sample counts, baselines from the profile's own comparable posts. Golden tests built from the workbook formulas. This is the "formulas, not LLM math" rule made real.

**social-wiring (organs):**

| Module | Holds |
|---|---|
| `modules/tiktok/` | Mirror of `modules/instagram`: catalog, daily snapshots, `snapshot_runs` |
| `modules/simec/` | Readouts, baselines, panel API, decision log, results control, weekly/monthly digests, alerts, an AI step that turns computed facts into hypotheses with confidence. Seams: `PlatformMetricsSource` (separate IG and TikTok, no cross-platform method) and an injected LLM callable |
| `modules/audiencia/` | Comment sync, comment bank, LLM classification, topic embeddings, opportunity report, retention sweep |
| AR3 | Local (N=1), with a seed-shaped `TopicTreeStore` Protocol so a later lift into the seed is mechanical |
| Central Editorial | Extends `modules/media_creation` (§4) |

**Data model sketch** (schema `social_wiring`; every table has `org_id` and `marca_id`):
- `tt_videos`, `tt_video_snapshots`, `tt_profile_snapshots`: same shape as migration 208.
- `simec_readouts`: window, `source_snapshot_id` for traceability, validation status, raw and derived values.
- `simec_baselines`: per format, duration bucket, window and metric: n, median, p25, p75.
- `simec_decisoes`: one table for the workbook's DECISÕES sheet and the Central's DECISOES.csv; linked to `cs_posts`.
- `simec_relatorios`: kind, period, facts, hypotheses with confidence, narrative, `prompt_version`, `ai_output_id`.
- `sw_comentarios`: `external_id` UNIQUE, verbatim text, `autor_hash` (HMAC, no username), `purge_at`.
- `sw_comentario_analises`: category, topics, `sensivel` flag, model, prompt version.
- `sw_audiencia_topicos`: label, embedding, count, first/last seen; plus a link table to comments.
- `ar3_arvores` + `ar3_nos`: parent, level, label, path, status, embedding with an HNSW index, and an RPC that rejects semantic repeats across the whole tree.
- `marca_acessos (marca_id, user_id, papel)` + RLS helper `can_access_marca()`.

## 4 · Central Editorial and AR3 reuse Criação de Mídia

| Command / base | Reuse or extend |
|---|---|
| INICIAR PERFIL, AUDITAR POSICIONAMENTO, `02_PERFIL_*.md` | Segundo Cérebro brains + marca bio; import the dossiers via `cs_brain_imports` |
| RADAR DO NICHO, CRIAR PAUTAS | A new Pesquisa source, plus Assuntos Virais and perfis_monitorados. Shares the `NOC-REMEDIATE[roteiro-web-search]` blocker with Roteiro (no web-search provider yet): build one seam for both |
| ROTEIRIZAR, CRIAR LEGENDA, REVISAR | Extend `roteiro_service` input (pauta or AR3 node, platform, target duration); reuse `legenda_service` |
| PREPARAR PUBLICAÇÃO, ORGANIZAR TRELLO | **The Esteira replaces Trello** (migration 241, `esteira_service`, `publish_service`) |
| CALENDARIO.csv | Extend `cs_posts` (`data_prevista`, `canal`, `objetivo`, `territorio`, `chamada_acao`, `tt_video_id`); widen the `formato` CHECK, which only allows 'reel' today |
| PAUTAS.csv | New `cs_pautas` with an origin (pesquisa / ar3 / comentário / simec / radar) |
| IMPORTAR RESULTADOS SIMEC | Same database, no import: `simec_decisoes` ↔ `cs_posts` |
| PROCESSAR COMENTÁRIOS | From `modules/audiencia`; replies go through the existing route, each approved by a human |
| PLANEJAR MÊS, FECHAR MÊS | Calendar view over `cs_posts`; month close is a digest |
| PLANEJAR CAMPANHA | Check the existing `campanhas_*` first; don't add a second campaign table |
| The command interface | Tools of the existing Criação de Mídia chat (`chat_service` + seed `tool_loop`), not new screens |
| AR3 placement (open question 5) | Recommended: a tab under Pesquisa; nodes become pautas; seed it with application 01 |

## 5 · Build order (pilot: Mônica's Instagram)

| Phase | File-disjoint slices |
|---|---|
| P0 owner | Confirm Mônica's account is connected via Instagram Login with the insights scope; answer §6; start TikTok developer-app registration now |
| P1 SIMEC-IG panel | S1 seed B3 + golden tests · S2 `modules/simec` + migration + API contract · S3 FE SIMEC page (contract first) |
| P1b comments | S4 seed B2 + scope (Mônica reconnects) · S5 `modules/audiencia` sync + comment bank |
| P2 automation | S6 weekly/monthly reports · S7 failure and incomplete-data alerts |
| P3 comment intelligence | S8 classification, topics, opportunity report, retention sweep, `marca_acessos` (needs the LGPD decisions first) |
| P4 Central Editorial | S9 `cs_posts` + `cs_pautas` · S10 calendar FE · S11 roteiro/legenda inputs · S12 chat command tools |
| P5 AR3 | S13 tree tables, expansion, dedup RPC, import of application 01 · S14 FE tab |
| P6 TikTok | S15 seed B1 · S16 `modules/tiktok` · S17 SIMEC-TikTok panel (gated on TikTok approval) |
| P7 | Gilson and Isa onboarding; clients as separate orgs |

Migrations are collision class C3: assign numbers one at a time (`noctus.dev.next_migration_number`; latest was 266), or have one engineer own all of a wave's migrations.

## 6 · Risks and owner questions

1. **Who sees whose data inside one org:** per-marca grants (`marca_acessos` + RLS), or one org per operator? Clients go in separate orgs.
2. **LGPD:** Mônica's audience comments are sensitive data (art. 11). Decide:
   - retention (proposal: 12 months raw, aggregates kept);
   - who reads raw text (proposal: the marca's owner only);
   - HMAC-pseudonymised authors;
   - anonymised quotes in reports;
   - the LLM providers' data-processing agreements.
   Then write a ROPA (like `../core-studio/ROPA-biblioteca.md`).
3. **Meta Business Verification** for clients: has it been started?
4. **TikTok:** are the accounts Business accounts? App review is needed; there's no guarantee of history before the connection date.
5. **Metric gaps to accept:** no retention curve; no exact "views above 3 s" (skip rate is the proxy); IG duration needs a probe; no attributed followers for Reels.
6. **Cost:** Meta rate limits; batched LLM classification on a cheap model; a paid web-search provider for RADAR.
7. **Gilson's and Isa's diagnosis** is needed before P7.
8. **Approval workflow:** wire the seed `domain/editorial` organ into the Esteira, or keep the Esteira's stages only? Decide before P4.

**Verdict:** [F] seed pieces B1, B2 and B3; SIMEC, audiência and AR3 as social-wiring modules over the existing Instagram module and Criação de Mídia. [R] the Central Editorial extends Criação de Mídia instead of forking it. [A] AR3 stays local until a second product needs it.
