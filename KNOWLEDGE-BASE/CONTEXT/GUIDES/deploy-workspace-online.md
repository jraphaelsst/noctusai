# Putting a workspace product online for testing

When the user says **"put X online"** / **"bring X up"** / **"deploy for testing"** / **"let me test it"** / **"spin up the stack"** in the context of a workspace product, this is the drill — already automated by the seeding system, no hand-authoring required.

> **Scope.** Local docker-compose stack for a sibling-workspace product (testing-ground / sandbox shape). **Out of scope:** noc-internal multi-product startup via `start.sh`, production cloud deploys, or any orchestration outside the single-workspace pattern.

---

## Prerequisites

- Workspace exists as a sibling of noc (has `.noctusai-workspace` marker at root, kind=`seed`).
- A product is scaffolded inside it (`products/<slug>/`).
- Docker + docker-compose v2 installed (`docker compose version` ≥ 2.0).
- Workspace's `.env` carries `NOCTUSAI_HOME=<absolute path to noc>` so the build can reach the seed packages via the `additional_contexts: noc` mechanism. See `KB § PATTERNS/seed-workspace.md § Docker scaffolding` for why.

---

## The drill (1 step — script-driven)

Since 2026-05-07 every workspace inherits a substituted **`./start.sh`** + **`./stop.sh`** at its root (placeholders patched by `noctus.dev.scaffold_product`). That collapses the deploy drill to:

```bash
cp .env.example .env       # first time only — fill in keys
./start.sh                 # full stack: app + frontend + redis + waha
```

Profiles: `./start.sh minimal` (app + redis), `./start.sh tunnel` (full + cloudflared).
Shutdown: `./stop.sh` (graceful), `./stop.sh --volumes` (wipe state), `./stop.sh --prune` (wipe state + images).

`start.sh` polls `/api/health` for up to 60s and prints the URLs + WAHA dashboard credentials on success; exits non-zero with last 50 backend log lines on failure.

---

## The drill (long-form — what start.sh does under the hood)

### 1. Verify docker artifacts are present at the workspace root

After `noctus.dev.create_testing_ground` + `noctus.dev.scaffold_product` (since 2026-05-06), the workspace MUST have:

```
<workspace>/
├── Dockerfile               (backend image)
├── Dockerfile.frontend      (multi-stage Node 20 build → nginx serve)
├── docker-compose.yml       (services: app + frontend + redis + waha + tunnel-profile)
├── .dockerignore
├── .env.example
├── start.sh                 (full stack up + health-poll + URL summary)
└── stop.sh                  (graceful / --volumes / --prune)
```

If any are missing, the workspace was bootstrapped before the docker convention landed. Re-run the bootstrap (idempotent — preserves local content):

```bash
bash $NOCTUSAI_HOME/scripts/bootstrap/bootstrap-seed-workspace.sh \
     --target $(pwd)
```

If a product was scaffolded *before* the docker files arrived, the placeholder substitution didn't run; surface this and either re-scaffold (last-resort) or substitute by hand using the recipe in `KB § PATTERNS/seed-workspace.md § Docker scaffolding`.

> **Convention.** `start.sh` and `stop.sh` are **inherited surface** — never hand-author them per workspace. Source of truth is `templates/seed-workspace-docker/{start,stop}.sh`; `bootstrap-seed-workspace.sh` copies them at workspace creation time and `scaffold_product` runs the placeholder substitution + restamps the executable bit. If the script is missing or stale, fix the template + bootstrap + scaffolder; do **not** patch the workspace copy in place.

### 2. Materialise `.env` from `.env.example`

```bash
cp .env.example .env
```

Then fill in:

| Section | Why it matters |
|---|---|
| **NOCTUSAI_HOME** | Required — Dockerfile's `additional_contexts: noc` resolves through it |
| **Supabase** (URL + anon + service-role) | Required — backend won't boot cleanly without |
| **LLM** (ANTHROPIC_API_KEY *or* OPENAI_API_KEY) | At least one — seed default-wires LLMConfig in lifespan |
| **WAHA** | Optional — empty `WAHA_BASE_URL` triggers `FakeWahaClient` fallback (logs-instead-of-sends, safe for dev) |
| **Product-specific** | Whatever the scaffold wrote to the brief — OAuth client IDs, encryption keys, SMTP creds, etc. |

The product's Settings → API Keys tab (when one exists) surfaces which keys are configured vs missing — agent can verify post-up by hitting `/api/settings/keys/status` (or the product's equivalent).

### 3. Bring the stack online

| Recipe | What runs | When to use |
|---|---|---|
| `./start.sh` | app + frontend + redis + waha | Default — full stack online (replaces `docker compose up -d --build`) |
| `./start.sh minimal` | app + redis only | Backend smoke; frontend not needed |
| `./start.sh tunnel` | full stack + cloudflared | OAuth callback testing — gives a public hostname so Google/Stripe/etc. will redirect |
| `docker compose up -d --build` (manual) | same as `./start.sh` but no health-poll/URL summary | Use ONLY when start.sh is missing on a pre-2026-05-07 workspace; then re-run bootstrap |

`start.sh` runs `docker compose up -d --build`, polls `/api/health` for up to 60s, prints the public URLs + WAHA dashboard credentials, and tails the last 50 lines of `docker compose logs app` if the backend doesn't come up. Tail logs at any time with `docker compose logs -f app`.

### 4. Verify

