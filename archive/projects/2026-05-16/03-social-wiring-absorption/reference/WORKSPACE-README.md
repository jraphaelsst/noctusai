# noctusai-youtube-crawler — Template Workspace

A sibling-of-noc workspace that **consumes noc strictly read-only** via symlinks.
You operate by noc's full methodology (CLAUDE.md, KB, hooks, MCP toolkit, seed,
noctusai_lib) without ever modifying noc.

> Bootstrap origin: `noctusai/scripts/bootstrap-seed-workspace.sh`
> Design source: `KNOWLEDGE-BASE/CONTEXT/PATTERNS/seed-workspace.md` (in noc; symlinked here as `KNOWLEDGE-BASE/`)
> Created: 2026-05-06T17:14:04Z · NoctusAI home: `/Users/rapha/Documents/repository/NoctusAI/noctusai`

---

## The one rule that shapes everything

**Templates cannot modify noc.** Three layers of defense:

1. **Pre-commit hook (PRIMARY).** `.githooks/pre-commit` refuses any staged path that resolves through a symlinked surface, AND any non-sandbox addition without a matching `.promotions/` entry. This is the real protection.
2. **Documented rule (AGENT-LEVEL).** CLAUDE.md §1 carries a universal rule; KB pattern doc carries the depth; agent-memory carries the working-agreement entry. Agents read it; humans read this README.
3. **chmod a-w on symlinks (SYMBOLIC).** Bootstrap applies `chmod -h a-w` to the workspace's symlink entries. **macOS symlinks ignore mode bits at the kernel level** — this is symbolic on Mac and partially-effective on Linux. Treat it as a marker, not a guarantee. The pre-commit hook is what actually defends.

If you find yourself wanting to edit `CLAUDE.md` or anything under `KNOWLEDGE-BASE/`, `.claude/`, `mcp/`, `seed/`, `noctusai_lib/`, or `templates/` from this workspace — STOP. Edit those in noc directly. They live in noc.

---

## Layout

```
noctusai-youtube-crawler/
├── CLAUDE.md           → symlink to noc/CLAUDE.md            (READ-ONLY)
├── CLAUDE/             → symlink to noc/CLAUDE/              (READ-ONLY)
├── KNOWLEDGE-BASE/     → symlink to noc/KNOWLEDGE-BASE/      (READ-ONLY)
├── .claude/            → symlink to noc/.claude/             (READ-ONLY)
├── mcp/                → symlink to noc/mcp/                 (READ-ONLY — toolkit shared)
├── seed/               → symlink to noc/seed/                (READ-ONLY)
├── noctusai_lib/       → symlink to noc/noctusai_lib/        (READ-ONLY)
├── templates/          → symlink to noc/templates/           (READ-ONLY)
│
├── projects/           # LOCAL — workspace's own projects
├── sandbox/            # LOCAL — throwaway experiments (no manifest required)
├── products/           # LOCAL — staged products awaiting promotion to noc
├── .promotions/        # LOCAL — per-addition metadata (one .md per addition)
├── PROMOTIONS.md       # LOCAL — index of .promotions/ entries
├── .noctusai-workspace # LOCAL — marker file (workspace_kind=seed)
├── .noctusai-state/    # LOCAL — MCP per-workspace state (gitignored)
├── .env                # LOCAL — NOCTUSAI_HOME pointer (gitignored)
├── .githooks/          # LOCAL — pre-commit hook (Rule 1 + Rule 2)
└── README.md           # this file
```

---

## Three use cases

### 1. Sandbox

Drop anything in `sandbox/` for throwaway experimentation. The pre-commit hook waives the promotion-manifest requirement here. Nothing in `sandbox/` is ever expected to land in noc.

```bash
mkdir -p sandbox/<topic>
# scratch away
git add sandbox/<topic>/
git commit -m "sandbox: <topic>"  # accepted by hook (sandbox carve-out)
```

### 2. New-product staging

Scaffold a product against the symlinked seed + lib so it is noc-compatible from line one:

