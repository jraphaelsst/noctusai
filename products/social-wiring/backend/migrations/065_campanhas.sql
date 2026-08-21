-- ============================================================================
-- Migration 065 -- social_wiring: campanhas, anchored on imovel_registry
--
-- SCOPE: deliberately small. The user's instruction on 2026-08-20 was
-- "let's keep it simple for later refinement" — the full
-- campanhas × imoveis × leads × usuarios × corretores × $$ model is
-- explicitly deferred. What ships here is the spine plus the ONE surface
-- they asked for by name: a "solicitar campanha" button on every imóvel.
--
-- WHY NOT A FIFTH CAMPAIGN TABLE
-- ------------------------------
-- Four campaign-shaped surfaces already exist and each is the truth of ONE
-- channel:
--   ads_objects   401 rows  Meta campaign/adset/ad hierarchy (live)
--   campaigns       0 rows  e-mail marketing sends
--   mc_posts        6 rows  organic social posts
--   lead_campanhas  0 rows  per-portal spend + CPC/CPL, built for T5
--
-- `campanhas` is NOT a fifth. It is the business-level thing that spans
-- them — "Lançamento Residencial X, set/2026" — and `campanha_veiculacoes`
-- LINKS to the channel rows rather than copying them. Each channel keeps
-- owning its own data.
--
-- `lead_campanhas` is EXTENDED, not superseded (user decision D2): it has
-- the right shape already (investimento, impressoes, cliques, cpc, cpl per
-- origem + período) and zero rows, so it gains a nullable `campanha_id`
-- and becomes the cost ledger. A new table with the same shape would be
-- exactly the fork the recurrence rule forbids.
--
-- AD-FIRST, ENTERED THROUGH THE IMÓVEL (user decision D3)
-- -------------------------------------------------------
-- The strong data link is `campanha_veiculacoes.imovel_ref_id` — a single
-- ad is about a specific imóvel. `campanha_imoveis` is the weaker roster
-- view. Those are not in tension with "contained inside properties": the
-- DATA is ad-first, the NAVIGATION starts at the imóvel.
--
-- EVERYTHING POINTS AT imovel_registry, NEVER AT imoveis
-- -----------------------------------------------------
-- `imoveis` holds only the ACTIVE catalog. A campaign outlives the listing
-- it promoted — that is the normal case, not the edge case, since the
-- imóvel selling is the campaign SUCCEEDING. An FK to `imoveis` would
-- delete the campaign's subject at the moment it worked.
--
-- PREREQUISITE: 063_imovel_registry.sql, 043_lead_campanhas_vendas.sql,
--               046_clients_to_marcas.sql.
-- Forward-only + idempotent.
-- ============================================================================

SET search_path = social_wiring, public;

-- ── campanhas ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.campanhas (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID        NOT NULL,
    marca_id      UUID        REFERENCES social_wiring.marcas (id) ON DELETE SET NULL,

    nome          TEXT        NOT NULL,
    objetivo      TEXT        NOT NULL DEFAULT 'venda',
    status        TEXT        NOT NULL DEFAULT 'rascunho',

    data_inicio   DATE,
    data_fim      DATE,
    -- NULL means "not budgeted yet", which is different from zero. Same
    -- rule 040 applied to valores: 0 would be a real, and wrong, number.
    orcamento_previsto NUMERIC(14, 2),
    CONSTRAINT campanhas_orcamento_positivo
        CHECK (orcamento_previsto IS NULL OR orcamento_previsto > 0),
    -- A campaign that ends before it starts is a data-entry slip, not a
    -- state the UI should have to render.
    CONSTRAINT campanhas_periodo_coerente
        CHECK (data_fim IS NULL OR data_inicio IS NULL OR data_fim >= data_inicio),

    observacoes   TEXT,
    created_by    UUID,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT campanhas_objetivo_valido CHECK (
        objetivo IN ('venda', 'locacao', 'lancamento', 'marca')
    ),
    CONSTRAINT campanhas_status_valido CHECK (
        status IN ('rascunho', 'ativa', 'pausada', 'encerrada')
    )
);

-- ── campanha_imoveis — the roster ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.campanha_imoveis (
    campanha_id   UUID        NOT NULL REFERENCES social_wiring.campanhas (id) ON DELETE CASCADE,
    imovel_ref_id UUID        NOT NULL REFERENCES social_wiring.imovel_registry (id) ON DELETE RESTRICT,
    org_id        UUID        NOT NULL,
    papel         TEXT        NOT NULL DEFAULT 'destaque',
    adicionado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (campanha_id, imovel_ref_id),
    CONSTRAINT campanha_imoveis_papel_valido CHECK (papel IN ('destaque', 'apoio'))
);