| Check | Command / URL | Expected |
|---|---|---|
| Backend health | `curl localhost:<backend_port>/api/health` | `{"status": "ok", ...}` |
| Frontend renders | `http://localhost:<frontend_port>/` in browser | Login page or product landing |
| LLM wired | `docker compose logs app \| grep "LLM configured"` | Single line emitted at startup |
| DB schema bound | `docker compose logs app \| grep "schema="` | Schema name from `create_product_app` |

If `/api/health` returns 502 / connection-refused, `docker compose logs app` shows the import-time failure — usually a missing env var or a typo in `requirements.txt`.

---

## Shutdown

`./stop.sh` is the companion to `start.sh` and follows the same inherited-surface convention.

| Recipe | Effect | When to use |
|---|---|---|
| `./stop.sh` | `docker compose down` (containers down, volumes + images preserved) | End of test session; restart with `./start.sh` keeps DB state |
| `./stop.sh --volumes` | + remove named volumes | Reset to clean state (DB / redis wiped) |
| `./stop.sh --prune` | + remove dangling local images | Reclaim disk before a major rebuild |
| `docker compose down` (manual) | same as `./stop.sh` | Pre-2026-05-07 workspace fallback |

Idempotent — already-stopped is a no-op.

### Noc-side counterpart

The repo root (`noc/`) has its own `start.sh` (multi-product uvicorn + vite under one venv) and a 2026-05-07 sibling **`./stop.sh`**. Same pattern, different mechanism: noc's stop.sh reads the `BEGIN/END_PRODUCTS_REGISTRY` block from `start.sh` so the registry has one writer (`scaffold_product`) and two readers (`start.sh` + `stop.sh`), and sweeps stale processes by port via `lsof -ti`.

| Recipe | Effect |
|---|---|
| `./stop.sh` | Kill processes on registered backend + frontend ports |
| `./stop.sh --venv` | + remove `venv/` (full python reset) |
| `./stop.sh --node` | + remove `products/*/frontend/node_modules` |
| `./stop.sh --all` | ports + venv + node_modules |

Use this when `start.sh` was backgrounded or run from another shell so `Ctrl+C` cannot reach the trap.

---

## Anti-patterns

- **Hand-authoring `docker-compose.yml`** — the bootstrap drops the canonical version with placeholders; `scaffold_product` substitutes them. If the file doesn't exist or still has `{{PRODUCT_SLUG}}` literals, fix the seeding-system gap, don't hand-edit. Memory rule: `feedback_seed_workspace_docker_scaffolding`.
- **Hand-authoring `start.sh` or `stop.sh`** — same as above. Source of truth is `templates/seed-workspace-docker/`. Workspace copies are derivative; fix the template, re-run bootstrap, do not edit in place.
- **`${NOCTUSAI_HOME}:${NOCTUSAI_HOME}:ro` bind-mount instead of `additional_contexts`** — works first build, breaks on subsequent rebuilds when noc paths change. The named context is the structural fix because Docker COPY does not follow directory symlinks at build time.
- **Skipping `.env` and relying on shell exports** — `docker compose` reads `.env` at compose-time only; `export FOO=bar; docker compose up` does NOT propagate `FOO` into the running container unless the compose file's `environment:` block declares it.
- **Running uvicorn directly on the host instead of through compose** — works for tight dev loops but skips redis + waha; the user almost always wants the *stack* online when they ask. Default to compose unless explicitly asked otherwise.
- **Committing `.env` to git** — `.env` is gitignored on every workspace by default; if it ever shows up in `git status`, treat it as a leak risk and check the gitignore wasn't broken.

---

## Trigger phrases (recognise → execute)

Treat any of these as *"run the drill above without further confirmation"* in the workspace context:

- "put X online" / "put it online"
- "bring X up" / "bring it up" / "spin up X"
- "deploy X for testing" / "deploy this"
- "let me test it" / "let me try it"
- "fire it up"
- "run the full stack"

Trigger phrases for shutdown (recognise → `./stop.sh`):

- "stop X" / "stop the stack" / "stop it"
- "bring X down" / "bring it down"
- "shut down X" / "kill the stack" / "tear it down"
- "deploy down" / "stop testing"

If the workspace state isn't drill-ready (missing docker files, no scaffold, no `.env.example`), surface what's missing + the recipe to fix it; do NOT try to deploy halfway.

---

## Possible future extensions

- **`noctus.dev.deploy` MCP tool** — wraps the drill: verifies artifacts, confirms `.env` health, runs `docker compose up -d`, polls `/api/health`, surfaces logs on failure. Would close the loop so the agent can deploy without shelling out.
- **Per-product `compose.override.yml`** — when a product needs an extra service (postgres, mongo, MinIO), drop a `compose.override.yml` in `products/<slug>/` and have the bootstrap link it from the workspace root. Not yet a recurrence (N=1, youtube-crawler doesn't need it).
- **CI smoke-test** — `docker compose up -d && curl health && docker compose down` in a GitHub Action so the docker convention itself stays green across noc changes.

---

See also:
- `KB § PATTERNS/seed-workspace.md § Docker scaffolding` — the structural layer (templates, bootstrap, scaffold patch step).
- `KB § GUIDES/new-product.md § Mandatory files from day one § item 9` — the docker artifacts as a day-one requirement.
- `templates/seed-workspace-docker/` — the canonical files (source of truth — never edit the workspace copies in place). Includes `start.sh` + `stop.sh` since 2026-05-07.
