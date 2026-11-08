-- 105: products.exibir_no_site — the noctusai.com showcase mirrors the live catalog.
--
-- (098 is claimed by feat/nosnolimiar-rename.)
--   1. public.products.exibir_no_site boolean NOT NULL DEFAULT true
--      -- the site lists every product in the catalog (paused ones as "lista de espera");
--      this flag is the owner's per-product opt-out. Edited via PATCH /api/products/{id}.
--   2. Internal builds are hidden from the site; everything else defaults to visible.
--      Owner-approved 2026-11-07 (Q20): hidden = seed, monica, dev-team, knowledge-extractor.
--      academia-de-reciclagem and p-studio stay VISIBLE (15 products on the site).
--   2b. public.products.descricao_publica text NULL -- the site-facing description. The internal
--      `descricao` NEVER reaches the public projection (Q21). NULL = the FE shows
--      "Descrição não informada.". Seeded below (pt-BR copy owner-approved) only where still NULL;
--      orbity stays NULL on purpose. The admin path refuses turning exibir_no_site ON for a row
--      with an empty descricao_publica; rows already visible at migration time are not blocked.
--      Also fixes the personal-finance display name ("Finanças Pessoais").
--   3. public.products.destaque_no_site smallint NULL -- the 6 products FEATURED on the landing
--      (position = display order; the rest sit behind "Ver todos os produtos"). CHECK 1..6,
--      partial UNIQUE on the position, and CHECK (destaque_no_site IS NULL OR exibir_no_site) so a
--      hidden product cannot be featured. The admin write path refuses a duplicate/7th/hidden
--      entry in pt-BR BEFORE the write (no silent swap); these constraints are the backstop.
--      Initial positions (owner picks, will adjust): 1 agents, 2 social-wiring, 3 erp-imobiliario,
--      4 commerce, 5 therapy-platform, 6 igig -- seeded only while NOTHING is featured yet.
--   4. products_scope_sync trigger also fires on exibir_no_site, destaque_no_site, nome, descricao,
--      descricao_publica, icone, and the
--      dispatch carries the site catalog projection NESTED under the single key `site_catalog`
--      (GitHub repository_dispatch client_payload allows max 10 top-level keys; we use 5).
--      Redefinition of the function from 051; same Vault secret, same non-blocking failure mode.
-- Backward-compatible with the previous image (additive column; trigger payload only gains a key).
-- Re-runnable.
SET search_path = public, public;
SET lock_timeout = '5s';

ALTER TABLE public.products
    ADD COLUMN IF NOT EXISTS exibir_no_site boolean NOT NULL DEFAULT true;

UPDATE public.products SET exibir_no_site = false
 WHERE slug IN ('seed', 'monica', 'dev-team', 'knowledge-extractor')
   AND exibir_no_site;

ALTER TABLE public.products ADD COLUMN IF NOT EXISTS descricao_publica text;

UPDATE public.products p
   SET descricao_publica = v.txt
  FROM (VALUES
    ('agents', 'Agentes de IA que atendem e qualificam os seus leads no WhatsApp. Você liga e desliga cada um quando quiser.'),
    ('social-wiring', 'Para imobiliárias: leads, funil, imóveis e contratos num só lugar, com atendimento por IA no WhatsApp.'),
    ('academia-de-reciclagem', 'Conteúdos e trilhas de um projeto de educação ambiental, organizados para consulta.'),
    ('adconnect', 'Um lugar para empresas comprarem e venderem espaços de publicidade.'),
    ('commerce', 'Loja virtual com pedidos, estoque e gestão no mesmo sistema.'),
    ('community', 'Área de membros e grupos de WhatsApp para quem vende acesso a uma comunidade.'),
    ('daily-life', 'Tarefas, metas, hábitos e agenda pessoal num só aplicativo.'),
    ('erp-imobiliario', 'CRM, funil de vendas, financeiro e documentos para imobiliárias.'),
    ('personal-finance', 'Contas, orçamento e investimentos da sua vida pessoal num só lugar.'),
    ('igig', 'Gestão de agência de comunicação, da criação ao financeiro.'),
    ('p-studio', 'Gestão de estúdio de fotografia: captações, produção e cobrança.'),
    ('pilates', 'Agenda de aulas, alunos e mensalidades para estúdios de pilates.'),
    ('therapy-platform', 'Sessões por vídeo, agenda, prontuário e financeiro para terapeutas.'),
    ('store', 'Página de vendas de produtos digitais com pagamento online.')
  ) AS v(slug, txt)
 WHERE p.slug = v.slug
   AND p.descricao_publica IS NULL;

