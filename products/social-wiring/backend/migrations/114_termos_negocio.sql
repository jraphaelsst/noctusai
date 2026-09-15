-- ============================================================================
-- Migration 114 · social_wiring: Termos do negócio — the per-deal terms the
-- contract generator prints and nothing stores yet
--
-- The F5 generator (`card_hub/contrato_gerador`) reads a `Complementos`
-- dataclass whose fields are USED by every contract variant and HELD nowhere
-- (NOC-REMEDIATE[contrato-f6-campos-missing]). This migration gives those
-- terms real storage. It adds:
--
--   1. `atendimento_negociacao_termos` — one row per atendimento: posse,
--      itens integrantes / ad corpus / obrigações do vendedor, quitação de
--      ônus, confissão de dívida, corretagem;
--   2. parcela `tipo = 'permuta'` + `dispara_corretagem` on
--      `atendimento_negociacao_parcelas` (108);
--   3. `atendimento_parcela_permuta_ativos` — a permuta parcela pays with ONE
--      OR MORE `permuta_ativos` (101) — plus a backfill of the legacy
--      `atendimento_negociacao.permuta_ativo_id` into that link;
--   4. PF/PJ qualification columns on `atendimento_intermediarios` (108);
--   5. `assinatura_data` + `prazo_pendencias_dias` on
--      `atendimento_contratos` (106).
--
-- 🔴 A NEW ONE-ROW TABLE, NOT MORE COLUMNS ON `atendimento_negociacao`
-- ------------------------------------------------------------------------
-- `atendimento_negociacao` (077) is written through ONE path,
-- `negociacao_service._gravar`, which materialises the org's commission-split
-- defaults on first insert and enforces the split-sums-to-100 rule. A second
-- writer for contract terms would either have to duplicate that
-- insert-with-defaults logic (the place the two quietly diverge) or route
-- contract-clause edits through the commercial-terms endpoint. These terms
-- are a different concern — what the INSTRUMENT says, not the commercial
-- split — edited from a different panel, so they get their own row keyed on
-- `atendimento_id`, CASCADEing with it, same shape as
-- `atendimento_negociacao` itself. `negociacao_estruturada_service` owns it.
--
-- LEGACY COLUMNS KEPT, NOT DROPPED
-- --------------------------------
-- `atendimento_negociacao.posse_data` / `posse_condicoes` (108) are superseded
-- by `posse_prazo_dias` + `posse_marco` (a contract says "N dias contados
-- da assinatura", never a calendar date) and `permuta_ativo_id` (108) by the
-- permuta parcela link (one swap can involve several matrículas). All three
-- stay: the existing panel and `negociacao_service` still read and write
-- them, and dropping a column in the same change that introduces its
-- successor removes the ability to compare the two. COMMENTed legacy below.
--
-- `posse_marco = 'parcela'` NAMES THE PARCELA
-- ---------------------------------------------
-- "Posse transfers on payment of parcela X" is only printable if X is known,
-- so `posse_marco_parcela_id` is REQUIRED exactly when the marco is
-- 'parcela' and FORBIDDEN otherwise (CHECK below — the backstop; the service
-- raises a named 400 first). The FK is `NO ACTION`, not `SET NULL`: a
-- SET NULL would violate that same CHECK and surface as a 500 on a parcela
-- delete. The service refuses deleting a parcela that is a posse marco with a
-- named 409 instead; deleting the whole atendimento still works, because
-- NO ACTION is checked at end of statement, after both CASCADEs ran. The FK is
-- the plain `-> id` shape, validated against the SAME atendimento in the
-- service, for the reason migration 108's header gives for `favorecido_id`.
--
-- `permuta_posse_marco_parcela_id` mirrors that for the permuta side (the
-- buyer hands the swapped property over on the same three kinds of marco).
--
-- 🔴 PERMUTA LINK: VALIDATED AT BOTH ENDS
-- -----------------------------------------
-- A link is only meaningful when the parcela is `tipo = 'permuta'`, the ativo
-- is `natureza = 'permuta_imovel'` (property BROUGHT as swap currency — not a
-- catalog listing, not an automobile), and both belong to the link's org.
-- The service checks all of it first (404 for an unknown / other-org ativo,
-- 400 for a wrong natureza or tipo); a BEFORE INSERT/UPDATE trigger holds the
-- same rule for any writer that bypasses the service, and a BEFORE UPDATE OF
-- tipo trigger on parcelas refuses turning a linked permuta parcela into
-- another tipo. Same backstop-not-message posture as 108's
-- `enforce_max_org_testemunhas`.
--
-- 🔴 LGPD — NEW PERSONAL DATA ON `atendimento_intermediarios`
-- -------------------------------------------------------------
-- categoria: dados pessoais comuns de identificação e contato (LGPD art. 5º,
-- I) — CPF/CNPJ (`documento`), `email`, residential/business address
-- (`endereco_*`), and the legal representative's name + CPF
-- (`representante_nome`, `representante_cpf`). NOT sensitive data (art. 5º,
-- II). Base legal: execução de contrato (art. 7º, V) — the intermediary is
-- qualified in the instrument they sign. Same posture migration 108 set for
-- `atendimento_favorecidos`: RLS org-scoped, ATENDIMENTO-scoped (CASCADE with
-- the deal), and — the operative rule — **values are never logged**; the
-- service logs only ids and counts. Retention follows the atendimento row
-- (no separate clock), same as every other 108 table. Flagged via
-- `noctus.dev.lgpd_flag` in the same change.
--
-- `documento` / `representante_cpf` / `endereco_cep` are stored NORMALISED
-- (no punctuation; CNPJ uppercased — alphanumeric CNPJs exist since July 2026)
-- and verified by check digit in the service
-- (`noctusai_lib.integrations.documents.{cpf,cnpj}.is_valid`). The CHECKs
-- below pin only the SHAPE, which a DB can verify cheaply.
--
-- `prazo_pendencias_dias` — NULL MEANS "THE OFFICE DEFAULT"
-- -----------------------------------------------------------
-- The generator's policy default (`contrato_gerador.politica.
-- prazo_pendencias_dias = 10`) is the office rule; a per-contract value is an
-- override, so the column is nullable and a NULL is not "zero days". `> 0`
-- when set: a zero-day deadline to resolve pendências is not a term anyone
-- signs.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- 🔴 MIGRATION FILE ONLY — applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. atendimento_negociacao_termos — the instrument's per-deal clauses
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_negociacao_termos (
    atendimento_id UUID PRIMARY KEY
        REFERENCES social_wiring.atendimentos (id) ON DELETE CASCADE,
    org_id         UUID NOT NULL,

    -- Posse (buyer receives the property)
    posse_prazo_dias       INTEGER
        CHECK (posse_prazo_dias IS NULL OR posse_prazo_dias >= 0),
    posse_marco            TEXT
        CHECK (posse_marco IS NULL
               OR posse_marco IN ('assinatura', 'parcela', 'protocolo_registro')),
    posse_marco_parcela_id UUID
        REFERENCES social_wiring.atendimento_negociacao_parcelas (id),

    -- Posse of the swapped property (seller receives it)
    permuta_posse_prazo_dias       INTEGER
        CHECK (permuta_posse_prazo_dias IS NULL OR permuta_posse_prazo_dias >= 0),
    permuta_posse_marco            TEXT
        CHECK (permuta_posse_marco IS NULL
               OR permuta_posse_marco IN ('assinatura', 'parcela', 'protocolo_registro')),
    permuta_posse_marco_parcela_id UUID
        REFERENCES social_wiring.atendimento_negociacao_parcelas (id),
    permuta_obrigacoes_entrega     TEXT,

    -- The object of the sale
    itens_integrantes   TEXT,
    ad_corpus           BOOLEAN,
    obrigacoes_vendedor TEXT,

    -- Ônus payoff on this deal
    onus_quitacao   TEXT
        CHECK (onus_quitacao IS NULL
               OR onus_quitacao IN (
                   'compradores_prazo', 'interveniente_quitante', 'parcela',
                   'ja_quitado'
               )),
    onus_prazo_dias INTEGER
        CHECK (onus_prazo_dias IS NULL OR onus_prazo_dias >= 0),

    -- Confissão de dívida
    confissao_juros_am NUMERIC(7,4)
        CHECK (confissao_juros_am IS NULL
               OR confissao_juros_am BETWEEN 0 AND 100),
    confissao_garantia TEXT,

    -- Corretagem
    corretagem_contratantes TEXT
        CHECK (corretagem_contratantes IS NULL
               OR corretagem_contratantes IN ('vendedores', 'compradores', 'partes')),
    corretagem_num_parcelas INTEGER
        CHECK (corretagem_num_parcelas IS NULL OR corretagem_num_parcelas > 0),

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_por    UUID,
    updated_at     TIMESTAMPTZ,
    updated_por    UUID,

    -- marco = 'parcela' <=> a parcela is named (see the 114 header).
    -- IS NOT DISTINCT FROM so a NULL marco with a stray id is still refused.
    CONSTRAINT atendimento_negociacao_termos_posse_marco_parcela
        CHECK ((posse_marco IS NOT DISTINCT FROM 'parcela')
               = (posse_marco_parcela_id IS NOT NULL)),
    CONSTRAINT atendimento_negociacao_termos_permuta_posse_marco_parcela
        CHECK ((permuta_posse_marco IS NOT DISTINCT FROM 'parcela')
               = (permuta_posse_marco_parcela_id IS NOT NULL))
);

COMMENT ON TABLE social_wiring.atendimento_negociacao_termos IS
    'Per-deal contract clauses the generator prints (posse, itens integrantes, '
    'ad corpus, ônus, confissão de dívida, corretagem). One row per '
    'atendimento, owned by negociacao_estruturada_service — a separate table '
    'so atendimento_negociacao keeps its single writer. See the 114 header.';
COMMENT ON COLUMN social_wiring.atendimento_negociacao_termos.posse_marco IS
    'assinatura | parcela | protocolo_registro — the event posse_prazo_dias '
    'counts from. parcela requires posse_marco_parcela_id (CHECK).';
COMMENT ON COLUMN social_wiring.atendimento_negociacao_termos.onus_quitacao IS
    'compradores_prazo | interveniente_quitante | parcela | ja_quitado.';
COMMENT ON COLUMN social_wiring.atendimento_negociacao_termos.confissao_juros_am IS
    'Juros da confissão de dívida, % ao mês (0-100).';
COMMENT ON COLUMN social_wiring.atendimento_negociacao_termos.corretagem_contratantes IS
    'vendedores | compradores | partes — who contracts (and pays) the '
    'brokerage. Which parcelas trigger its payment is '
    'atendimento_negociacao_parcelas.dispara_corretagem.';

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_negociacao_termos_org
    ON social_wiring.atendimento_negociacao_termos (org_id);
CREATE INDEX IF NOT EXISTS idx_sw_atendimento_negociacao_termos_posse_parcela
    ON social_wiring.atendimento_negociacao_termos (posse_marco_parcela_id)
    WHERE posse_marco_parcela_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sw_atendimento_negociacao_termos_permuta_posse_parcela
    ON social_wiring.atendimento_negociacao_termos (permuta_posse_marco_parcela_id)
    WHERE permuta_posse_marco_parcela_id IS NOT NULL;

ALTER TABLE social_wiring.atendimento_negociacao_termos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_negociacao_termos_select_own_org"
    ON social_wiring.atendimento_negociacao_termos;
CREATE POLICY "atendimento_negociacao_termos_select_own_org"
    ON social_wiring.atendimento_negociacao_termos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_negociacao_termos_service_role"
    ON social_wiring.atendimento_negociacao_termos;
CREATE POLICY "atendimento_negociacao_termos_service_role"
    ON social_wiring.atendimento_negociacao_termos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 2. atendimento_negociacao_parcelas: tipo 'permuta' + dispara_corretagem
-- ----------------------------------------------------------------------------
-- 108 declared the CHECK inline, so Postgres named it
-- `<table>_<column>_check`. Drop-then-add is the idempotent CHECK extension.
ALTER TABLE social_wiring.atendimento_negociacao_parcelas
    DROP CONSTRAINT IF EXISTS atendimento_negociacao_parcelas_tipo_check;
ALTER TABLE social_wiring.atendimento_negociacao_parcelas
    ADD CONSTRAINT atendimento_negociacao_parcelas_tipo_check
    CHECK (tipo IN (
        'sinal', 'intermediaria', 'financiamento', 'fgts', 'saldo', 'direta',
        'permuta'
    ));

ALTER TABLE social_wiring.atendimento_negociacao_parcelas
    ADD COLUMN IF NOT EXISTS dispara_corretagem BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN social_wiring.atendimento_negociacao_parcelas.tipo IS
    'sinal | intermediaria | financiamento | fgts | saldo | direta | permuta. '
    'permuta = paid with the permuta_ativos linked in '
    'atendimento_parcela_permuta_ativos (114).';
COMMENT ON COLUMN social_wiring.atendimento_negociacao_parcelas.dispara_corretagem IS
    'Payment of THIS parcela triggers payment of the brokerage commission '
    '(114). Per-parcela, several may be true.';

-- ----------------------------------------------------------------------------
-- 3. atendimento_parcela_permuta_ativos — which ativos pay a permuta parcela
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_parcela_permuta_ativos (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL,
    parcela_id       UUID NOT NULL
        REFERENCES social_wiring.atendimento_negociacao_parcelas (id) ON DELETE CASCADE,
    -- CASCADE, mirroring 108's SET NULL on the legacy column: losing which
    -- ativo was swapped is not losing the deal; the parcela survives and
    -- `completude` reports it as `parcela_permuta_sem_imoveis`.
    permuta_ativo_id UUID NOT NULL
        REFERENCES social_wiring.permuta_ativos (id) ON DELETE CASCADE,

    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_por      UUID,

    CONSTRAINT atendimento_parcela_permuta_ativos_unico
        UNIQUE (parcela_id, permuta_ativo_id)
);

COMMENT ON TABLE social_wiring.atendimento_parcela_permuta_ativos IS
    'Links a tipo=permuta parcela to the ONE OR MORE permuta_ativos '
    '(natureza=permuta_imovel) it is paid with — one swap can hand over two '
    'matrículas for a single value. Validated by service AND trigger. See the '
    '114 header.';

CREATE INDEX IF NOT EXISTS idx_sw_parcela_permuta_ativos_org_parcela
    ON social_wiring.atendimento_parcela_permuta_ativos (org_id, parcela_id);
CREATE INDEX IF NOT EXISTS idx_sw_parcela_permuta_ativos_ativo
    ON social_wiring.atendimento_parcela_permuta_ativos (org_id, permuta_ativo_id);

ALTER TABLE social_wiring.atendimento_parcela_permuta_ativos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_parcela_permuta_ativos_select_own_org"
    ON social_wiring.atendimento_parcela_permuta_ativos;
CREATE POLICY "atendimento_parcela_permuta_ativos_select_own_org"
    ON social_wiring.atendimento_parcela_permuta_ativos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_parcela_permuta_ativos_service_role"
    ON social_wiring.atendimento_parcela_permuta_ativos;
CREATE POLICY "atendimento_parcela_permuta_ativos_service_role"
    ON social_wiring.atendimento_parcela_permuta_ativos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- 🔴 The backstop half of the link rule — the service checks first.
CREATE OR REPLACE FUNCTION social_wiring.enforce_parcela_permuta_ativo()
  RETURNS TRIGGER
  LANGUAGE plpgsql
  SET search_path TO 'social_wiring', 'public'
AS $$
DECLARE
    v_tipo        TEXT;
    v_parcela_org UUID;
    v_natureza    TEXT;
    v_ativo_org   UUID;
BEGIN
    SELECT tipo, org_id INTO v_tipo, v_parcela_org
      FROM social_wiring.atendimento_negociacao_parcelas
     WHERE id = NEW.parcela_id;
    IF v_tipo IS DISTINCT FROM 'permuta' OR v_parcela_org IS DISTINCT FROM NEW.org_id THEN
        RAISE EXCEPTION
            'atendimento_parcela_permuta_ativos: a parcela % não é uma parcela de permuta desta organização',
            NEW.parcela_id;
    END IF;

    SELECT natureza, org_id INTO v_natureza, v_ativo_org
      FROM social_wiring.permuta_ativos
     WHERE id = NEW.permuta_ativo_id;
    IF v_natureza IS DISTINCT FROM 'permuta_imovel' OR v_ativo_org IS DISTINCT FROM NEW.org_id THEN
        RAISE EXCEPTION
            'atendimento_parcela_permuta_ativos: o ativo % não é um imóvel de permuta desta organização',
            NEW.permuta_ativo_id;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS enforce_parcela_permuta_ativo_trigger
    ON social_wiring.atendimento_parcela_permuta_ativos;
CREATE TRIGGER enforce_parcela_permuta_ativo_trigger
    BEFORE INSERT OR UPDATE ON social_wiring.atendimento_parcela_permuta_ativos
    FOR EACH ROW EXECUTE FUNCTION social_wiring.enforce_parcela_permuta_ativo();

CREATE OR REPLACE FUNCTION social_wiring.enforce_parcela_permuta_tipo()
  RETURNS TRIGGER
  LANGUAGE plpgsql
  SET search_path TO 'social_wiring', 'public'
AS $$
BEGIN
    IF NEW.tipo IS DISTINCT FROM 'permuta' AND EXISTS (
        SELECT 1 FROM social_wiring.atendimento_parcela_permuta_ativos
         WHERE parcela_id = NEW.id
    ) THEN
        RAISE EXCEPTION
            'atendimento_negociacao_parcelas: a parcela % tem imóveis de permuta vinculados — remova-os antes de mudar o tipo',
            NEW.id;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS enforce_parcela_permuta_tipo_trigger
    ON social_wiring.atendimento_negociacao_parcelas;
CREATE TRIGGER enforce_parcela_permuta_tipo_trigger
    BEFORE UPDATE OF tipo ON social_wiring.atendimento_negociacao_parcelas
    FOR EACH ROW EXECUTE FUNCTION social_wiring.enforce_parcela_permuta_tipo();

-- ----------------------------------------------------------------------------
-- 3b. Backfill: legacy atendimento_negociacao.permuta_ativo_id -> link
-- ----------------------------------------------------------------------------
-- For every deal whose legacy column points at a `permuta_imovel` ativo of
-- its own org and that is not linked yet: create ONE `tipo='permuta'` parcela
-- (valor = the ativo's own `valor`, 0 when unknown — `valor` is NOT NULL and
-- the ativo's appraisal is the only figure on record; the operator adjusts
-- it) at the end of the schedule, and link the ativo to it.
--
-- A plpgsql loop, NOT a data-modifying CTE: the link trigger above SELECTs
-- the parcela, and sibling sub-statements of one WITH do not see each
-- other's rows. Each loop statement sees the previous one's insert.
-- Idempotent through the NOT EXISTS guard. A legacy pointer at any other
-- natureza (a catalog `imovel`, an automobile) is NOT payment currency and is
-- left on the legacy column only — counted in a NOTICE, never guessed.
DO $$
DECLARE
    r           RECORD;
    v_parcela   UUID;
    v_migrados  INTEGER := 0;
    v_ignorados INTEGER;
BEGIN
    FOR r IN
        SELECT n.org_id, n.atendimento_id, n.permuta_ativo_id,
               GREATEST(ROUND(COALESCE(pa.valor, 0), 2), 0) AS valor
          FROM social_wiring.atendimento_negociacao n
          JOIN social_wiring.permuta_ativos pa
            ON pa.id = n.permuta_ativo_id
           AND pa.org_id = n.org_id
           AND pa.natureza = 'permuta_imovel'
         WHERE n.permuta_ativo_id IS NOT NULL
           AND NOT EXISTS (
               SELECT 1
                 FROM social_wiring.atendimento_parcela_permuta_ativos l
                 JOIN social_wiring.atendimento_negociacao_parcelas p
                   ON p.id = l.parcela_id
                WHERE p.atendimento_id = n.atendimento_id
                  AND l.permuta_ativo_id = n.permuta_ativo_id
           )
    LOOP
        INSERT INTO social_wiring.atendimento_negociacao_parcelas
            (org_id, atendimento_id, tipo, valor, ordem)
        VALUES (
            r.org_id, r.atendimento_id, 'permuta', r.valor,
            COALESCE((
                SELECT MAX(p.ordem) + 1
                  FROM social_wiring.atendimento_negociacao_parcelas p
                 WHERE p.atendimento_id = r.atendimento_id
            ), 0)
        )
        RETURNING id INTO v_parcela;

        INSERT INTO social_wiring.atendimento_parcela_permuta_ativos
            (org_id, parcela_id, permuta_ativo_id)
        VALUES (r.org_id, v_parcela, r.permuta_ativo_id);

        v_migrados := v_migrados + 1;
    END LOOP;

    SELECT COUNT(*) INTO v_ignorados
      FROM social_wiring.atendimento_negociacao n
      JOIN social_wiring.permuta_ativos pa ON pa.id = n.permuta_ativo_id
     WHERE pa.natureza <> 'permuta_imovel';

    RAISE NOTICE
        '114 backfill: % permuta_ativo_id migrado(s) para parcela de permuta; % apontam para natureza <> permuta_imovel e ficaram só na coluna legada',
        v_migrados, v_ignorados;
END
$$;

-- ----------------------------------------------------------------------------
-- 3c. Legacy columns on atendimento_negociacao (kept — see the 114 header)
-- ----------------------------------------------------------------------------
COMMENT ON COLUMN social_wiring.atendimento_negociacao.posse_data IS
    'LEGACY (superseded by atendimento_negociacao_termos.posse_prazo_dias + '
    'posse_marco, 114). Kept for the existing panel; the contract generator '
    'does not read it.';
COMMENT ON COLUMN social_wiring.atendimento_negociacao.posse_condicoes IS
    'LEGACY (superseded by atendimento_negociacao_termos.posse_* , 114). Free '
    'text kept for the existing panel; the contract generator does not read it.';
COMMENT ON COLUMN social_wiring.atendimento_negociacao.permuta_ativo_id IS
    'LEGACY (superseded by a tipo=permuta parcela + '
    'atendimento_parcela_permuta_ativos, 114 — backfilled there). One swap can '
    'involve several ativos; this column can only hold one.';

-- ----------------------------------------------------------------------------
-- 4. atendimento_intermediarios — PF/PJ qualification (LGPD: see header)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.atendimento_intermediarios
    ADD COLUMN IF NOT EXISTS favorecido_id        UUID,
    ADD COLUMN IF NOT EXISTS pessoa_tipo          TEXT,
    ADD COLUMN IF NOT EXISTS documento            TEXT,
    ADD COLUMN IF NOT EXISTS email                TEXT,
    ADD COLUMN IF NOT EXISTS endereco_cep         TEXT,
    ADD COLUMN IF NOT EXISTS endereco_logradouro  TEXT,
    ADD COLUMN IF NOT EXISTS endereco_numero      TEXT,
    ADD COLUMN IF NOT EXISTS endereco_complemento TEXT,
    ADD COLUMN IF NOT EXISTS endereco_bairro      TEXT,
    ADD COLUMN IF NOT EXISTS endereco_cidade      TEXT,
    ADD COLUMN IF NOT EXISTS endereco_uf          TEXT,
    ADD COLUMN IF NOT EXISTS representante_nome   TEXT,
    ADD COLUMN IF NOT EXISTS representante_cpf    TEXT;

-- Who the intermediary's commission is paid to — one of THIS deal's
-- favorecidos (validated per-atendimento in the service, plain FK here for
-- the reason 108's header gives).
ALTER TABLE social_wiring.atendimento_intermediarios
    DROP CONSTRAINT IF EXISTS atendimento_intermediarios_favorecido_fk;
ALTER TABLE social_wiring.atendimento_intermediarios
    ADD CONSTRAINT atendimento_intermediarios_favorecido_fk
    FOREIGN KEY (favorecido_id)
    REFERENCES social_wiring.atendimento_favorecidos (id) ON DELETE SET NULL;

ALTER TABLE social_wiring.atendimento_intermediarios
    DROP CONSTRAINT IF EXISTS atendimento_intermediarios_pessoa_tipo_check;
ALTER TABLE social_wiring.atendimento_intermediarios
    ADD CONSTRAINT atendimento_intermediarios_pessoa_tipo_check
    CHECK (pessoa_tipo IS NULL OR pessoa_tipo IN ('pf', 'pj'));

-- Shape only; check digits are the service's job (see header).
ALTER TABLE social_wiring.atendimento_intermediarios
    DROP CONSTRAINT IF EXISTS atendimento_intermediarios_documento_formato;
ALTER TABLE social_wiring.atendimento_intermediarios
    ADD CONSTRAINT atendimento_intermediarios_documento_formato
    CHECK (
        documento IS NULL
        OR (pessoa_tipo = 'pf' AND documento ~ '^[0-9]{11}$')
        OR (pessoa_tipo = 'pj' AND documento ~ '^[0-9A-Z]{12}[0-9]{2}$')
    );

ALTER TABLE social_wiring.atendimento_intermediarios
    DROP CONSTRAINT IF EXISTS atendimento_intermediarios_representante_cpf_formato;
ALTER TABLE social_wiring.atendimento_intermediarios
    ADD CONSTRAINT atendimento_intermediarios_representante_cpf_formato
    CHECK (representante_cpf IS NULL OR representante_cpf ~ '^[0-9]{11}$');

COMMENT ON COLUMN social_wiring.atendimento_intermediarios.documento IS
    'CPF (pessoa_tipo=pf, 11 digits) or CNPJ (pj, 14 chars, alphanumeric '
    'allowed), normalised, check digits verified by the service. LGPD: '
    'identificação — never logged.';
COMMENT ON COLUMN social_wiring.atendimento_intermediarios.favorecido_id IS
    'Which of THIS deal''s favorecidos receives the intermediary''s '
    'commission (114).';
COMMENT ON COLUMN social_wiring.atendimento_intermediarios.representante_cpf IS
    'CPF of the legal representative signing for a PJ intermediary, '
    'normalised. LGPD: identificação — never logged.';

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_intermediarios_favorecido
    ON social_wiring.atendimento_intermediarios (org_id, favorecido_id)
    WHERE favorecido_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 5. atendimento_contratos — signature date + pendências deadline override
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.atendimento_contratos
    ADD COLUMN IF NOT EXISTS assinatura_data       DATE,
    ADD COLUMN IF NOT EXISTS prazo_pendencias_dias INTEGER;

ALTER TABLE social_wiring.atendimento_contratos
    DROP CONSTRAINT IF EXISTS atendimento_contratos_prazo_pendencias_positivo;
ALTER TABLE social_wiring.atendimento_contratos
    ADD CONSTRAINT atendimento_contratos_prazo_pendencias_positivo
    CHECK (prazo_pendencias_dias IS NULL OR prazo_pendencias_dias > 0);

COMMENT ON COLUMN social_wiring.atendimento_contratos.assinatura_data IS
    'Date the contract was / will be signed (114).';
COMMENT ON COLUMN social_wiring.atendimento_contratos.prazo_pendencias_dias IS
    'Per-contract override of the office deadline to resolve pendências. '
    'NULL = office default (contrato_gerador.politica.prazo_pendencias_dias, '
    '10). > 0 when set (114).';
