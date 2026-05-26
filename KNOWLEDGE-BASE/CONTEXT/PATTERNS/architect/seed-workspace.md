# Seed workspace — sibling symlink-consumer of noc

> **One-line rule:** Templates cannot modify noc.
>
> **Where this lives:** referenced from `CLAUDE.md §1` universal rules; full design here; mirrored in agent memory at `feedback_template_cannot_modify_noc.md`.

A **seed workspace** is a sibling folder to `noctusai/` that gives an agent or developer the *exact same operating surface* as working inside noc — same `CLAUDE.md` rules, same KB depth, same `.claude/` hooks/skills/permissions, same MCP toolkit, same `seed/` and `noctusai_lib/` — without duplicating any of those files. The template **points back** at noc's filesystem via symlinks; a single edit in noc propagates instantly. It is noc's methodology delivered to a workspace that isn't noc.

---

## When to use a seed workspace

Three intended use cases:

1. **Sandbox.** Throwaway experiments outside the monorepo while keeping noc's discipline (keeper, three-way sync, recurrence rule, seed-first, etc.). Agent operates by noc's rules; throwaway code never enters noc's git history.
2. **New-product staging.** Scaffold a new product against the symlinked `seed/` + `noctusai_lib/` so it is noc-compatible from line one. Promote when ready via the manifest.
3. **Parallel agent.** Run two Claude Code sessions — one with cwd in noc, one in template. They share the same rule surface (CLAUDE.md, KB, `.claude/` settings, MCP toolkit) via symlinks, with isolated git histories, isolated `projects/`, isolated `products/`, and zero file-collision risk.

When NOT to use a template:
- **Long-term per-product workspaces** with methodology evolution merged back to noc — that's the *deferred and abandoned* `methodology-mirror-and-workspaces` design (heavier 3-tier mirror + per-product fork-and-merge model). The seed workspace is the lighter consume-only alternative.
- **Multi-machine portability** — template is sibling-on-this-machine. Multi-machine wants a different design.
- **Editing noc's docs / methodology / seed from template** — strictly forbidden by Rule 1 below; do that work in noc.

---

## The hard rule — three layers of defense

**Templates cannot modify noc.** Filesystem permission games can't fully enforce this (same OS user owns both directories, and macOS symlinks ignore mode bits at the kernel level), so defense is layered:

### Layer 1 — Pre-commit hook (PRIMARY)

Template's `.githooks/pre-commit` (installed by bootstrap; activated via `git config core.hooksPath .githooks`) runs two rules on every staged path:

- **Rule 1 — read-only re: noc.** Refuses any staged path that resolves through one of the symlinked surfaces (CLAUDE.md, CLAUDE/, KNOWLEDGE-BASE/, .claude/, mcp/, seed/, noctusai_lib/, templates/). Edits to those belong in noc.
- **Rule 2 — separated additions are explicit.** Refuses any newly added path under the workspace (outside `sandbox/`, the marker, the README, .promotions/) without a matching `.promotions/<slug>.md` entry staged in the same commit.

Bypass with `git commit --no-verify` only when genuinely necessary (rare).

### Layer 2 — Documented rule (AGENT-LEVEL)

- `CLAUDE.md §1` carries a one-bullet universal rule pointing here.
- This KB doc carries the depth.
- Agent memory carries the working-agreement entry (`feedback_template_cannot_modify_noc.md`).
- Template's `README.md` carries a banner for humans browsing the workspace.

Agents read these files at session start; humans read the README. The rule is therefore alive across both surfaces.

### Layer 3 — chmod on symlinks (SYMBOLIC)

Bootstrap applies `chmod -h a-w` to each symlink entry in the workspace.

- **Linux:** mode bits on symlinks are mostly-ignored by the kernel; this is symbolic, not enforcing.
- **macOS:** symlinks ignore mode bits entirely — pure no-op.

**Treat this as a marker that the surface is read-only, not a guarantee.** The pre-commit hook is the actual write defense; chmod is an audit trail in case of casual exploration.

> **Why not chmod the symlink TARGETS in noc?** That would lock noc itself out of editing its own files (same OS user owns both). Tested and rejected during Phase 0 of the `seed-workspace` project. The realistic enforcement boundary is at commit-time, not write-time.

