-- Migration 010: Add 'na_fila' to certidao_resultados status check constraint
-- Required for the TJSP queue system (35-min cooldown between requests).

-- Drop the existing constraint and recreate with 'na_fila' included
ALTER TABLE erp.certidao_resultados
    DROP CONSTRAINT IF EXISTS certidao_resultados_status_check;

ALTER TABLE erp.certidao_resultados
    ADD CONSTRAINT certidao_resultados_status_check
    CHECK (status IN ('pendente', 'processando', 'na_fila', 'sucesso', 'erro'));
