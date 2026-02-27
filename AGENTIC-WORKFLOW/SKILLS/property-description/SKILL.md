---
name: property-description
description: >
  Generate marketing descriptions and titles for real estate property listings
  using GPT-4o-mini. Use when a user creates or updates a property (ativo) and
  needs professional copy for the listing.
version: 1.0.0
triggers:
  - "generate property description"
  - "create listing text"
  - "write ativo description"
  - "gerar descrição do imóvel"
dependencies:
  - mcp: openai-api
---

# Property Description

## Purpose

Generates professional, marketing-oriented property descriptions and suggested titles in Portuguese (Brazilian) for real estate listings. The skill takes structured property data (type, location, area, rooms, price, features) and produces a compelling 3-5 paragraph description plus a title (max 80 chars).

## Instructions

### Step 1: Collect Property Data

Gather the following from the ativo record:
- `tipo` (apartment, house, land, etc.)
- `cidade`, `estado`, `bairro` (location)
- `area` (square meters)
- `quartos`, `suites`, `vagas` (rooms, suites, parking)
- `valor` (price in BRL)
- `titulo` (existing title, if any)
- `descricao` (existing description, if any)
- `pois` (points of interest nearby)
- `condominio` (condominium features)

### Step 2: Call AI Service

Send property data to:
```
POST /api/ai/generate-description
Authorization: Bearer {token}
Body: { imovel_data: { ...property fields } }
```

The backend calls `ai_service.generate_description()` which uses GPT-4o-mini with temperature 0.7 for creative output.

### Step 3: Return Results

The response contains:
```json
{
  "titulo_sugerido": "Apartamento de Luxo com Vista para o Parque — 3 Suítes",
  "descricao": "Localizado no coração de... (3-5 paragraphs)"
}
```

Present both the suggested title and description to the user for review before applying.

## Edge Cases

- **Missing property data** → AI generates with available fields, notes missing info in description
- **OpenAI API key not configured** → Returns error: "Chave da API OpenAI não configurada"
- **API rate limit** → Returns 429, retry after backoff
- **Very minimal data (only type + location)** → Generates shorter, more generic description
- **Non-residential property (land, commercial)** → Adapts tone and terminology accordingly

## Examples

### Example 1: Full Property Data
**Input:** Apartamento, 120m², 3 quartos, 2 suítes, 2 vagas, R$ 850.000, Granja Viana, Cotia/SP
**Expected tool call:** `POST /api/ai/generate-description` with full imovel_data
**Expected behavior:** Returns creative title (max 80 chars) + 3-5 paragraph marketing description in PT-BR

### Example 2: Minimal Data
**Input:** Terreno, 500m², Cotia/SP, R$ 300.000
**Expected tool call:** `POST /api/ai/generate-description` with sparse data
**Expected behavior:** Returns shorter description focused on location and lot characteristics

### Example 3: No API Key
**Input:** Any property, but OPENAI_API_KEY not set
**Expected behavior:** Returns structured error indicating API key is not configured, suggests configuring in org settings
