# Biblioteca de virais via Apify — build contract v1 (2026-11-04)

Owner decision 2026-11-04: until Meta verifies noc (App Review / business verification), the
Biblioteca de virais reads third-party public Instagram profiles through **Apify** (actor
`apify/instagram-scraper`), not Business Discovery. Transitional: the Business Discovery path
**stays in the code**, selectable by a setting, and becomes the default again after verification.
Scope is the Core Studio side only (Criação de Mídia). `/meta` and every other Meta surface
(DMs, comments, publish, ads, leadgen, snapshots) are **out of scope — do not touch**.

Reference workflow (corestudio.ai, observed 2026-11-02/04): curated profiles → scrape posts
(plays, likes, comments, video url, date) → transcribe → hook → format/niche/profession →
structure blueprint, one per viral with a numeric id → chat `@perfil` lets the agent pick that
profile's best structure; `@post` forces that post's structure; roteiro answers open with
"Análise da Estrutura Escolhida"; headline answers cite `estrutura #N` per headline; the citation
opens the viral modal. Our pipeline already does almost all of it (audit 2026-11-04); this
contract closes the gaps.

## Slices

| Slice | Owner | Paths (collision zone) | Depends |
|---|---|---|---|
| **A** seed Apify adapter | backend-engineer | `seed/lib/backend/noctusai_lib/integrations/apify/**`, `seed/lib/backend/tests/integrations/apify/**`, `seed/lib/backend/tests/fixtures/apify/**` | — |
| **B** SW ingestion source | same engineer as A, after A | `products/social-wiring/backend/app/modules/media_creation/services/biblioteca_ingestao.py`, `…/media_creation/services/biblioteca_fonte*.py` (new), `products/social-wiring/backend/app/config.py`, `products/social-wiring/backend/app/services/api_keys_store.py` (**additive only** — `feat/jl-s8-sw-grant-sink` is live on it), one new migration, backend tests, README + LIA/ROPA docs | A |
| **C** chat structure | backend-engineer | `…/media_creation/prompts/chat_roteiro.py`, `…/prompts/chat_headline.py`, `…/services/chat_contexto.py`, `…/services/chat_service.py` (only if needed), tests | — |
| **D** FE modal + citations | frontend-engineer | `products/social-wiring/frontend/src/components/geracao/**`, `…/pages/geracao/**`, `src/types/geracao.ts` (additive) | C's §3 wire shape (stable below) |

## 1 · Seed: `noctusai_lib.integrations.apify` (slice A)

Seed IO module → **Fake + Real + factory** (`KB § PATTERNS/backend/seed-fake-real-adapter.md`,
`fake_or_refuse` — never a silent fake in production). Model on `integrations/media/`.

```python
# types.py (pydantic/dataclasses, frozen)
class InstagramPublicProfile: username, full_name, biography, followers_count: int|None,
    follows_count: int|None, posts_count: int|None, profile_pic_url: str|None,
    is_private: bool, is_business: bool|None, verified: bool|None, external_id: str|None
class InstagramPublicPost: id: str, shortcode: str, permalink: str,
    media_type: Literal["IMAGE","VIDEO","CAROUSEL_ALBUM"],      # Image/Video/Sidecar mapped
    product_type: str|None,                                     # "clips" = reel
    caption: str|None, timestamp: datetime (UTC),
    likes: int|None,          # Apify -1 (hidden) → None
    comments: int|None, views: int|None,   # videoPlayCount ?? videoViewCount ?? None
    duration_s: float|None, display_url: str|None, video_url: str|None, owner_username: str
class ApifyRunCost: results: int, usd: Decimal|None, run_id: str|None
class InstagramProfileScrape: profile: InstagramPublicProfile, posts: list[InstagramPublicPost], cost: ApifyRunCost

# errors (all subclass ApifyError)
ApifyNotConfigured   # no token
ApifyProfileNotFound # unknown / private / empty — carries reason: "nao_encontrado"|"privado"
ApifyRateLimited     # 429 / concurrency; carries retry_after_s|None
ApifyRunFailed       # actor FAILED/ABORTED/TIMED-OUT, non-2xx, malformed item — message has no token

# port
class InstagramScraper(Protocol):
    def scrape_profile(self, handle: str, *, max_posts: int, newer_than: date|None = None,
                       timeout_s: float = 240) -> InstagramProfileScrape: ...

def get_instagram_scraper(*, token: str|None, real: bool|None = None) -> InstagramScraper  # factory
```

