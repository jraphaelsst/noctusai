-- ============================================================================
-- Migration 101 -- social_wiring: permutas (property swapping) + matching
--
-- WHAT THIS IS
-- ------------
-- The storage half of absorbing the legacy Permutas platform. The legacy CODE
-- is not coming (it was reverted off `dev` on 2026-09-06 carrying 100 open
-- HIGH/CRITICAL CVEs); its DATA and its INTENT are, onto the matching engine
-- already built in erp-imobiliario.
--
-- ── The shape, and why it mirrors `erp.ativos` ──────────────────────────────
--
-- The engine (`noctusai_lib.domain.matching`, promoted from erp in this same
-- slice) scores ONE dict against ANOTHER dict, both carrying a `natureza`:
--
--     natureza='imovel'          → a catalog listing whose owner ACCEPTS a swap
--     natureza='permuta_imovel'  → a property BROUGHT as swap currency
--
-- `permuta_ativos` below is that unified row, deliberately shaped like
-- `erp.ativos` so the same scorer reads both products without a per-product
-- adapter dialect. Copying the *shape* is not copying the *code*: the scorer
-- itself lives in the seed lib and both products import it.
--
-- 🔴 THE `imovel` SIDE IS A POINTER, NOT A COPY
-- ----------------------------------------------
-- 219 of the 271 legacy property refs ALREADY exist in `social_wiring.imoveis`
-- as Vista-synced rows with 69 columns — areas, dormitórios, vagas, lat/long,
-- características. The legacy `imovel_imovel` had NINE columns and no area, no
-- rooms, no photos. Duplicating the property here would fork the catalog
-- against its own sync and leave two answers to "how big is ONE9265".
--
-- So a `natureza='imovel'` row carries `imovel_codigo` and almost nothing
-- else; the adapter joins `imoveis` at read time. The denormalised address and
-- spec columns exist for the OTHER side — a `permuta_imovel` a client brings
-- is frequently NOT in our catalog (52 legacy refs are not, and never will be)
-- and has nowhere else to live.
--
-- 🔴 `permuta_interesses` IS A CHILD TABLE, NOT A jsonb COLUMN
-- -------------------------------------------------------------
-- erp keeps interests in an `interesses` jsonb. Here they are rows, because
-- the legacy data proves the cardinality is real: `permuta_imovel_id=13` has
-- TWO interests (apartamento OR casa em condomínio, same value ceiling), and
-- 135 legacy interest rows spread over 127 distinct properties. A jsonb array
-- would hold that, but it cannot be indexed on `valor_maximo` for the
-- candidate-narrowing query the matcher wants, and it cannot carry its own
-- provenance back to the legacy row. The adapter projects these rows INTO the
-- `interesses` list shape the scorer expects, so the engine never sees the
-- difference.
--
-- 🔴 `percentual_min`/`percentual_max` — A COLUMN THE LEGACY APP NEVER HAD
-- -------------------------------------------------------------------------
-- The single most common thing written in these free-text notes is a
-- PROPORTION, not a price: "Estuda permuta de 30% a 50% do valor total",
-- "Avalia permuta até 30% ou 40% do valor", "Permuta de 80% do valor de
-- venda", "que aceite 100 por cento da permuta". The legacy schema had
-- nowhere to put it, so every one of those sat in prose and no filter could
-- read it. A swap where the counterparty covers 30% and one where they cover
-- 100% are completely different deals; conflating them is most of why the
-- legacy funnel shows 74 rejected against 8 surviving.
--
-- NULLABLE and unconstrained beyond 0..100 — these are extracted from prose,
-- and a wrong guess must be correctable, not enforced.
--
-- ── The embedding columns, and the erp defect they close ────────────────────
--
-- `embedding` (what this ativo IS) and `embedding_interesses` (what it WANTS)
-- are both here from the start, because the scorer's bilateral similarity
-- needs BOTH and erp shipped only one:
--
--   * `erp.ativos` has `embedding` but NOT `embedding_interesses` — migration
--     `012_bilateral_embeddings.sql` was written and never applied, and
--   * `_MATCHING_FIELDS` in erp's router does not SELECT it either.
--
-- Two independent reasons `_calcular_bilateral_similarity` returns 0.0 on
-- every pair, so erp's matching has ALWAYS been pure rule-based despite the
-- composite-score code being right there. This migration does not fix erp
-- (that is erp's migration to apply); it makes sure social-wiring does not
-- inherit the same hole on day one.
--
-- ── lead_corretores gains an identity ──────────────────────────────────────
--
-- 🔴 EXTENDED, NOT REPLACED BY A NEW `corretores` TABLE.
-- `social_wiring.lead_corretores` already IS the per-org broker registry —
-- 25 rows, with `lead_corretor_aliases` resolving the name variants that
-- arrive on portal leads. A second table would mean two answers to "who is
-- Cindy", and the alias resolver would keep pointing at the old one.
--
-- What it lacked is IDENTITY: which noc account is this person, which Vista
-- address attaches their listings. Those columns land here.
--
-- NOC-REMEDIATE[naming]: the `lead_` prefix no longer describes this table —
-- it is the org's broker registry, and lead attribution is one consumer of
-- it. Renaming touches the leads module, its aliases table, `vw_lead_corretor_
-- contagem` and the analytics RPCs, so it is deliberately NOT bundled into a
-- migration about permutas. Batch it with the next leads-module change.
--
-- FORWARD-ONLY, IDEMPOTENT (safe to re-run; every step is existence-guarded).
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. lead_corretores gains the identity columns
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.lead_corretores
    -- The noc account this broker signs in as. NULLABLE: a broker exists in
    -- this registry the moment a lead names them, which is long before (and
    -- sometimes instead of) them getting a login.
    ADD COLUMN IF NOT EXISTS user_id       UUID,
    -- Their login address (…@one.com.br).
    ADD COLUMN IF NOT EXISTS email_login   TEXT,
    -- 🔴 THE JOIN KEY INTO THE CATALOG, and the reason this is a separate
    -- column from `email_login`. `imoveis.corretores` is a Vista-sourced jsonb
    -- array whose elements carry {nome, email, codigo}, and that email is the
    -- agency's own domain (…@oneconsultoriaimobiliaria.com.br). It is NOT the
    -- address they log in with, and collapsing the two would detach every
    -- broker from their listings the day the login domain changes.
    ADD COLUMN IF NOT EXISTS email_vista   TEXT,
    -- `imoveis.corretores[].codigo` — Vista's own broker id, a second and more
    -- stable attachment key than the address.
    ADD COLUMN IF NOT EXISTS codigo_vista  TEXT,
    ADD COLUMN IF NOT EXISTS telefone      TEXT,
    ADD COLUMN IF NOT EXISTS creci         TEXT,
    -- Provenance: `permutas.corretor_corretor.id` this row was reconciled
    -- against, so a re-run of the backfill is idempotent and a disagreement
    -- between the two systems stays traceable.
    ADD COLUMN IF NOT EXISTS permuta_origem_id INTEGER;

COMMENT ON COLUMN social_wiring.lead_corretores.user_id IS
    'The noctus_users/auth.users id this broker signs in as. NULLABLE — a '
    'broker is registered here as soon as a lead names them, which precedes '
    '(and may never reach) an account.';
COMMENT ON COLUMN social_wiring.lead_corretores.email_vista IS
    'The agency-domain address that appears in imoveis.corretores[].email. '
    'This is what attaches a broker to their listings — deliberately NOT the '
    'same column as email_login. See the 101 header.';

-- One account per broker, one broker per account. Partial so the many rows
-- with no login do not collide with each other on NULL.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_lead_corretores_user
    ON social_wiring.lead_corretores (user_id)
    WHERE user_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_lead_corretores_org_email_vista
    ON social_wiring.lead_corretores (org_id, lower(trim(email_vista)))
    WHERE email_vista IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sw_lead_corretores_org_email_login
    ON social_wiring.lead_corretores (org_id, lower(trim(email_login)))
    WHERE email_login IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 2. permuta_ativos -- the unified matchable row
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.permuta_ativos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,

    -- 'imovel'          → a catalog listing whose owner accepts a swap
    -- 'permuta_imovel'  → a property brought as swap currency
    --
    -- CHECKed rather than an enum: the legacy app also modelled
    -- 'permuta_automovel', both of whose tables came across with ZERO rows.
    -- Adding a value to a CHECK is one migration; adding one to a TYPE that
    -- other objects depend on is several. The value is listed so the intent
    -- survives, and the scorer already handles it.
    natureza       TEXT NOT NULL
        CHECK (natureza IN ('imovel', 'permuta_imovel', 'permuta_automovel')),

    -- 🔴 THE POINTER. Set on the `imovel` side; the adapter joins `imoveis`
    -- for every spec. NOT a foreign key: `imoveis` is keyed (org_id, codigo)
    -- and Vista's sync deletes and reinserts rows, so an FK would either
    -- refuse the sync or cascade a swap intent away with a re-listing. The
    -- adapter reports an unresolvable codigo rather than dropping it.
    imovel_codigo  TEXT,

    -- Human handle. Legacy carried PM0001..PM0014 on the permuta side.
    codigo         TEXT,

    corretor_id    UUID REFERENCES social_wiring.lead_corretores(id) ON DELETE SET NULL,

    -- The owner. Denormalised on purpose: the legacy `proprietario` rows are
    -- NOT `clientes` in this product, and promoting 256 of them into the
    -- person layer is a merge decision (dedupe against 1200 existing clientes)
    -- that does not belong in a swap-matching migration. NOC-REMEDIATE[merge]:
    -- promote these to `clientes` once the merge path is decided.
    proprietario_nome     TEXT,
    proprietario_telefone TEXT,
    proprietario_email    TEXT,

    -- ── Profile (what this ativo IS) — populated for `permuta_imovel`, left
    -- NULL for `imovel` where `imoveis` is the source of truth. ──
    tipo_imovel    TEXT,
    cep            TEXT,
    logradouro     TEXT,
    numero         TEXT,
    complemento    TEXT,
    bairro         TEXT,
    cidade         TEXT,
    uf             TEXT,
    zona           TEXT,
    condominio_nome TEXT,
    valor          NUMERIC,
    area_total     NUMERIC,
    area_privativa NUMERIC,
    quartos        INTEGER,
    suites         INTEGER,
    vagas          INTEGER,

    -- ── Search criteria (what this ativo WANTS), when it is expressed as a
    -- single band rather than as `permuta_interesses` rows. ──
    faixa_preco_min NUMERIC,
    faixa_preco_max NUMERIC,
    regiao_preferida TEXT[] NOT NULL DEFAULT '{}',
    aceita_completar_diferenca BOOLEAN,
    limite_complemento NUMERIC,
    -- See the header: the proportion of the deal the swap is meant to cover.
    percentual_min INTEGER CHECK (percentual_min IS NULL OR percentual_min BETWEEN 0 AND 100),
    percentual_max INTEGER CHECK (percentual_max IS NULL OR percentual_max BETWEEN 0 AND 100),

    -- The prose. 🔴 THIS IS THE HIGH-VALUE COLUMN, not a comment field: in the
    -- legacy data the structured criteria are near-empty (cidade filled on 0
    -- of 135 rows) while 95 of 135 carry a sentence, and the sentences hold
    -- the actual constraints — "casa sem escada", "rua do condomínio sem
    -- ladeira", "quintal amplo", "garagem coberta". It is what gets embedded.
    observacoes    TEXT,
    -- The text actually sent to the embedding model for `embedding_interesses`,
    -- kept so a stale vector can be detected without re-deriving it.
    interesses_descricao TEXT,

    status         TEXT NOT NULL DEFAULT 'ativo'
        CHECK (status IN ('ativo', 'pausado', 'concluido', 'arquivado')),

    -- Provenance back to the legacy app.
    origem         TEXT NOT NULL DEFAULT 'manual'
        CHECK (origem IN ('manual', 'permutas_legacy', 'vista')),
    origem_tabela  TEXT,
    origem_id      INTEGER,

    -- Bilateral vectors. See the header for the erp hole this avoids.
    embedding             extensions.vector(1536),
    embedding_interesses  extensions.vector(1536),
    embedding_atualizado_em TIMESTAMPTZ,

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_por    UUID,
    updated_at     TIMESTAMPTZ,
    updated_por    UUID,

    -- An `imovel` row without its pointer is unresolvable — it has no specs of
    -- its own and no catalog row to borrow them from, so it would silently
    -- score as an empty property against everything.
    CONSTRAINT permuta_ativos_imovel_tem_codigo
        CHECK (natureza <> 'imovel' OR imovel_codigo IS NOT NULL)
);

