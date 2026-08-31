-- ============================================================================
-- 009_repontar_org_para_noctusai.sql — P Studio
-- Schema: p_studio (+ leitura de public.organizations / public.noctus_users)
--
-- Aponta o P Studio para a organização `noctusai`, para que o dono da
-- plataforma entre no produto com a conta que já tem.
--
-- POR QUE. `public.noctus_users.org_id` é UMA coluna NOT NULL: um usuário
-- pertence a exatamente UMA organização. Depois que a `007` removeu o admin
-- de desenvolvimento, a org `P Studio` (`cb78914a-…`) ficou com ZERO membros —
-- e o convite (`team.invite`) exige um usuário já autenticado para ser
-- emitido. Ou seja: ninguém conseguia entrar, e não havia por onde começar.
--
-- Três saídas existiam. A escolhida foi (a), pelo dono, em 2026-08-18:
--   (a) repontar o produto para a org que o dono já tem  ← esta
--   (b) criar uma segunda conta dele dentro da org `P Studio`
--   (c) mover a conta dele para a org `P Studio` — recusada: ele perderia a
--       associação com `noctusai` e, com ela, o acesso a core/igig/orbity/
--       erp-imobiliario/social-wiring.
--
-- CONSEQUÊNCIA REGISTRADA, não escondida: quando o dono do estúdio (Cadu)
-- for convidado, ele cairá na org `noctusai`, que não é onde ele deveria
-- estar. Repontar de volta para uma org própria do estúdio é uma migration
-- futura — e ela precisará re-carimbar os dados que já existirem. Fazer isso
-- com 0 clientes e 0 lançamentos, como hoje, é barato; depois não é. Este
-- comentário existe para que a decisão não seja redescoberta como um bug.
--
-- Forward-only e idempotente. Não edita nenhuma migration já aplicada.
-- ============================================================================

SET search_path = p_studio, public;

DO $$
DECLARE
  org_noctus  UUID;
  org_antiga  UUID;
  movidas     INT := 0;
  n           INT;
  t           TEXT;
BEGIN
  SELECT id INTO org_noctus  FROM public.organizations WHERE slug = 'noctusai';
  SELECT id INTO org_antiga  FROM public.organizations WHERE slug = 'p-studio';

  -- Banco novo (ou plataforma sem a org `noctusai`): nada a fazer, e isso
  -- NÃO é erro — a 002 já criou a org do produto e os seeds estão corretos
  -- nela. Sair em silêncio aqui seria errado; sair dizendo por quê, não.
  IF org_noctus IS NULL THEN
    RAISE NOTICE 'P Studio 009: org `noctusai` não existe neste banco — '
                 'nada re-apontado (esperado num banco limpo).';
    RETURN;
  END IF;

  IF org_antiga IS NULL OR org_antiga = org_noctus THEN
    RAISE NOTICE 'P Studio 009: nada a mover (org de origem ausente ou já é a de destino).';
    RETURN;
  END IF;

  -- Re-carimba TODA tabela org-scoped do schema. Enumerar à mão convidaria a
  -- esquecer uma no dia em que uma tabela nova aparecer — e uma tabela
  -- esquecida some da tela sem erro nenhum, porque a RLS simplesmente não
  -- devolve a linha. Derivar do catálogo é o que não envelhece.
  FOR t IN
    SELECT c.relname
      FROM pg_class c
      JOIN pg_namespace ns ON ns.oid = c.relnamespace
      JOIN pg_attribute a  ON a.attrelid = c.oid
     WHERE ns.nspname = 'p_studio'
       AND c.relkind = 'r'
       AND a.attname = 'org_id'
       AND NOT a.attisdropped
     ORDER BY c.relname
  LOOP
    EXECUTE format(
      'UPDATE p_studio.%I SET org_id = $1 WHERE org_id = $2', t
    ) USING org_noctus, org_antiga;
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n > 0 THEN
      RAISE NOTICE 'P Studio 009: % linha(s) re-apontada(s) em p_studio.%', n, t;
      movidas := movidas + n;
    END IF;
  END LOOP;

  RAISE NOTICE 'P Studio 009: % linha(s) movidas de % para % (noctusai).',
               movidas, org_antiga, org_noctus;

  -- A org `P Studio` NÃO é apagada. Ela fica vazia e disponível para o dia em
  -- que o estúdio tiver a própria — e apagar uma linha de `organizations`
  -- num banco compartilhado por 13 produtos é exatamente o tipo de escrita
  -- larga que este projeto já aprendeu a não fazer de passagem.
END $$;
