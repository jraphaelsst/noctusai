-- Migration 013: Add api_requested_at to certidao_resultados for TJSP cooldown tracking
--
-- The TJSP queue cooldown was tracked via updated_at of resultados with status
-- IN ('sucesso', 'erro'). When reprocessing resets status to 'na_fila', the
-- cooldown signal was lost, causing the queue worker to fire immediately and
-- hit the TJSP rate limit.
--
-- api_requested_at records when the API was actually called. It survives status
-- resets (reprocessing never clears it), so the cooldown is always enforced.

ALTER TABLE erp.certidao_resultados
    ADD COLUMN IF NOT EXISTS api_requested_at timestamptz;
