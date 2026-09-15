-- ============================================================================
-- Migration 118 · social_wiring: Imóvel documentos — extração estruturada
-- (numero/emitida_em/validade_ate/resultado/inscricao_imobiliaria) + o grupo
-- de CNDs do imóvel exigido pela cláusula de certidões do contrato
--
-- WHAT THIS IS FOR
-- -----------------
-- The contract's certidões clause names an imóvel group the backend has no
-- columns for yet: the IPTU CND (número + data de emissão + resultado), the
-- condomínio debt certificate/declaração de quitação (data de emissão +
-- resultado), and the matrícula certidão's OWN emissão date — all of which
-- the office treats as stale past 30 days at signing. `imovel_documentos`
-- (075) already holds the PDFs; this gives it somewhere to record what was
-- read off them, in the SAME shape `certidao_resultados` uses for the exact
-- same three (numero/emitida_em/validade_ate/resultado — migration 107) plus
-- one field that surface never needed: `inscricao_imobiliaria`, which a guia
-- de IPTU and a CND de IPTU both carry and `imovel_dados.prefeitura_
-- cadastro_imobiliario` (075) has so far only ever been typed by hand.
--
-- TWO NEW TIPOS, ZERO SCHEMA CHANGE FOR THEM
-- --------------------------------------------
-- `cnd_iptu` and `cnd_condominio` join `imovel_documentos.tipo_documento`'s
-- allow-list — code-owned (`documentos_service.TIPOS_DOCUMENTO`), per 075's
-- own note that the set would grow and a CHECK would make each addition a
-- migration. This file adds no CHECK for them.
--
-- WHY `origem`/`resultado` ARE A NARROWER VOCABULARY THAN 107'S
-- -----------------------------------------------------------------
-- `certidao_resultados.resultado_origem` has three legs (`api`/`ia`/
-- `manual`) because a resultado can arrive via the InfoSimples API. Every
-- document here is one this module ALREADY HOLDS (an upload, not a pending
-- consulta), so there is no `api` leg — only `ia` (the background read) and
-- `manual` (an operator confirmed/corrected it via `PATCH .../extracao`).
-- Likewise `resultado` drops `nao_emitida` (107's fourth value, for a
-- consulta that came back empty): a document that is IN HAND was, by
-- definition, emitted.
--
-- WHY NO STATUS/TENTATIVAS LIFECYCLE (UNLIKE `extracao_status` ABOVE)
-- -----------------------------------------------------------------------
-- `extracao_status`/`extracao_tentativas` (075/092) track the número-de-
-- matrícula read, which is a due-diligence record a retry sweep must
-- recover if the job dies mid-flight. This structured read is a best-effort
-- SUGGESTION next to fields an operator reviews anyway before the contract
-- is generated — a failure logs its reason and leaves the row exactly as it
-- was; nothing here is ever left in an intermediate state a sweep would
-- need to find. See `documentos_service.extrair_estrutura`.
--
-- RETENTION — THE MIGRATION 111 PATTERN, EXTENDED TO THE TWO NEW TIPOS
-- --------------------------------------------------------------------------
-- 111 gave the `imovel` superfície its clock (`documento_retencao_
-- politicas`, anchored at `envio`) for `matricula`/`guia_iptu`/
-- `texto_extraido`. `cnd_iptu` and `cnd_condominio` are the SAME due-
-- diligence evidence class — they back the contract's clearance clause the
-- same way a matrícula backs the título aquisitivo — so they get the same
-- 3650-day (CC art. 205 decenal) platform row, not a shorter, arbitrary one.
-- `superficie` stays `'imovel'`; no CHECK change is needed (111 already
-- widened it to include `'imovel'`).
--
-- ACCESS LOGGING — NOTHING NEW TO WIRE
-- ---------------------------------------
-- `imovel_documentos.acessos_table` (`documentos_service.STORE`) is already
-- `imovel_documento_acessos` (migration 109) for EVERY tipo this table
-- holds — a CND/guia is exactly as much due-diligence evidence about the
-- property (and, via the inscrição, the owner) as a matrícula. Adding a
-- tipo to the code-owned tuple is what turns its logging on; there is no
-- per-tipo switch to flip here.
--
-- FORWARD-ONLY, IDEMPOTENT (every step existence-guarded; safe to re-run).
-- 🔴 MIGRATION FILE ONLY — not applied to any database by this change. Apply
-- via `noctus.dev.migrate_product` only after the tech-lead has stated the
-- row counts this will touch and the user has given an explicit go-ahead.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. imovel_documentos — the structured fields
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.imovel_documentos
    ADD COLUMN IF NOT EXISTS numero                 TEXT,
    ADD COLUMN IF NOT EXISTS emitida_em              DATE,
    ADD COLUMN IF NOT EXISTS validade_ate            DATE,
    ADD COLUMN IF NOT EXISTS resultado               TEXT,
    ADD COLUMN IF NOT EXISTS inscricao_imobiliaria   TEXT,
    ADD COLUMN IF NOT EXISTS origem                  TEXT,
    ADD COLUMN IF NOT EXISTS confirmado_por          UUID,
    ADD COLUMN IF NOT EXISTS confirmado_em           TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.imovel_documentos.numero IS
    'The document''s own control/registration number (a CND''s protocolo), '
    'when it prints one. NULL for tipos that never carry one — see '
    'documentos_service.CAMPOS_ESTRUTURA_POR_TIPO.';
