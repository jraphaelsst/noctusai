-- ============================================================================
-- Migration 251 — social_wiring.favorecidos: the ORG-LEVEL payee registry.
--
-- WHY (owner request): a favorecido (who a parcela's money is owed to) was
-- typed afresh on every card (`atendimento_favorecidos`, 108). The owner wants
-- the person registered ONCE per org, and cards only SELECT from the registry.
--
-- REFERENCE, NOT SNAPSHOT. `atendimento_favorecidos.favorecido_id` points at
-- the registry row; the card reader (negociacao_estruturada_service) overlays
-- the registry's CURRENT values on a linked card row, so a corrected bank
-- account reaches every OPEN card at once. A generated contract version already
-- persists its rendered text, so history is not rewritten. The card row keeps
-- its own columns: they are the fallback for an unlinked (legacy / hand-typed)
-- favorecido and the copy a card keeps if the registry row is ever
-- hard-removed (ON DELETE SET NULL).
--
-- 🔴 FINANCIAL PII + PERSONAL DATA (LGPD). CPF/CNPJ, bank account, PIX key of a
-- named person. RLS org-scoped like every SW table; values are never logged;
-- list responses mask the document / account / pix and the full values are
-- served only to a write role (favorecidos_service). DELETE is a soft
-- `ativo=false` — cards already referencing the row keep working.
--
-- RLS mirrors `atendimento_favorecidos` (108 + 211): SELECT for `authenticated`
-- scoped by `current_org_id_for('social_wiring')` (org-picker aware); every
-- write is service_role (the backend client), so the API's role gate is the one
-- writer. Idempotent (IF NOT EXISTS / DROP POLICY IF EXISTS) and replay-safe;
-- the backfill only touches UNLINKED card rows, so a second run is a no-op.
-- ============================================================================
SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.favorecidos (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,

    nome         TEXT NOT NULL CHECK (length(trim(nome)) > 0),
    -- NULL only for rows backfilled from cards whose document was never typed
    -- (we do not invent a type); the API requires it on create.
    tipo_pessoa  TEXT CHECK (tipo_pessoa IN ('PF', 'PJ')),
    cpf_cnpj     TEXT,

    banco        TEXT,
    agencia      TEXT,
    conta        TEXT,
    tipo_conta   TEXT CHECK (tipo_conta IN ('corrente', 'poupanca', 'pagamento')),
    pix_tipo     TEXT CHECK (pix_tipo IN ('cpf', 'cnpj', 'email', 'telefone', 'aleatoria')),
    pix          TEXT,

    -- Optional link to an in-house corretor/intermediário (lead_corretores).
    corretor_id  UUID REFERENCES social_wiring.lead_corretores (id) ON DELETE SET NULL,

    ativo        BOOLEAN NOT NULL DEFAULT true,

    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_por  UUID,
    updated_at   TIMESTAMPTZ,
    updated_por  UUID
);

COMMENT ON TABLE social_wiring.favorecidos IS
    'Org-level payee registry (migration 251). Financial PII — RLS org-scoped, '
    'values never logged, masked in list responses. Cards link via '
    'atendimento_favorecidos.favorecido_id.';

CREATE INDEX IF NOT EXISTS idx_sw_favorecidos_org_ativo
    ON social_wiring.favorecidos (org_id, ativo, nome);

-- One ACTIVE registry row per document per org (alphanumeric-safe key: a CNPJ
-- may carry letters). A soft-deleted row frees the document.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_favorecidos_org_documento
    ON social_wiring.favorecidos (
        org_id, (regexp_replace(upper(cpf_cnpj), '[^0-9A-Z]', '', 'g'))
    )
    WHERE ativo AND cpf_cnpj IS NOT NULL
      AND regexp_replace(upper(cpf_cnpj), '[^0-9A-Z]', '', 'g') <> '';

ALTER TABLE social_wiring.favorecidos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "favorecidos_select_own_org" ON social_wiring.favorecidos;
CREATE POLICY "favorecidos_select_own_org"
    ON social_wiring.favorecidos
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "favorecidos_service_role" ON social_wiring.favorecidos;
CREATE POLICY "favorecidos_service_role"
    ON social_wiring.favorecidos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- Card side: nullable reference to the registry.
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.atendimento_favorecidos
    ADD COLUMN IF NOT EXISTS favorecido_id UUID
        REFERENCES social_wiring.favorecidos (id) ON DELETE SET NULL;

COMMENT ON COLUMN social_wiring.atendimento_favorecidos.favorecido_id IS
    'Registry entry (migration 251) this card row references. When set, the '
    'registry''s current values win at read time; the row''s own columns are '
    'the fallback. NULL = typed on the card (legacy).';

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_favorecidos_registro
    ON social_wiring.atendimento_favorecidos (org_id, favorecido_id)
    WHERE favorecido_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- Backfill — dedupe key per (org): the document's alphanumerics when typed,
-- else the lower-cased trimmed name. Pass 1 creates a registry row (newest card
-- row wins the values) for every key that has none; pass 2 links every
-- unlinked card row to the registry row of its key.
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.favorecidos
    (org_id, nome, tipo_pessoa, cpf_cnpj, banco, agencia, conta, pix)
SELECT DISTINCT ON (k.org_id, k.chave)
    k.org_id, k.nome,
    CASE
        WHEN k.tem_doc AND length(k.chave) = 11 THEN 'PF'
        WHEN k.tem_doc AND length(k.chave) = 14 THEN 'PJ'
    END,
    k.cpf_cnpj, k.banco, k.agencia, k.conta, k.pix
FROM (
    SELECT
        af.*,
        COALESCE(
            NULLIF(regexp_replace(upper(af.cpf_cnpj), '[^0-9A-Z]', '', 'g'), ''),
            'N:' || lower(btrim(af.nome))
        ) AS chave,
        (NULLIF(regexp_replace(upper(af.cpf_cnpj), '[^0-9A-Z]', '', 'g'), '') IS NOT NULL) AS tem_doc
    FROM social_wiring.atendimento_favorecidos af
    WHERE af.favorecido_id IS NULL
) k
WHERE NOT EXISTS (
    SELECT 1 FROM social_wiring.favorecidos r
    WHERE r.org_id = k.org_id AND r.ativo
      AND (
          (k.tem_doc AND regexp_replace(upper(r.cpf_cnpj), '[^0-9A-Z]', '', 'g') = k.chave)
          OR (NOT k.tem_doc
              AND NULLIF(regexp_replace(upper(coalesce(r.cpf_cnpj, '')), '[^0-9A-Z]', '', 'g'), '') IS NULL
              AND lower(btrim(r.nome)) = lower(btrim(k.nome)))
      )
)
ORDER BY k.org_id, k.chave, k.created_at DESC;

UPDATE social_wiring.atendimento_favorecidos af
SET favorecido_id = (
    SELECT r.id
    FROM social_wiring.favorecidos r
    WHERE r.org_id = af.org_id AND r.ativo
      AND (
          (NULLIF(regexp_replace(upper(coalesce(af.cpf_cnpj, '')), '[^0-9A-Z]', '', 'g'), '') IS NOT NULL
           AND regexp_replace(upper(coalesce(r.cpf_cnpj, '')), '[^0-9A-Z]', '', 'g')
               = regexp_replace(upper(af.cpf_cnpj), '[^0-9A-Z]', '', 'g'))
          OR (NULLIF(regexp_replace(upper(coalesce(af.cpf_cnpj, '')), '[^0-9A-Z]', '', 'g'), '') IS NULL
              AND NULLIF(regexp_replace(upper(coalesce(r.cpf_cnpj, '')), '[^0-9A-Z]', '', 'g'), '') IS NULL
              AND lower(btrim(r.nome)) = lower(btrim(af.nome)))
      )
    ORDER BY r.created_at
    LIMIT 1
)
WHERE af.favorecido_id IS NULL;

-- ----------------------------------------------------------------------------
-- Nav page row (the Favorecidos page of the FE slice). Insert-if-missing.
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('favorecidos', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
