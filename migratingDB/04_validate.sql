-- =====================================================================
-- ETAPA 4: Validação
-- Roda queries para verificar que tudo migrou corretamente
-- =====================================================================

-- 1. Count migrated ativos by type
SELECT
  'MIGRATED ATIVOS' AS category,
  natureza,
  COUNT(*) AS total
FROM erp.ativos
WHERE observacoes LIKE '%MIGRADO%' OR titulo_anuncio LIKE '%MOCK%'
GROUP BY natureza
ORDER BY natureza;
-- Expected: imovel=264, permuta_imovel=13

-- 2. Count placeholder clientes
SELECT
  'PLACEHOLDER CLIENTES' AS category,
  COUNT(*) AS total
FROM erp.clientes
WHERE observacoes LIKE '%MIGRADO%';
-- Expected: ~214

-- 3. Count placeholder condominios
SELECT
  'PLACEHOLDER CONDOMINIOS' AS category,
  COUNT(*) AS total
FROM erp.condominios
WHERE observacoes LIKE '%MIGRADO%';
-- Expected: ~147

-- 4. Verify erp.matches is empty (populated by algorithm)
SELECT
  'MATCHES (should be 0)' AS category,
  COUNT(*) AS total
FROM erp.matches;
-- Expected: 0

-- 5. Verify interesses were populated
SELECT
  'ATIVOS WITH INTERESSES' AS category,
  COUNT(*) AS total
FROM erp.ativos
WHERE interesses != '[]'::JSONB AND interesses IS NOT NULL;
-- Expected: ~115

-- 6. Verify no orphaned references
SELECT 'ORPHANED PROPRIETARIOS' AS check_name, COUNT(*) AS issues
FROM erp.ativos a
WHERE a.proprietario_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM erp.clientes c WHERE c.id = a.proprietario_id)
UNION ALL
SELECT 'ORPHANED CONDOMINIOS', COUNT(*)
FROM erp.ativos a
WHERE a.condominio_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM erp.condominios c WHERE c.id = a.condominio_id);
-- Expected: 0 issues for both

-- 7. Sample migrated imovel with interests
SELECT
  a.ref,
  a.tipo_imovel,
  a.valor,
  a.zona,
  a.aceita_permutas,
  jsonb_array_length(a.interesses) AS num_interesses,
  a.interesses
FROM erp.ativos a
WHERE a.natureza = 'imovel'
  AND a.interesses != '[]'::JSONB
LIMIT 5;
