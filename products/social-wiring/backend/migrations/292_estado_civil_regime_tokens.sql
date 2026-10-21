-- ============================================================================
-- Migration 292 -- social_wiring: clientes.estado_civil / regime_bens as tokens
-- ============================================================================
-- WHY: the "Dados pessoais" form used to save display LABELS ("Casado(a)",
-- "Comunhão parcial de bens"); the contract generator needs the canonical
-- tokens (frases.REGIME_EXTENSO / civil_status.ESTADO_CIVIL_VALORES). The write
-- path now normalises (estado_civil_canonico); this maps the rows already
-- stored in label form (prod 2026-10-21: 4 estado_civil, 1 regime_bens).
-- DATA-ONLY, idempotent (matches labels only; tokens never match), no DDL.
-- ============================================================================
SET search_path = social_wiring, public;

UPDATE clientes SET estado_civil = CASE estado_civil
    WHEN 'Solteiro(a)' THEN 'solteiro'
    WHEN 'Casado(a)' THEN 'casado'
    WHEN 'Divorciado(a)' THEN 'divorciado'
    WHEN 'Viúvo(a)' THEN 'viuvo'
    WHEN 'Separado(a)' THEN 'separado_judicialmente'
    WHEN 'Separado(a) judicialmente' THEN 'separado_judicialmente'
    WHEN 'União estável' THEN 'uniao_estavel'
  END
WHERE estado_civil IN ('Solteiro(a)', 'Casado(a)', 'Divorciado(a)', 'Viúvo(a)',
                       'Separado(a)', 'Separado(a) judicialmente', 'União estável');

UPDATE clientes SET regime_bens = CASE regime_bens
    WHEN 'Comunhão parcial de bens' THEN 'comunhao_parcial'
    WHEN 'Comunhão universal de bens' THEN 'comunhao_universal'
    WHEN 'Separação total de bens' THEN 'separacao_total'
    WHEN 'Separação obrigatória de bens' THEN 'separacao_obrigatoria'
    WHEN 'Participação final nos aquestos' THEN 'participacao_final_aquestos'
  END
WHERE regime_bens IN ('Comunhão parcial de bens', 'Comunhão universal de bens',
                      'Separação total de bens', 'Separação obrigatória de bens',
                      'Participação final nos aquestos');
