---
name: ativo-embedding
description: >
  Generate dual vector embeddings (profile + interesses) for ativos using
  OpenAI text-embedding-3-small to enable bilateral semantic matching.
  Use when preparing ativos for AI-powered matching or after creating/updating an ativo.
version: 2.0.0
triggers:
  - "embed ativo"
  - "generate embeddings"
  - "prepare for matching"
  - "gerar embeddings"
  - "embedar ativos"
dependencies:
  - mcp: openai-api
---

# Ativo Embedding

## Purpose

Generates **two** 1536-dimensional vector embeddings per ativo using OpenAI's text-embedding-3-small model:
- **`embedding`** — Profile: what the ativo IS (property description, specs, location)
- **`embedding_interesses`** — Interest: what the ativo WANTS in exchange (from `interesses` JSONB array)

The matching algorithm compares **profile↔interest** across pairs (not profile↔profile), enabling bilateral semantic similarity: "does the permuta want this imóvel?" AND "does the imóvel owner want what the permuta offers?"

## Instructions

### Step 1: Build Text Representations

The embedding service builds two texts per ativo:

**Profile text** (`build_ativo_text`) — what the ativo IS:

- **`imovel`:**
  > Tipo: Apartamento. Localização: Moema, São Paulo, SP, Zona Sul. Área: 65m². Quartos: 2. Suítes: 1. Vagas: 1. Valor: R$ 450000. Apto Moema. Pontos de interesse: Metrô.

- **`permuta_imovel`:**
  > Tipo desejado: apartamento. Localização preferida: Moema, São Paulo, SP, Zona Sul. Faixa de preço: R$ 380000 - R$ 520000. Quartos mínimos: 2. Vagas mínimas: 1.

- **`permuta_automovel`:**
  > Tipo veículo: suv. Marca: BMW. Modelo: X3. Valor: R$ 250000.

**Interest text** (`build_interesses_text`) — what the ativo WANTS:

Built from the `interesses` JSONB array on the ativo. For each entry:
- **tipo=imovel:** "Busca imóvel, tipo: apartamento, cidade: São Paulo, faixa: R$ 300000 - R$ 600000"
- **tipo=automovel:** "Busca automóvel, marca: BMW, faixa: R$ 150000 - R$ 300000"

Falls back to `interesses_descricao` free-text if `interesses` array is empty.

### Step 2: Generate Embedding (Single)

```
POST /api/matching/embed
Authorization: Bearer {token}
Body: { "ativo_id": "uuid" }
```

The backend:
1. Validates OpenAI API key is configured (422 if not)
2. Loads the ativo from database
3. Calls `build_ativo_text()` → generates profile embedding → stores in `ativos.embedding`
4. Calls `build_interesses_text()` → generates interest embedding → stores in `ativos.embedding_interesses`
5. Returns success with ativo_id

### Step 3: Generate Embeddings (Batch)

For bulk operations:
```
POST /api/matching/embed-batch
Authorization: Bearer {token}
```

Fetches all ativos where `embedding IS NULL` and `status = 'ativo'`, processes each sequentially, skipping failures.

### Step 4: Auto-Embedding

Embeddings are automatically triggered when:
- A new ativo is created (`POST /api/ativos`)
- An existing ativo is updated (`PATCH /api/ativos/{id}`)

No manual action needed for day-to-day operations.

## API Key Resolution

The embedding service resolves the OpenAI API key via:
1. **Org settings**: `resolve_credential("openai_api_key", org_id)` (allows per-org billing)
2. **Platform settings**: Global fallback
3. **Environment variable**: `OPENAI_API_KEY`

## Database Columns

| Column | Type | Purpose |
|--------|------|---------|
| `ativos.embedding` | `vector(1536)` | Profile embedding — what the ativo IS |
| `ativos.embedding_interesses` | `vector(1536)` | Interest embedding — what the ativo WANTS |

Both columns have IVFFlat indexes for similarity search. Migration: `012_bilateral_embeddings.sql`.

## Edge Cases

- **No API key configured** → Router returns 422 with message pointing to Configurações > Chaves de API
- **Empty ativo data** → `build_ativo_text()` returns empty string → embedding skipped, returns `success: false`
- **No interesses** → Profile embedding generated, interest embedding skipped (only profile stored)
- **API rate limit (429)** → Batch processing continues with remaining ativos, failed ones logged
- **Ativo already has embeddings** → Overwritten with new embeddings (useful after data updates)
- **Very long text** → OpenAI API handles truncation automatically (8191 token limit)

## Examples

### Example 1: Single Ativo Embedding
**Input:** Ativo UUID of a newly created apartamento with interesses
**Call:** `POST /api/matching/embed` with `{ "ativo_id": "uuid" }`
**Behavior:** Two embeddings generated (profile + interesses) and stored in DB

### Example 2: Batch Embedding
**Input:** Platform has 50 ativos without embeddings
**Call:** `POST /api/matching/embed-batch`
**Behavior:** All 50 ativos embedded (both profile + interesses where available)

### Example 3: Auto-Trigger on Create
**Input:** User creates new ativo via `POST /api/ativos`
**Behavior:** Ativo created in DB, both embeddings automatically generated
