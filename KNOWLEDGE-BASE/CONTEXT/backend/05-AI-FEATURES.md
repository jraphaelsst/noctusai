# 07 — AI Features Context

> All AI features live in ERP backend: `products/erp-imobiliario/backend/app/`
> LLM: OpenAI GPT-4o-mini (chat) + text-embedding-3-small (embeddings)
> API key resolution: org settings → platform settings → `OPENAI_API_KEY` env

---

## AI Service (`services/ai_service.py`)

Three capabilities exposed via `POST /api/ai/*` endpoints:

### 1. Property Description Generation

- **Function**: `generate_description(imovel_data)`
- **Endpoint**: `POST /api/ai/generate-description`
- **Model**: GPT-4o-mini (temperature 0.7 — creative)
- **Input**: Property data (type, location, area, rooms, price, features)
- **Output**: `{ titulo_sugerido, descricao }` (title max 80 chars + 3-5 paragraph marketing text)

### 2. Lead Scoring

- **Function**: `score_lead(cliente_data)`
- **Endpoint**: `POST /api/ai/lead-score`
- **Model**: GPT-4o-mini (temperature 0.3 — consistent)
- **Input**: Client profile (data completeness, estimated value, funnel stage, probability)
- **Output**: `{ score (0-100), justificativa, recomendacao }`

### 3. Price Suggestion

- **Function**: `suggest_price(imovel_data, comparables)`
- **Endpoint**: `POST /api/ai/suggest-price`
- **Model**: GPT-4o-mini (temperature 0.3 — deterministic)
- **Input**: Property data + comparable properties from database
- **Output**: `{ preco_sugerido, faixa_min, faixa_max, analise }`

### Helper Functions
- `_chat_completion()` — Core OpenAI API wrapper (async httpx)
- `_get_api_key()` — Retrieve API key from env
- `_parse_money()` — Parse Brazilian real format (R$ 1.234.567,89)

---

## Embedding Service (`services/embedding_service.py`)

### Configuration
- **Model**: text-embedding-3-small (1536 dimensions)
- **API**: `https://api.openai.com/v1/embeddings`
- **Key resolution**: `resolve_credential("openai_api_key", org_id)` → org_settings → platform_settings → env

### Two Embeddings per Ativo

Every ativo gets **two** embedding vectors:
- **`embedding`** — Profile embedding: what the ativo IS (property description, location, specs)
- **`embedding_interesses`** — Interest embedding: what the ativo WANTS in exchange (from `interesses` JSONB array)

Matching compares **profile↔interest** across pairs (not profile↔profile):
- B→A: `cosine(imovel.embedding, permuta.embedding_interesses)` — does the permuta want this imóvel?
- A→B: `cosine(permuta.embedding, imovel.embedding_interesses)` — does the imóvel owner want this permuta?

### Functions

| Function | Purpose |
|----------|---------|
| `generate_embedding(text, org_id)` | Generate embedding vector via OpenAI API |
| `build_ativo_text(ativo)` | Build rich text representation of what an ativo IS |
| `build_interesses_text(ativo)` | Build text representation of what an ativo WANTS |
| `embed_ativo(ativo, db)` | Generate + store both embeddings (profile + interesses) in DB |
| `embed_ativos_batch(ativo_ids, db)` | Batch embed multiple ativos |

### Text Building by Natureza

**Profile text** (`build_ativo_text`):

| Natureza | Text Includes |
|----------|---------------|
| `imovel` | Type, location (city/state/bairro/zona), area, quartos, suites, vagas, valor, title, description, POIs, condominio |
| `permuta_imovel` | Desired type, preferred location, price range, min rooms/parking, metragem |
| `permuta_automovel` | Vehicle type, brand, model, engine, year, km, price |

**Interest text** (`build_interesses_text`):

Built from the `interesses` JSONB array. For each interesse entry:
- **tipo=imovel**: "Busca imóvel, tipo: apartamento, cidade: São Paulo, faixa: R$ 300000 - R$ 600000"
- **tipo=automovel**: "Busca automóvel, marca: BMW, faixa: R$ 150000 - R$ 300000"

