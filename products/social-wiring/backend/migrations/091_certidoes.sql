-- ============================================================================
-- Migration 091 · social_wiring: Certidões Negativas
--
-- WHAT
-- ----
-- The automated emission + AI-analysis workflow for negative certificates
-- (CND Federal, TRF3, TRT2, TST, TJSP, CENPROT, Fazenda SP, Dívida Ativa SP),
-- ported from `products/erp-imobiliario/backend/migrations/007` + `010`
-- (`na_fila` status) + `013` (`api_requested_at`) as the ERP product is
-- retired. Two tables: one CONSULTA per person/company, one RESULTADO per
-- certificate type within it (10 today, see `CERTIDOES_CONFIG`).
--
-- 🔴 WHY ORG-SCOPED AND NOT CREATOR-SCOPED (the one real divergence from ERP)
-- ---------------------------------------------------------------------------
-- ERP's 007 scoped every policy to `created_by = auth.uid()`: the person who
-- asked for the certidão was the only one who could read it back. That is the
-- wrong shape for this product, and arguably was for that one.
--
-- A certidão negativa is DUE-DILIGENCE EVIDENCE about a counterparty in a
-- transaction the whole org is working. The person who clicked "emitir" is
-- rarely the person who reads the result — a corretor requests it, the
-- administrativo files it, whoever closes the deal has to be able to produce
-- it months later. Creator-scoping means a certidão becomes invisible the day
-- that employee leaves, while the row (and the LGPD obligation attached to it)
-- stays. It also makes the TJSP cooldown queue unreadable: the queue is a
-- per-ORG rate limit (one InfoSimples email per org), so a queue only its
-- individual creators can see cannot be shown as the shared waiting line it
-- actually is.
--
-- So: `org_id = public.current_org_id()`, matching every other table in this
-- schema (`credentials`, `imovel_documentos`, the pipeline tables). `org_id`
-- is `NOT NULL` here where ERP left it nullable — a nullable org column under
-- an org-scoped policy is a row nobody can read, which is a silent data-loss
-- shape, not a permissive one. `created_by` is KEPT: who asked is still worth
-- recording, it simply is not the access-control boundary.
--
-- Reads are `TO authenticated` (SELECT only); every write goes through the
-- service-role client, because the whole pipeline is a background task that
-- outlives the request that started it (see `app/modules/certidoes/service.py`).
-- That is the same split `075_imovel_dados_cartorio.sql` uses.
--
-- 🔴 WHY THE NAV ROW IS 'producao' AND NOT 'desenvolvimento'
-- ----------------------------------------------------------
-- `status_pagina`'s only read policy is `USING (status = 'producao')` — a
-- 'desenvolvimento' row is returned to NOBODY, including the developer who
-- wrote it, so the page is invisible to every branch of the frontend rather
-- than dev-only. This surface ships to a live user, so it is 'producao'.
-- → KB § PATTERNS/frontend/status-pagina-dev-visibility.md
--
-- FORWARD-ONLY, IDEMPOTENT.
-- 🔴 MIGRATION FILE ONLY — apply after the tech-lead has stated the row counts
-- and the user has given an explicit go-ahead.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. certidao_consultas — one request, for one CPF/CNPJ
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.certidao_consultas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    created_by      UUID NOT NULL,
    tipo_documento  TEXT NOT NULL CHECK (tipo_documento IN ('cpf', 'cnpj')),
    documento       TEXT NOT NULL,
    nome            TEXT NOT NULL,
    -- `data_nascimento` is TEXT, not DATE, deliberately: it is passed straight
    -- through to InfoSimples as the `birthdate` parameter in the exact string
    -- form the endpoints expect. Parsing it to a DATE here would mean
    -- re-formatting it on the way out, i.e. one more place to get it wrong.
    data_nascimento TEXT,
    genero          TEXT CHECK (genero IS NULL OR genero IN ('M', 'F')),
    rg              TEXT,
    nome_mae        TEXT,
    nome_pai        TEXT,
    status          TEXT NOT NULL DEFAULT 'pendente'
                    CHECK (status IN ('pendente', 'processando', 'concluida', 'erro')),
    total_certidoes INT NOT NULL DEFAULT 0,
    concluidas      INT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- 2. certidao_resultados — one certificate type inside a consulta
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.certidao_resultados (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consulta_id      UUID NOT NULL
                     REFERENCES social_wiring.certidao_consultas(id) ON DELETE CASCADE,
    org_id           UUID NOT NULL,
    tipo             TEXT NOT NULL,
    nome_display     TEXT NOT NULL,
    ordem            INT NOT NULL DEFAULT 0,
    -- 'na_fila' is the TJSP cooldown queue (ERP migration 010). TJSP rate-limits
    -- to one request per 30 minutes per email; firing early RESETS their counter,
    -- so a queued item is a first-class state, not a retry.
    status           TEXT NOT NULL DEFAULT 'pendente'
                     CHECK (status IN ('pendente', 'processando', 'na_fila', 'sucesso', 'erro')),
    analise_ia       TEXT,
    -- Either an `https://` URL from the source (when we could not persist the
    -- file) or a KEY in the `social-wiring-documentos` bucket under the
    -- `{org_id}/certidoes/…` prefix (the normal case). The download routes
    -- branch on the scheme; see `app/modules/certidoes/service.py`.
    arquivo_url      TEXT,
    arquivo_nome     TEXT,
    api_response     JSONB,
    erro_mensagem    TEXT,
    -- 🔴 ERP migration 013. When the InfoSimples call was actually made — set
    -- immediately before the request and NEVER cleared on reprocessing, which
    -- is what makes the TJSP cooldown survive an `erro` → `na_fila` reset.
    -- `updated_at` cannot serve this purpose: it moves on every status change.
    api_requested_at TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- 3. Indexes
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_sw_certidao_consultas_org_created
    ON social_wiring.certidao_consultas (org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sw_certidao_consultas_status
    ON social_wiring.certidao_consultas (org_id, status);
CREATE INDEX IF NOT EXISTS idx_sw_certidao_consultas_documento
    ON social_wiring.certidao_consultas (org_id, documento);

CREATE INDEX IF NOT EXISTS idx_sw_certidao_resultados_consulta
    ON social_wiring.certidao_resultados (consulta_id, ordem);
CREATE INDEX IF NOT EXISTS idx_sw_certidao_resultados_org
    ON social_wiring.certidao_resultados (org_id);

-- The two hot sweeps: the stale-`processando` recovery, and the TJSP queue.
CREATE INDEX IF NOT EXISTS idx_sw_certidao_resultados_processando
    ON social_wiring.certidao_resultados (status)
    WHERE status = 'processando';
CREATE INDEX IF NOT EXISTS idx_sw_certidao_resultados_fila_tjsp
    ON social_wiring.certidao_resultados (org_id, created_at)
    WHERE tipo = 'tjsp' AND status = 'na_fila';
-- The cooldown read: most recent TJSP `api_requested_at` for an org.
CREATE INDEX IF NOT EXISTS idx_sw_certidao_resultados_tjsp_cooldown
    ON social_wiring.certidao_resultados (org_id, created_at DESC)
    WHERE tipo = 'tjsp';

-- ----------------------------------------------------------------------------
-- 4. updated_at
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION social_wiring.set_updated_at_certidoes()
  RETURNS TRIGGER
  LANGUAGE plpgsql
  SET search_path TO 'social_wiring', 'public'
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS set_certidao_consultas_updated
    ON social_wiring.certidao_consultas;
CREATE TRIGGER set_certidao_consultas_updated
    BEFORE UPDATE ON social_wiring.certidao_consultas
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_certidoes();

DROP TRIGGER IF EXISTS set_certidao_resultados_updated
    ON social_wiring.certidao_resultados;
CREATE TRIGGER set_certidao_resultados_updated
    BEFORE UPDATE ON social_wiring.certidao_resultados
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_certidoes();

-- ----------------------------------------------------------------------------
-- 5. RLS — org-scoped read, service-role write. See the header for WHY org.
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.certidao_consultas ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_wiring.certidao_resultados ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "certidao_consultas_select_own_org"
    ON social_wiring.certidao_consultas;
CREATE POLICY "certidao_consultas_select_own_org"
    ON social_wiring.certidao_consultas
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "certidao_consultas_service_role"
    ON social_wiring.certidao_consultas;
CREATE POLICY "certidao_consultas_service_role"
    ON social_wiring.certidao_consultas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "certidao_resultados_select_own_org"
    ON social_wiring.certidao_resultados;
CREATE POLICY "certidao_resultados_select_own_org"
    ON social_wiring.certidao_resultados
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "certidao_resultados_service_role"
    ON social_wiring.certidao_resultados;
CREATE POLICY "certidao_resultados_service_role"
    ON social_wiring.certidao_resultados
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 6. Nav row — 'producao', see the header for why not 'desenvolvimento'.
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.status_pagina (nome_pagina, status)
VALUES ('certidoes', 'producao')
ON CONFLICT DO NOTHING;
