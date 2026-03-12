-- =====================================================================
-- ETAPA 3: Migração dos dados
-- Transforma staging → erp.clientes, erp.condominios, erp.ativos
-- =====================================================================

-- ─────────────────────────────────────────────────────────────────────
-- Generate UUID mappings for all old IDs
-- ─────────────────────────────────────────────────────────────────────

INSERT INTO imovel_id_map (old_id)
  SELECT DISTINCT id FROM stg_imovel;

INSERT INTO permuta_id_map (old_id)
  SELECT DISTINCT id FROM stg_permuta_imovel;

INSERT INTO proprietario_id_map (old_id)
  SELECT DISTINCT proprietario_id FROM stg_imovel
  UNION
  SELECT DISTINCT proprietario_id FROM stg_permuta_imovel;

INSERT INTO condominio_id_map (old_id)
  SELECT DISTINCT condominio_id FROM stg_imovel
  WHERE condominio_id IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────
-- Create placeholder clientes (from old proprietarios)
-- ─────────────────────────────────────────────────────────────────────

INSERT INTO erp.clientes (
  id, usuario_id, nome, email, telefone, origem, interesse,
  observacoes, etapa_atual, probabilidade, valor_estimado
)
SELECT
  pm.new_uuid,
  (SELECT value::UUID FROM migration_config WHERE key = 'profile_id'),
  'Proprietário #' || pm.old_id,
  'proprietario_' || pm.old_id || '@migrado.placeholder',
  NULL,
  'migração',
  'permuta',
  '[MIGRADO] Proprietário importado do sistema antigo. ID original: ' || pm.old_id || '. Atualizar nome/email/telefone com dados reais.',
  'qualificacao',
  50,
  0
FROM proprietario_id_map pm
ON CONFLICT (email) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────
-- Create placeholder condominios (from old condominio IDs)
-- ─────────────────────────────────────────────────────────────────────

INSERT INTO erp.condominios (
  id, owner_id, nome, observacoes
)
SELECT
  cm.new_uuid,
  (SELECT value::UUID FROM migration_config WHERE key = 'owner_id'),
  'Condomínio #' || cm.old_id,
  '[MIGRADO] Condomínio importado do sistema antigo. ID original: ' || cm.old_id || '. Atualizar nome/endereço com dados reais.'
FROM condominio_id_map cm;

-- ─────────────────────────────────────────────────────────────────────
-- Build interesses JSONB for each imovel
-- ─────────────────────────────────────────────────────────────────────

CREATE TEMP TABLE imovel_interesses_json (
  imovel_id INTEGER PRIMARY KEY,
  interesses JSONB NOT NULL DEFAULT '[]'::JSONB,
  observacoes_interesse TEXT
);

INSERT INTO imovel_interesses_json (imovel_id, interesses, observacoes_interesse)
SELECT
  si.imovel_id,
  COALESCE(
    jsonb_agg(
      jsonb_strip_nulls(jsonb_build_object(
        'tipo', 'imovel',
        'tipo_imovel', tim.novo_tipo,
        'estado', NULLIF(si.estado, ''),
        'cidade', NULLIF(si.cidade, ''),
        'bairro', NULLIF(si.bairro, ''),
        'cep', NULLIF(si.cep, ''),
        'zona', zm.nova_zona,
        'valor_min', CASE WHEN si.valor_minimo > 0 THEN si.valor_minimo END,
        'valor_max', CASE WHEN si.valor_maximo > 0 THEN si.valor_maximo END
      ))
    ),
    '[]'::JSONB
  ),
  string_agg(NULLIF(si.observacoes, ''), ' | ' ORDER BY si.id)
FROM stg_interesse_imovel si
LEFT JOIN tipo_imovel_map tim ON si.tipo_imovel_id = tim.old_id
LEFT JOIN zona_map zm ON si.zona_id = zm.old_id
GROUP BY si.imovel_id;

