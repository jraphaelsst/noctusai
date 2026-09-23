-- ============================================================================
-- Migration 155 · social_wiring: certidões — a bounded vision read for
-- scanned manual uploads, and a surfaced/retried structured-extraction leg.
--
-- WHAT THIS SLICE CLOSES
-- -----------------------------------------------------------------------
-- `POST /api/certidoes/resultados/{id}/upload` ran a manually uploaded PDF
-- through `_extract_pdf_text` with `CERTIDAO_MAX_VISION_PAGES = 0` — the same
-- constant the AUTOMATED scheduler flow uses, which is correct THERE (a timer
-- nobody is watching must never start billing vision calls per §
-- `service.py::CERTIDAO_MAX_VISION_PAGES`'s own docstring) and wrong HERE: a
-- human just clicked "upload" for a certidão the automation could not obtain,
-- and a scanned PDF got a text layer of nothing — no analysis, no
-- numero/emitida_em/validade_ate/resultado, and no record of WHY, only a
-- `sucesso` row that looks identical to one nothing was ever asked to read.
--
-- `app/modules/certidoes/service.py` now bounds a MANUAL upload's vision
-- calls to `CERTIDAO_MANUAL_MAX_VISION_PAGES` (3) instead of 0 — a one-time,
-- human-triggered read, not a recurring bill — and runs that read (plus the
-- AI analysis/structured-determination legs that depend on it) as a
-- background job (`service.process_manual_extraction`) the way
-- `card_hub`/`imovel_hub` already run their own document extractions, so a
-- slow vision call never makes the upload response hang.
--
-- WHY TWO NEW COLUMNS, NOT A REUSE OF `erro_mensagem`
-- -----------------------------------------------------------------------
-- `erro_mensagem` already means "the CERTIFICATE ITSELF could not be
-- obtained" (an InfoSimples 4xx, a stale `processando` timeout). For a manual
-- upload the file IS obtained the moment storage succeeds — `status` goes
-- straight to `sucesso` — and a failure in the STRUCTURED read that follows
-- must not read as "this certidão failed": the same posture `_analyze_with_
-- ai`'s own docstring already states for the free-text analysis column
-- ("the certificate itself is unaffected, only the summary is missing").
-- `estrutura_erro` is that column's sibling for the structured/vision leg — a
-- human-readable PT-BR sentence a UI can render, NULL once resolved.
--
-- `estrutura_tentativas` is the bounded-retry counter D3 asks for (KB roadmap
-- `sw-extraction-contract-gate-2026-09.md`), the SAME shape migration 072's
-- `cliente_documentos.extracao_tentativas` already established for
-- `card_hub.identidade_extracao_service.MAX_TENTATIVAS`: how many times the
-- structured/vision extraction leg has been STARTED for this resultado,
-- including the first. `service.MAX_ESTRUTURA_TENTATIVAS` bounds it; once
-- reached, `recover_stale_processando` stops retrying a resultado stranded
-- mid-extraction and closes it out instead of retrying forever.
--
-- FORWARD-ONLY, IDEMPOTENT (every step existence-guarded; safe to re-run).
-- 🔴 MIGRATION FILE ONLY — not applied to any database by this change. Apply
-- via `noctus.dev.migrate_product` only after the tech-lead has stated the row
-- counts this will touch and the user has given an explicit go-ahead. See
-- `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.certidao_resultados
    ADD COLUMN IF NOT EXISTS estrutura_erro TEXT;

COMMENT ON COLUMN social_wiring.certidao_resultados.estrutura_erro IS
    'Human-readable (PT-BR) reason the structured/vision extraction leg '
    '(numero/emitida_em/validade_ate/resultado) failed for THIS resultado — '
    'independent of erro_mensagem, which covers the certificate FETCH itself. '
    'NULL when never attempted, still pending retry, or resolved. Set by '
    'app/modules/certidoes/service.py::process_manual_extraction.';

ALTER TABLE social_wiring.certidao_resultados
    ADD COLUMN IF NOT EXISTS estrutura_tentativas INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN social_wiring.certidao_resultados.estrutura_tentativas IS
    'How many times the structured/vision extraction leg has been STARTED '
    'for this resultado, including the first. Bounded by '
    'service.MAX_ESTRUTURA_TENTATIVAS; once reached, recover_stale_processando '
    'stops retrying and leaves estrutura_erro as the terminal reason.';