Real adapter: HTTPS POST `https://api.apify.com/v2/acts/apify~instagram-scraper/run-sync-get-dataset-items`
(token in the `Authorization: Bearer` header, **never** in the URL or a log line), input
`{"directUrls": ["https://www.instagram.com/<handle>/"], "resultsType": "details",
"resultsLimit": max_posts, "onlyPostsNewerThan": …, "addParentData": false}` — one call returns the
profile with `latestPosts`; if `latestPosts` is shorter than `max_posts`, a second call with
`resultsType: "posts"` fills the rest (dedupe by id). Handle validated with the same regex as
`POST /biblioteca/perfis` (`^@?[a-zA-Z0-9._]{1,30}$`) before any call. `max_posts` hard-capped
at 200. Cost: results count from the dataset length; `usd` from the run's `usageTotalUsd` when the
response exposes it (else `None` — never invented). Fake: deterministic fixtures in
`tests/fixtures/apify/` (a public profile, a private one, a hidden-likes post, a reel without
plays). Tests: mapping of every field above, -1 likes, private → `ApifyProfileNotFound`, 429,
timeout, token absent from every exception string and log record.

## 2 · Social-wiring: ingestion source (slice B)

- New setting `biblioteca_fonte ∈ {"apify","business_discovery"}`, default **`apify`**, read like
  `biblioteca_ingestao_habilitada` (DB first, then env). Business Discovery code stays intact
  behind `"business_discovery"`.
- `IngestaoPorts` gains `scraper_factory: Callable[[str], InstagramScraper]` (org_id → scraper,
  token from `resolve_api_key("apify_api_token", org_id)`). The sync branches on the source at the
  ONE place it fetches today (`biblioteca_ingestao.py` ~:380–:420): `"apify"` → one
  `scrape_profile(handle, max_posts=cap, newer_than=None if first else today-REFRESH_WINDOW_DAYS)`
  call mapped to the same per-post `base` dict (likes, comments, **views**, permalink, media_type,
  product_type, caption, publicado_em, duracao_s) and header patch (nome, seguidores, media_count,
  foto). The Apify path does **not** require a connected Meta account (no `sem_conta` status).
- `ApifyProfileNotFound` → status `nao_encontrado` (or `privado` if that status exists; else
  `nao_encontrado` with the reason in `erro_mensagem`); `ApifyNotConfigured` → a visible profile
  status `sem_credencial` with "Configure a chave do Apify em Configurações → Chaves de API" (never
  a silent skip); `ApifyRateLimited` → re-queue with backoff; `ApifyRunFailed` → logged by type
  (no token, no raw body) and raised so the job records the failure.
- Video for transcription: keep using the job payload URL (`media_urls`), now from
  `video_url`. **Persist** `video_url` + `video_url_em` on `cs_virais` (new migration, take the
  number from `noctus.dev.next_migration_number`) so a re-transcription within ~24h needs no
  re-scrape; past that the job re-syncs. Apify CDN hosts are Instagram's
  (`*.cdninstagram.com`/`*.fbcdn.net`) — already in `safe_fetch` allow-list; verify, don't widen.
- API key: `ApiKeySpec(name="apify_api_token", …)` in `app/services/api_keys_store.py` —
  **additive only** (another branch is live on that file). It must show up in Configurações →
  Chaves de API automatically; platform/env fallback `APIFY_API_TOKEN` through the existing
  `resolve_api_key` chain.
- Cost: every run appends to `public.cost_ledger` like InfoSimples (provider `apify`, org, profile,
  results, usd). Caps (settings, defaults): `biblioteca_apify_max_posts_primeira_sync=60`,
  `…_max_posts_sync=24`, `biblioteca_apify_resultados_dia_org=600`; reaching the daily cap parks
  the profile as `sem_orcamento` with a visible message, never silently.