COMMENT ON TABLE social_wiring.permuta_ativos IS
    'Unified matchable row for property swapping — shaped like erp.ativos so '
    'the shared scorer in noctusai_lib.domain.matching reads both products. '
    'natureza=imovel is a POINTER at social_wiring.imoveis (the adapter joins '
    'it); natureza=permuta_imovel carries its own snapshot because a brought '
    'property is frequently not in the catalog. See the 101 header.';

-- One legacy row lands once, however many times the backfill runs.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_permuta_ativos_origem
    ON social_wiring.permuta_ativos (org_id, origem, origem_tabela, origem_id)
    WHERE origem_id IS NOT NULL;

-- A catalog listing declares its swap intent once.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_permuta_ativos_imovel
    ON social_wiring.permuta_ativos (org_id, imovel_codigo)
    WHERE natureza = 'imovel';

CREATE INDEX IF NOT EXISTS idx_sw_permuta_ativos_org_natureza_status
    ON social_wiring.permuta_ativos (org_id, natureza, status);
CREATE INDEX IF NOT EXISTS idx_sw_permuta_ativos_org_corretor
    ON social_wiring.permuta_ativos (org_id, corretor_id)
    WHERE corretor_id IS NOT NULL;
-- The candidate-narrowing predicate the matcher runs before scoring.
CREATE INDEX IF NOT EXISTS idx_sw_permuta_ativos_valor
    ON social_wiring.permuta_ativos (org_id, natureza, valor)
    WHERE status = 'ativo';