-- Add automovel interests to existing records
WITH auto_interesses AS (
  SELECT
    sa.imovel_id,
    jsonb_agg(
      jsonb_strip_nulls(jsonb_build_object(
        'tipo', 'automovel',
        'tipo_veiculo', tam.novo_tipo,
        'valor_min', CASE WHEN sa.valor_minimo > 0 THEN sa.valor_minimo END,
        'valor_max', CASE WHEN sa.valor_maximo > 0 THEN sa.valor_maximo END
      ))
    ) AS interesses
  FROM stg_interesse_automovel sa
  LEFT JOIN tipo_automovel_map tam ON sa.tipo_automovel_id = tam.old_id
  GROUP BY sa.imovel_id
)
INSERT INTO imovel_interesses_json (imovel_id, interesses)
SELECT imovel_id, interesses
FROM auto_interesses
ON CONFLICT (imovel_id) DO UPDATE
  SET interesses = imovel_interesses_json.interesses || EXCLUDED.interesses;

-- ─────────────────────────────────────────────────────────────────────
-- Build interesses JSONB for each permuta_imovel
-- ─────────────────────────────────────────────────────────────────────

CREATE TEMP TABLE permuta_interesses_json (
  permuta_imovel_id INTEGER PRIMARY KEY,
  interesses JSONB NOT NULL DEFAULT '[]'::JSONB,
  observacoes_interesse TEXT
);

INSERT INTO permuta_interesses_json (permuta_imovel_id, interesses, observacoes_interesse)
SELECT
  spi.permuta_imovel_id,
  COALESCE(
    jsonb_agg(
      jsonb_strip_nulls(jsonb_build_object(
        'tipo', 'imovel',
        'tipo_imovel', tim.novo_tipo,
        'estado', NULLIF(spi.estado, ''),
        'cidade', NULLIF(spi.cidade, ''),
        'bairro', NULLIF(spi.bairro, ''),
        'cep', NULLIF(spi.cep, ''),
        'zona', zm.nova_zona,
        'valor_min', CASE WHEN spi.valor_minimo > 0 THEN spi.valor_minimo END,
        'valor_max', CASE WHEN spi.valor_maximo > 0 THEN spi.valor_maximo END
      ))
    ),
    '[]'::JSONB
  ),
  string_agg(NULLIF(spi.observacoes, ''), ' | ' ORDER BY spi.id)
FROM stg_permuta_interesse spi
LEFT JOIN tipo_imovel_map tim ON spi.tipo_imovel_id = tim.old_id
LEFT JOIN zona_map zm ON spi.zona_id = zm.old_id
GROUP BY spi.permuta_imovel_id;

-- ─────────────────────────────────────────────────────────────────────
-- Insert imóveis into erp.ativos (natureza = 'imovel') — 264 records
-- ─────────────────────────────────────────────────────────────────────

INSERT INTO erp.ativos (
  id, owner_id, natureza, valor, status, observacoes,
  tipo_imovel, zona, condominio_id,
  ref, corretor, proprietario_id, aceita_permutas, finalidade,
  interesses, observacoes_negociacao,
  titulo_anuncio, fotos, plantas, palavras_chave, pontos_de_interesse
)
SELECT
  im.new_uuid,
  (SELECT value::UUID FROM migration_config WHERE key = 'owner_id'),
  'imovel',
  si.valor_venda,
  'ativo',
  COALESCE(ij.observacoes_interesse, ''),
  COALESCE(tim.novo_tipo, 'outro'),
  zm.nova_zona,
  cm.new_uuid,
  si.ref,
  'Corretor #' || COALESCE(NULLIF(si.corretor_id::TEXT, ''), '0'),
  pm.new_uuid,
  CASE WHEN ij.imovel_id IS NOT NULL THEN true ELSE false END,
  'venda',
  COALESCE(ij.interesses, '[]'::JSONB),
  ij.observacoes_interesse,
  '[MOCK] ' || si.ref || ' - Atualizar título do anúncio',
  ARRAY[]::TEXT[],
  ARRAY[]::TEXT[],
  ARRAY[]::TEXT[],
  ARRAY[]::TEXT[]
