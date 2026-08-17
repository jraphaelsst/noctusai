-- ============================================================================
-- 005_status_pagina_dev_visibility.sql — P Studio
-- Schema: p_studio (+ public para a função de papel)
--
-- A 001 criou `status_pagina` com UMA política de leitura:
--
--     CREATE POLICY status_pagina_select_producao ON p_studio.status_pagina
--       FOR SELECT USING (status = 'producao');
--
-- Ou seja: uma linha marcada `desenvolvimento` não é devolvida a NINGUÉM —
-- nem ao dono da organização. Como o frontend lê a tabela pelo cliente
-- Supabase autenticado, o RLS se aplica: qualquer `if (status ===
-- 'desenvolvimento')` no FE vira código morto, e a página simplesmente
-- desaparece da navegação sem erro, sem log, sem nada.
--
-- Esse é exatamente o defeito descrito em
-- `KB § PATTERNS/frontend/status-pagina-dev-visibility.md`, pego aqui pelo
-- keeper `check_status_pagina_role_parity`. P Studio o herdou por ter sido
-- construído fora do noc: a 001 copiou o formato antigo do seed, anterior ao
-- fan-out que corrigiu a frota. É *epoch delta* de absorção, não um bug novo.
--
-- ⚠️ Nota honesta de escopo: hoje o frontend do P Studio **não lê**
-- `status_pagina` — nenhuma página é gated por ela ainda. Então isto não
-- desbloqueia nenhuma tela agora; corrige a metade SQL de um contrato de
-- duas metades ANTES de a outra metade existir, que é a hora barata de
-- fazer. Sem isto, a primeira página marcada `desenvolvimento` sumiria para
-- todo mundo e o sintoma ("a página não aparece") não apontaria para o RLS.
--
-- O FIX: uma SEGUNDA política de SELECT, aditiva. O Postgres faz OR entre
-- políticas permissivas, então isto só pode ALARGAR a visibilidade —
-- `status_pagina_select_producao` fica intocada.
--
-- FONTE DE PAPEL SEGURA: `public.noctus_users.org_role` via `auth.uid()`, a
-- mesma raiz de confiança de `public.current_org_id()`.
-- 🔴 NUNCA `user_metadata` — é spoofável pelo próprio usuário e não pode
-- chavear RLS (`KB § PATTERNS/backend/database-rls.md`).
--
-- Forward-only e idempotente (não existe CREATE POLICY IF NOT EXISTS, daí o
-- DROP antes). `current_org_role()` vive no schema `public` compartilhado e
-- já existe no banco vivo — o CREATE OR REPLACE aqui é idempotente e mantém
-- a migration auto-suficiente para um banco novo.
-- ============================================================================

SET search_path = p_studio, public;

CREATE OR REPLACE FUNCTION public.current_org_role()
  RETURNS text
  LANGUAGE sql
  STABLE SECURITY DEFINER
  SET search_path TO 'public'
AS $f$
  SELECT org_role FROM public.noctus_users WHERE id = (SELECT auth.uid());
$f$;

-- Aditiva: linhas `desenvolvimento` passam a ser legíveis por dev/owner/admin.
-- `TO authenticated` é obrigatório — anon não tem `auth.uid()`, logo
-- `current_org_role()` é NULL e `NULL = ANY(...)` é falso ⇒ zero linhas.
-- Escopo só em 'desenvolvimento'; 'desativado' continua invisível para todos.
DROP POLICY IF EXISTS "dev_veem_desenvolvimento" ON p_studio.status_pagina;
CREATE POLICY "dev_veem_desenvolvimento" ON p_studio.status_pagina
    FOR SELECT TO authenticated
    USING (
        status = 'desenvolvimento'
        AND public.current_org_role() = ANY (ARRAY['owner', 'dev', 'admin'])
    );

-- 🔴 CONTRATO DE PARIDADE: o array de papéis acima tem de ficar idêntico ao
-- const `DEV_ROLES` do frontend (`seed/lib/frontend/src/roles.ts`). Não há
-- fonte compartilhada entre este literal SQL e aquele const TS hoje; manter
-- os dois em sincronia é contrato manual até um keeper cobrir isso.
