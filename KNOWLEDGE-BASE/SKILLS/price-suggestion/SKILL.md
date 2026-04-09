---
name: price-suggestion
description: >
  Suggest property pricing based on comparable properties in the database
  using GPT-4o-mini market analysis. Use when listing a property and the
  user needs a data-driven price recommendation.
version: 1.0.0
triggers:
  - "suggest price"
  - "price recommendation"
  - "how much should I list this for"
  - "sugerir preço"
  - "avaliação de preço"
dependencies:
  - mcp: openai-api
  - skill: property-description
---

# Price Suggestion

## Purpose

Provides data-driven pricing recommendations for real estate listings by analyzing the target property against comparable properties (comps) from the database. Returns a suggested price, price range (min/max), and written market analysis in Portuguese.

## Instructions

### Step 1: Collect Property Data

Gather from the target ativo:
- `tipo` (property type)
- `cidade`, `estado`, `bairro` (location)
- `area` (square meters)
- `quartos`, `suites`, `vagas` (rooms, suites, parking)
- Current `valor` if any (for comparison)
- `condominio` features

### Step 2: Fetch Comparable Properties

The backend automatically queries the ativos database for comparable properties matching:
- Same `tipo` (property type)
- Same or nearby `cidade`/`bairro`
- Similar `area` range (±30%)
- Similar `quartos` count (±1)

### Step 3: Call AI Service

Send property data + comparables to:
```
POST /api/ai/suggest-price
Authorization: Bearer {token}
Body: { imovel_data: { ... }, comparables: [ ... ] }
```

The backend calls `ai_service.suggest_price()` which uses GPT-4o-mini with temperature 0.3 for deterministic pricing.

### Step 4: Present Results

The response contains:
```json
{
  "preco_sugerido": 850000,
  "faixa_min": 780000,
  "faixa_max": 920000,
  "analise": "Com base em 5 imóveis comparáveis na região de Granja Viana..."
}
```

Present the suggested price, range, and analysis. All values in BRL.

## Edge Cases

- **No comparable properties found** → AI estimates based on general market knowledge, flags low confidence
- **Very few comps (< 3)** → Wider price range, analysis notes limited data
- **Unusual property type** → Falls back to broader comparison criteria
- **OpenAI API key not configured** → Returns error suggesting configuration
- **Price significantly above/below comps** → Analysis explicitly notes the deviation

## Examples

### Example 1: Good Comp Data
**Input:** Apartamento 120m², 3 quartos, Granja Viana/Cotia-SP, 8 comparable properties found
**Expected tool call:** `POST /api/ai/suggest-price` with property + comps array
**Expected behavior:** Returns precise price ± 10%, detailed analysis referencing specific comps

### Example 2: No Comps Available
**Input:** Terreno comercial 2000m² in a rare location, 0 comps found
**Expected tool call:** `POST /api/ai/suggest-price` with property + empty comps
**Expected behavior:** Returns wider range (± 25%), analysis warns about limited market data

### Example 3: Luxury Property
**Input:** Casa 500m², 5 suítes, piscina, Alphaville, R$ 3M+ range
**Expected behavior:** Returns price with context about luxury market dynamics
