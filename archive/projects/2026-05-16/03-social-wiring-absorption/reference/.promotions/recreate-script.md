---
slug: recreate-script
origin:
  - scripts/recreate.sh
intended_noc_destination: templates/seed-workspace-docker/scripts/recreate.sh
layer_rationale: |
  Operator-facing infra script — belongs in
  `templates/seed-workspace-docker/scripts/` alongside `start.sh`,
  `stop.sh`, `refresh_cf_tunnel.sh`. Scaffolded into every new
  noc product workspace by `scaffold_product`.
seed_first_analysis: |
  Q1 — Cross-product candidate? YES. Every Docker-Compose-based
  product hits the "restart-doesn't-reload-env" trap. Lifting once
  saves every adopter from rediscovering it.
  Q2 — Variance? None. The script is generic over service names
  (compose handles the actual selection).
  Q3 — Existing seed coverage? None. The template ships
  `start.sh`/`stop.sh` but no recreate wrapper. The bare
  `docker compose up -d --force-recreate` syntax is non-obvious
  enough that operators reach for `restart` first.
  Q4 — Fake+Real? N/A (shell script).
  Q5 — Migration cost? Trivial — copy + commit.
  Q6 — Premature lift risk? Zero. This is pure operator
  ergonomics; no API surface.
dependencies_on_other_additions: []
promoted_on: not-yet
---

## Why this addition exists

Twice in one session (2026-05-13):

1. After pasting `META_APP_ID` + `META_APP_SECRET` into `.env`,
   `docker compose restart app` left the container with stale env —
   `/api/meta/status` returned `configured: false` until we used
   `--force-recreate` instead. The user was confused for a few
   minutes.
2. After pasting the WAHA API key, the WAHA container's running
   env was still empty until recreate. Same trap, second time.

Both are the same trap: `docker compose restart <svc>` keeps the
existing container (and its env baked in at creation). `.env`
changes are invisible to it. The Docker Compose docs note this but
most operators expect `restart` to be a "kick the tires" command
that picks up everything.

The fix is one line (`docker compose up -d --force-recreate
<svc>`) but it's the second word that's non-obvious. A wrapper
turns it into the obvious thing.

## Integration notes for noc-side

When promoting:

1. Move `scripts/recreate.sh` → `templates/seed-workspace-docker/scripts/recreate.sh`.
   Add to `scaffold_product`'s manifest so every new workspace
   inherits it.

2. Cross-reference from `start.sh` / `stop.sh` headers so operators
   discover it on first read: "If you've edited `.env`, use
   `./scripts/recreate.sh <svc>` (NOT `docker compose restart`)
   to pick up changes."

3. Add a "Common gotchas" section to the seed's
   `KB § PATTERNS/containerization.md` documenting the trap and
   pointing at the script.

4. If a future seed adopts a different orchestrator (Kubernetes,
   nomad, etc.), this script's behavior generalizes — same idea,
   different recreation primitive. The KB pattern doc captures the
   _principle_ ("env baked at creation"); the script is one
   implementation.

## Future work (NOT in this promotion)

- **Auto-detect .env changes** — a `.env`-watching wrapper that
  triggers recreate on save. Useful for active development; not
  worth the complexity for the seed.
- **Diff-driven recreate** — only recreate services whose env
  block (in docker-compose.yml) references variables that
  actually changed in `.env`. Avoids wasted recreates when the
  edit was unrelated to running services.
