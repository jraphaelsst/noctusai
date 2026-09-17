-- 047_assinaturas_external_id.sql — Migration: erp.assinaturas gains external_id
-- Generated for projects/signature-integration-CONTRACT.md (Slice S-D)
-- Schema: erp
--
-- Drift-fix-on-contact: `app.services.assinatura_service.preparar_envio`
-- already inserted an `external_id` key into `erp.assinaturas` (both before
-- and after this slice's adapter swap onto `noctusai_lib.integrations.
-- signature`), but no migration ever added the column — 001/004 never
-- defined it, and `MockSupabaseClient` in tests runs with
-- `validate_schema=False`, so the gap never surfaced. `external_id` is the
-- provider's own envelope id (`EnvelopeCriado.external_id`) and is needed to
-- correlate a stored assinatura with its D4Sign document going forward.
-- Additive only; no data touched.

SET search_path = erp, public;

ALTER TABLE erp.assinaturas
    ADD COLUMN IF NOT EXISTS external_id text;

NOTIFY pgrst, 'reload schema';
