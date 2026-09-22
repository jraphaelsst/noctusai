-- ============================================================================
-- 051_product_scope_sync_trigger — the catalog toggle PUSHES the gate scope
-- ============================================================================
--
-- WHY (2026-09-22). `deploy/fleet/active-scope.txt` (the set every CI job,
-- keeper, hook and gate sweep checks) and `build-scope.txt` (the set whose
-- images get built) are git mirrors of `public.products.ativo` /
-- `deploy_scope`. A mirror that updates only when someone happens to commit or
-- remembers `--refresh-build-scope` is not a mirror: the user flips a product
-- asleep in /admin/products (or on the core dashboard card — same endpoints,
-- same hook, same rows) and expects it OUT of every gate from that moment, with
-- nobody working and nothing to remember.
--
-- WHAT. A statement-level trigger on `public.products` fires on any INSERT,
-- DELETE, or UPDATE of `ativo`/`deploy_scope` — whoever the writer is (FastAPI,
-- SQL editor, a migration). It computes the FULL resulting sets from the table
-- and sends them via `pg_net` as a GitHub `repository_dispatch`
-- (`product-scope-changed`). `.github/workflows/sync-product-scope.yml`
-- regenerates both files from that payload with the same generator as
-- `--refresh-build-scope` and commits them to `dev`. The payload carries the
-- whole state, not a delta, so a lost or reordered dispatch self-heals on the
-- next one. No database credential ever reaches GitHub.
--
-- SECRET. The GitHub token (fine-grained PAT: this repo only, "Contents:
-- Read and write" — the permission `repository_dispatch` requires) lives in
-- Supabase Vault as `github_product_scope_dispatch_token`, created by the user,
-- never in this file.
--
-- FAILURE IS NEVER SILENT, NEVER BLOCKING. A toggle must never fail because
-- GitHub is unreachable, so the trigger does not raise. A missing secret
-- raises a WARNING (Postgres log), `pg_net` records every response in
-- `net._http_response`, and `noctus.dev.product_scope_report` compares the
-- live catalog with the checked-in file and flags `STALE` — the backstop that
-- makes any lost dispatch visible.
--
-- KB § PATTERNS/architect/product-working-scope.md § 4c.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;

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
  AFTER INSERT OR DELETE OR UPDATE OF ativo, deploy_scope
  ON public.products
  FOR EACH STATEMENT
  EXECUTE FUNCTION public.dispatch_product_scope_sync();
