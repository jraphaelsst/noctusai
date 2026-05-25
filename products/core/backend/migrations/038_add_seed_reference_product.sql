-- 038_add_seed_reference_product.sql
--
-- Re-add the `seed` product row to public.products — REVERSES migration
-- 036 § 3 (which deleted it as "the product template, not a deployable
-- product"). That premise changed: `products/seed/` is now a FIRST-CLASS
-- RUNNING product — the canonical living reference + a CANARY. It builds
-- and runs like any house product (single container, uvicorn serves
-- API+SPA on house port 8004) and deploys to prod at seed.noctusai.com.
-- "Break the seed → break all" already holds via code inheritance (every
-- product bakes noctusai_lib + noctusai_seed); this gives that coupling a
-- visible, testable living body on the dashboard.
--
-- url_base = the single-container HOUSE port (8004 = FIRST port in the
-- start.sh `seed:Seed:8004:8100` row — what the container publishes), NOT
-- the vestigial 2-container frontend port. Dev stays localhost by design;
-- prod overrides per-product via PRODUCT_URL_SEED env (set on the VPS) —
-- see KB § PATTERNS/core-url-routing.md (launcher→product layer) +
-- the feedback_product_url_base_house_port memory.
--
-- Idempotent: ON CONFLICT (slug) DO UPDATE re-applies cleanly whether the
-- row is absent (post-036) or a stale one lingers.

INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo)
VALUES
    ('Seed (Reference)', 'seed',
     'Canonical living reference — the minimal seed skeleton every product is built from. A running canary: if the seed breaks, this app breaks first, before any real product.',
     'Sprout', 'http://localhost:8004', '#22c55e', true)
ON CONFLICT (slug) DO UPDATE SET
    nome      = EXCLUDED.nome,
    descricao = EXCLUDED.descricao,
    icone     = EXCLUDED.icone,
    url_base  = EXCLUDED.url_base,
    cor       = EXCLUDED.cor,
    ativo     = EXCLUDED.ativo;
