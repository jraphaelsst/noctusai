-- ============================================================
-- 045 — academia-de-reciclagem + agents: dev scope → live, prod URLs
-- ============================================================
-- HELD FOR CUTOVER. Do NOT apply before the M6 cutover runs: this row
-- change is what makes both products "live" for every catalog-driven
-- surface, and several of those surfaces are load-bearing:
--
--   * deploy/fleet/build-scope.txt is DERIVED from
--     `SELECT slug FROM public.products WHERE ativo = true AND
--     deploy_scope = 'live'` (mcp/noctusai/tools/noctus/dev/build_scope.py:111),
--     and `build-and-push.yml` REFUSES a slug listed there that is absent
--     from deploy/fleet/docker-compose.prod.yml. So applying this BEFORE
--     both services exist in the prod compose breaks the next build for
--     EVERY product, not just these two.
--   * noctus.dev.deploy_verify and sso_smoke use the same roster: a
--     catalog-live product with no running container reports as `missing`.
--
-- Mandatory cutover order (roadmap julia-agents-academia-2026-09, M6):
--   1. user consent recorded per slug (deploy/consent/<slug>.prod.yml)
--   2. agents + academia service blocks added to
--      deploy/fleet/docker-compose.prod.yml (copy the social-wiring block:
--      `<<: *prod-defaults`, ghcr image, expose, /api/health healthcheck)
--   3. hostnames added to deploy/tunnel/ingress.yml + DNS CNAMEs
--      (`cloudflared tunnel route dns <tunnel> <hostname>`), then
--      noctus.dev.tunnel_config action='apply'
--   4. product migrations applied in §F order (academia 006→009,
--      agents 006→009; social-wiring 105 and erp 046 already covered)
--   5. THIS migration
--   6. python mcp/noctusai/cli.py --refresh-build-scope (regenerates the
--      derived file; never hand-edit it)
--   7. build + deploy_image + deploy_verify + spa_smoke + sso_cors_smoke
--
-- The hostnames below are the user's decision (2026-09-15): short names,
-- matching the erp./social. convention already in ingress.yml.
--
-- Forward-only and idempotent: each UPDATE is scoped by slug and rewrites
-- only the two columns it owns.
-- ============================================================

UPDATE public.products
   SET deploy_scope = 'live',
       url_base     = 'https://academia.noctusai.com'
 WHERE slug = 'academia-de-reciclagem';

UPDATE public.products
   SET deploy_scope = 'live',
       url_base     = 'https://agents.noctusai.com'
 WHERE slug = 'agents';
