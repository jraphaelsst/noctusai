-- ============================================================================
-- Migration 137 -- social_wiring: matrícula party qualification -> the
-- existing extraction suggest/confirm/apply pipeline
--
-- WHAT THIS IS
-- ------------
-- `noctusai_lib.integrations.documents.matricula_qualificacao` reads every
-- party a matrícula's own act text qualifies (nome, nacionalidade,
-- estado_civil, profissão, RG + órgão, endereço, gênero), anchored on a
-- checksum-valid CPF/CNPJ rather than a label. Measured against the org's 5
-- real matrículas (2026-09-18): 14 people, all `alta`, with
-- nacionalidade/profissão/RG/órgão/gênero at 14/14 and estado_civil/endereço
-- at 9/14. Nothing consumed it before this file.
--
-- `identidade_extracao_service.CAMPOS` already IS the suggest/confirm/apply
-- pipeline this platform settled on for a machine-read identity value (097's
-- header, restated by 110: table-driven, one apply/suggest/confirm/access-log
-- code path per field). This migration makes matrícula qualification a new
-- SOURCE for that same pipeline -- not a parallel one -- by:
--
--   1. giving `nacionalidade` and `profissao` the SAME provenance quintet
--      097/110/117 gave cpf/rg/estado_civil/regime_bens/data_casamento, so
--      they become real `CAMPOS` entries (code change alongside this file --
--      see `identidade_extracao_service.py`);
--   2. adding `matricula_qualificacoes`, the table a `cliente_documentos`
--      row structurally cannot be for this source -- see below.
--
-- 🔴 WHY THIS IS A NEW TABLE, NOT MORE `cliente_documentos` COLUMNS
-- --------------------------------------------------------------------------
-- `cliente_documentos.cliente_id` is `NOT NULL` (057): a cliente_documento
-- IS a specific cliente's own upload, by construction. A matrícula is an
-- `imovel_documentos` row -- an IMÓVEL's file, keyed by `(org_id, codigo)`,
-- not a cliente's -- and one matrícula names MANY people, most of whom are
-- not (yet, or ever) a `clientes` row in this org at all. There is no
-- `cliente_id` to hang a `cliente_documentos` insert off until AFTER a
-- person is identified, which is exactly the question this table answers.
-- Same reasoning `115` gave for `matricula_ato_detalhes` being its own
-- table beside `cliente_documentos`'s extraction columns rather than forced
-- onto them: the owning entity is different, so the row is different, and
-- the FIELD-LEVEL mechanics (CAMPOS, sobrescreve, provenance) are what gets
-- reused, not the table.
--
-- One row per CONSOLIDATED person per extraction
-- (`mesclar_qualificacoes`'s own output), not one per act -- an act-grained
-- table would re-litigate the seed's own cross-act merge (first-writer-wins
-- per field, already done once, correctly, in Python) instead of reusing
-- it. `UNIQUE (extracao_id, cpf_cnpj_normalizado)` is that shape: minted
-- once, exactly like `matricula_atos` and `matricula_ato_detalhes` are
-- minted once per extraction and self-heal on read
-- (`qualificacao_service.qualificacoes_da_extracao`).
--
-- 🔴 KEYING A SUGGESTION BEFORE A CLIENTE EXISTS
-- --------------------------------------------------------------------------
-- A CPF/CNPJ carries its own check digits -- the same reason the seed
-- module anchors on it instead of a label -- so it is also the right join
-- key against `clientes`, org-wide (`idx_sw_clientes_cpf_norm`, 097), the
-- same lookup `is_same_as_cpf`'s callers already trust. Three outcomes,
-- every one of them VISIBLE, never a silent drop (KB 01-PHILOSOPHY.md):
--
--   `vinculado`          -- exactly one cliente in this org carries this
--                            normalised CPF/CNPJ. `cliente_id` is set.
--   `sem_correspondencia` -- no cliente in this org carries it yet. This
--                            is the ordinary case for a party who has not
--                            been created as a cliente -- a transmitente on
--                            an old registered act very often never is.
--                            `cliente_id` stays NULL; the row is still
--                            listed, still readable, still quotable.
--   `ambiguo`             -- more than one cliente in this org carries it
--                            (the `identidade_incerta` shape 048/097
--                            already anticipate can happen). NEVER picked
--                            for the operator -- `cliente_id` stays NULL
--                            and the row says why.
--
-- This migration does NOT create a `clientes` row for a `sem_correspondencia`
-- party. Deciding whether a matrícula party becomes a new cliente, gets
-- linked to an `atendimento_partes` row, and on which `lado` (098) is a
-- product/business decision this file does not make for the operator.
--
-- 🔴 `endereco` IS CARRIED, NEVER AUTO-APPLIED
-- --------------------------------------------------------------------------
-- `clientes.endereco_*` (097) is SEVEN structured columns; a matrícula
-- qualification's `endereco` is ONE free-text clause ("residente e
-- domiciliado na Rua ..."). Splitting that clause into logradouro/número/
-- bairro/cidade/UF correctly is a real parsing problem this migration does
-- not attempt -- a wrong split is worse than an unsplit value sitting in
-- front of a human. `endereco` is therefore stored and returned on the
-- suggestion row (so nothing is lost) but is NOT one of `CAMPOS_QUALIFICACAO`
-- and never reaches `clientes.endereco_*` through `confirmar`.
-- NOC-REMEDIATE[matricula-endereco-estruturado]: address-clause -> structured
-- columns, deferred until a real corpus of the clause's own shapes justifies
-- a parser -- 2026-09-18.
--
-- 🔴 PROVENANCE: `origem` IS PER-FIELD, NOT PER-ROW
-- --------------------------------------------------------------------------
-- `mesclar_qualificacoes` already tracks, per field, which act (`ato_ref`)
-- first supplied it -- first-writer-wins across acts, same rule
-- `data_nascimento` uses across documents. `origem` here is that same dict,
-- `{campo: ato_id}` (the `matricula_atos.id` UUID, as text), so an operator
-- -- or a generated deed -- can be pointed at exactly which act named a
-- value. `nome_inicio`/`nome_fim` are the seed module's own offsets into
-- `matricula_extracoes.texto_extraido`, letting the FE highlight the exact
-- span the name came from, the same way `matricula_atos` already highlights
-- an act's own span.
--
-- 🔴 READING THESE ROWS DOES NOT MINT A NEW ACCESS-LOG ACTION
-- --------------------------------------------------------------------------
-- `estrutura_service.listar_atos` already logs `text_view` (111) for the
-- SAME `texto_extraido` these rows are derived from, and its own docstring
-- already states the reasoning `115` used to justify NOT adding a second log
-- row for `detalhes`: "readings OF the text this response already hands
-- back". Qualificações ride the same response, so they ride the same log --
-- no `imovel_documento_acessos.acao` CHECK widening in this file.
--
-- 🔴 `sobrescreve=False` FOR EVERY `CAMPOS_QUALIFICACAO` ENTRY, SAME REASON
-- AS 097/110/117
-- --------------------------------------------------------------------------
-- None of nome_oficial's sibling fields here (genero, cpf, rg, estado_civil,
-- nacionalidade, profissao) has a second column holding what an operator
-- typed. `nome_oficial` alone is `sobrescreve=True`, on the same terms
-- 071/097 already gave it: `nome_completo` sits beside it holding the
-- registration spelling, so overwriting `nome_oficial` destroys nothing --
-- see `identidade_extracao_service.CAMPOS`'s own comments (code, not this
-- file) for where the policy actually lives.
--
-- FORWARD-ONLY, IDEMPOTENT (safe to re-run; every step is existence-guarded).
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. `nacionalidade` / `profissao` -- the two new `CAMPOS` entries
-- ----------------------------------------------------------------------------
-- Same quintet shape as every other field on this list (097/110/117):
-- `_origem` | `_documento_id` | `_em` | `_confirmado_por` | `_confirmado_em`.
-- `_documento_id` stays NULL for `origem='matricula'` -- there is no
-- `cliente_documentos` row for this source (see the header) -- the SAME way
-- it already stays NULL for `origem='manual'` today. A matrícula-sourced
-- value's real provenance (which extraction, which act) lives on
-- `matricula_qualificacoes`, addressable by `(cliente_id, cliente
-- .nacionalidade_em)` or, more directly, by the operator following the
-- suggestion they confirmed.
ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS nacionalidade_origem          TEXT,
    ADD COLUMN IF NOT EXISTS nacionalidade_documento_id    UUID
        REFERENCES social_wiring.cliente_documentos(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS nacionalidade_em              TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS nacionalidade_confirmado_por  UUID,
    ADD COLUMN IF NOT EXISTS nacionalidade_confirmado_em   TIMESTAMPTZ,

    ADD COLUMN IF NOT EXISTS profissao_origem              TEXT,
    ADD COLUMN IF NOT EXISTS profissao_documento_id        UUID
        REFERENCES social_wiring.cliente_documentos(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS profissao_em                  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS profissao_confirmado_por      UUID,
    ADD COLUMN IF NOT EXISTS profissao_confirmado_em       TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.clientes.nacionalidade_origem IS
    '''manual'' | ''matricula'' -- where the CURRENT nacionalidade value '
    'came from. NULL alongside a non-null nacionalidade predates 137. See '
    'identidade_extracao_service.CAMPOS (sobrescreve=False).';
COMMENT ON COLUMN social_wiring.clientes.nacionalidade_documento_id IS
    'NULL for origem=''matricula'' -- this source has no cliente_documentos '
    'row (see migration 137''s header). Non-NULL only for a future document '
    '-based source of nacionalidade, if one is ever added.';
COMMENT ON COLUMN social_wiring.clientes.profissao_origem IS
    'Same contract as nacionalidade_origem, for profissao (073''s '
    'plain-TEXT, provenance-free column until now).';

-- ----------------------------------------------------------------------------
-- 2. matricula_qualificacoes -- one row per consolidated party per extraction
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.matricula_qualificacoes (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL,
    extracao_id          UUID NOT NULL
        REFERENCES social_wiring.matricula_extracoes(id) ON DELETE CASCADE,

    -- The anchor. `cpf_cnpj` as `mesclar_qualificacoes` formatted it
    -- (punctuation for display); `cpf_cnpj_normalizado` digits-only, for the
    -- uniqueness constraint and the cliente lookup -- CPF/CNPJ never carry a
    -- check-digit letter the way an RG can, so a plain digit strip is exact,
    -- unlike `normalizar_documento` which also has to cope with a trailing
    -- ''X''.
    cpf_cnpj             TEXT NOT NULL,
    cpf_cnpj_normalizado TEXT NOT NULL,

    -- The Qualificacao fields, verbatim (literal substrings of the
    -- extraction's texto_extraido, or None) -- see
    -- noctusai_lib.integrations.documents.matricula_qualificacao.Qualificacao.
    nome                 TEXT NOT NULL,
    nacionalidade        TEXT,
    estado_civil         TEXT,
    profissao            TEXT,
    rg                   TEXT,
    rg_orgao_expedidor   TEXT,
    endereco             TEXT,
    genero               TEXT,

    -- Offsets into texto_extraido for the NAME span (module docstring) --
    -- same idea as matricula_atos.char_inicio/fim, one coordinate space per
    -- extraction.
    nome_inicio          INT,
    nome_fim             INT,

    -- Whole-qualification grade (module-wide, not per-field) --
    -- 'alta' | 'baixa'. NEVER 'nenhuma': a Qualificacao that named no
    -- document/name at all is not reported by extrair_qualificacoes.
    confianca            TEXT NOT NULL CHECK (confianca IN ('alta', 'baixa')),

    -- Per-field provenance: {campo: ato_id} (matricula_atos.id, as text) --
    -- mesclar_qualificacoes' own `origem`, JSON-encoded verbatim.
    origem                JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- The cliente match -- see the header's three-outcome contract.
    cliente_id            UUID
        REFERENCES social_wiring.clientes(id) ON DELETE SET NULL,
    vinculo_status         TEXT NOT NULL
        CHECK (vinculo_status IN ('vinculado', 'sem_correspondencia', 'ambiguo')),
    CONSTRAINT matricula_qualificacoes_cliente_por_status
        CHECK ((vinculo_status = 'vinculado') = (cliente_id IS NOT NULL)),

    -- Operator confirmation -- mirrors ato_detalhes_service's
    -- origem/confirmado_por/confirmado_em shape. `aplicado_campos` records
    -- which CAMPOS_QUALIFICACAO fields the confirm actually wrote onto
    -- `clientes` (a field already present under sobrescreve=False is
    -- skipped, visibly, not silently -- same contract
    -- aplicar_campos_ao_cliente already returns to its callers).
    confirmado_por        UUID,
    confirmado_em         TIMESTAMPTZ,
    aplicado_campos       JSONB,

    -- Dismiss -- mirrors cliente_documentos.extracao_descartada_em/por
    -- (068): the reading is KEPT, only stops being offered.
    descartado_por        UUID,
    descartado_em         TIMESTAMPTZ,

    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT matricula_qualificacoes_extracao_pessoa
        UNIQUE (extracao_id, cpf_cnpj_normalizado)
);

COMMENT ON TABLE social_wiring.matricula_qualificacoes IS
    'One row per person mesclar_qualificacoes consolidated for one matrícula '
    'extraction (migration 137). Suggestion-only: a row never writes to '
    'clientes by itself -- see qualificacao_service.confirmar. See this '
    'migration''s header for the full design.';
COMMENT ON COLUMN social_wiring.matricula_qualificacoes.vinculo_status IS
    '''vinculado'' (cliente_id set, exactly one org cliente shares this '
    'CPF/CNPJ) | ''sem_correspondencia'' (no match -- the ordinary case for '
    'a party not yet a cliente) | ''ambiguo'' (more than one match -- never '
    'auto-picked). Never silently dropped -- every party the seed module '
    'anchored on gets a row, whichever status applies.';
COMMENT ON COLUMN social_wiring.matricula_qualificacoes.origem IS
    '{campo: ato_id} -- which act (matricula_atos.id) first supplied each '
    'field, straight from mesclar_qualificacoes. A deed quotes this text; an '
    'operator must be able to see where a value came from.';
COMMENT ON COLUMN social_wiring.matricula_qualificacoes.endereco IS
    'The address clause verbatim. NOT one of CAMPOS_QUALIFICACAO -- '
    'clientes.endereco_* is 7 structured columns and this is one free-text '
    'clause. Shown to the operator, never auto-applied. See this '
    'migration''s header, NOC-REMEDIATE[matricula-endereco-estruturado].';

CREATE INDEX IF NOT EXISTS idx_sw_matricula_qualificacoes_extracao
    ON social_wiring.matricula_qualificacoes (org_id, extracao_id);

CREATE INDEX IF NOT EXISTS idx_sw_matricula_qualificacoes_cliente
    ON social_wiring.matricula_qualificacoes (org_id, cliente_id)
    WHERE cliente_id IS NOT NULL;

-- The operator's actionable queue: a vinculado suggestion still awaiting a
-- decision, or an unmatched/ambiguous party someone needs to look at.
CREATE INDEX IF NOT EXISTS idx_sw_matricula_qualificacoes_pendente
    ON social_wiring.matricula_qualificacoes (org_id, created_at DESC)
    WHERE descartado_em IS NULL AND confirmado_em IS NULL;

ALTER TABLE social_wiring.matricula_qualificacoes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "matricula_qualificacoes_select_own_org"
    ON social_wiring.matricula_qualificacoes;
CREATE POLICY "matricula_qualificacoes_select_own_org"
    ON social_wiring.matricula_qualificacoes
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "matricula_qualificacoes_service_role"
    ON social_wiring.matricula_qualificacoes;
CREATE POLICY "matricula_qualificacoes_service_role"
    ON social_wiring.matricula_qualificacoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);
