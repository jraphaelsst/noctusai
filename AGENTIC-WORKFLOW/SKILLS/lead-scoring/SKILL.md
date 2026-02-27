---
name: lead-scoring
description: >
  Score leads 0-100 based on their profile data using GPT-4o-mini, providing
  a numeric score, justification, and follow-up recommendation. Use when
  evaluating lead quality or prioritizing sales pipeline.
version: 1.0.0
triggers:
  - "score this lead"
  - "evaluate lead quality"
  - "lead scoring"
  - "pontuar lead"
  - "avaliar cliente"
dependencies:
  - mcp: openai-api
---

# Lead Scoring

## Purpose

Evaluates lead quality on a 0-100 scale by analyzing client profile data including data completeness, estimated deal value, funnel stage, and conversion probability. Returns a score, human-readable justification, and actionable recommendation — all in Portuguese.

## Instructions

### Step 1: Collect Client Data

Gather the following from the cliente record:
- `nome`, `email`, `telefone` (contact completeness)
- `valor_estimado` (estimated deal value)
- `etapa_funil` (current funnel stage)
- `probabilidade` (conversion probability %)
- `responsavel_id` (assigned agent)
- `origem` (lead source)
- Any additional profile fields available

### Step 2: Call AI Service

Send client data to:
```
POST /api/ai/lead-score
Authorization: Bearer {token}
Body: { cliente_data: { ...client fields } }
```

The backend calls `ai_service.score_lead()` which uses GPT-4o-mini with temperature 0.3 for consistent scoring.

### Step 3: Interpret Results

The response contains:
```json
{
  "score": 78,
  "justificativa": "Lead com perfil completo, valor estimado alto e em fase avançada do funil...",
  "recomendacao": "Priorizar contato imediato. Agendar visita ao imóvel de interesse..."
}
```

Score ranges:
- **80-100**: Hot lead — prioritize immediately
- **60-79**: Warm lead — nurture actively
- **40-59**: Cool lead — qualify further
- **0-39**: Cold lead — low priority, automated nurturing

## Edge Cases

- **Incomplete profile (missing email, phone)** → Score penalized for data gaps, recommendation suggests completing profile
- **No estimated value** → Score based on other signals, flagged as needing qualification
- **OpenAI API key not configured** → Returns error suggesting configuration
- **API rate limit** → Returns 429, retry after backoff
- **Very new lead (no history)** → Conservative scoring with recommendation to gather more data

## Examples

### Example 1: Hot Lead
**Input:** Complete profile, R$ 1.2M estimated value, "Proposta" funnel stage, 80% probability
**Expected tool call:** `POST /api/ai/lead-score` with full cliente_data
**Expected behavior:** Score 80+, justification highlighting deal value and advanced stage, recommendation to close

### Example 2: Cold Lead
**Input:** Name only, no phone/email, no estimated value, "Primeiro Contato" stage
**Expected tool call:** `POST /api/ai/lead-score` with sparse data
**Expected behavior:** Score below 40, justification noting incomplete data, recommendation to qualify and complete profile

### Example 3: Edge Case — Mid-Funnel
**Input:** Complete contact info, R$ 500K value, "Visita" stage, 50% probability
**Expected behavior:** Score 55-70, balanced justification, recommendation for follow-up visit
