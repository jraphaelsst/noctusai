---
name: ativo-matching
description: >
  Match imóveis (properties) with permutas (exchange profiles) using a composite
  scoring algorithm combining region, price, specs, interests, and embedding
  similarity. Use when generating match suggestions for a property or exchange.
version: 1.0.0
triggers:
  - "find matches"
  - "match properties"
  - "generate matches"
  - "gerar matches"
  - "encontrar permutas"
dependencies:
  - skill: ativo-embedding
---

# Ativo Matching

## Purpose

Matches real estate properties (imóveis) with exchange profiles (permutas) using a multi-factor scoring algorithm. Supports both rule-based matching (region + price + specs + interests + listing quality) and embedding-enhanced matching (semantic similarity + price + specs + interests). Returns ranked match results with detailed score breakdowns.

## Instructions

### Step 1: Identify Source Ativo

Determine whether the source is an `imovel` or a `permuta`:
- `imovel` → Find matching permutas
- `permuta_imovel` or `permuta_automovel` → Find matching imóveis

The endpoint auto-detects based on `natureza` field.

### Step 2: Ensure Embeddings Exist

For embedding-enhanced matching, the source ativo and candidates must have embeddings. If not:
- Call `POST /api/matching/embed` to embed the source
- Or `POST /api/matching/embed-batch` for bulk embedding

### Step 3: Generate Matches

Call the matching endpoint:
```
POST /api/matching/gerar
Authorization: Bearer {token}
Body: { ativo_id: "uuid" }
```

The backend:
1. Loads the source ativo
2. Fetches candidate ativos of the opposite type (same org)
3. Runs the scoring algorithm on each pair
4. Returns ranked results

### Step 4: Interpret Results

Each match result includes:
```json
{
  "match_id": "uuid",
  "ativo": { ... },
  "score": 82,
  "score_regiao": 25,
  "score_preco": 22,
  "score_specs": 18,
  "score_interesses": 12,
  "embedding_similarity": 0.87
}
```

## Scoring Algorithm

### Rule-Based Mode (100 points)

| Component | Points | Logic |
|-----------|--------|-------|
| Region | 30 | State match (5), city (10), bairro (10), zona (5), preferred region text (5) |
| Price | 25 | Range overlap, direct value comparison, difference gap analysis |
| Specs | 20 | Property type match, quartos/vagas/area for imóveis; brand/model/price for vehicles |
| Interests | 15 | Imovel's `interesses` JSON matching permuta's `natureza` |
| Listing Quality | 10 | Title (2), description (2), photos (2), virtual tour (1), POI (1), condominio (2) |

### Embedding-Enhanced Mode (0-100)

| Component | Weight |
|-----------|--------|
| Embedding cosine similarity | 40% |
| Price compatibility | 25% |
| Specs compatibility | 20% |
| Interest alignment | 15% |

## Edge Cases

- **No candidates found** → Returns empty match list
- **Source ativo has no embedding** → Falls back to rule-based scoring only
- **Permuta for vehicle (permuta_automovel)** → Uses vehicle-specific spec matching (brand, model, engine, year, km)
- **All scores very low (< 20)** → Still returns results but they should be presented as weak matches
- **Large candidate pool (100+ permutas)** → Algorithm processes all; consider pagination on frontend

## Examples

### Example 1: Imovel with Good Matches
**Input:** Apartamento 120m², Granja Viana, R$ 850K, with embeddings
**Expected tool call:** `POST /api/matching/gerar` with ativo_id
**Expected behavior:** Returns ranked permutas sorted by composite score, top matches > 70

### Example 2: Permuta Looking for Match
**Input:** Permuta imóvel seeking casa in Cotia, R$ 600K-900K range
**Expected tool call:** `POST /api/matching/gerar` with ativo_id
**Expected behavior:** Returns matching imóveis in price/region range

### Example 3: No Embeddings Available
**Input:** Ativo without embedding, OPENAI_API_KEY not configured
**Expected behavior:** Falls back to rule-based scoring (no embedding_similarity component)