Falls back to `interesses_descricao` free-text field if `interesses` array is empty.

### Auto-Embedding Trigger

In `routers/ativos.py`, embedding is triggered automatically on:
- `POST /api/ativos` (create) — embeds new ativo after insert
- `PATCH /api/ativos/{id}` (update) — re-embeds after update

Graceful degradation: if `OPENAI_API_KEY` is missing, embedding is silently skipped.

---

## Matching Service (`services/matching.py`)

### Architecture: Unified Path with Bilateral Logic

The matching system uses a **single unified path** — hard filters run first (free), then structured scoring, then optional embedding enhancement. There are no separate "rule-based" and "embedding-based" code paths.

**Bilateral matching principle**: Both sides must want what the other offers.
- A→B: The permuta's profile must satisfy what the imóvel owner wants (checked via `_permuta_atende_interesse`)
- B→A: The imóvel's profile must satisfy what the permuta wants (checked via `_imovel_atende_permuta`)

### Matching Flow

```
For each (imovel, permuta) pair:
  1. Skip same-owner and inactive pairs
  2. Compute structured sub-scores: region, price, specs
  3. Apply hard filters (_passa_filtros_minimos):
     a. Bilateral A→B: permuta profile matches imóvel's interesses?
     b. Bilateral B→A: imóvel profile matches permuta's interesses?
     c. Type-specific: permuta_imovel requires same state; permuta_automovel requires explicit auto interest
     d. 2-of-3 meaningful categories (region ≥5, price ≥8, specs ≥5)
  4. If filters pass → compute interest alignment + listing quality
  5. Compute bilateral embedding similarity (if both ativos have embeddings)
  6. Final score: composite formula if embeddings available, else pure rule-based
```

### Rule-Based Scoring (100 pts max)

| Component | Max Points | Logic |
|-----------|------------|-------|
| Region compatibility | 30 pts | State (5), city (10), bairro (10), zona (5), preferred region (5) |
| Price compatibility | 25 pts | Range matching, value ratio, accepts-complement bonus |
| Specs compatibility | 20 pts | Property type, quartos, vagas, area (imóveis) or brand/model/price (vehicles) |
| Interest alignment | 15 pts | Imovel's `interesses` JSON matching permuta's natureza + sub-criteria |
| Listing quality | 10 pts | Title (2), description (2), photos (1-3), virtual tour (1), POI (1), condominio (1) |
| **Total** | **100 pts** | |

### Embedding Enhancement (when available)

When both ativos have all 4 embeddings (profile + interesses for each), bilateral cosine similarity is computed:
- B→A: `cosine(imovel.embedding, permuta.embedding_interesses)`
- A→B: `cosine(permuta.embedding, imovel.embedding_interesses)`
- Both directions must exceed **`_SIM_THRESHOLD = 0.60`** — if either falls below, similarity = 0 (no enhancement)
- Final similarity = average of both directions

**Composite score formula** (replaces rule-based total when embeddings qualify):

| Component | Weight |
|-----------|--------|
| Bilateral embedding similarity | 40% |
| Price compatibility (normalized) | 25% |
| Specs compatibility (normalized) | 20% |
| Interest alignment (normalized) | 15% |
| **Total** | **100** |

### Hard Filters (`_passa_filtros_minimos`)

Pairs that fail hard filters are **discarded before scoring** — no wasted computation or API tokens.

| Filter | Logic |
|--------|-------|
| Bilateral A→B | Permuta's profile must match ≥1 of imóvel's `interesses` (city, type, value range with 20% tolerance) |
| Bilateral B→A | Imóvel's profile must match permuta's `interesses` or fallback criteria (`faixa_preco`, `regiao_preferida`) |
| Region gate (permuta_imovel) | Must share at least same state (region score ≥ 5) |
| Auto gate (permuta_automovel) | Imóvel must have explicit `tipo: "automovel"` in interesses |
| Category breadth | Must score meaningfully in ≥2 of 3 categories (region, price, specs) |

