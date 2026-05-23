# `deploy/services/` — raw replacement for Coolify-managed services

Coolify currently runs **n8n + waha + postgres + redis** on the VPS and serves
`n8n.noctusai.com` / `waha.noctusai.com` through its Traefik proxy. We are
**dropping Coolify entirely**, so these services move to plain `docker compose`
(this folder) and routing moves to the **Cloudflare named tunnel** (`../tunnel/`).

The win: the new containers attach to the **existing Coolify data volumes**
(`external: true`), so **n8n workflows + the WhatsApp pairing survive** the swap.

## The swap (run ON the VPS, in this folder)

```bash
# 1. Capture the live secrets BEFORE removing anything:
cp .env.services.example .env.services
docker inspect postgres-r8co0gwsw8g4gggcc0sko8ko --format '{{range .Config.Env}}{{println .}}{{end}}' | grep POSTGRES_PASSWORD
docker inspect waha-r8co0gwsw8g4gggcc0sko8ko     --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E 'WHATSAPP_API_KEY|WAHA_DASHBOARD'
# → paste values into .env.services

# 2. Stop ONLY the Coolify-managed app containers (data stays in the volumes):
docker stop n8n-r8co0gwsw8g4gggcc0sko8ko waha-r8co0gwsw8g4gggcc0sko8ko \
            postgres-r8co0gwsw8g4gggcc0sko8ko redis-r8co0gwsw8g4gggcc0sko8ko

# 3. Bring up the raw equivalents on the SAME volumes + noctus-net:
docker compose --env-file .env.services -f compose.services.yml up -d

# 4. Verify:
docker compose -f compose.services.yml ps
docker exec -it $(docker ps -qf name=noctus-services-n8n) wget -qO- localhost:5678/healthz || true
```

> **Routing note.** Until the Cloudflare tunnel serves `n8n`/`waha`.noctusai.com,
> these are reachable only inside `noctus-net` (and any published host port). Public
> URLs resume when `../tunnel/` is live. That is the one coupling between the Coolify
> teardown and the domain/DNS step.

## Final Coolify teardown (LAST step, after the tunnel is verified)

```bash
docker rm -f n8n-r8co0gwsw8g4gggcc0sko8ko waha-r8co0gwsw8g4gggcc0sko8ko \
             postgres-r8co0gwsw8g4gggcc0sko8ko redis-r8co0gwsw8g4gggcc0sko8ko
docker rm -f coolify coolify-proxy coolify-db coolify-redis coolify-realtime coolify-sentinel
# then uninstall Coolify per its docs; the r8co0… DATA volumes are kept.
```

## Open verification before teardown
- **What uses postgres?** n8n here is SQLite-backed (no `DB_POSTGRESDB_*`). Confirm
  whether any DB in `pgdata` is live (`docker exec … psql -U default -l`) before relying on it.
- The `*_NO_PASSWORD` WAHA flags from the Coolify env were dashboard toggles — re-add only if the dashboard behaves differently.
