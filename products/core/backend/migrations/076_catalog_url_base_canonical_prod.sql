-- Migration: catalog_url_base_canonical_prod
-- Schema: public
--
-- WHY (2026-10-10, measured read-only in prod). public.products.url_base for
-- igig, seed, social-wiring, orbity and p-studio was `http://localhost:80xx`:
-- the seed-row migrations (and scaffold_product's emitter) wrote localhost
-- "by design", relying on noctus-core's PRODUCT_URL_<SLUG> env overrides to
-- win in resolve_product_url. Any consumer that reads the column directly
-- (the resolver's final fallback, the SSO probe, a missing env var) got a
-- dead localhost URL. url_base is now the canonical prod URL; the emitter
-- derives it the same way (noctusai_lib.config.product_urls.canonical_prod_url).
--
-- COUPLING. core's deployment-status probe parsed the container HOUSE port
-- out of url_base. A canonical https URL has no port, so the port gets its own
-- column, backfilled from start.sh's registry BEFORE url_base is rewritten.
--
-- SAFETY. Idempotent. The url_base UPDATE only touches rows still on a
-- localhost URL (never overwrites a non-localhost value). Triggers: 075
-- (BEFORE UPDATE) only checks transitions INTO live and NULLs the SSO stamp on
-- non-live rows -- a url_base-only update on a live row passes; orbity and
-- p-studio are 'dev' so the NULLing is a no-op. 051 (scope sync) is
-- `AFTER ... UPDATE OF ativo, deploy_scope`, so it does not fire here.
SET search_path = public, public;

ALTER TABLE public.products
  ADD COLUMN IF NOT EXISTS house_port integer;

-- House ports = FIRST port of each start.sh PRODUCTS row. Fill only NULLs.
UPDATE public.products SET house_port = CASE slug
    WHEN 'erp-imobiliario'        THEN 8001
    WHEN 'personal-finance'       THEN 8002
    WHEN 'therapy-platform'       THEN 8003
    WHEN 'seed'                   THEN 8004
    WHEN 'daily-life'             THEN 8005
    WHEN 'adconnect'              THEN 8007
    WHEN 'dev-team'               THEN 8009
    WHEN 'orbity'                 THEN 8010
    WHEN 'social-wiring'          THEN 8011
    WHEN 'knowledge-extractor'    THEN 8012
    WHEN 'igig'                   THEN 8013
    WHEN 'p-studio'               THEN 8014
    WHEN 'academia-de-reciclagem' THEN 8015
    WHEN 'agents'                 THEN 8016
    WHEN 'community'              THEN 8017
    WHEN 'store'                  THEN 8018
  END
 WHERE house_port IS NULL
   AND slug IN ('erp-imobiliario','personal-finance','therapy-platform','seed',
                'daily-life','adconnect','dev-team','orbity','social-wiring',
                'knowledge-extractor','igig','p-studio','academia-de-reciclagem',
                'agents','community','store');

UPDATE public.products SET url_base = CASE slug
    WHEN 'igig'          THEN 'https://igig.noctusai.com'
    WHEN 'seed'          THEN 'https://seed.noctusai.com'
    WHEN 'social-wiring' THEN 'https://social.noctusai.com'
    WHEN 'orbity'        THEN 'https://orbity.noctusai.com'
    WHEN 'p-studio'      THEN 'https://p-studio.noctusai.com'
  END
 WHERE slug IN ('igig','seed','social-wiring','orbity','p-studio')
   AND url_base LIKE 'http://localhost%';