-- ── campanha_veiculacoes — the link to each channel's own rows ──────────
CREATE TABLE IF NOT EXISTS social_wiring.campanha_veiculacoes (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID        NOT NULL,
    campanha_id   UUID        NOT NULL REFERENCES social_wiring.campanhas (id) ON DELETE CASCADE,
    -- Optional: an ad may be about one imóvel or about the whole campaign.
    imovel_ref_id UUID        REFERENCES social_wiring.imovel_registry (id) ON DELETE RESTRICT,

    canal         TEXT        NOT NULL,
    -- TWO reference columns, not one. `ads_objects` identifies itself by
    -- `object_id TEXT` (Meta's id); `campaigns`, `mc_posts` and
    -- `upload_jobs` use `id UUID`. Forcing one type would put a cast in
    -- every join. Exactly one is set — see the CHECK.
    ref_tabela    TEXT        NOT NULL,
    ref_id        UUID,
    ref_codigo    TEXT,

    criado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT campanha_veiculacoes_canal_valido CHECK (
        canal IN ('meta_ads', 'email', 'organico', 'youtube', 'portal')
    ),
    CONSTRAINT campanha_veiculacoes_uma_referencia CHECK (
        (ref_id IS NOT NULL AND ref_codigo IS NULL)
     OR (ref_id IS NULL AND ref_codigo IS NOT NULL)
    )
);

-- ── campanha_solicitacoes — the "solicitar campanha" button ─────────────
-- The one surface the user named. A corretor looking at an imóvel presses
-- it to say "this one deserves paid traffic". It is a SIGNAL, not a
-- campaign: no budget, no channel, no dates — deliberately, because the
-- person pressing it is not the person who decides those.
--
-- `campanha_id` is the eventual outcome: NULL while pending, set when a
-- request is converted into a real campaign. That makes "which requests
-- did we act on" a query rather than a guess.
CREATE TABLE IF NOT EXISTS social_wiring.campanha_solicitacoes (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID        NOT NULL,
    imovel_ref_id UUID        NOT NULL REFERENCES social_wiring.imovel_registry (id) ON DELETE RESTRICT,
    campanha_id   UUID        REFERENCES social_wiring.campanhas (id) ON DELETE SET NULL,

    status        TEXT        NOT NULL DEFAULT 'pendente',
    justificativa TEXT,
    solicitado_por UUID,
    solicitado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    respondido_em TIMESTAMPTZ,
    resposta      TEXT,

    CONSTRAINT campanha_solicitacoes_status_valido CHECK (
        status IN ('pendente', 'aprovada', 'recusada', 'convertida')
    )
);

-- One PENDING request per imóvel, not one ever. A partial unique index,
-- because the same imóvel legitimately gets requested again next quarter —
-- but two open requests for it are just noise in the queue.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_campanha_solicitacoes_pendente
    ON social_wiring.campanha_solicitacoes (org_id, imovel_ref_id)
    WHERE status = 'pendente';

-- ── lead_campanhas becomes the cost ledger (decision D2) ────────────────
-- Nullable: the per-portal spend rows it was designed for do not belong to
-- any campanha, and must keep working exactly as before.
ALTER TABLE social_wiring.lead_campanhas
    ADD COLUMN IF NOT EXISTS campanha_id UUID
    REFERENCES social_wiring.campanhas (id) ON DELETE SET NULL;

-- ── RLS — mirrors imoveis/leads exactly ─────────────────────────────────
-- `public.current_org_id()` is SECURITY DEFINER. NEVER `auth.jwt()`
-- top-level or `user_metadata` — the first is always-null here, the second
-- is user-editable.
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'campanhas', 'campanha_imoveis', 'campanha_veiculacoes', 'campanha_solicitacoes'
    ] LOOP
        EXECUTE format('ALTER TABLE social_wiring.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS %I ON social_wiring.%I', t || '_select_own_org', t);
        EXECUTE format(
            'CREATE POLICY %I ON social_wiring.%I FOR SELECT TO authenticated '
            'USING (org_id = public.current_org_id())',
            t || '_select_own_org', t);
        EXECUTE format('DROP POLICY IF EXISTS %I ON social_wiring.%I', t || '_service_role', t);
        EXECUTE format(
            'CREATE POLICY %I ON social_wiring.%I FOR ALL TO service_role '
            'USING (true) WITH CHECK (true)',
            t || '_service_role', t);
    END LOOP;
END $$;

CREATE INDEX IF NOT EXISTS idx_sw_campanhas_org_status
    ON social_wiring.campanhas (org_id, status);
CREATE INDEX IF NOT EXISTS idx_sw_campanha_imoveis_imovel
    ON social_wiring.campanha_imoveis (imovel_ref_id);
CREATE INDEX IF NOT EXISTS idx_sw_campanha_veiculacoes_campanha
    ON social_wiring.campanha_veiculacoes (campanha_id);
CREATE INDEX IF NOT EXISTS idx_sw_campanha_veiculacoes_imovel
    ON social_wiring.campanha_veiculacoes (imovel_ref_id)
    WHERE imovel_ref_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sw_campanha_solicitacoes_org_status
    ON social_wiring.campanha_solicitacoes (org_id, status);

CREATE OR REPLACE FUNCTION social_wiring.touch_campanhas_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path TO 'social_wiring', 'public'
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

DROP TRIGGER IF EXISTS trg_campanhas_updated_at ON social_wiring.campanhas;
CREATE TRIGGER trg_campanhas_updated_at
    BEFORE UPDATE ON social_wiring.campanhas
    FOR EACH ROW EXECUTE FUNCTION social_wiring.touch_campanhas_updated_at();

-- ── status_pagina — WITHOUT THIS THE NAV ITEM IS INVISIBLE ──────────────
-- The seed's `filterNavByPageStatus` hides a nav item with no matching
-- row, silently: the route works if typed, the sidebar link never appears.
-- Migrations 018/021/023/039/040 all exist to close this same failure.
-- 'desenvolvimento' until the UI is proven end-to-end in a container.
-- → KB § PATTERNS/frontend/status-pagina-dev-visibility.md
INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('campanhas', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;
