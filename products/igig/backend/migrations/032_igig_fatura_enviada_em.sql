-- ============================================================================
-- IgIg — fatura.enviada_em (Módulo 6 closeout)
--
-- "Enviada" was already a valid `fatura.status` value (the CHECK on migration
-- 011 already allows it) but nothing ever set it and there was no timestamp
-- to say WHEN — every fatura action stayed "aberta" until "paga"/"cancelada".
-- This adds the ONE missing column the new "Enviar fatura" action needs
-- (achado 12 (parcial), 2026-09 audit). Expand-only, nullable: an existing
-- deployed image reading `fatura.*` is unaffected.
--
-- SQLite mirror: migrations/sqlite/032_fatura_enviada_em.sql (parity-tested).
-- ============================================================================
SET search_path = igig, public;

ALTER TABLE igig.fatura ADD COLUMN IF NOT EXISTS enviada_em TIMESTAMPTZ;
