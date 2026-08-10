# Tunnel ingress — a canonical file nothing derives from is a comment, not a contract

**What it is.** `deploy/tunnel/ingress.yml` is the declared single source of truth for public `hostname → in-network service` routing. This pattern is what makes that claim *true*: a renderer (`noctus.dev.tunnel_config`), a pre-commit keeper (`check_tunnel_ingress_snapshot_sync`) for the in-repo derived artifact, and an SSH drift check for the live one.

## The incident — 2026-08-10, publishing igig

`ingress.yml`'s first line has said **"SINGLE SOURCE OF TRUTH"** since 2026-05-21, and `config.yml.template` has said its `ingress:` block is "generated from ingress.yml". Neither was ever mechanised. Three failures compounded:

1. **The live config was somewhere else entirely.** `compose.tunnel.yml` mounts **`./`**, so the running config is whatever directory the tunnel was brought up from. On the VPS that was `projects/production-deploy-migration/deploy/tunnel/` — a gitignored, deploy-local copy. Adding igig's route to the canonical file changed **nothing live, silently**; the route had to be hand-patched into the deploy-local copy with `sed`.
2. **The in-repo snapshot had drifted too.** `config.yml.template`'s `ingress:` block was **two routes stale** (`igig`, `orbity`) — nothing compared it to `ingress.yml`.
3. **Five products had no DNS at all.** `daily-life`, `adconnect`, `dev-team`, `personal-finance`, `therapy-platform` were deployed and healthy but had no CNAME — edge NXDOMAIN. `route-dns.sh` exists precisely to fix that and had not been run since it was written.

This is the **hand-maintained-list** failure mode already gated elsewhere in this repo (`KB § PATTERNS/devops/product-lockfile-and-slug-drift.md`), wearing a different hat: the list here was "canonical" by assertion only.

## The intended layout — `.gitignore` already said so

```
**/tunnel/config.yml     # "so a `git pull` can NEVER touch the live tunnel config"
**/tunnel/*.json         # cloudflared credentials — a SECRET, deploy-local
```

Both live files are gitignored **inside the repo's own `deploy/tunnel/`**. That is the design: config and credentials sit next to `ingress.yml`, untracked, so a pull cannot clobber them and a secret cannot be committed. The `projects/…` copy was never a deliberate choice — it was the drift. Migrated back on 2026-08-10.

## The three legs

| Leg | Where it runs | What it catches |
|---|---|---|
| `tunnel_config action='render'` | offline, pure | the `ingress:` block, **catch-all last by construction** |
| `check_tunnel_ingress_snapshot_sync` | pre-commit | the committed `config.yml.template` drifting from `ingress.yml` |
| `tunnel_config action='check'` | SSH, read-only | the **live** VPS config drifting from `ingress.yml` |

The split is deliberate and stated rather than left as an unspoken gap: a pre-commit hook cannot see the VPS, so the local keeper covers the in-repo artifact and the SSH check covers the running one. `action='apply' confirm=True` backs up, rewrites and restarts — and **refuses to drop a live hostname** `ingress.yml` does not declare, because a silently removed route is an outage.

## Operational footgun — file ownership, learned the hard way

`cloudflared` runs as uid **65532** (distroless, non-root). Copying the credentials JSON as root yields `root:root 0600` and the tunnel crash-loops with `permission denied`, which surfaces at the edge as **Cloudflare 530** across every hostname. This caused a ~60-second full-edge outage during the 2026-08-10 migration. Always:

```bash
chown 65532:65532 deploy/tunnel/<TUNNEL_ID>.json && chmod 600 deploy/tunnel/<TUNNEL_ID>.json
```

The failure is loud and fast (`docker logs noctus-tunnel` says it in one line), but only if you actually probe the edge after a tunnel change — verify, don't assume.

## `deploy/tunnel/` is a TRACKED directory holding untracked secrets

Three artifacts live there and all three must stay gitignored:

| File | What it is | Ignored by |
|---|---|---|
| `config.yml` | the live cloudflared config | `**/tunnel/config.yml` |
| `<TUNNEL_ID>.json` | per-tunnel credentials | `**/tunnel/*.json` |
| `cert.pem` | **zone-scoped** origin certificate | `**/tunnel/cert.pem` (added 2026-08-10) |

`cert.pem` was uncovered until 2026-08-10 — caught **before** `cloudflared tunnel login` was run, not after. It is strictly more powerful than the tunnel credentials JSON: the JSON proves which tunnel you are, `cert.pem` can create or modify DNS for the **entire zone**. A `tunnel login` on the VPS drops it right next to `ingress.yml` in a tracked directory. Pinned by `TestTunnelSecretsAreGitignored`, which asserts all three via `git check-ignore` rather than trusting the file to stay correct.

## DNS is a separate, human-gated step

Routing and DNS are two different artifacts. `route-dns.sh <TUNNEL_NAME>` reads hostnames straight from `ingress.yml` and creates the proxied CNAMEs — idempotent, safe to re-run. It requires the **zone-scoped `cert.pem`** from `cloudflared tunnel login`, which is an interactive browser flow and is deliberately **not** wired into any auto-deploy path: creating public DNS is outward-facing and stays a human action. An agent with only the tunnel credentials JSON cannot do it, and should say so rather than improvise.

## Composes with

- [`product-lockfile-and-slug-drift`](product-lockfile-and-slug-drift.md) — same failure mode (derive, don't sync by hand), different surface.
- [`prod-exposure-consent`](prod-exposure-consent.md) — `ingress.yml` is one of the three prod-exposure surfaces; adding a hostname there is part of the promotion decision.
- [`dev-prod-parity`](dev-prod-parity.md) — the live-vs-declared split this pattern closes for the edge.

## CLI / MCP

```bash
python mcp/noctusai/cli.py --check-tunnel-ingress-snapshot-sync
```

- `noctus.dev.tunnel_config(action='render'|'check'|'apply', ssh_host=…, live_path=…, confirm=…)`

## History

- **2026-08-10** — Shipped while publishing igig. Renderer + keeper + SSH drift check + 14 regression tests; template regenerated (was 2 routes stale); the live tunnel migrated off the `projects/…` deploy-local copy back to `deploy/tunnel/`, where `.gitignore` always intended it.