### Score Breakdown (returned with every match)

Every match includes a `score_breakdown` dict with percentage values (0-100) for frontend display:

```json
{
  "embedding_similarity": 67.5,
  "compatibilidade_regiao": 83.3,
  "compatibilidade_preco": 60.0,
  "compatibilidade_specs": 75.0,
  "qualidade_anuncio": 50.0,
  "interesses": 100.0
}
```

### Upsert Protection

`upsert_matches()` protects matches with non-pendente status. Matches marked as `aceito` or `rejeitado` are **never overwritten** by re-running match generation. Only `pendente` matches are updated.

### Key Functions

| Function | Purpose |
|----------|---------|
| `calcular_compatibilidade_regiao(imovel, permuta)` | Location matching (max 30 pts) |
| `calcular_compatibilidade_preco(imovel, permuta)` | Price range validation (max 25 pts) |
| `calcular_compatibilidade_specs(imovel, permuta)` | Specs matching (max 20 pts) |
| `calcular_alinhamento_interesses(imovel, permuta)` | Interest type matching (max 15 pts) |
| `calcular_qualidade_anuncio(imovel)` | Listing completeness (max 10 pts) |
| `_permuta_atende_interesse(permuta, interesse)` | Bilateral A→B: does permuta's profile match one interesse? |
| `_imovel_atende_permuta(imovel, permuta)` | Bilateral B→A: does imóvel satisfy permuta's criteria? |
| `_passa_filtros_minimos(imovel, permuta, ...)` | Hard gate before scoring |
| `_calcular_bilateral_similarity(imovel, permuta)` | Cosine similarity of profile↔interest in both directions |
| `calcular_score_total(imovel, permuta)` | Unified scoring: filters → rules → embedding enhancement |
| `gerar_matches_para_imovel(imovel, permutas)` | Generate matches for a property |
| `gerar_matches_para_permuta(permuta, imoveis)` | Generate matches for a trade |
| `upsert_matches(matches, db)` | Bulk persist matches, protecting accepted/rejected |

### Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /api/matching/gerar` | Generate matches (single ativo or full platform scan when body is `{}`) |
| `POST /api/matching/embed` | Generate embeddings for a single ativo |
| `POST /api/matching/embed-batch` | Batch embed unembedded ativos |
| `GET /api/matching` | List matches with filters, enriched with ativo summaries |
| `PATCH /api/matching/{id}` | Update match status (aceito/rejeitado/pendente/expirado) |

---

## WhatsApp Integration

### Service (`services/whatsapp_service.py`)

- **API**: WhatsApp Business API (via WAHA at `waha.noctusai.com`)
- **Dry-run mode**: Works without credentials for development
- **Phone normalization**: Strips special chars, adds BR country code (55)

| Function | Purpose |
|----------|---------|
| `send_message(phone, text)` | Send text message |
| `send_property_card(phone, ativo_data)` | Send formatted property card |
| `get_message_history(phone, page, page_size)` | Retrieve paginated history |

### Router (`routers/whatsapp.py`)

| Endpoint | Purpose |
|----------|---------|
| `GET /api/whatsapp/config` | Check configuration status |
| `POST /api/whatsapp/send` | Send text message |
| `POST /api/whatsapp/send-property` | Send property card |
| `GET /api/whatsapp/history/{phone}` | Message history (paginated) |

### Database

Messages stored in `whatsapp_messages` table: `org_id`, `phone`, `direction` (sent/received), `message`, `message_type` (text/property_card/image), `status` (sent/delivered/read/failed).

---

## API Key Resolution Chain

For OpenAI API key used by AI and embedding services:

1. Check org-specific setting via core settings API: `GET /api/settings/resolve/openai_api_key`
2. Fallback to platform-wide setting
3. Final fallback to `OPENAI_API_KEY` environment variable

This allows per-org API keys for billing isolation.