-- ----------------------------------------------------------------------------
-- 3. permuta_interesses -- what an ativo will accept
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.permuta_interesses (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    -- CASCADE: an interest has no meaning without the ativo that holds it.
    ativo_id       UUID NOT NULL
        REFERENCES social_wiring.permuta_ativos(id) ON DELETE CASCADE,

    -- 'imovel' | 'automovel' — the scorer branches on this, and the legacy app
    -- modelled both even though the automóvel tables arrived empty.
    tipo           TEXT NOT NULL DEFAULT 'imovel'
        CHECK (tipo IN ('imovel', 'automovel')),

    tipo_imovel    TEXT,
    zona           TEXT,
    cidade         TEXT,
    bairro         TEXT,
    valor_minimo   NUMERIC,
    valor_maximo   NUMERIC,
    percentual_min INTEGER CHECK (percentual_min IS NULL OR percentual_min BETWEEN 0 AND 100),
    percentual_max INTEGER CHECK (percentual_max IS NULL OR percentual_max BETWEEN 0 AND 100),

    -- Automóvel criteria — present so the branch the scorer already carries
    -- has somewhere to read from the day the first one is registered.
    marca          TEXT,
    modelo         TEXT,
    ano_min        INTEGER,
    ano_max        INTEGER,

    observacoes    TEXT,

    origem         TEXT NOT NULL DEFAULT 'manual'
        CHECK (origem IN ('manual', 'permutas_legacy')),
    origem_tabela  TEXT,
    origem_id      INTEGER,

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ
);

