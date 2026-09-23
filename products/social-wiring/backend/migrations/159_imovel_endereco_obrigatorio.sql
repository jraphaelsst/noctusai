-- ============================================================================
-- Migration 159 · social_wiring: the property table is the address of record
-- ============================================================================
-- OWNER RULE (verbatim, 2026-09-23)
-- ----------------------------------
-- "The address doesn't come from the matrícula. The address comes from the
-- property table; it will be mandatory upon property registration that it
-- has the address in it. The extraction of the address can be useful to
-- check and warn when it diverges from the document."
--
-- 149 gave `imovel_dados` a manual override for 4 of the 7 address fields
-- (logradouro/número/cidade/UF) — exactly the 4 `derivacao._imovel` gates
-- the contract on. `complemento`/`bairro`/`cep` were left mirror-only
-- ("nothing gates on them", 149's own comment) because nothing needed them
-- overridable yet. Two things now do:
--
-- 1. MANUAL REGISTRATION REQUIRES A FULL ADDRESS. `POST /{codigo}/registrar`
--    (`ImovelCodigoPicker`'s "Cadastrar '<código>' como imóvel novo") now
--    writes the override in the SAME request — logradouro/número/bairro/
--    cidade/UF/CEP required, complemento optional — so a hand-registered
--    imóvel can never again exist without an address the way EUROVILLE-535
--    did (measured live 2026-09-22 — see `test_carregador_empreendimento_
--    manual.py`'s header for that incident, and the duplicate it caused).
--
-- 2. CONDOMINIUM INTERNAL ADDRESS. Vista mirrors a condo as its GATE address
--    (`imoveis.logradouro/numero/complemento` — e.g. "Itália 343, compl.
--    535") with the unit's real address elsewhere in the paperwork (e.g.
--    "Alameda Alemanha nº 535") — the SAME "public field is not the real
--    address" shape 139/derivacao.py's `resolver_endereco_posse` docstring
--    already documents for the posse clause, just for `logradouro`/`numero`/
--    `complemento` specifically instead of the whole street. The manual
--    override already applies to ANY registered código (`ensure_imovel`
--    only checks `imovel_registry`, never `origem_descoberta`) — 149 built
--    that generically even though its own docstring only imagined the
--    off-market use case. This migration just gives it the 3 remaining
--    fields, so an operator can override the UNIT's full address (including
--    complemento/bairro/CEP) for a Vista-synced condo, not only a manually
--    registered one.
--
-- WHY NOT A NEW TABLE / NEW COLUMN FAMILY
-- ----------------------------------------
-- `endereco_manual_*` already IS "the property table's address, operator-
-- authored, per-field override over the mirror" — precisely the owner's
-- rule. Extending it to all 7 mirror fields is the direct, non-duplicating
-- way to make the property table (mirror ⊕ override) the single address of
-- record `carregador._imovel` and the new divergence check both read.
--
-- FORWARD-ONLY, IDEMPOTENT (safe to re-run; every step is existence-guarded).
-- 🔴 MIGRATION FILE ONLY — applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`. NOT applied by this change.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. imovel_dados — the 3 remaining address fields (complemento/bairro/cep)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.imovel_dados
    ADD COLUMN IF NOT EXISTS endereco_manual_complemento TEXT,
    ADD COLUMN IF NOT EXISTS endereco_manual_bairro      TEXT,
    ADD COLUMN IF NOT EXISTS endereco_manual_cep         TEXT;

COMMENT ON COLUMN social_wiring.imovel_dados.endereco_manual_complemento IS
    'Manual override for the CRM/Vista mirror''s complemento (migration 159) '
    '-- e.g. the UNIT number for a condo whose Vista row mirrors the GATE '
    'address only. Wins over the mirror per-field when set '
    '(carregador._endereco_manual). NULL falls back to the mirror. Part of '
    'the same single-stamp confirmation as the other endereco_manual_* '
    'fields (endereco_manual_confirmado_por/_em, migration 149) -- not its '
    'own quintet, same reasoning as 149''s own columns.';
COMMENT ON COLUMN social_wiring.imovel_dados.endereco_manual_bairro IS
    'Manual override for the CRM/Vista mirror''s bairro (migration 159). '
    'See endereco_manual_complemento''s comment for the shape.';
COMMENT ON COLUMN social_wiring.imovel_dados.endereco_manual_cep IS
    'Manual override for the CRM/Vista mirror''s CEP (migration 159). '
    'See endereco_manual_complemento''s comment for the shape. Required at '
    'manual registration time (app.modules.imovel_hub.schemas.'
    'RegistrarImovelBody) -- not enforced as NOT NULL here, because the '
    'contract gate''s existing per-field falta loop '
    '(contrato_gerador.derivacao._imovel) still only requires logradouro/'
    'numero/cidade/uf; a DB-level NOT NULL would refuse the 149-era rows '
    'that predate this migration and have never set an override at all.';

-- ----------------------------------------------------------------------------
-- 2. imovel_endereco_historico.campo — widen the CHECK to the 3 new fields
-- ----------------------------------------------------------------------------
-- Same table, same append-only log (149) -- every touched field still
-- appends one row under the MIRROR-FACING name ('complemento'/'bairro'/
-- 'cep'), matching the vocabulary the FE and the `Endereco` dataclass
-- already use for the other 4.
ALTER TABLE social_wiring.imovel_endereco_historico
    DROP CONSTRAINT IF EXISTS imovel_endereco_historico_campo_check;
ALTER TABLE social_wiring.imovel_endereco_historico
    ADD CONSTRAINT imovel_endereco_historico_campo_check
    CHECK (campo IN ('logradouro', 'numero', 'complemento', 'bairro', 'cidade', 'uf', 'cep'));
