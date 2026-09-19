-- ============================================================================
-- Migration 139 · social_wiring: imovel_dados gains the CONFIRMED registry
-- address — the posse clauses must never print the CRM's público endereço
-- ============================================================================
-- WHAT THIS IS FOR
-- ----------------
-- At least one tenant (ONE Consultoria Imobiliária) deliberately publishes
-- the PORTARIA (gatehouse) address in `imoveis.endereco` / `Numero` — the
-- CRM field synced from Vista's `Endereco`/`Numero`/`Complemento` — and keeps
-- the real property address only on the matrícula. The reason is
-- competitive: the pública listing is visible to agents outside the firm,
-- and the office does not want them harvesting the actual address. So
-- `imoveis.logradouro` / `.numero` are POLICY-DRIVEN DECOYS at this tenant,
-- not bad data — see `KB § INTEGRATIONS/vista.md` and
-- `contrato_gerador/dados.py`'s `Imovel.endereco` docstring.
--
-- `contrato_gerador/modelo_texto.py`'s posse clauses ("...a posse do imóvel
-- situado à {{ imovel.endereco_curto }}...") used to print `imovel.endereco`
-- straight from that CRM mirror. Under this business rule that would put the
-- GATEHOUSE's street into a signed instrument as the location of the
-- property whose possession is being transferred. Nobody had noticed because
-- the pipeline had never produced a contract.
--
-- Neither existing source is a safe drop-in replacement:
--   - the matrícula's own `descricao_imovel_texto` (migration 136) is
--     authoritative but a full prose clause, not a short "situado à X"
--     address;
--   - Vista does not sync a distinct "endereço interno"/registry-address
--     field for this tenant (confirmed against the 32-field, 107-candidate
--     live probe in `noctusai_lib.integrations.vista.calibration.
--     CANDIDATE_IMOVEL_DETAIL_FIELDS`, measured 2026-09-04) — there is
--     nothing to sync.
--
-- WHAT CHANGES
-- ------------
-- `imovel_dados` gains `endereco_registro_texto` (+ confirmation stamp),
-- mirroring `titulo_aquisitivo_texto` (migration 115) exactly: the OPERATOR's
-- confirmed short address after reading the matrícula, never a recomputed
-- suggestion (parsing a reliable compact address out of free legal prose is
-- exactly the kind of guess this feature must not make) and never the CRM
-- mirror. Until an operator confirms it for a given imóvel, the column is
-- NULL and `derivacao._imovel` / `_permuta` refuse to generate
-- (`av.falta("imovel.endereco_registro_texto", ...)`) rather than fall back
-- to the CRM's público endereço — printing the gatehouse is worse than
-- refusing.
-- ============================================================================

ALTER TABLE social_wiring.imovel_dados
    ADD COLUMN IF NOT EXISTS endereco_registro_texto                TEXT,
    ADD COLUMN IF NOT EXISTS endereco_registro_confirmado_por        UUID,
    ADD COLUMN IF NOT EXISTS endereco_registro_confirmado_em         TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.imovel_dados.endereco_registro_texto IS
    'The short address ("situado à ...") as an operator confirmed it after '
    'reading the matrícula (migration 139) — never the CRM/Vista mirror''s '
    'público endereço, which some tenants deliberately publish as the '
    'portaria/gatehouse address rather than the real one. Never a recomputed '
    'suggestion.';

ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_endereco_registro_confirmado;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_endereco_registro_confirmado
    CHECK ((endereco_registro_texto IS NULL) = (endereco_registro_confirmado_em IS NULL));