COMMENT ON TABLE social_wiring.permuta_interesses IS
    'What an ativo will accept in exchange — rows, not a jsonb array, because '
    'the cardinality is real (a legacy offer wanting apartamento OR casa em '
    'condomínio) and because each row carries its own provenance. The adapter '
    'projects these into the `interesses` list the shared scorer expects.';

CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_permuta_interesses_origem
    ON social_wiring.permuta_interesses (org_id, origem, origem_tabela, origem_id)
    WHERE origem_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sw_permuta_interesses_ativo
    ON social_wiring.permuta_interesses (ativo_id);

-- ----------------------------------------------------------------------------
-- 4. permuta_matches -- the scored pairs
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.permuta_matches (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,

    -- Origem is always the `imovel` side, destino always the `permuta_*` side
    -- — the same orientation the shared scorer emits, so a pair has exactly
    -- one representation and the unique index below actually means something.
    ativo_origem_id  UUID NOT NULL
        REFERENCES social_wiring.permuta_ativos(id) ON DELETE CASCADE,
    ativo_destino_id UUID NOT NULL
        REFERENCES social_wiring.permuta_ativos(id) ON DELETE CASCADE,

    score          NUMERIC NOT NULL,
    justificativa  TEXT NOT NULL DEFAULT '',
    -- Raw sub-scores, in the scorer's own units (região/30, preço/25, …).
    detalhes       JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- The same sub-scores normalised to 0..100, which is what the UI plots.
    -- Both are stored: the raw numbers are what a scoring change is diffed
    -- against, the normalised ones are what a person reads.
    score_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- True when BOTH directions cleared the similarity threshold. The legacy
    -- app carried this flag too, and all 82 of its matches set it.
    is_bilateral   BOOLEAN NOT NULL DEFAULT false,

    -- 🔴 THE FUNNEL, AND WHY `sugerido` IS NOT `pendente`.
    -- erp calls the initial state 'pendente', which reads as "someone must
    -- act on this". These rows are machine-generated and most of them will
    -- never be looked at — the legacy funnel closed 74 of 82 as rejeitado.
    -- 'sugerido' says what the row actually is: an offer from the engine, not
    -- a task. `avaliacao` onward are the states a PERSON moved it to.
    etapa          TEXT NOT NULL DEFAULT 'sugerido'
        CHECK (etapa IN ('sugerido', 'avaliacao', 'negociacao', 'fechado', 'rejeitado')),
    observacoes    TEXT NOT NULL DEFAULT '',

    origem         TEXT NOT NULL DEFAULT 'motor'
        CHECK (origem IN ('motor', 'permutas_legacy', 'manual')),
    origem_id      INTEGER,

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ,
    -- Who moved it off `sugerido`, and when. NULL while the engine owns it.
    decidido_por   UUID,
    decidido_em    TIMESTAMPTZ,

    -- A pair matched against itself is a bug in the caller, not a match.
    CONSTRAINT permuta_matches_nao_reflexivo
        CHECK (ativo_origem_id <> ativo_destino_id)
);