FROM stg_imovel si
JOIN imovel_id_map im ON si.id = im.old_id
LEFT JOIN tipo_imovel_map tim ON si.tipo_id = tim.old_id
LEFT JOIN zona_map zm ON si.zona_id = zm.old_id
LEFT JOIN condominio_id_map cm ON si.condominio_id = cm.old_id
LEFT JOIN proprietario_id_map pm ON si.proprietario_id = pm.old_id
LEFT JOIN imovel_interesses_json ij ON si.id = ij.imovel_id;

-- ─────────────────────────────────────────────────────────────────────
-- Insert permutas into erp.ativos (natureza = 'permuta_imovel') — 13 records
-- ─────────────────────────────────────────────────────────────────────

INSERT INTO erp.ativos (
  id, owner_id, natureza, valor, status, observacoes,
  tipo_imovel, cep, logradouro, numero, bairro, cidade, estado, zona, condominio_nome,
  ref, corretor, proprietario_id, interesses, observacoes_negociacao,
  faixa_preco_min, faixa_preco_max,
  fotos, plantas, palavras_chave, pontos_de_interesse, regiao_preferida
)
SELECT
  prm.new_uuid,
  (SELECT value::UUID FROM migration_config WHERE key = 'owner_id'),
  'permuta_imovel',
  spi.valor,
  'ativo',
  COALESCE(pij.observacoes_interesse, ''),
  COALESCE(tim.novo_tipo, 'outro'),
  NULLIF(spi.cep, ''),
  NULLIF(spi.endereco, ''),
  NULLIF(spi.numero, ''),
  NULLIF(spi.bairro, ''),
  NULLIF(spi.cidade, ''),
  NULLIF(spi.estado, ''),
  zm.nova_zona,
  NULLIF(spi.condominio, ''),
  spi.ref,
  'Corretor #' || COALESCE(NULLIF(spi.corretor_id::TEXT, ''), '0'),
  pm.new_uuid,
  COALESCE(pij.interesses, '[]'::JSONB),
  pij.observacoes_interesse,
  (SELECT MIN((elem->>'valor_min')::NUMERIC) FROM jsonb_array_elements(COALESCE(pij.interesses, '[]'::JSONB)) elem WHERE elem->>'valor_min' IS NOT NULL),
  (SELECT MAX((elem->>'valor_max')::NUMERIC) FROM jsonb_array_elements(COALESCE(pij.interesses, '[]'::JSONB)) elem WHERE elem->>'valor_max' IS NOT NULL),
  ARRAY[]::TEXT[],
  ARRAY[]::TEXT[],
  ARRAY[]::TEXT[],
  ARRAY[]::TEXT[],
  CASE
    WHEN spi.cidade != '' AND spi.bairro != '' THEN ARRAY[spi.cidade || ' - ' || spi.bairro]
    WHEN spi.cidade != '' THEN ARRAY[spi.cidade]
    ELSE ARRAY[]::TEXT[]
  END
FROM stg_permuta_imovel spi
JOIN permuta_id_map prm ON spi.id = prm.old_id
LEFT JOIN tipo_imovel_map tim ON spi.tipo_id = tim.old_id
LEFT JOIN zona_map zm ON spi.zona_id = zm.old_id
LEFT JOIN proprietario_id_map pm ON spi.proprietario_id = pm.old_id
LEFT JOIN permuta_interesses_json pij ON spi.id = pij.permuta_imovel_id;

-- erp.matches is NOT populated — filled automatically by the matching algorithm.

-- Audit trail
COMMENT ON TABLE erp.ativos IS 'Contains migrated records from old permutas system. Search observacoes for [MIGRADO] or [MOCK] to find them.';
