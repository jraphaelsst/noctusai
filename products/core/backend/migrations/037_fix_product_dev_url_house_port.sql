-- ============================================================
-- 037 — Fix dev url_base to the single-container HOUSE port
-- ============================================================
-- The launcher tile's dev URL comes from public.products.url_base (when no
-- PRODUCT_URL_<SLUG>/PATTERN env override is set — i.e. in dev). Those rows
-- held the VESTIGIAL 2-container-era "frontend" port (e.g. social-wiring 8160)
-- instead of the single-container HOUSE port the container actually publishes
-- (social-wiring 8011 — the FIRST port in the start.sh
-- `slug:Name:HOUSE:OLD_FRONTEND` row). Result in dev: the noc dashboard tile
-- linked to a dead port → ERR_CONNECTION_REFUSED. (Prod is unaffected — the
-- PRODUCT_URL_<SLUG> env overrides url_base there.)
--
-- Set every product's url_base to its house port. Migration 036's INSERT used
-- the wrong (frontend) port for adconnect/dev-team; this corrects the live DB
-- and a fresh DB alike (runs after 036). Going forward, scaffold_product emits
-- the house port (backend_port) — see scaffold.py _emit_products_seed_row_migration.
--
-- Mirror to the live DB via Supabase MCP. Idempotent (plain UPDATEs).
-- ============================================================

UPDATE public.products SET url_base = 'http://localhost:8001' WHERE slug = 'erp-imobiliario';
UPDATE public.products SET url_base = 'http://localhost:8002' WHERE slug = 'personal-finance';
UPDATE public.products SET url_base = 'http://localhost:8003' WHERE slug = 'therapy-platform';
UPDATE public.products SET url_base = 'http://localhost:8005' WHERE slug = 'daily-life';
UPDATE public.products SET url_base = 'http://localhost:8007' WHERE slug = 'adconnect';
UPDATE public.products SET url_base = 'http://localhost:8009' WHERE slug = 'dev-team';
UPDATE public.products SET url_base = 'http://localhost:8011' WHERE slug = 'social-wiring';
UPDATE public.products SET url_base = 'http://localhost:8012' WHERE slug = 'knowledge-extractor';
