-- ============================================================================
-- Migration 365 · social_wiring: CoreStudio criação pipeline, M-D -- cs_consentimentos_voz (voice / avatar consent)
-- ============================================================================
-- WHY
-- ---
-- Spec: criacao-pipeline-contract.md sections 2 (M-D), 5, 10.1 (owner: one ElevenLabs voice feeds HeyGen as audio, so
-- consent is held for BOTH vendors). A cloned voice / avatar is biometric data of a real person (LGPD art. 5 II / 11):
-- the media worker may call `clone_voice` only against a VALID consent row. The consent document itself (signed term)
-- lives in a private bucket; this table holds its path + sha256 so the file cannot be swapped silently.
--
--   * cs_consentimentos_voz  -- APPEND-ONLY. A grant is a row (fase = 'concedido'); a revocation is a NEW row
--                               (fase = 'revogado', revoga_id -> the granted row, revogado_em). Nothing is ever updated;
--                               DELETE is refused except by a future LGPD erasure path (GUC carve-out, below).
--   * cs_consentimento_voz_vigente(org, marca, vendor, voice_id) -- the one derivation of "is there a valid consent":
--                               the newest grant for that voice, not revoked by a later row, not past valido_ate.
--                               This is what the seed `tts.clone_voice` port reads.
--
-- Records -> metrics: consents granted / revoked per vendor, time-to-revoke, clones refused for lack of consent.
-- Backward compatible with the previous image: a NEW table + function. Tier: org (service-only grants; the document is
-- served by signed URL). marca_id is held by id only, no FK: an append-only consent record outlives its marca.
-- FORWARD-ONLY, IDEMPOTENT.
--
-- NOC-REMEDIATE[cs-consentimentos-voz-expurgo-lgpd]: the erasure path (data-subject request) must be a SECURITY DEFINER function setting the `social_wiring.cs_consentimentos_voz_expurgo` GUC via guc_carveout_set_config_sql — 2026-11-19
-- ============================================================================

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.cs_consentimentos_voz (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID NOT NULL,
    marca_id          UUID NOT NULL,
    pessoa_nome       TEXT NOT NULL,
    vendor            TEXT NOT NULL,
    voice_id          TEXT NOT NULL,
    documento_path    TEXT NOT NULL,
    documento_sha256  TEXT NOT NULL,
    escopo            TEXT NOT NULL,
    fase              TEXT NOT NULL DEFAULT 'concedido',
    valido_ate        TIMESTAMPTZ,
    revoga_id         UUID,
    revogado_em       TIMESTAMPTZ,
    registrado_por    UUID,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT cs_consentimentos_voz_pessoa_check CHECK (char_length(btrim(pessoa_nome)) BETWEEN 1 AND 200),
    CONSTRAINT cs_consentimentos_voz_vendor_check CHECK (vendor IN ('elevenlabs', 'heygen')),
    CONSTRAINT cs_consentimentos_voz_voice_check CHECK (char_length(voice_id) BETWEEN 1 AND 200),
    CONSTRAINT cs_consentimentos_voz_doc_path_check CHECK (char_length(documento_path) BETWEEN 1 AND 1024),
    CONSTRAINT cs_consentimentos_voz_doc_sha_check CHECK (documento_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT cs_consentimentos_voz_escopo_check CHECK (escopo IN ('clone_voz', 'avatar', 'clone_voz_e_avatar')),
    CONSTRAINT cs_consentimentos_voz_fase_check CHECK (fase IN ('concedido', 'revogado')),
    -- a revocation points at the grant it revokes and is dated; a grant does neither
    CONSTRAINT cs_consentimentos_voz_revogacao_check
        CHECK ((fase = 'revogado') = (revoga_id IS NOT NULL) AND (fase = 'revogado') = (revogado_em IS NOT NULL)),
    CONSTRAINT cs_consentimentos_voz_id_alvo_uq UNIQUE (id, org_id, marca_id, vendor),
    -- the revoked grant is of the SAME org, marca and vendor
    CONSTRAINT cs_consentimentos_voz_revoga_fk FOREIGN KEY (revoga_id, org_id, marca_id, vendor)
        REFERENCES social_wiring.cs_consentimentos_voz (id, org_id, marca_id, vendor)
);
CREATE INDEX IF NOT EXISTS cs_consentimentos_voz_alvo_idx
    ON social_wiring.cs_consentimentos_voz (org_id, marca_id, vendor, voice_id, created_at DESC);
CREATE INDEX IF NOT EXISTS cs_consentimentos_voz_revoga_idx
    ON social_wiring.cs_consentimentos_voz (revoga_id) WHERE revoga_id IS NOT NULL;

-- guc-carveout-guard: rendered by noctusai_lib.domain.sql_templates.guc_carveout_guard_sql
CREATE OR REPLACE FUNCTION social_wiring.guard_cs_consentimentos_voz_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = social_wiring, public
AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('social_wiring.cs_consentimentos_voz_expurgo', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'guard_cs_consentimentos_voz_append_only: cs_consentimentos_voz is append-only (a revocation is a new row)' USING ERRCODE = 'P0001';
END;
$$;

REVOKE ALL ON FUNCTION social_wiring.guard_cs_consentimentos_voz_append_only() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.guard_cs_consentimentos_voz_append_only() TO service_role;

DROP TRIGGER IF EXISTS guard_cs_consentimentos_voz_append_only ON social_wiring.cs_consentimentos_voz;
CREATE TRIGGER guard_cs_consentimentos_voz_append_only
    BEFORE UPDATE OR DELETE ON social_wiring.cs_consentimentos_voz
    FOR EACH ROW EXECUTE FUNCTION social_wiring.guard_cs_consentimentos_voz_append_only();

-- The one derivation of "is this voice cleared": newest unrevoked, unexpired grant. NULL = none.
CREATE OR REPLACE FUNCTION social_wiring.cs_consentimento_voz_vigente(
    p_org UUID, p_marca UUID, p_vendor TEXT, p_voice_id TEXT)
RETURNS UUID
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = social_wiring, pg_catalog, pg_temp
AS $fn$
    SELECT c.id
      FROM social_wiring.cs_consentimentos_voz c
     WHERE c.org_id = p_org AND c.marca_id = p_marca AND c.vendor = p_vendor AND c.voice_id = p_voice_id
       AND c.fase = 'concedido'
       AND (c.valido_ate IS NULL OR c.valido_ate > now())
       AND NOT EXISTS (SELECT 1 FROM social_wiring.cs_consentimentos_voz r WHERE r.revoga_id = c.id)
     ORDER BY c.created_at DESC
     LIMIT 1;
$fn$;

REVOKE ALL ON FUNCTION social_wiring.cs_consentimento_voz_vigente(UUID, UUID, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION social_wiring.cs_consentimento_voz_vigente(UUID, UUID, TEXT, TEXT) TO service_role;

ALTER TABLE social_wiring.cs_consentimentos_voz ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "cs_consentimentos_voz_service_role" ON social_wiring.cs_consentimentos_voz;
CREATE POLICY "cs_consentimentos_voz_service_role" ON social_wiring.cs_consentimentos_voz FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.cs_consentimentos_voz FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT ON TABLE social_wiring.cs_consentimentos_voz TO service_role;

COMMENT ON TABLE social_wiring.cs_consentimentos_voz IS 'tier:org';
COMMENT ON COLUMN social_wiring.cs_consentimentos_voz.documento_sha256 IS
    'sha256 of the signed consent document (private bucket); the file cannot be swapped silently. Biometric consent: LGPD art. 11. Migration 365.';
