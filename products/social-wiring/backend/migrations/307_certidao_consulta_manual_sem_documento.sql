-- Migration: certidao_consulta_manual_sem_documento
-- Schema: social_wiring

SET search_path = social_wiring, public;

-- F86 (2026-10-24): a party added by NAME only (an antigo proprietário whose
-- identity comes from his own certidões) could not receive a certidão PDF —
-- the cell holder `POST /api/clientes/{id}/certidoes/celulas` creates is a
-- `certidao_consultas` row, and `documento` was NOT NULL. The CPF/CNPJ is an
-- InfoSimples PARAMETER: only an automatic (billed) consulta needs it. A
-- manual consulta (`origem='manual'`, migration 147) is never dispatched to
-- the API, so it may be created before the document is known.
--
-- Forward-safe: relaxes NOT NULL and replaces it with a CHECK that keeps the
-- invariant for every automatic consulta. Every existing row already has a
-- non-empty documento, so the CHECK validates. Idempotent.
ALTER TABLE social_wiring.certidao_consultas
    ALTER COLUMN documento DROP NOT NULL;

ALTER TABLE social_wiring.certidao_consultas
    DROP CONSTRAINT IF EXISTS certidao_consultas_documento_automatica_check;
ALTER TABLE social_wiring.certidao_consultas
    ADD CONSTRAINT certidao_consultas_documento_automatica_check
    CHECK (origem = 'manual' OR (documento IS NOT NULL AND btrim(documento) <> ''));

COMMENT ON COLUMN social_wiring.certidao_consultas.documento IS
    'CPF/CNPJ of the searched party. Required for origem=automatica (the '
    'InfoSimples parameter); NULL allowed only for a manual cell holder '
    'created before the party''s document is known (migration 307, F86).';
