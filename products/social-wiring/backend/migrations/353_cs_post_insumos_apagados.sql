-- ============================================================================
-- Migration 353 · social_wiring: CoreStudio S5 -- raw inputs deleted at publish are a recorded, dated fact
-- ============================================================================
-- WHY: owner rule Q5 (2026-11-13) -- raw video inputs (``.../posts/<post>/insumos/``) are deleted when the post is fully
-- published (LGPD data minimisation). The deletion must be MEASURABLE: ``cs_post_assets.apagado_em`` is the dated fact and
-- an AFTER trigger writes the ``insumos_apagados`` event in the SAME transaction as that UPDATE (EOA, no hand-written
-- history). Backward-compatible with the previous image: one nullable column + a widened CHECK + a superset trigger.
-- ============================================================================
SET search_path = social_wiring, public;

ALTER TABLE social_wiring.cs_post_assets ADD COLUMN IF NOT EXISTS apagado_em TIMESTAMPTZ;

ALTER TABLE social_wiring.cs_post_eventos DROP CONSTRAINT IF EXISTS cs_post_eventos_tipo_check;
ALTER TABLE social_wiring.cs_post_eventos ADD CONSTRAINT cs_post_eventos_tipo_check CHECK (tipo IN (
    'midia_versao_criada', 'midia_status_alterado', 'insumos_apagados',
    'publicacao_agendada', 'publicacao_reagendada', 'publicado', 'publicacao_falhou', 'publicacao_cancelada'));

CREATE OR REPLACE FUNCTION social_wiring.cs_post_assets_evento()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = social_wiring, pg_catalog, pg_temp
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO social_wiring.cs_post_eventos (org_id, post_id, asset_id, tipo, para, dados, ator_id)
        VALUES (NEW.org_id, NEW.post_id, NEW.id, 'midia_versao_criada', NEW.status,
                jsonb_build_object('tipo_midia', NEW.tipo_midia, 'ordem', NEW.ordem, 'versao', NEW.versao,
                                   'proporcao', NEW.proporcao, 'duracao_s', NEW.duracao_s),
                COALESCE(NEW.atualizado_por, NEW.criado_por));
        RETURN NULL;
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        INSERT INTO social_wiring.cs_post_eventos (org_id, post_id, asset_id, tipo, de, para, dados, ator_id)
        VALUES (NEW.org_id, NEW.post_id, NEW.id, 'midia_status_alterado', OLD.status, NEW.status,
                jsonb_build_object('ordem', NEW.ordem, 'versao', NEW.versao), NEW.atualizado_por);
    END IF;
    IF OLD.apagado_em IS NULL AND NEW.apagado_em IS NOT NULL THEN
        INSERT INTO social_wiring.cs_post_eventos (org_id, post_id, asset_id, tipo, para, dados, ator_id)
        VALUES (NEW.org_id, NEW.post_id, NEW.id, 'insumos_apagados', NEW.status,
                jsonb_build_object('ordem', NEW.ordem, 'versao', NEW.versao, 'tipo_midia', NEW.tipo_midia,
                                   'tamanho_bytes', NEW.tamanho_bytes), NEW.atualizado_por);
    END IF;
    RETURN NULL;
END;
$$;
