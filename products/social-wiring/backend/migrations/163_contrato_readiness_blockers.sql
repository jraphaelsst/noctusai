-- ============================================================================
-- Migration 163 -- social_wiring: itens integrantes' silent-omission gap
--                  promoted from a silent aviso to a real, storable,
--                  blocking answer
--
-- WHAT THIS IS
-- ------------
-- [Owner directive, 2026-09-23] "all those data are mandatory for the deal
-- contract" -- the contract-readiness gate's `ITENS_INTEGRANTES_NAO_
-- INFORMADOS` orange `aviso` (`contrato_gerador.derivacao._contrato`) let
-- an unanswered question sit forever without blocking generation. It now
-- blocks (`av.falta`) -- but "itens integrantes" is genuinely absent from
-- plenty of real deals (spec §1.3 variant 3's own sample contract has
-- none), and `TestNumeracaoAoLigarEDesligarClausulas.
-- test_a_lone_paragraph_is_unico_and_disappears_with_its_switch` pins that
-- the paragraph legitimately disappears with its switch when that is the
-- confirmed answer -- so blocking on "unanswered" must not also block on
-- "confirmed: none".
--
-- `itens_integrantes` (text) alone cannot tell those two states apart:
-- `negociacao_estruturada_service._texto` collapses blank to NULL on
-- write, same as every other termos text field, so an empty string can
-- never mean "answered: nothing". This boolean is the SAME tri-state
-- shape `ad_corpus` already uses (a typed bool sibling of a text field,
-- not a sentinel string): `False` (default) means unanswered and blocks;
-- `True` means a human confirmed there are none, and the paragraph stays
-- correctly omitted.
--
-- 🔴 The 2026-09-23 owner revision explicitly withdrew the two OTHER
-- columns an earlier draft of this migration added here (a manual
-- `foro_comarca` field, and a `clientes.rg_igual_cpf_confirmado` flag) --
-- the foro/comarca is derived from the matrícula transcription instead
-- (`derivacao.comarca_da_matricula`, no new storage), and RG == CPF is
-- folded into the existing qualificação `rg`/`cpf` checklist rather than
-- a separate confirmation. Neither needed a migration; this file only
-- ever carries the one column that survived that revision.
--
-- FORWARD-ONLY, IDEMPOTENT (safe to re-run; every step is existence-guarded).
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.atendimento_negociacao_termos
    ADD COLUMN IF NOT EXISTS itens_integrantes_ausente_confirmado BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN social_wiring.atendimento_negociacao_termos.itens_integrantes_ausente_confirmado IS
    'A human confirmed this deal genuinely has no itens integrantes -- the '
    'ONLY way `itens_integrantes IS NULL` stops blocking generation '
    '(contrato_gerador.derivacao._contrato). Same tri-state shape as '
    '`ad_corpus`: unset (FALSE) means unanswered, not "no".';
