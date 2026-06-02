-- ============================================================================
-- Migration 004 — Codify the live RLS fix: current_org_id() for adconnect schema
--
-- WHY THIS EXISTS
-- ---------------
-- All authenticated RLS policies in adconnect were created in 001_adconnect.sql
-- using the broken TOP-LEVEL JWT claim:
--
--     org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
--
-- This claim is ALWAYS NULL in Supabase (org_id lives under user_metadata).
-- Additionally, some policies used an indirect form:
--
--     d.org_id = ((SELECT auth.jwt()) ->> 'org_id')::uuid
--
-- Both forms must be replaced with public.current_org_id().
--
-- The fix was applied LIVE on 2026-06-02. This migration codifies that state.
--
-- PREREQUISITE: public.current_org_id() must exist (defined in
--   products/core/backend/migrations/001_noctusai_core.sql, root-fixed 2026-06-02).
--
-- IDEMPOTENT: all policies use DROP POLICY IF EXISTS before CREATE POLICY.
--
-- SOURCE OF TRUTH: pg_policies on Supabase project nyplttplcoyiiqjrvtiw,
-- queried 2026-06-02.
-- ============================================================================

-- ----- adconnect.invitations -----
DROP POLICY IF EXISTS "invitations_select_own_org" ON adconnect.invitations;
CREATE POLICY "invitations_select_own_org" ON adconnect.invitations
  FOR SELECT TO authenticated
  USING (org_id = public.current_org_id());

-- ----- adconnect.categorias -----
DROP POLICY IF EXISTS "categorias_select_own_org" ON adconnect.categorias;
CREATE POLICY "categorias_select_own_org" ON adconnect.categorias
  FOR SELECT TO authenticated
  USING (org_id = public.current_org_id());

-- ----- adconnect.products -----
DROP POLICY IF EXISTS "products_select_own_org" ON adconnect.products;
CREATE POLICY "products_select_own_org" ON adconnect.products
  FOR SELECT TO authenticated
  USING (org_id = public.current_org_id());

-- ----- adconnect.precos_distribuidor -----
DROP POLICY IF EXISTS "precos_brand_admin_sees_all" ON adconnect.precos_distribuidor;
CREATE POLICY "precos_brand_admin_sees_all" ON adconnect.precos_distribuidor
  FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM adconnect.distributors d
      WHERE d.id = precos_distribuidor.distributor_id
        AND d.org_id = public.current_org_id()
    )
  );

-- ----- adconnect.promos -----
DROP POLICY IF EXISTS "promos_select_own_org" ON adconnect.promos;
CREATE POLICY "promos_select_own_org" ON adconnect.promos
  FOR SELECT TO authenticated
  USING (org_id = public.current_org_id());

-- ----- adconnect.relatorios_sellout -----
DROP POLICY IF EXISTS "sellout_brand_admin_sees_all" ON adconnect.relatorios_sellout;
CREATE POLICY "sellout_brand_admin_sees_all" ON adconnect.relatorios_sellout
  FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM adconnect.distributors d
      WHERE d.id = relatorios_sellout.distributor_id
        AND d.org_id = public.current_org_id()
    )
  );

-- ----- adconnect.carts -----
DROP POLICY IF EXISTS "carts_brand_admin_sees_all" ON adconnect.carts;
CREATE POLICY "carts_brand_admin_sees_all" ON adconnect.carts
  FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM adconnect.distributors d
      WHERE d.id = carts.distributor_id
        AND d.org_id = public.current_org_id()
    )
  );

-- ----- adconnect.pedidos -----
DROP POLICY IF EXISTS "pedidos_brand_admin_sees_all" ON adconnect.pedidos;
CREATE POLICY "pedidos_brand_admin_sees_all" ON adconnect.pedidos
  FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM adconnect.distributors d
      WHERE d.id = pedidos.distributor_id
        AND d.org_id = public.current_org_id()
    )
  );

-- ----- adconnect.regras_recompensa -----
DROP POLICY IF EXISTS "regras_select_own_org" ON adconnect.regras_recompensa;
CREATE POLICY "regras_select_own_org" ON adconnect.regras_recompensa
  FOR SELECT TO authenticated
  USING (org_id = public.current_org_id());

-- ----- adconnect.recompensas_acumuladas -----
DROP POLICY IF EXISTS "recompensas_brand_admin_sees_all" ON adconnect.recompensas_acumuladas;
CREATE POLICY "recompensas_brand_admin_sees_all" ON adconnect.recompensas_acumuladas
  FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM adconnect.distributors d
      WHERE d.id = recompensas_acumuladas.distributor_id
        AND d.org_id = public.current_org_id()
    )
  );

-- ----- adconnect.resgates_recompensa -----
DROP POLICY IF EXISTS "resgates_brand_admin_sees_all" ON adconnect.resgates_recompensa;
CREATE POLICY "resgates_brand_admin_sees_all" ON adconnect.resgates_recompensa
  FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM adconnect.distributors d
      WHERE d.id = resgates_recompensa.distributor_id
        AND d.org_id = public.current_org_id()
    )
  );

-- ----- adconnect.faturas -----
DROP POLICY IF EXISTS "faturas_brand_admin_sees_all" ON adconnect.faturas;
CREATE POLICY "faturas_brand_admin_sees_all" ON adconnect.faturas
  FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM adconnect.distributors d
      WHERE d.id = faturas.distributor_id
        AND d.org_id = public.current_org_id()
    )
  );
