# 07 — AI Features Context

> ERP: `products/erp-imobiliario/backend/app/` · LLM: OpenAI GPT-4o-mini + text-embedding-3-small
> Therapy: `products/therapy-platform/backend/app/` · LLM: OpenAI GPT + Whisper

## ERP AI Service (`services/ai_service.py`)

Three capabilities via `POST /api/ai/*`:

| Endpoint | Model Temp | Input → Output |
|----------|-----------|----------------|
| `/generate-description` | 0.7 | Property data → `{ titulo_sugerido, descricao }` |
| `/lead-score` | 0.3 | Client profile → `{ score (0-100), justificativa, recomendacao }` |
| `/suggest-price` | 0.3 | Property + comparables → `{ preco_sugerido, faixa_min, faixa_max, analise }` |

API key resolution: `resolve_credential("openai_api_key", org_id)` → org_settings → platform_settings → env.

## Embedding Service (`services/embedding_service.py`)

Model: text-embedding-3-small (1536d). Every ativo gets **two vectors**:
- `embedding` — what the ativo IS (profile: description, location, specs)
- `embedding_interesses` — what the ativo WANTS (from `interesses` JSONB array)

Auto-triggered on POST/PATCH `/api/ativos`. Gracefully skips when `OPENAI_API_KEY` is missing.

## Matching Service (`services/matching.py`)

**Bilateral matching**: both sides must want what the other offers.
- B→A: `cosine(imovel.embedding, permuta.embedding_interesses)` — does the permuta want this?
- A→B: `cosine(permuta.embedding, imovel.embedding_interesses)` — does the owner want this?

### Flow

```
For each (imovel, permuta) pair:
  1. Skip same-owner and inactive
  2. Compute structured sub-scores: region (30), price (25), specs (20)
  3. Hard filters (_passa_filtros_minimos):
     - Bilateral A→B and B→A checks
     - Type-specific gates (same state for permuta_imovel; explicit auto interest for permuta_automovel)
     - Must score meaningfully in ≥2 of 3 categories
  4. Interest alignment (15) + listing quality (10)
  5. Bilateral embedding similarity (threshold: 0.60 per direction)
  6. Final score: embedding-enhanced composite if available, else pure rule-based (100 pts max)
```

### Composite Formula (with embeddings)

| Component | Weight |
|-----------|--------|
| Bilateral embedding similarity | 40% |
| Price compatibility | 25% |
| Specs compatibility | 20% |
| Interest alignment | 15% |

**Upsert protection**: matches marked `aceito`/`rejeitado` are never overwritten by re-generation.

### Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /api/matching/gerar` | Generate matches (single or full scan) |
| `POST /api/matching/embed` | Embed single ativo |
| `POST /api/matching/embed-batch` | Batch embed unembedded ativos |
| `GET /api/matching` | List matches with filters + ativo summaries |
| `PATCH /api/matching/{id}` | Update match status |

## Therapy AI Pipeline

Orchestrated by `ai_pipeline` service:
1. **Transcription** (Whisper) → text from session audio
2. **Summary** (GPT) → dual-track: therapist-facing clinical + patient-facing accessible
3. **Longitudinal** (GPT) → cross-session analysis (min 4 sessions, second person "Você...")
4. **Crisis detection** → keyword analysis on content, severity assessment

Audio kept 24h after transcription for download, then auto-deleted. Summary versions: infinite retention. Prompt hierarchy: per-therapist > per-clinic > global default.
