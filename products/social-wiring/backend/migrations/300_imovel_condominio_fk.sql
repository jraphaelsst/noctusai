-- ============================================================================
-- Migration 300 · social_wiring: an imóvel is ATTACHED to its condomínio (FK)
--                 or explicitly marked "casa de rua"
-- ============================================================================
-- Owner decision 2026-10-21: "this data should be set in the imovel schema as
-- we attach them to empreendimentos/condominios. or if we check a box with
-- 'Casa de rua', which refers to properties outside condominiums. ... only 1
-- condominium is allowed per property (or none if De Rua), but a condominium
-- can have multiple properties."
--
-- WHY: `em_condominio` (202) was a free flag and the modal saved an unchecked
-- checkbox as an explicit "não" — wrong contract wording on real deals. The
-- answer now has two typed shapes, never a free boolean:
--   condominio_id  -> the condomínio master list row (265) the imóvel sits in.
--   casa_de_rua    -> TRUE = explicitly outside any condomínio.
--   neither        -> not answered (the contract readiness asks for it).
-- Both at once is a contradiction, refused by CHECK
-- `imovel_dados_condominio_ou_casa_de_rua`. A condomínio of ANOTHER org is
-- refused by the trigger `imovel_dados_condominio_mesma_org` (the FK alone
-- would accept any org's row; condominios.id is a bare PK, so a composite FK
-- would need a second UNIQUE (id, org_id) on condominios — a trigger is the
-- smaller surface). Both are probed by noctus.dev.verify_db_guards.
--
-- BACKFILL: em_condominio = FALSE -> casa_de_rua = TRUE (the only explicit
-- "not in a condomínio" answer the old flag could carry). TRUE/NULL rows stay
-- UNLINKED — no condomínio is auto-created from a name (owner decision); the
-- contract readiness surfaces them (TRUE: aviso, NULL: falta).
--
-- `em_condominio` is KEPT for one release (read-only legacy; the app stops
-- writing it). The app exposes the derived answer: condominio_id -> true,
-- casa_de_rua -> false, neither -> null.
--
-- VIEW `condominio_imoveis` (265) now resolves the FK FIRST and falls back to
-- the alias/name match only when the imóvel has no FK and is not casa de rua;
-- FK-linked manual imóveis (no Vista mirror row) are included too. Column
-- order of the original view is preserved (`vinculo` appended).
--
-- Code shipping with this file: `imovel_hub.dados_service` (CAMPOS_EDITAVEIS,
-- `_saida`, `condominio_resumo`), `imovel_hub.schemas`, `condominios.service`
-- (`buscar`/`criar`, FK-first stats, merge re-points the FK),
-- `contrato_gerador.carregador`/`derivacao`, the imóvel page + manual modal.
--
-- FORWARD-ONLY, IDEMPOTENT. PREREQUISITES: 075 (imovel_dados), 202, 265.
-- 🔴 MIGRATION FILE ONLY — apply via noctus.dev.migrate_product with consent.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.imovel_dados
    ADD COLUMN IF NOT EXISTS condominio_id UUID REFERENCES social_wiring.condominios (id);

ALTER TABLE social_wiring.imovel_dados
    ADD COLUMN IF NOT EXISTS casa_de_rua BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_sw_imovel_dados_condominio
    ON social_wiring.imovel_dados (condominio_id)
    WHERE condominio_id IS NOT NULL;

-- Backfill BEFORE the CHECK (no row can be in both states yet: condominio_id
-- is brand new, so every row is NULL there).
UPDATE social_wiring.imovel_dados
   SET casa_de_rua = true
 WHERE em_condominio IS FALSE
   AND condominio_id IS NULL
   AND casa_de_rua IS FALSE;

ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_condominio_ou_casa_de_rua;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_condominio_ou_casa_de_rua
    CHECK (NOT (casa_de_rua AND condominio_id IS NOT NULL));

-- Same-org guard: an imóvel may only be attached to a condomínio of its own org.
CREATE OR REPLACE FUNCTION social_wiring.imovel_dados_condominio_mesma_org()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path TO 'social_wiring', 'public'
AS $$
BEGIN
    IF NEW.condominio_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM social_wiring.condominios c
         WHERE c.id = NEW.condominio_id AND c.org_id = NEW.org_id
    ) THEN
        RAISE EXCEPTION 'imovel_dados.condominio_id deve ser um condomínio da mesma organização (condominio_id=%)',
            NEW.condominio_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_imovel_dados_condominio_mesma_org ON social_wiring.imovel_dados;
CREATE TRIGGER trg_imovel_dados_condominio_mesma_org
    BEFORE INSERT OR UPDATE OF condominio_id, org_id ON social_wiring.imovel_dados
    FOR EACH ROW EXECUTE FUNCTION social_wiring.imovel_dados_condominio_mesma_org();

COMMENT ON COLUMN social_wiring.imovel_dados.condominio_id IS
    'The condomínio (master list, migration 265) this imóvel sits in (migration '
    '300). One per imóvel; a condomínio has many imóveis. Mutually exclusive '
    'with casa_de_rua (CHECK); same org (trigger).';
COMMENT ON COLUMN social_wiring.imovel_dados.casa_de_rua IS
    'TRUE = explicitly outside any condomínio (migration 300). FALSE with no '
    'condominio_id = not answered yet.';
COMMENT ON COLUMN social_wiring.imovel_dados.em_condominio IS
    'LEGACY (migration 202; superseded by condominio_id/casa_de_rua, migration '
    '300). No longer written by the app; read only as the contract''s fallback '
    'for an unlinked imóvel. Drop after one release.';

-- ── Resolution view: FK first, alias/name match as the fallback ───────────
CREATE OR REPLACE VIEW social_wiring.condominio_imoveis
WITH (security_invoker = true) AS
SELECT i.org_id,
       i.codigo_norm AS codigo_canonical,
       COALESCE(d.condominio_id, a.condominio_id) AS condominio_id,
       a.alias_normalizado,
       CASE WHEN d.condominio_id IS NOT NULL THEN 'fk' ELSE 'alias' END AS vinculo
  FROM social_wiring.imoveis i
  LEFT JOIN social_wiring.imovel_dados d
         ON d.org_id = i.org_id AND d.codigo = i.codigo
  LEFT JOIN social_wiring.condominio_aliases a
         ON d.condominio_id IS NULL
        AND COALESCE(d.casa_de_rua, false) = false
        AND a.org_id = i.org_id
        AND a.alias_normalizado = upper(regexp_replace(btrim(
                COALESCE(NULLIF(btrim(d.empreendimento_manual), ''), i.empreendimento)
            ), '\s+', ' ', 'g'))
 WHERE COALESCE(d.condominio_id, a.condominio_id) IS NOT NULL
UNION ALL
-- FK-linked imóveis with no Vista mirror row (manual captação, migration 226).
SELECT d.org_id,
       d.codigo AS codigo_canonical,
       d.condominio_id,
       NULL::text AS alias_normalizado,
       'fk' AS vinculo
  FROM social_wiring.imovel_dados d
 WHERE d.condominio_id IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM social_wiring.imoveis i
        WHERE i.org_id = d.org_id AND i.codigo = d.codigo
   );