UPDATE public.products SET nome = 'Finanças Pessoais'
 WHERE slug = 'personal-finance' AND nome IS DISTINCT FROM 'Finanças Pessoais';

ALTER TABLE public.products ADD COLUMN IF NOT EXISTS destaque_no_site smallint;

ALTER TABLE public.products DROP CONSTRAINT IF EXISTS products_destaque_no_site_range;
ALTER TABLE public.products ADD CONSTRAINT products_destaque_no_site_range
    CHECK (destaque_no_site IS NULL OR destaque_no_site BETWEEN 1 AND 6);

ALTER TABLE public.products DROP CONSTRAINT IF EXISTS products_destaque_requires_exibir;
ALTER TABLE public.products ADD CONSTRAINT products_destaque_requires_exibir
    CHECK (destaque_no_site IS NULL OR exibir_no_site);

CREATE UNIQUE INDEX IF NOT EXISTS products_destaque_no_site_uniq
    ON public.products (destaque_no_site) WHERE destaque_no_site IS NOT NULL;

UPDATE public.products p
   SET destaque_no_site = v.pos
  FROM (VALUES ('agents', 1), ('social-wiring', 2), ('erp-imobiliario', 3),
               ('commerce', 4), ('therapy-platform', 5), ('igig', 6)) AS v(slug, pos)
 WHERE p.slug = v.slug
   AND p.exibir_no_site
   AND NOT EXISTS (SELECT 1 FROM public.products WHERE destaque_no_site IS NOT NULL);

CREATE OR REPLACE FUNCTION public.dispatch_product_scope_sync()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
  _token text;
  _payload jsonb;
BEGIN
  SELECT decrypted_secret INTO _token
    FROM vault.decrypted_secrets
   WHERE name = 'github_product_scope_dispatch_token'
   LIMIT 1;

  IF _token IS NULL OR _token = '' THEN
    RAISE WARNING 'product scope sync: Vault secret github_product_scope_dispatch_token is missing — deploy/fleet/active-scope.txt will NOT follow this change (see migration 051)';
    RETURN NULL;
  END IF;

  _payload := jsonb_build_object(
    'event_type', 'product-scope-changed',
    'client_payload', jsonb_build_object(
      'active', (SELECT coalesce(jsonb_agg(slug ORDER BY slug), '[]'::jsonb)
                   FROM public.products WHERE ativo),
      'live',   (SELECT coalesce(jsonb_agg(slug ORDER BY slug), '[]'::jsonb)
                   FROM public.products WHERE ativo AND deploy_scope = 'live'),
      -- Nested on purpose: ONE top-level key for the whole site projection.
      'site_catalog', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                          'slug', slug, 'nome', nome, 'descricao_publica', descricao_publica, 'icone', icone,
                          'destaque_no_site', destaque_no_site, 'ativo', ativo, 'deploy_scope', deploy_scope) ORDER BY slug), '[]'::jsonb)
                   FROM public.products WHERE exibir_no_site),
      'op',     TG_OP,
      'at',     to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
    )
  );

  PERFORM net.http_post(
    url     := 'https://api.github.com/repos/jraphaelsst/noctusai/dispatches',
    body    := _payload,
    headers := jsonb_build_object(
      'Authorization',        'Bearer ' || _token,
      'Accept',               'application/vnd.github+json',
      'X-GitHub-Api-Version', '2022-11-28',
      'User-Agent',           'noctus-product-scope-sync',
      'Content-Type',         'application/json'
    )
  );
  RETURN NULL;
END;
$$;

REVOKE ALL ON FUNCTION public.dispatch_product_scope_sync() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS products_scope_sync ON public.products;
CREATE TRIGGER products_scope_sync
  AFTER INSERT OR DELETE OR UPDATE OF ativo, deploy_scope, exibir_no_site, destaque_no_site, nome, descricao, descricao_publica, icone
  ON public.products
  FOR EACH STATEMENT
  EXECUTE FUNCTION public.dispatch_product_scope_sync();