---

## Workspace layout

```
~/Documents/repository/NoctusAI/
├── noctusai/                           # source of truth
│   ├── CLAUDE.md
│   ├── CLAUDE/
│   ├── KNOWLEDGE-BASE/
│   ├── .claude/
│   ├── mcp/
│   ├── seed/
│   ├── noctusai_lib/
│   ├── templates/
│   ├── scripts/
│   │   └── bootstrap-seed-workspace.sh
│   └── .noctusai-workspace             # workspace_kind=primary
│
└── noctusai-template/                  # sibling — created by bootstrap
    ├── CLAUDE.md                       → symlink → noc/CLAUDE.md            [chmod -h a-w]
    ├── CLAUDE/                         → symlink → noc/CLAUDE/              [chmod -h a-w]
    ├── KNOWLEDGE-BASE/                 → symlink → noc/KNOWLEDGE-BASE/      [chmod -h a-w]
    ├── .claude/                        → symlink → noc/.claude/             [chmod -h a-w]
    ├── mcp/                            → symlink → noc/mcp/                 [chmod -h a-w]
    ├── seed/                           → symlink → noc/seed/                [chmod -h a-w]
    ├── noctusai_lib/                   → symlink → noc/noctusai_lib/        [chmod -h a-w]
    ├── templates/                      → symlink → noc/templates/           [chmod -h a-w]
    │
    ├── projects/                       # LOCAL — workspace's own projects
    ├── sandbox/                        # LOCAL — throwaway (no manifest required)
    ├── products/                       # LOCAL — staged products awaiting promotion
    ├── .promotions/                    # LOCAL — per-addition metadata
    ├── PROMOTIONS.md                   # LOCAL — index of .promotions/
    ├── .noctusai-workspace             # LOCAL — marker (workspace_kind=seed)
    ├── .noctusai-state/                # LOCAL — MCP per-workspace state (gitignored)
    ├── .env                            # LOCAL — NOCTUSAI_HOME pointer (gitignored)
    ├── .git/                           # LOCAL — own git repo
    ├── .gitignore
    ├── .githooks/pre-commit            # LOCAL — Rule 1 + Rule 2
    ├── README.md                       # LOCAL — conventions
    │
    ├── Dockerfile                      # LOCAL — backend image (placeholders patched at scaffold time)
    ├── Dockerfile.frontend             # LOCAL — frontend image (multi-stage: build + nginx)
    ├── docker-compose.yml              # LOCAL — full stack: app + frontend + redis + waha + tunnel
    ├── .dockerignore                   # LOCAL — excludes .git, symlinks, secrets, build artifacts
    ├── .env.example                    # LOCAL — env template (NOCTUSAI_HOME + Supabase + LLM + WAHA)
    ├── start.sh                        # LOCAL — full-stack up + health-poll + URL summary (chmod +x)
    └── stop.sh                         # LOCAL — graceful / --volumes / --prune (chmod +x)
```

---

## Why the inherited surface is not trimmed

> **One-line rule:** Seed workspaces inherit noc whole. Trim none of the 8 surfaces.

A natural instinct when scaffolding a new product is to *narrow* the inherited surface — strip the KB pages for products this workspace doesn't ship, drop memory entries about decisions in unrelated products, prune CLAUDE/ topical files that don't apply. **Resist that instinct.** The architecture is already designed to make trimming unnecessary, and trimming actively breaks methodology guarantees.

### The cost model the inheritance is built on

Auto-load weight is already minimal *by design*:

- **`CLAUDE.md` is a router.** Per its own §0: "What this file is NOT … rule body container." Sub-200-line surface, every line is a pointer.
- **`CLAUDE/<topic>.md` files are on-demand.** Loaded by agent discipline when §3 of `CLAUDE.md` says to (per "When to read what"). No topic = no load.
- **`KNOWLEDGE-BASE/` is on-demand depth.** A KB page enters context only when an agent opens it. Files never read = zero cost. The full KB symlink and a trimmed KB symlink have *identical* runtime weight for any given conversation.
- **`MEMORY.md` is an index.** One line per entry, ≤150 chars. Entry bodies live in their own files and load only on topic match (per `auto memory § How to access memories`).
- **`seed/` and `noctusai_lib/` are code.** Not auto-loaded into the agent's context — read by tooling (pytest, imports), not by reading-discipline budget.