```bash
mkdir -p products/<name>/{backend,frontend}
# build against seed/ and noctusai_lib/ (symlinked from noc) — your imports work today
# create the matching .promotions/ entry:
cat > .promotions/<name>-product.md <<'EOF'
---
slug: <name>-product
origin: products/<name>/
intended_noc_destination: products/<name>/
layer_rationale: |
  New product following the standard products/<slug>/ layout.
  Consumes seed framework (create_product_app + createProductApp) — no structural fork.
seed_first_analysis: |
  Q1 contract identical: yes (standard product factory).
  Q2 product-specific data: yes — products/<name>/backend/migrations/.
  Q3 placement: products/<name>/.
  Q4 visibility: standard auth + RLS.
  Q5 seam: create_product_app + createProductApp.
  Q6 default-on: opt-in (new product).
dependencies_on_other_additions: []
promoted_on: not-yet
---

## Why this addition exists
<why>

## Integration notes for noc-side
- Seed-wiring follows products/<existing>/backend/main.py pattern.
- Migrations apply via Supabase MCP; mirror to products/<name>/backend/migrations/NNN_*.sql.
- Add to KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md.
EOF
git add products/<name>/ .promotions/<name>-product.md PROMOTIONS.md
git commit -m "product: <name> initial scaffold"
```

When ready to promote into noc:

```bash
# Dry-run (from noc cwd or template cwd):
python -m mcp.noctusai.cli noctus.dev.promote_from_seed_workspace --slug=<name>-product --dry-run

# Real promotion:
python -m mcp.noctusai.cli noctus.dev.promote_from_seed_workspace --slug=<name>-product
```

### 3. Parallel agent

Run two Claude Code sessions — one with cwd in noc, one with cwd here. They share the same rule surface (CLAUDE.md, KB, `.claude/` settings, MCP toolkit) via symlinks. They have **isolated git histories** (your work here doesn't show up in noc's `git status`). They have **isolated MCP state** (proposals registry / scan caches / status snapshots live under `.noctusai-state/`, distinct per workspace).

---

## Promotion manifest format

`.promotions/<slug>.md` — one per addition. Frontmatter fields:

| Field | Required | Description |
|---|---|---|
| `slug` | yes | Filename slug; globally unique within workspace |
| `origin` | yes | Workspace-relative path of the addition |
| `intended_noc_destination` | yes | Where this lands in noc (path + layer rationale below) |
| `layer_rationale` | yes | Why this destination — invokes the seed-lib 6-layer model when relevant |
| `seed_first_analysis` | yes | Six checklist answers (`KB § GUIDES/seed-first-design.md`) |
| `dependencies_on_other_additions` | yes | List (possibly empty); other slugs this depends on |
| `promoted_on` | yes | ISO date when promoted; `not-yet` until then |

`PROMOTIONS.md` is a one-line-per-entry index, same shape as `MEMORY.md`.

---

## MCP from this workspace

The MCP toolkit at `mcp/noctusai/` is symlinked from noc — same code, same tool set. Workspace-aware tools (status, file_proposal, scaffold_product) detect this workspace via the `.noctusai-workspace` marker and operate on local `projects/` + `products/`. Noc-shared tools (catalog, kb_sync, lgpd, three_way_sync, ai_*) operate on noc's authoritative resources regardless of where the MCP is invoked from.

Per-workspace MCP state (proposals registry, scan caches, status snapshots) is written under `.noctusai-state/` — never in noc.

---

## Tear-down

```bash
# from noc
rm -rf <this-workspace-path>
```

Symlinks dangle harmlessly when removed; noc is unaffected.

---

## Rebuild / refresh

If noc moves on disk, or you want to refresh symlinks:

```bash
bash /Users/rapha/Documents/repository/NoctusAI/noctusai/scripts/bootstrap-seed-workspace.sh \
  --target $(pwd) --noc-home <new-noc-path>
```

Bootstrap is idempotent — preserves local content (`projects/`, `sandbox/`, `products/`, `.promotions/`, git history), refreshes symlinks + chmod + marker.
