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
- **Key resolution**: `_resolve_api_key(auth_token)` → core settings API → env fallback

### Functions

| Function | Purpose |
|----------|---------|
| `generate_embedding(text, auth_token)` | Generate embedding vector via OpenAI API |
| `build_ativo_text(ativo)` | Build rich text representation for any ativo natureza |
| `embed_ativo(ativo, supabase, auth_token)` | Generate + store embedding in DB |
| `embed_ativos_batch(ativo_ids, supabase, auth_token)` | Batch embed multiple ativos |

### Text Building by Natureza

| Natureza | Text Includes |
|----------|---------------|
| `imovel` | Type, location (city/state/bairro), area, quartos, suites, vagas, valor, title, description, POIs, condominio |
| `permuta_imovel` | Desired type, preferred location, price range, min rooms/parking, metragem |
| `permuta_automovel` | Vehicle type, brand, model, engine, year, km, price |

### Auto-Embedding Trigger

In `routers/ativos.py`, embedding is triggered automatically on:
- `POST /api/ativos` (create) — embeds new ativo after insert
- `PATCH /api/ativos/{id}` (update) — re-embeds after update

Graceful degradation: if `OPENAI_API_KEY` is missing, embedding is silently skipped.

---

## Matching Service (`services/matching.py`)

### Composite Scoring Algorithm

Two modes of operation:

#### Rule-Based Scoring (no embeddings)

| Component | Weight | Max Points | Logic |
|-----------|--------|------------|-------|
| Region compatibility | — | 30 pts | State, city, bairro, zona, preferred region match |
| Price compatibility | — | 25 pts | Range matching, value comparison, difference gap |
| Specs compatibility | — | 20 pts | Property type, quartos, vagas, area (imóveis) or brand/model/price (vehicles) |
| Interest alignment | — | 15 pts | Imovel's `interesses` JSON matching permuta's natureza |
| Listing quality | — | 10 pts | Title, description, photos, virtual tour, POI, condominio completeness |
| **Total** | | **100 pts** | |

#### Embedding-Enhanced Scoring

| Component | Weight |
|-----------|--------|
| Embedding cosine similarity | 40% |
| Price compatibility | 25% |
| Specs compatibility | 20% |
| Interest alignment | 15% |
| **Total** | **100** |

### Key Functions

| Function | Purpose |
|----------|---------|
| `calcular_compatibilidade_regiao(imovel, permuta)` | Location matching (30 pts) |
| `calcular_compatibilidade_preco(imovel, permuta)` | Price range validation (25 pts) |
| `calcular_compatibilidade_specs(imovel, permuta)` | Specs matching (20 pts) |
| `calcular_alinhamento_interesses(imovel, permuta)` | Interest type matching (15 pts) |
| `calcular_qualidade_anuncio(imovel)` | Listing completeness (10 pts) |
| `calcular_score_total(imovel, permuta)` | Full rule-based scoring (100 pts) |
| `calcular_score_composto(imovel, permuta)` | Embedding-enhanced scoring (0-100) |
| `gerar_matches_para_imovel(imovel, permutas)` | Find matches for a property |
| `gerar_matches_para_permuta(permuta, imoveis)` | Find matches for a trade |
| `gerar_matches_com_embeddings(imovel, permutas)` | Semantic + structured matching |

### Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /api/matching/gerar` | Generate matches for an ativo (auto-detects imovel vs permuta) |
| `POST /api/matching/embed` | Generate embedding for a single ativo |
| `POST /api/matching/embed-batch` | Batch generate embeddings |

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
