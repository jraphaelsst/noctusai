-- ============================================================
-- CLEANUP: Remove all mock matching test data
-- Tag: [MOCK-MATCHING-TEST]
-- Run this in Supabase SQL Editor after evaluating matches
-- ============================================================

-- Step 1: Delete matches that reference any mock ativo
DELETE FROM erp.matches
WHERE ativo_origem_id IN (
    SELECT id FROM erp.ativos WHERE observacoes LIKE '%[MOCK-MATCHING-TEST]%'
)
OR ativo_destino_id IN (
    SELECT id FROM erp.ativos WHERE observacoes LIKE '%[MOCK-MATCHING-TEST]%'
);

-- Step 2: Delete the mock ativos themselves
DELETE FROM erp.ativos
WHERE observacoes LIKE '%[MOCK-MATCHING-TEST]%';

-- Step 3: Verify cleanup
SELECT 'Remaining mock ativos' AS check, COUNT(*) AS count
FROM erp.ativos WHERE observacoes LIKE '%[MOCK-MATCHING-TEST]%'
UNION ALL
SELECT 'Orphaned matches', COUNT(*)
FROM erp.matches m
WHERE NOT EXISTS (SELECT 1 FROM erp.ativos a WHERE a.id = m.ativo_origem_id)
   OR NOT EXISTS (SELECT 1 FROM erp.ativos a WHERE a.id = m.ativo_destino_id);