- `views` now real → `score_viral` uses the views base (existing ≥80% rule; no change needed).
- Docs same commit: README (Criação de Mídia line), `specs/biblioteca-lia.md` + `ROPA-biblioteca.md`
  (source = Apify scraping of public profiles, Apify as sub-processor (Czech Republic/EU, servers
  in US), owner decision 2026-11-04, transitional; re-assessment trigger "new data source" hit),
  the seed consent text that names Business Discovery
  (`seed/framework/frontend/src/content/consent.ts` ~:370) and `geracao-contract.md` §3.3 pointer.
- Kill switch unchanged: `biblioteca_ingestao_habilitada` still defaults OFF; turning it on is
  the owner's call.

## 3 · Chat: structure chosen and cited (slice C)

Wire shape (stable; D builds to it): assistant `conteudo` stays markdown; citations stay the
existing literal `(estrutura #<codigo>)` that `citacoes.ts` already links, validated against
`codigos_permitidos`. No new response fields.

- **Roteiro** (`prompts/chat_roteiro.py`): when structures are in context the answer MUST open with
  `### Análise da Estrutura Escolhida` → which viral (`estrutura #<codigo>`, its hook in quotes),
  1–2 reasons it fits the request, and the beat progression as one line `Beat → Beat → …`; then
  `### Roteiro — <tema>` with each beat as a bold label `**(Headline)**`, `**(CTA de Salvar)**`…,
  then `Total de palavras: N`. It models rhetoric/beats, never copies topic or sentences.
- **Selection rule** (`services/chat_contexto.py` + prompt): exactly one `@post` mention (and no
  other library mention) ⇒ only that structure is offered and the agent must use it; any other set
  of mentions (`@perfil`, several `@post`, mixed) ⇒ only the mentioned structures are offered (a
  profile brings its top ones by `score_viral`) and the agent reasons which to use, may combine
  them, and explains why (owner 2026-11-04: "let the agent work his thing"); no mention ⇒ the
  automatic pool. The chosen `#codigo` must be in `codigos_permitidos`.
- **Headline** (`prompts/chat_headline.py`): N = the number the user asked for (1–10), default 5
  (today fixed 3–5); each headline ends with `(estrutura #<codigo>)`, and different headlines use
  different structures when the pool has enough.
- Tests: prompt snapshot updated; a single-`@post` context exposes exactly one structure; a
  profile context exposes the top-K; a mention of a foreign-org viral is refused (existing 404).

## 4 · Frontend (slice D)

- `ViralModal.tsx` adds: the **`#<codigo>`** badge in the header, **Gancho** (quoted), and
  **Estrutura** — the blueprint's beat sequence (render `blueprint` as given; if it is a labeled
  list, show the labels as a `Beat → Beat` line with the full text collapsible). Existing métricas
  show **Visualizações** now that views are filled (no layout change when null).
- Roteiro messages: the `(estrutura #N)` inside "Análise da Estrutura Escolhida" becomes the same
  link that opens the viral modal (`citacoes.ts` already does it for headlines — make sure roteiro
  messages go through it too).
- **No animated/rotating gradient border** anywhere in Criação de Mídia (owner, 2026-11-04: the
  reference app's neon spinning line around the chat/picker is explicitly NOT wanted). Static
  borders only.
- MinhaBiblioteca: profile status labels for `sem_credencial` / `sem_orcamento` / `privado` with
  the backend message; any copy that says the data comes from Business Discovery / "conta Meta
  conectada" is updated to source-neutral wording.
- States: loading/empty/error/success per `KB § PATTERNS/common/server-state-family-index.md`.

## 5 · Acceptance

1. With `biblioteca_fonte=apify`, a token, and ingestion on, "Solicitar perfil @eliasmaman"
   produces virals with views, transcriptions, gancho, blueprint and `#codigo`, and no Meta account
   is needed.
2. `@eliasmaman — Todos os vídeos` + "crie um roteiro sobre X" → the answer opens with the
   analysis citing one `estrutura #N` of that profile; clicking it opens the modal of that viral.
3. `@<one post>` → the roteiro uses that post's structure.
4. "crie 10 headlines" → 10 headlines, each with its own `estrutura #N` link.
5. Switching `biblioteca_fonte=business_discovery` restores the old path unchanged (its tests stay green).
6. No token string appears in logs, errors or the DB except encrypted in `credentials`.