The *one* surface where inheritance does add weight is **memory entry bodies** — and even there the budget is small (entries are short, focused, and load only when the agent's question matches the description).

### What trimming actually breaks

| Trim target | What breaks |
|---|---|
| KB pages for "other" products (`KB § backend/02-ERP.md`, etc.) | **Seed-first analysis** (`KB § GUIDES/seed-first-design.md`). §3a question 5 asks *"does the seam already exist in seed?"* — answering needs visibility into how other products solved it. Trim PF/ERP/Mailing → blind to absorbable patterns. |
| Per-product memory entries | **Triage-at-decision-time** (`KB § PATTERNS/common/accept-with-rationale.md`). The accept catalog accumulates *across* products by design; trimming a product's entries hides the precedent that informs the next decision. |
| Unrelated KB pattern docs (`PATTERNS/backend/whatsapp-chatbot-seed.md` if not used here) | **Pointer integrity.** KB pages cross-reference each other (`PATTERNS/backend/seed-fake-real-adapter.md` references `03-SEED-ARCHITECTURE.md`, etc.). Pruned pages leave dangling pointers that `noctus.dev.kb_sync` flags. |
| Other products' code (`products/<other-slug>/`) | **Recurrence-rule scans.** `noctus.dev.scan_cross_product_helpers` + `scan_within_product_helpers` + `scan_service_line_recurrence` walk *every* product to detect N≥2/N≥3 patterns. Trim → blind to the very duplications the rule exists to catch. The whole DRY recurrence rule (`KB § PATTERNS/architect/project-execution.md § 2.7`) becomes silent. |
| `CLAUDE/projects.md` / `CLAUDE/platform.md` | **Three-way sync.** Methodology rules live across three layers (KB + CLAUDE/topical + memory); pruning a topical file orphans the rules pointing into it. |
| Archived projects (`archive/projects/<date>/`) | **Phase-enrichment loop and historical rationale.** "Why did we decide X?" answers often live in archived `PROJECT.md` §11 change logs and `findings.md` files. Pruning makes the rationale unreachable; future seed-first analyses re-derive instead of inherit. |

### What IS legitimately product-specific (and gets *added*, not subtracted)

- `products/<slug>/MASTER-PROMPT.md` — the right place to surface "for this product, the relevant seed surfaces are X / Y / Z and the relevant patterns are A / B." This *focuses* attention without *removing* options. The agent still has the full surface; the MASTER-PROMPT just biases the on-demand reads.
- `products/<slug>/README.md` — product-specific developer setup.
- `products/<slug>/projects/<slug>/PROJECT.md` and `findings.md` — the project layer.
- The product's own backend/frontend code under `products/<slug>/`.

### Mental model

The seed workspace is **`noc + this product`**, not **`subset(noc) + this product`**. The "essentials" the user wants for a new product are not a subset of noc — they ARE noc, plus the product layer added on top. The cost concern that motivates trimming (auto-load weight, cognitive surface) is a real concern that's already solved by the *router + on-demand* split, not by pruning.

### How to apply

- When scaffolding a sibling workspace, accept the full 8-surface symlink set as-is. The bootstrap script intentionally takes no `--exclude` flags.
- When working on a single product, your *focus* mechanism is `MASTER-PROMPT.md` plus selective `Read`/`grep` discipline — not pre-emptive pruning.
- If an agent or human asks "should we trim X out of this workspace?", the answer is no, and the answer to "why?" is one of the four breakage rows above. Cite the specific row.
- Drive-by reduction during a project (e.g. "we don't need this KB page, let's delete it") is forbidden under the same rule that forbids `--no-verify` on commits: bypassing a safety mechanism to make a friction go away. Surface the friction; don't remove the safety.

### Anti-pattern history (lessons that drove this rule)

- *(Recorded 2026-05-06.)* Asked at YouTube-Crawler scaffold time: "shouldn't the KB and all docs be trimmed to fit only the new product?" Investigation showed the auto-load surface was already minimal (router-shaped), KB depth was on-demand (zero unread cost), and trimming would break four methodology guarantees with no offsetting benefit. The rule was formalized here so the next agent encountering the instinct gets the answer without re-deriving it.

---

## Marker file format

Plain-text key=value, one pair per line. Lines starting with `#` are comments; blank lines ignored.

```ini
# NoctusAI workspace marker — DO NOT EDIT.
workspace_kind=seed          # or "primary"
workspace_name=noctusai-template # human label
noctusai_home=/Users/rapha/Documents/repository/NoctusAI/noctusai
bootstrap_version=1
created_at=2026-05-03T03:14:00Z
```

The MCP toolkit's `mcp/noctusai/workspace.py` walks up from cwd looking for this file. Found → workspace context activated; not found → file-relative fallback to noc root.

**Both noc AND every template plant a marker.** Detection is uniform — no implicit "I must be in noc" fallback ambiguity.

---

## Promotion manifest

Every addition in the workspace that isn't sandbox throwaway gets a `.promotions/<slug>.md` entry with frontmatter:

```markdown
---
slug: <addition-slug>
origin: <workspace-relative-path>          # OR list: [path1, path2]
intended_noc_destination: <noc-relative-path>
layer_rationale: |
  Why this destination — invokes the seed-lib 6-layer model
  (KB § PATTERNS/architect/seed-lib-layout.md) when relevant.
seed_first_analysis: |
  Q1 ... Q2 ... Q3 ... Q4 ... Q5 ... Q6 ...
dependencies_on_other_additions: []         # OR list: [other-slug-1, other-slug-2]
promoted_on: not-yet                        # OR ISO date when promoted
---

## Why this addition exists
<prose>

## Integration notes for noc-side
<prose — what to wire up, what to test, what migrations to run>
```

`PROMOTIONS.md` at the workspace root is the index — but it is a **DERIVED artifact, never hand-maintained.** A hand-kept parallel index drifts: the social-wiring-absorption W0.2 audit found the originating workspace's hand-written `PROMOTIONS.md` listed only **7 of 14** manifests. The `.promotions/` directory is the single source of truth; `PROMOTIONS.md` is regenerated from it.

**Generation contract (mirrors `update-kb-counts.py` / `verify-kb-sync.sh`):**

- **Generator:** `noctus.dev.gen_promotions_index` — scans `.promotions/*.md`, reuses the canonical manifest parser from `mcp/noctusai/tools/noctus/dev/promotion.py` (so the index and `noctus.dev.promote_from_seed_workspace` never diverge on what a manifest means), and (re)emits `PROMOTIONS.md` as `Pending` / `Promoted` tables (slug · destination · readiness · promoted_on) between `<!-- promotions:start -->` / `<!-- promotions:end -->` markers. Prose outside the markers is preserved. Unparseable manifests are surfaced under a "Needs attention" section, never silently dropped.
- **`--check` mode** (`python mcp/noctusai/cli.py --gen-promotions-index --workspace . --check`) exits non-zero on drift — wired into the seed-workspace pre-commit hook as **Rule 3** (`templates/seed-workspace-pre-commit.sh`): a commit touching `.promotions/*.md` or `PROMOTIONS.md` is refused if the index is stale, with the regen command in the message.
- **Shipped by default by bootstrap:** `bootstrap-seed-workspace.sh` drops `.promotions/MANIFEST-TEMPLATE.md` (the per-capability manifest shape — author copies one file per promotable capability) + `.promotions/gen-index.py` (a self-contained generator copy, since `scripts/` is not a symlinked surface) and generates the initial `PROMOTIONS.md`. The generator copy stays DRY against noc by importing its parser from the symlinked `mcp/` surface.
- **Colocated test:** `mcp/noctusai/tests/test_gen_promotions_index.py` (regression-test-the-detector discipline; same `spec_from_file_location` convention as `test_render_history.py`).

Net effect: the absorption map is now an **automatic, derived** artifact of the seed-workspace scaffolding system — a future noc absorption is pre-mapped + drift-proof by construction, not by hand-discipline.

The `seed_first_analysis` block is filled at **addition time**, not at promotion time — invoking the six-question checklist at the moment of authorship surfaces design questions before the file's shape ossifies. Skipping this in the manifest is a design smell that the pre-commit hook does not catch (humans + agents enforce).

---

## MCP workspace-awareness

The MCP toolkit at `mcp/noctusai/` ships from noc and is symlinked into every template — same code, same tools. Workspace-aware path resolution is provided by `mcp/noctusai/workspace.py` (a new utility module added by the `seed-workspace` project):

```python
from workspace import get_workspace_root, get_noctusai_home, get_workspace_state_dir

REPO_ROOT = get_workspace_root()       # workspace-local; cwd-walk for marker
PROJECTS_DIR = REPO_ROOT / "projects"  # template's projects/, not noc's
TEMPLATE_PATH = get_noctusai_home() / "templates" / "PROPOSAL-TEMPLATE.md"
                                       # noc-shared resource; always reads from noc
```

The classification of which tools should adopt workspace-aware roots vs stay noc-shared:

| Tool | Should resolve via | Reason |
|---|---|---|
| `noctus.dev.status`, `noctus.dev.file_proposal`, `noctus.dev.scaffold_product`, `noctus.dev.promote_from_seed_workspace`, `noctus.dev.list_promotions` | `get_workspace_root()` | Workspace-local — operate on cwd's projects/products |
| `noctus.dev.catalog`, `noctusai_kb_sync`, `noctusai_lgpd_*`, `noctusai_three_way_sync`, `noctusai_ai_*` | unchanged (file-relative noc root) | Noc-shared — operate on noc's authoritative resources regardless of where the MCP was invoked |

Per-workspace MCP state (proposals registry, scan caches, status snapshots) lives under `<workspace>/.noctusai-state/` — never in noc.

**Integration status (as of 2026-05-03):** the `workspace.py` utility ships ready-to-use; integration into the workspace-local tools listed above (`status.py`, `proposals.py`, `scaffold.py` + `server.py` registration of the promotion tools) is **deferred to the parallel `mcp-server-expansion` project's Phase 4** (which restructures every tool file under `tools/noctus/dev/<service>/<action>.py` and replaces the flat dispatch map). When that restructure lands, each workspace-local tool gets a one-line `from workspace import get_workspace_root` + `REPO_ROOT = get_workspace_root()` swap. Until then, the MCP from a template cwd reports noc's projects/products (back-compat fallback). The `noctus.dev.promote_from_seed_workspace` + `noctus.dev.list_promotions` tools live in `mcp/noctusai/tools/promotion.py` and are import-callable today from any Python entrypoint; their MCP server registration also lands in `mcp-server-expansion` Phase 4 alongside the dotted `noctus.dev.promote_from_seed_workspace` alias.

---

## Bootstrap recipe

```bash
# From noc:
bash scripts/bootstrap/bootstrap-seed-workspace.sh \
     --target ~/Documents/repository/NoctusAI/noctusai-template
```

What bootstrap does (in order):

1. Verifies noc looks legitimate (CLAUDE.md, KNOWLEDGE-BASE/, mcp/, seed/, noctusai_lib/ all present).
2. Refuses to bootstrap inside noc (would create a symlink loop).
3. Creates target dir.
4. Symlinks 8 surfaces from noc.
5. Applies `chmod -h a-w` to each symlink (best-effort symbolic).
6. Creates local dirs: `projects/ sandbox/ products/ .promotions/ .noctusai-state/ .githooks/`.
7. Plants `.noctusai-workspace` marker (workspace_kind=seed, noctusai_home=<path>).
8. Creates `.env` (NOCTUSAI_HOME pointer; gitignored).
9. Creates `.gitignore` (excludes `.noctusai-state/`, `.env`).
10. Drops `.promotions/MANIFEST-TEMPLATE.md` + `.promotions/gen-index.py`, then **generates** `PROMOTIONS.md` from `.promotions/` (derived; never a hand-written stub).
11. Copies pre-commit hook into `.githooks/pre-commit`.
12. Renders README from `templates/seed-workspace-README.md` (substitutes `{{WORKSPACE_NAME}}`, `{{NOCTUSAI_HOME}}`, `{{CREATED_AT}}`).
13. Drops docker artifacts from `templates/seed-workspace-docker/`: `Dockerfile`, `Dockerfile.frontend`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `start.sh`, `stop.sh` — all carrying `{{PRODUCT_SLUG}}` / `{{PRODUCT_NAME}}` / `{{BACKEND_PORT}}` / `{{FRONTEND_PORT}}` placeholders. `start.sh` + `stop.sh` are `chmod +x` at copy-time. Substitution happens later when the user runs `noctus.dev.scaffold_product` (see "Docker scaffolding" below).
14. `git init` + `git config core.hooksPath .githooks`.

**Idempotent** — re-running on an existing workspace refreshes symlinks + chmod + marker without touching local content (`projects/`, `sandbox/`, `products/`, `.promotions/`, git history). Docker artifacts are skipped on re-run if already present.

---

## Docker scaffolding

Every seed workspace ships docker artifacts at the workspace root so the user can put a freshly scaffolded product **online to test it before absorbing functionality** — the explicit reason this convention exists. Two-step flow mirrors the bootstrap → scaffold split:

1. **Bootstrap** drops the unsubstituted templates (`Dockerfile`, `Dockerfile.frontend`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `start.sh`, `stop.sh`) carrying `{{PRODUCT_SLUG}}` / `{{PRODUCT_NAME}}` / `{{BACKEND_PORT}}` / `{{FRONTEND_PORT}}` placeholders. `start.sh` + `stop.sh` are `chmod +x` at copy-time so the inherited copy is runnable as soon as the placeholders are patched. Source: `templates/seed-workspace-docker/`.

2. **`noctus.dev.scaffold_product`** detects it's running in a workspace (any caller whose `base_products_dir.parent` contains the docker files at root) and patches the placeholders in place via `_patch_workspace_docker_files`. Idempotent: files already-substituted (no placeholders left) are skipped without error. The patcher re-stamps `start.sh` + `stop.sh` with the executable bit (`mode | 0o111`) since `Path.write_text` doesn't preserve mode reliably across filesystems (Windows + WSL extracts in particular can clear it). The result lands in the scaffold tool's response under the `docker_patch` key with `{patched: [files], skipped: [files]}`.

After scaffold:
```bash
cp .env.example .env       # then fill in NOCTUSAI_HOME + Supabase + LLM keys
./start.sh                 # full stack online (default profile)
./start.sh minimal         # backend + redis only
./start.sh tunnel          # adds cloudflared for OAuth callback testing
./stop.sh                  # graceful: down, keep volumes + images
./stop.sh --volumes        # + wipe DB / redis state
./stop.sh --prune          # + remove dangling images
```

`start.sh` and `stop.sh` are **inherited surface** like Dockerfile etc.: source of truth is the template, never patch the workspace copy in place.

### Why this lives at workspace-root, not per-product

Workspaces are N=1-product by design (the bootstrap → scaffold flow expects one product per testing-ground; multi-product workspaces are a future shape). Putting docker at the workspace root means the user runs `docker compose up` once, with `cwd=workspace`, and gets the full stack — backend + frontend + redis + waha + optional tunnel — not a per-product fan-out. The product-side image build copies only `products/<slug>/backend|frontend/`, so the workspace-root docker layout doesn't leak into the product itself when promoted to noc.

### Why Docker uses an "additional context" for noc

The workspace's `seed/` is a symlink into noc. Docker COPY does **not** follow directory symlinks at build time. Solution: the docker-compose `app` and `frontend` services declare an `additional_contexts: noc: ${NOCTUSAI_HOME}` block, and the Dockerfiles use `COPY --from=noc seed/...` to pull the real seed packages into the image. Set `NOCTUSAI_HOME` in `.env` (the bootstrap's `.env` already has the pointer; the docker-compose `.env` is what the build reads).

