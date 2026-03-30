---
name: ativo-matching
description: >
  Match imóveis (properties) with permutas (exchange profiles) using bilateral
  matching with unified scoring: hard filters → rule-based scoring → optional
  embedding enhancement. Use when generating match suggestions for a property or exchange.
version: 2.0.0
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

Matches real estate properties (imóveis) with exchange profiles (permutas) using a **bilateral matching** algorithm. "What goes around, comes around" — both sides must want what the other offers. Uses a single unified path: hard filters first (free) → rule-based scoring → optional embedding enhancement (when embeddings exist).

## Architecture

### Bilateral Matching Principle

Every match is validated in **both directions**:
- **A→B**: The permuta's profile (what they offer) must satisfy at least one of the imóvel owner's `interesses`
- **B→A**: The imóvel's profile must satisfy what the permuta wants (via their `interesses` or search criteria)

A pair that only works in one direction is rejected.

### Unified Flow (No Separate Paths)

There is **one path**, not separate "rule-based" and "embedding" paths:

```
1. Skip same-owner / inactive pairs
2. Compute sub-scores: region, price, specs
3. Hard filters (bilateral A→B + B→A, type gates, 2-of-3 categories)
4. If pass → interest alignment + listing quality
5. Bilateral embedding similarity (if available, threshold ≥ 0.60)
6. Final score: composite if embeddings qualify, else pure rule-based
```

Hard filters run **before** any embedding computation — no wasted OpenAI tokens.

### Two Embeddings per Ativo

Each ativo generates two embedding vectors:
- **`embedding`** — Profile: what the ativo IS
- **`embedding_interesses`** — Interest: what the ativo WANTS in exchange

Matching compares **profile↔interest** (not profile↔profile):
- B→A: `cosine(imovel.profile, permuta.interest)` — does the permuta want this imóvel?
- A→B: `cosine(permuta.profile, imovel.interest)` — does the imóvel owner want this permuta?

Both directions must exceed 0.60 threshold for embedding enhancement to apply.

## Instructions

### Step 1: Identify Source Ativo

Determine whether the source is an `imovel` or a `permuta`:
- `imovel` → Find matching permutas
- `permuta_imovel` or `permuta_automovel` → Find matching imóveis

The endpoint auto-detects based on `natureza` field.

### Step 2: Ensure Embeddings Exist (Optional)

For embedding-enhanced matching, both ativos need profile + interest embeddings:
- Call `POST /api/matching/embed` to embed a single ativo
- Or `POST /api/matching/embed-batch` for bulk embedding

Matching works without embeddings — it falls back to pure rule-based scoring.

### Step 3: Generate Matches

```
POST /api/matching/gerar
Authorization: Bearer {token}
Body: { "ativo_origem_id": "uuid" }    # single imóvel
Body: { "ativo_destino_id": "uuid" }   # single permuta
Body: {}                                # full platform scan
```

The backend:
1. Loads the source ativo (or all active imóveis for full scan)
2. Fetches counterparts (permutas for imóveis, imóveis for permutas)
3. Applies hard filters → scoring → embedding enhancement
4. Bulk upserts results to `matches` table (protecting accepted/rejected matches)
5. Returns ranked results

### Step 4: Interpret Results

Each match result includes:
```json
{
  "ativo_origem_id": "uuid",
  "ativo_destino_id": "uuid",
  "score": 82.0,
  "justificativa": "Boa compatibilidade de região. Preço alinhado. Características compatíveis.",
  "detalhes": {
    "compatibilidade_regiao": 25,
    "compatibilidade_preco": 20,
    "compatibilidade_specs": 15,
    "alinhamento_interesses": 12,
    "qualidade_anuncio": 8,
    "gap_valor": 50000,
    "embedding_similarity": 0.6823
  },
  "score_breakdown": {
    "embedding_similarity": 68.2,
    "compatibilidade_regiao": 83.3,
    "compatibilidade_preco": 80.0,
    "compatibilidade_specs": 75.0,
    "qualidade_anuncio": 80.0,
    "interesses": 80.0
  }
}
```

## Scoring Algorithm

### Hard Filters (Applied First — Free)

| Filter | Logic |
|--------|-------|
| Bilateral A→B | Permuta's profile must match ≥1 of imóvel's `interesses` (city, type, value ±20% tolerance) |
| Bilateral B→A | Imóvel's profile must match permuta's `interesses` or fallback criteria |
| Region gate | `permuta_imovel`: must share same state (region ≥ 5) |
| Auto gate | `permuta_automovel`: imóvel must have explicit automovel interest |
| Category breadth | Must score meaningfully in ≥2 of 3 categories (region, price, specs) |

### Rule-Based Scoring (100 points max)

| Component | Points | Logic |
|-----------|--------|-------|
| Region | 30 | State (5), city (10), bairro (10), zona (5), preferred region (5) |
| Price | 25 | Range overlap, value ratio, accepts-complement bonus |
| Specs | 20 | Type match, quartos/vagas/area (imóveis); brand/model/price (vehicles) |
| Interests | 15 | Imóvel's `interesses` matching permuta's natureza + sub-criteria |
| Listing Quality | 10 | Title (2), description (2), photos (1-3), tour (1), POI (1), condominio (1) |

### Embedding Enhancement (When Available)

Composite formula replaces rule-based total when bilateral similarity ≥ 0.60:

| Component | Weight |
|-----------|--------|
| Bilateral embedding similarity | 40% |
| Price compatibility (normalized) | 25% |
| Specs compatibility (normalized) | 20% |
| Interest alignment (normalized) | 15% |

### Upsert Protection

Matches with status `aceito` or `rejeitado` are **never overwritten** by re-running match generation. Only `pendente` matches are updated with new scores.

## Edge Cases

- **No candidates found** → Returns empty match list with `total: 0`
- **No embeddings** → Pure rule-based scoring (no embedding enhancement)
- **One direction below 0.60** → Embedding enhancement skipped, rule-based score used
- **Permuta has no `interesses`** → B→A falls back to `faixa_preco_min/max` and `regiao_preferida`
- **Full scan (`{}` body)** → Matches all active imóveis against all active permutas
- **permuta_automovel** → Vehicle-specific spec matching (brand, model, price range)
- **Cross-state permutas** → Rejected by region hard filter (score < 5)

## Examples

### Example 1: Single Imóvel Match
**Input:** Apartamento 120m², Moema SP, R$ 850K, with embeddings
**Call:** `POST /api/matching/gerar` with `{ "ativo_origem_id": "uuid" }`
**Behavior:** Returns permutas that (a) want this type of property in this location/price AND (b) offer something the owner wants

### Example 2: Full Platform Scan
**Input:** Admin wants to refresh all matches
**Call:** `POST /api/matching/gerar` with `{}`
**Behavior:** Scans all active imóveis against all active permutas, upserts results

### Example 3: No Embeddings
**Input:** Ativo without embedding, OpenAI key not configured
**Behavior:** Falls back to pure rule-based scoring (no embedding_similarity component)
