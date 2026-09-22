-- ============================================================================
-- Migration 150 · social_wiring: vincular_imovel — link an EXISTING matrícula
-- transcription to a property, and log the linking
-- ============================================================================
-- WHAT THIS IS FOR
-- ----------------
-- The matrícula picker (`contrato_gerador`'s contract flow) can only offer
-- extractions the negociação's imóvel already knows about (`codigo`, 109).
-- An extraction transcribed WITHOUT a código — an upload-without-codigo
-- (092's original, unlinked shape) or a manual paste (149) that named the
-- wrong código or none at all — could never be selected, and the only way
-- an operator had to fix that was a second, PAID re-upload/re-transcription
-- of the exact same document. `PUT /api/matriculas/extracoes/{id}/imovel`
-- (`estrutura_service.vincular_imovel`) closes that gap.
--
-- 🔴 THIS MIGRATION CHANGES NOTHING ABOUT WHAT IS MUTABLE
-- ---------------------------------------------------------------------------
-- `matricula_extracoes.codigo` is still write-once, enforced by the trigger
-- 111/135/136 built (`matricula_extracoes_protege_concluida`): once `codigo`
-- IS NOT NULL, ANY change to it — even with an application-level
-- `substituir=true` confirmation — is refused, unconditionally. The new
-- endpoint only ever writes `codigo` when it is CURRENTLY NULL; it refuses,
-- at the application layer, before ever attempting a write the trigger would
-- reject. Nothing here alters that trigger — loosening a write-once
-- integrity guard on legal-document provenance is a production schema
-- decision for the tech-lead + owner, not something this feature needs.
--
-- 1. imovel_documento_acessos.acao — gains 'imovel_vinculado'
-- ---------------------------------------------------------------------------
-- Same table 111 built for `text_view` and 115 extended for `detalhes_view`
-- — `log_acesso_extracao`'s shape (`extracao_id` + `usuario_id` + `acao` +
-- `created_at`) is agnostic to read-vs-write, so the link operation reuses
-- it rather than adding a `codigo_vinculado_por`/`_em` provenance pair to
-- `matricula_extracoes`, which has no other provenance columns for `codigo`
-- to begin with. This is the ONLY schema change this migration makes.
--
-- No other table gains a column, and no other constraint changes.
--
-- FORWARD-ONLY, IDEMPOTENT (safe to re-run; the ALTER is existence-guarded).
-- 🔴 MIGRATION FILE ONLY — applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. imovel_documento_acessos — a matrícula-imóvel link is its own logged
--    action, the same way a detalhes/text read already is
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.imovel_documento_acessos
    DROP CONSTRAINT IF EXISTS imovel_documento_acessos_acao_check;
ALTER TABLE social_wiring.imovel_documento_acessos
    ADD CONSTRAINT imovel_documento_acessos_acao_check
    CHECK (acao IN ('view', 'download', 'delete', 'text_view', 'detalhes_view', 'imovel_vinculado'));