### Anti-pattern history (the gap that drove this)

- 2026-05-06 — A workspace was bootstrapped + scaffold_product ran successfully, but the user couldn't put the product online without authoring docker-compose by hand. The convention was missing from the seeding system entirely. Surfaced by user during youtube-crawler workspace recreation; closed by adding the `templates/seed-workspace-docker/` template set + bootstrap step + scaffold patch step.
- 2026-05-07 — Docker artifacts shipped, but the user still had to type `docker compose up -d --build` + remember the WAHA dashboard URL + manually `docker compose down` to stop. No script convention. Surfaced when the user asked *"how can I put the youtube platform online? You have a pre-defined workflow that we did yesterday, don't you?"* Closed by adding `start.sh` + `stop.sh` to the same template set, wiring them into bootstrap + scaffold_product, and adding a noc-side `./stop.sh` companion that reads the `BEGIN/END_PRODUCTS_REGISTRY` block out of `start.sh` (one-writer / two-reader registry).

---

## Promotion workflow

```bash
# In a seed workspace, after building an addition + creating its .promotions/ entry:
python -m mcp.noctusai.cli noctus.dev.list_promotions
# → reports pending vs promoted

python -m mcp.noctusai.cli noctus.dev.promote_from_seed_workspace \
       --slug=<addition-slug> --dry-run
# → prints the plan: origin, destination, would-copy paths

python -m mcp.noctusai.cli noctus.dev.promote_from_seed_workspace \
       --slug=<addition-slug>
# → copies into noc; rewrites manifest's promoted_on to today
```