COMMENT ON COLUMN social_wiring.imovel_documentos.emitida_em IS
    'Emission date PRINTED ON the document — not this row''s created_at. '
    'What the contract''s 30-day-old rule is checked against.';
COMMENT ON COLUMN social_wiring.imovel_documentos.validade_ate IS
    'Validity deadline printed on the document, when it states one.';
COMMENT ON COLUMN social_wiring.imovel_documentos.resultado IS
    'negativa | positiva | positiva_com_efeito_de_negativa. NULL means not '
    'yet read or not applicable to this tipo. Narrower than certidao_'
    'resultados.resultado (migration 107) — see this file''s header for why '
    '''nao_emitida'' does not apply to a document already in hand. CHECK '
    'constraint below is the vocabulary; kept in sync with '
    'documentos_service.RESULTADO_VALUES.';
COMMENT ON COLUMN social_wiring.imovel_documentos.inscricao_imobiliaria IS
    'The property''s cadastral number, read off a guia de IPTU or CND de '
    'IPTU. A guia''s reading SUGGESTS into imovel_dados.prefeitura_'
    'cadastro_imobiliario when that column is still empty — see '
    'documentos_service._sugestao_imovel_dados.';
COMMENT ON COLUMN social_wiring.imovel_documentos.origem IS
    'ia | manual — who last wrote the five columns above. NULL means '
    'neither has run yet. A row already ''manual'' (or with a non-null '
    'confirmado_por) is NEVER overwritten by a later automated read — see '
    'documentos_service.extrair_estrutura.';
COMMENT ON COLUMN social_wiring.imovel_documentos.confirmado_por IS
    'Who confirmed/corrected these fields via PATCH .../documentos/{id}/'
    'extracao — set even when the PATCH body was empty (a pure "I reviewed '
    'this and it is correct"). Independent of origem for the same reason '
    'certidao_resultados.confirmado_por is (migration 107): a human may '
    'confirm a value the AI already got right without changing it.';
COMMENT ON COLUMN social_wiring.imovel_documentos.confirmado_em IS
    'When confirmado_por confirmed it.';

ALTER TABLE social_wiring.imovel_documentos
    DROP CONSTRAINT IF EXISTS imovel_documentos_resultado_check;
ALTER TABLE social_wiring.imovel_documentos
    ADD CONSTRAINT imovel_documentos_resultado_check
    CHECK (resultado IS NULL OR resultado IN (
        'negativa', 'positiva', 'positiva_com_efeito_de_negativa'
    ));

ALTER TABLE social_wiring.imovel_documentos
    DROP CONSTRAINT IF EXISTS imovel_documentos_origem_check;
ALTER TABLE social_wiring.imovel_documentos
    ADD CONSTRAINT imovel_documentos_origem_check
    CHECK (origem IS NULL OR origem IN ('ia', 'manual'));

-- "The latest CND/matrícula per tipo for this imóvel" — GET .../certidoes.
CREATE INDEX IF NOT EXISTS idx_sw_imovel_documentos_estrutura
    ON social_wiring.imovel_documentos (org_id, codigo, tipo_documento, created_at DESC)
    WHERE deleted_at IS NULL;

-- ----------------------------------------------------------------------------
-- 2. Retention — the migration 111 pattern, for the two new tipos
-- ----------------------------------------------------------------------------
-- `superficie = 'imovel'` is already an allowed value (111's CHECK); no
-- constraint change needed. Same 3650-day (CC art. 205) reasoning 111 gave
-- matricula/guia_iptu — this is the same due-diligence evidence class.
INSERT INTO social_wiring.documento_retencao_politicas
    (org_id, superficie, tipo_documento, retencao_dias, motivo)
VALUES
    (NULL, 'imovel', 'cnd_iptu', 3650,
     'Evidência de quitação fiscal exigida pela cláusula de certidões do '
     'contrato: prescrição decenal de pretensões contratuais (CC art. 205).'),
    (NULL, 'imovel', 'cnd_condominio', 3650,
     'Evidência de quitação condominial exigida pela mesma cláusula — '
     'mesma janela de retenção do dossiê do imóvel.')
ON CONFLICT DO NOTHING;

-- FORWARD-ONLY, IDEMPOTENT. No DROP TABLE / DELETE / TRUNCATE anywhere in
-- this file. Every ALTER is ADD COLUMN IF NOT EXISTS or a DROP CONSTRAINT
-- IF EXISTS + re-ADD; the INSERT is an ON CONFLICT DO NOTHING seed of two
-- platform-tier rows. Safe to re-run.