COMMENT ON TABLE social_wiring.permuta_matches IS
    'Scored swap pairs. One row per (origem, destino) — a re-run UPSERTs the '
    'score and NEVER overwrites an etapa a person has moved off `sugerido`, '
    'the same protection erp.upsert_matches applies.';
COMMENT ON COLUMN social_wiring.permuta_matches.etapa IS
    'sugerido = the engine proposed it and nobody has looked. Everything else '
    'is a human decision. A re-run may only rewrite rows still at sugerido.';

-- The pair is the identity — this is what makes the re-run an UPSERT rather
-- than a duplicate factory.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_permuta_matches_par
    ON social_wiring.permuta_matches (org_id, ativo_origem_id, ativo_destino_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_permuta_matches_origem_legacy
    ON social_wiring.permuta_matches (org_id, origem, origem_id)
    WHERE origem_id IS NOT NULL;

-- The page's default read: this org's matches, best first, optionally by stage.
CREATE INDEX IF NOT EXISTS idx_sw_permuta_matches_org_etapa_score
    ON social_wiring.permuta_matches (org_id, etapa, score DESC);
CREATE INDEX IF NOT EXISTS idx_sw_permuta_matches_destino
    ON social_wiring.permuta_matches (org_id, ativo_destino_id);

-- ----------------------------------------------------------------------------
-- 5. RLS
-- ----------------------------------------------------------------------------
-- All three tables take the `agentes_financeiros` shape (migration 100): SELECT
-- and write both scoped to `current_org_id()` for `authenticated`, plus the
-- service role for the engine.
--
-- 🔴 A WRITE POLICY FOR `authenticated` IS CORRECT HERE, and it is a narrower
-- claim than it looks. The MATCHES are written by the engine under the service
-- role — but the ETAPA is moved by a person clicking "descartar" on the page,
-- and the ATIVOS are registered by a broker typing in what a client brought.
-- Those are user writes and RLS, not application code, is what should scope
-- them. See migration 100's note for the same call.
DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['permuta_ativos', 'permuta_interesses', 'permuta_matches']
    LOOP
        EXECUTE format('ALTER TABLE social_wiring.%I ENABLE ROW LEVEL SECURITY', t);

        EXECUTE format('DROP POLICY IF EXISTS %I ON social_wiring.%I',
                       t || '_select_own_org', t);
        EXECUTE format(
            'CREATE POLICY %I ON social_wiring.%I FOR SELECT TO authenticated '
            'USING (org_id = public.current_org_id())',
            t || '_select_own_org', t);

        EXECUTE format('DROP POLICY IF EXISTS %I ON social_wiring.%I',
                       t || '_write_own_org', t);
        EXECUTE format(
            'CREATE POLICY %I ON social_wiring.%I FOR ALL TO authenticated '
            'USING (org_id = public.current_org_id()) '
            'WITH CHECK (org_id = public.current_org_id())',
            t || '_write_own_org', t);

        EXECUTE format('DROP POLICY IF EXISTS %I ON social_wiring.%I',
                       t || '_service_role', t);
        EXECUTE format(
            'CREATE POLICY %I ON social_wiring.%I FOR ALL TO service_role '
            'USING (true) WITH CHECK (true)',
            t || '_service_role', t);
    END LOOP;
END
$$;

-- ----------------------------------------------------------------------------
-- 6. updated_at triggers
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION social_wiring.set_updated_at_permutas()
  RETURNS TRIGGER
  LANGUAGE plpgsql
  SET search_path TO 'social_wiring', 'public'
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS set_permuta_ativos_updated ON social_wiring.permuta_ativos;
CREATE TRIGGER set_permuta_ativos_updated
    BEFORE UPDATE ON social_wiring.permuta_ativos
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_permutas();

DROP TRIGGER IF EXISTS set_permuta_interesses_updated ON social_wiring.permuta_interesses;
CREATE TRIGGER set_permuta_interesses_updated
    BEFORE UPDATE ON social_wiring.permuta_interesses
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_permutas();

DROP TRIGGER IF EXISTS set_permuta_matches_updated ON social_wiring.permuta_matches;
CREATE TRIGGER set_permuta_matches_updated
    BEFORE UPDATE ON social_wiring.permuta_matches
    FOR EACH ROW EXECUTE FUNCTION social_wiring.set_updated_at_permutas();

-- ----------------------------------------------------------------------------
-- 7. Nav gating for the new page
-- ----------------------------------------------------------------------------
-- 🔴 'producao', not 'desenvolvimento'. A page seeded 'desenvolvimento' is
-- returned to NOBODY by the read policy, so the dev/owner branch never runs
-- and the page is invisible even to its author — the failure
-- `KB § PATTERNS/frontend/status-pagina-dev-visibility.md` records.
INSERT INTO social_wiring.status_pagina (nome_pagina, status)
VALUES ('permutas', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