The promotion tool refuses:

- Promoting from a primary workspace (noc → noc is meaningless).
- `origin` paths outside the workspace (`..` escape).
- `intended_noc_destination` outside noc (`..` escape).
- Origins that don't exist on disk.
- Already-promoted entries (use `force=True` to re-promote — destructive).
- Destinations that already exist in noc (use `force=True` — destructive).

After promotion, the file lands in noc and the manifest's `promoted_on` field is rewritten in place. The manifest stays in the workspace as a record of what was promoted and when.

---

## Tear-down

```bash
rm -rf ~/Documents/repository/NoctusAI/noctusai-template
```

Symlinks dangle harmlessly when removed; noc is unaffected.

---

## Troubleshooting

- **"chmod doesn't seem to be blocking writes"** — Correct, on macOS. The pre-commit hook is the real defense. See Layer 3.
- **Pre-commit hook didn't fire** — Verify `git config core.hooksPath` returns `.githooks` in the workspace; verify `.githooks/pre-commit` is executable.
- **MCP scans show noc's projects from template** — The MCP must have been imported from a path that didn't see template's marker. Check `cwd()` at MCP invocation; the marker is found by walking up from cwd, not by file-relative resolution.
- **Symlink to noc dangles after noc moved** — Re-run bootstrap with `--target <workspace-path>` (which auto-detects new noc location from script position) or `--noc-home <new-path>`.
- **"`{{WORKSPACE_NAME}}` literal appears in README"** — Bootstrap's `sed` substitution failed. Re-run bootstrap; it preserves your local README only if it already exists, so `rm README.md && bash scripts/bootstrap/bootstrap-seed-workspace.sh ...` to refresh.
- **`pyproject.toml` references sibling repo** — That's the parallel `mcp-server-expansion` project's concern, not seed-workspace's. Read its §12 No-leftovers constraint.

---

## Reference

- Project where this design landed: `projects/seed-workspace/PROJECT.md` (deleted at project close per apply-inline-then-delete; this KB doc is the durable record).
- Design supersedes: deferred + abandoned `methodology-mirror-and-workspaces` (heavier 3-tier mirror + per-product fork-and-merge — see PROJECT.md §1 final paragraph for context, although that folder was deleted as part of seed-workspace scaffolding).
- Bootstrap script: `noctusai/scripts/bootstrap/bootstrap-seed-workspace.sh`.
- Pre-commit hook source: `noctusai/templates/seed-workspace-pre-commit.sh`.
- README template: `noctusai/templates/seed-workspace-README.md`.
- Workspace resolver: `noctusai/mcp/noctusai/workspace.py`.
- Promotion tool: `noctusai/mcp/noctusai/tools/promotion.py`.
- Memory entry: `~/.claude/projects/-Users-rapha-Documents-repository-NoctusAI-noctusai/memory/feedback_template_cannot_modify_noc.md`.
