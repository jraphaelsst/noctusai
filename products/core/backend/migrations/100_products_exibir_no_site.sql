-- 100: products.exibir_no_site — the noctusai.com showcase mirrors the live catalog.
--
-- (098 is claimed by feat/nosnolimiar-rename.)
--   1. public.products.exibir_no_site boolean NOT NULL DEFAULT true
--      -- the site lists every product in the catalog (paused ones as "lista de espera");
--      this flag is the owner's per-product opt-out. Edited via PATCH /api/products/{id}.
--   2. Internal and single-client builds are hidden from the site; commercial products default
--      to visible. Owner-approved 2026-11-07: seed, monica (single-client CRM),
--      academia-de-reciclagem (client), p-studio (client), dev-team, knowledge-extractor.
--   3. products_scope_sync trigger also fires on exibir_no_site, nome, descricao, icone, and the
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
 WHERE slug IN ('seed', 'monica', 'academia-de-reciclagem', 'p-studio',
                'dev-team', 'knowledge-extractor')
   AND exibir_no_site;

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
                          'slug', slug, 'nome', nome, 'descricao', descricao, 'icone', icone,
                          'ativo', ativo, 'deploy_scope', deploy_scope) ORDER BY slug), '[]'::jsonb)
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
  AFTER INSERT OR DELETE OR UPDATE OF ativo, deploy_scope, exibir_no_site, nome, descricao, icone
  ON public.products
  FOR EACH STATEMENT
  EXECUTE FUNCTION public.dispatch_product_scope_sync();
