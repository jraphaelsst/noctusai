---
name: ativo-embedding
description: >
  Generate vector embeddings for ativos (properties/exchange profiles) using
  OpenAI text-embedding-3-small to enable semantic similarity matching.
  Use when preparing ativos for AI-powered matching or after creating/updating an ativo.
version: 1.0.0
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

Generates 1536-dimensional vector embeddings for ativos (properties and exchange profiles) using OpenAI's text-embedding-3-small model. These embeddings enable semantic similarity search in the matching algorithm, capturing nuanced relationships between properties that rule-based matching might miss.

## Instructions

### Step 1: Build Text Representation

The embedding service builds a rich text representation based on the ativo's `natureza`:

**For `imovel`:**
> Tipo: Apartamento. Localização: Granja Viana, Cotia, SP. Área: 120m². Quartos: 3, Suítes: 2, Vagas: 2. Valor: R$ 850.000. [Title]. [Description]. Próximo a: [POIs]. Condomínio: [features].

**For `permuta_imovel`:**
> Busca: Casa. Região preferida: Cotia, SP. Faixa de preço: R$ 600.000 a R$ 900.000. Mínimo quartos: 3, vagas: 2. Metragem desejada: 150m².

**For `permuta_automovel`:**
> Veículo tipo: SUV. Marca: Toyota. Modelo: Hilux SW4. Motor: 2.8. Ano: 2022. Km: 45.000. Preço: R$ 280.000.

### Step 2: Generate Embedding (Single)

```
POST /api/matching/embed
Authorization: Bearer {token}
Body: { ativo_id: "uuid" }
```

The backend:
1. Loads the ativo from database
2. Calls `build_ativo_text()` to create text representation
3. Sends text to OpenAI embeddings API
4. Stores the 1536-dim vector in `ativos.embedding` column

### Step 3: Generate Embeddings (Batch)

For bulk operations:
```
POST /api/matching/embed-batch
Authorization: Bearer {token}
Body: { ativo_ids: ["uuid1", "uuid2", ...] }
```

Processes each ativo sequentially, skipping failures.

### Step 4: Auto-Embedding

Embeddings are automatically triggered when:
- A new ativo is created (`POST /api/ativos`)
- An existing ativo is updated (`PATCH /api/ativos/{id}`)

No manual action needed for day-to-day operations.

## API Key Resolution

The embedding service resolves the OpenAI API key via a chain:
1. **Org settings**: `GET /api/settings/resolve/openai_api_key` (allows per-org billing)
2. **Platform settings**: Global fallback
3. **Environment variable**: `OPENAI_API_KEY`

## Edge Cases

- **No API key configured** → Embedding silently skipped, ativo saved without embedding
- **Empty ativo data** → Minimal text generated, embedding will be low quality but functional
- **API rate limit (429)** → Batch processing continues with remaining ativos, failed ones logged
- **Ativo already has embedding** → Overwritten with new embedding (useful after data updates)
- **Very long text** → OpenAI API handles truncation automatically (8191 token limit)

## Examples

### Example 1: Single Ativo Embedding
**Input:** Ativo UUID of a newly created apartamento
**Expected tool call:** `POST /api/matching/embed` with ativo_id
**Expected behavior:** Embedding generated and stored in DB, returns success

### Example 2: Batch Embedding
**Input:** List of 50 ativo UUIDs that need initial embedding
**Expected tool call:** `POST /api/matching/embed-batch` with ativo_ids array
**Expected behavior:** All 50 ativos embedded, any failures logged but don't block others

### Example 3: Auto-Trigger on Create
**Input:** User creates new ativo via `POST /api/ativos`
**Expected behavior:** Ativo created in DB, embedding automatically generated in background
