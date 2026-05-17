---
slug: single-url-tunnel
origin:
  - proxy/nginx.conf
  - products/youtube-crawler/frontend/nginx/default.conf
  - products/youtube-crawler/frontend/src/lib/apiBase.ts
intended_noc_destination:
  - templates/seed-workspace-docker/proxy/nginx.conf
  - templates/product-seed/frontend/nginx/default.conf
  - templates/product-seed/frontend/src/lib/apiBase.ts
layer_rationale: |
  Six-layer model: these are workspace/template infrastructure
  fragments, not domain code. They belong in the seed-workspace
  scaffolding so any new noctusai product inherits:
    - SPA fallback nginx for the frontend container
    - Reverse-proxy that fronts backend + frontend + WAHA + (future)
      additional services on one URL
    - Runtime-smart apiBase() so the same build artifact works in
      local-dev (8150), proxied (8090), and tunnel modes
seed_first_analysis: |
  Q1 — Cross-product candidate? YES. Every noctusai product with a
  frontend + tunnel-friendly backend benefits from single-URL
  routing. Each separately-tunneled product would otherwise pollute
  the OAuth-callback whitelist and confuse operators.
  Q2 — Variance across consumers? Routing rules per-product (which
  paths go to which upstreams) differ, but the SHAPE is identical.
  Could be a templated nginx.conf with placeholders for service names.
  Q3 — Existing seed coverage? None — the seed-workspace template
  ships only the backend + frontend + DB + (optional) waha; no
  unified proxy.
  Q4 — Fake+Real shape? n/a — pure infra config.
  Q5 — Migration cost? Low — drop the proxy/ folder into the
  template, add the proxy service to seed-workspace-docker/
  docker-compose.yml, repoint tunnel.
  Q6 — Risk of premature seed lift? Low. The shape is stable
  (matches the canonical "nginx in front of N upstreams" pattern).
dependencies_on_other_additions: []
promoted_on: not-yet
---

## Why this addition exists

The product had a tunnel for the backend but not the frontend, so
demoing the chat UI from a phone or showing it to anyone off the
laptop required two separate tunnels or a bunch of port-forwarding
gymnastics. Also `localhost:8150/chat` was returning a hard 404
because the frontend's nginx had no SPA fallback for React Router
routes.

This addition unifies everything: one reverse-proxy service on port
8090 fronts backend (`/api/*`), frontend (`/*`), and WAHA
(`/waha/*`). The Cloudflare Quick Tunnel points at that proxy, so a
single `https://<random>.trycloudflare.com` URL serves the entire
stack with path-based routing.

## Integration notes for noc-side

When promoting:

1. Move `proxy/nginx.conf` into the seed-workspace-docker template
   under `proxy/nginx.conf.template`, parametrizing the upstream
   names (`{{BACKEND_SERVICE}}:{{BACKEND_PORT}}` etc.).
2. Move `products/youtube-crawler/frontend/nginx/default.conf`
   into the product-seed template under `frontend/nginx/`.
3. Move `apiBase.ts` into the seed lib's frontend layer
   (`noctusai_lib/frontend/lib/apiBase.ts`) so every product
   imports the same helper instead of copy-pasting the URL
   resolution.
4. Update the workspace bootstrap (`bootstrap-seed-workspace.sh`)
   to add the `proxy` service to the generated docker-compose.yml
   when a frontend is present.
