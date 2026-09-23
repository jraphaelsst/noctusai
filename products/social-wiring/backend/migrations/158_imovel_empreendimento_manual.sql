-- ============================================================================
-- Migration 158 · social_wiring: imovel_dados gains the AUTHORED
-- empreendimento/condomínio name — the contract title's last missing input
-- for a manually registered property
-- ============================================================================
-- WHAT THIS IS FOR
-- ----------------
-- `contrato_gerador.contexto.titulo_curto` already composes
-- "{empreendimento} – {endereço}" (`[titulo-empreendimento-omitido]`) when
-- `imovel.empreendimento` is set — that logic is correct and unchanged by
-- this migration. Measured live 2026-09-22 on RODRIGO MORASCHI ENRIQUEZ /
-- EUROVILLE-535: the generated title read "… DE BEM IMÓVEL – ALAMEDA
-- ALEMANHA, Nº 535 – …", missing "RESIDENCIAL EUROVILLE" that the human
-- reference contract carries, because `empreendimento` EXISTS ONLY on
-- `imoveis` — the Vista-synced mirror. Código EUROVILLE-535 was hand-
-- registered (`POST /{codigo}/registrar`, migration 149, registry-only,
-- never synced), so there is no mirror row, nothing for `carregador._imovel`
-- to read, and — until this migration — NO input anywhere to type it either.
-- Every manually registered property prints a title missing its
-- empreendimento, and the contract gate never asks for it, so nothing
-- surfaces the omission.
--
-- This is the same class of gap 149 (endereço manual) and 152 (última
-- transferência manual) already closed: the Vista mirror supplies a field,
-- the manual path has no equivalent input.
--
-- SHAPE — mirrors `endereco_manual_*` (149), NOT `numero_matricula`'s (075)
-- quintet
-- --------------------------------------------------------------------------
-- `empreendimento_manual` is a per-imóvel override that wins over the Vista
-- mirror's `imoveis.empreendimento` (`carregador._empreendimento`), single-
-- stamped when set/cleared — exactly `endereco_manual_*`'s override-on-top-
-- of-the-mirror shape, one field instead of four. Deliberately NOT the
-- `numero_matricula`/`situacao_onus` quintet (`_origem`/`_documento_id`/
-- `_em` + confirmado pair): that shape exists because those fields have a
-- MACHINE reading to reconcile against (`campos_extraidos_service`'s D1
-- OCR pipeline) — there is no document extraction path for an
-- empreendimento name to conflict with, so a full quintet would carry three
-- columns that could never be written.
--
-- Code changes (`dados_service.CAMPOS_EDITAVEIS`/`.atualizar`/`._saida`,
-- `contrato_gerador.carregador._empreendimento`, `ImovelCartorioCard.tsx`)
-- ship alongside this file in the same change.
--
-- FORWARD-ONLY, IDEMPOTENT (safe to re-run; every step is existence-guarded).
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply via
-- noctus.dev.migrate_product with explicit tech-lead + user consent. See
-- `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.imovel_dados
    ADD COLUMN IF NOT EXISTS empreendimento_manual                TEXT,
    ADD COLUMN IF NOT EXISTS empreendimento_manual_confirmado_por  UUID,
    ADD COLUMN IF NOT EXISTS empreendimento_manual_confirmado_em   TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.imovel_dados.empreendimento_manual IS
    'The development/condomínio name a human typed for this imóvel '
    '(migration 158) — wins over the Vista mirror''s own `imoveis.'
    'empreendimento` in `carregador._empreendimento`. Exists because a '
    'manually registered imóvel (migration 149) has no mirror row, and '
    'therefore no `empreendimento` at all, without this override. Never a '
    'recomputed suggestion — an operator types it, same trust model as '
    '`endereco_manual_*` (149).';
COMMENT ON COLUMN social_wiring.imovel_dados.empreendimento_manual_confirmado_por IS
    'Who set (or cleared) the CURRENT override — one stamp for the whole '
    'field, mirroring `endereco_manual_confirmado_por` (149).';

-- A confirmation is a stamp: an override without WHEN is a claim (mirrors
-- migration 139's `imovel_dados_endereco_registro_confirmado` and 152's
-- `imovel_dados_ultima_transferencia_manual_confirmado`). GuardProbe
-- `imovel_dados.empreendimento_manual.confirmed_pair` in
-- `mcp/noctusai/tools/noctus/dev/verify_db_guards.py` proves this refuses a
-- half-written row.
ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_empreendimento_manual_confirmado;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_empreendimento_manual_confirmado
    CHECK ((empreendimento_manual IS NULL) = (empreendimento_manual_confirmado_em IS NULL));
