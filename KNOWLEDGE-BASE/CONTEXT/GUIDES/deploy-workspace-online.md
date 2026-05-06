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

## The drill (4 steps)

### 1. Verify docker artifacts are present at the workspace root

After `noctus.dev.create_testing_ground` + `noctus.dev.scaffold_product` (since 2026-05-06), the workspace MUST have:

```
<workspace>/
├── Dockerfile               (backend image)
├── Dockerfile.frontend      (multi-stage Node 20 build → nginx serve)
├── docker-compose.yml       (services: app + frontend + redis + waha + tunnel-profile)
├── .dockerignore
└── .env.example
```

If any are missing, the workspace was bootstrapped before the docker convention landed. Re-run the bootstrap (idempotent — preserves local content):

```bash
bash $NOCTUSAI_HOME/scripts/bootstrap-seed-workspace.sh \
     --target $(pwd)
```

If a product was scaffolded *before* the docker files arrived, the placeholder substitution didn't run; surface this and either re-scaffold (last-resort) or substitute by hand using the recipe in `KB § PATTERNS/seed-workspace.md § Docker scaffolding`.

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

### 3. `docker compose up`

Pick the profile that matches what's being tested:

| Command | What runs | When to use |
|---|---|---|
| `docker compose up` | app + frontend + redis + waha | Default — full stack online |
| `docker compose --profile minimal up` | app + redis only | Backend smoke; frontend not needed |
| `docker compose --profile tunnel up` | full stack + cloudflared | OAuth callback testing — gives a public hostname so Google/Stripe/etc. will redirect |

Add `-d` to run detached; tail logs with `docker compose logs -f app` (or `frontend`).

### 4. Verify

| Check | Command / URL | Expected |
|---|---|---|
| Backend health | `curl localhost:<backend_port>/api/health` | `{"status": "ok", ...}` |
| Frontend renders | `http://localhost:<frontend_port>/` in browser | Login page or product landing |
| LLM wired | `docker compose logs app \| grep "LLM configured"` | Single line emitted at startup |
| DB schema bound | `docker compose logs app \| grep "schema="` | Schema name from `create_product_app` |

If `/api/health` returns 502 / connection-refused, `docker compose logs app` shows the import-time failure — usually a missing env var or a typo in `requirements.txt`.

---

## Anti-patterns

- **Hand-authoring `docker-compose.yml`** — the bootstrap drops the canonical version with placeholders; `scaffold_product` substitutes them. If the file doesn't exist or still has `{{PRODUCT_SLUG}}` literals, fix the seeding-system gap, don't hand-edit. Memory rule: `feedback_seed_workspace_docker_scaffolding`.
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
- `templates/seed-workspace-docker/` — the canonical files (source of truth — never edit the workspace copies in place).
