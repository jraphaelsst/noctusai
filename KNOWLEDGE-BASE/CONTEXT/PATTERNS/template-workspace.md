# Template workspace — sibling symlink-consumer of noc

> **One-line rule:** Templates cannot modify noc.
>
> **Where this lives:** referenced from `CLAUDE.md §1` universal rules; full design here; mirrored in agent memory at `feedback_template_cannot_modify_noc.md`.

A **template workspace** is a sibling folder to `noctusai/` that gives an agent or developer the *exact same operating surface* as working inside noc — same `CLAUDE.md` rules, same KB depth, same `.claude/` hooks/skills/permissions, same MCP toolkit, same `seed/` and `noctusai_lib/` — without duplicating any of those files. The template **points back** at noc's filesystem via symlinks; a single edit in noc propagates instantly. It is noc's methodology delivered to a workspace that isn't noc.

---

## When to use a template workspace

Three intended use cases:

1. **Sandbox.** Throwaway experiments outside the monorepo while keeping noc's discipline (keeper, three-way sync, recurrence rule, seed-first, etc.). Agent operates by noc's rules; throwaway code never enters noc's git history.
2. **New-product staging.** Scaffold a new product against the symlinked `seed/` + `noctusai_lib/` so it is noc-compatible from line one. Promote when ready via the manifest.
3. **Parallel agent.** Run two Claude Code sessions — one with cwd in noc, one in template. They share the same rule surface (CLAUDE.md, KB, `.claude/` settings, MCP toolkit) via symlinks, with isolated git histories, isolated `projects/`, isolated `products/`, and zero file-collision risk.

When NOT to use a template:
- **Long-term per-product workspaces** with methodology evolution merged back to noc — that's the *deferred and abandoned* `methodology-mirror-and-workspaces` design (heavier 3-tier mirror + per-product fork-and-merge model). The template workspace is the lighter consume-only alternative.
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

> **Why not chmod the symlink TARGETS in noc?** That would lock noc itself out of editing its own files (same OS user owns both). Tested and rejected during Phase 0 of the `template-workspace` project. The realistic enforcement boundary is at commit-time, not write-time.

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
│   │   └── bootstrap-template-workspace.sh
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
    ├── .noctusai-workspace             # LOCAL — marker (workspace_kind=template)
    ├── .noctusai-state/                # LOCAL — MCP per-workspace state (gitignored)
    ├── .env                            # LOCAL — NOCTUSAI_HOME pointer (gitignored)
    ├── .git/                           # LOCAL — own git repo
    ├── .gitignore
    ├── .githooks/pre-commit            # LOCAL — Rule 1 + Rule 2
    └── README.md                       # LOCAL — conventions
```

---

## Marker file format

Plain-text key=value, one pair per line. Lines starting with `#` are comments; blank lines ignored.

```ini
# NoctusAI workspace marker — DO NOT EDIT.
workspace_kind=template          # or "primary"
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
  (KB § PATTERNS/seed-lib-layout.md) when relevant.
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

`PROMOTIONS.md` at the workspace root is the index — one line per `.promotions/` entry, same shape as `MEMORY.md`.

The `seed_first_analysis` block is filled at **addition time**, not at promotion time — invoking the six-question checklist at the moment of authorship surfaces design questions before the file's shape ossifies. Skipping this in the manifest is a design smell that the pre-commit hook does not catch (humans + agents enforce).

---

## MCP workspace-awareness

The MCP toolkit at `mcp/noctusai/` ships from noc and is symlinked into every template — same code, same tools. Workspace-aware path resolution is provided by `mcp/noctusai/workspace.py` (a new utility module added by the `template-workspace` project):

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
| `noctusai_status`, `noctusai_file_proposal`, `noctusai_scaffold_product`, `noctusai_promote_from_template`, `noctusai_list_promotions` | `get_workspace_root()` | Workspace-local — operate on cwd's projects/products |
| `noctusai_catalog`, `noctusai_kb_sync`, `noctusai_lgpd_*`, `noctusai_three_way_sync`, `noctusai_ai_*` | unchanged (file-relative noc root) | Noc-shared — operate on noc's authoritative resources regardless of where the MCP was invoked |

Per-workspace MCP state (proposals registry, scan caches, status snapshots) lives under `<workspace>/.noctusai-state/` — never in noc.

**Integration status (as of 2026-05-03):** the `workspace.py` utility ships ready-to-use; integration into the workspace-local tools listed above (`status.py`, `proposals.py`, `scaffold.py` + `server.py` registration of the promotion tools) is **deferred to the parallel `mcp-server-expansion` project's Phase 4** (which restructures every tool file under `tools/noctus/dev/<service>/<action>.py` and replaces the flat dispatch map). When that restructure lands, each workspace-local tool gets a one-line `from workspace import get_workspace_root` + `REPO_ROOT = get_workspace_root()` swap. Until then, the MCP from a template cwd reports noc's projects/products (back-compat fallback). The `noctusai_promote_from_template` + `noctusai_list_promotions` tools live in `mcp/noctusai/tools/promotion.py` and are import-callable today from any Python entrypoint; their MCP server registration also lands in `mcp-server-expansion` Phase 4 alongside the dotted `noctus.dev.promote_from_template` alias.

---

## Bootstrap recipe

```bash
# From noc:
bash scripts/bootstrap-template-workspace.sh \
     --target ~/Documents/repository/NoctusAI/noctusai-template
```

What bootstrap does (in order):

1. Verifies noc looks legitimate (CLAUDE.md, KNOWLEDGE-BASE/, mcp/, seed/, noctusai_lib/ all present).
2. Refuses to bootstrap inside noc (would create a symlink loop).
3. Creates target dir.
4. Symlinks 8 surfaces from noc.
5. Applies `chmod -h a-w` to each symlink (best-effort symbolic).
6. Creates local dirs: `projects/ sandbox/ products/ .promotions/ .noctusai-state/ .githooks/`.
7. Plants `.noctusai-workspace` marker (workspace_kind=template, noctusai_home=<path>).
8. Creates `.env` (NOCTUSAI_HOME pointer; gitignored).
9. Creates `.gitignore` (excludes `.noctusai-state/`, `.env`).
10. Creates `PROMOTIONS.md` index stub.
11. Copies pre-commit hook into `.githooks/pre-commit`.
12. Renders README from `templates/template-workspace-README.md` (substitutes `{{WORKSPACE_NAME}}`, `{{NOCTUSAI_HOME}}`, `{{CREATED_AT}}`).
13. `git init` + `git config core.hooksPath .githooks`.

**Idempotent** — re-running on an existing workspace refreshes symlinks + chmod + marker without touching local content (`projects/`, `sandbox/`, `products/`, `.promotions/`, git history).

---

## Promotion workflow

```bash
# In a template workspace, after building an addition + creating its .promotions/ entry:
python -m mcp.noctusai.cli noctusai_list_promotions
# → reports pending vs promoted

python -m mcp.noctusai.cli noctusai_promote_from_template \
       --slug=<addition-slug> --dry-run
# → prints the plan: origin, destination, would-copy paths

python -m mcp.noctusai.cli noctusai_promote_from_template \
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
- **"`{{WORKSPACE_NAME}}` literal appears in README"** — Bootstrap's `sed` substitution failed. Re-run bootstrap; it preserves your local README only if it already exists, so `rm README.md && bash scripts/bootstrap-template-workspace.sh ...` to refresh.
- **`pyproject.toml` references sibling repo** — That's the parallel `mcp-server-expansion` project's concern, not template-workspace's. Read its §12 No-leftovers constraint.

---

## Reference

- Project where this design landed: `projects/template-workspace/PROJECT.md` (deleted at project close per apply-inline-then-delete; this KB doc is the durable record).
- Design supersedes: deferred + abandoned `methodology-mirror-and-workspaces` (heavier 3-tier mirror + per-product fork-and-merge — see PROJECT.md §1 final paragraph for context, although that folder was deleted as part of template-workspace scaffolding).
- Bootstrap script: `noctusai/scripts/bootstrap-template-workspace.sh`.
- Pre-commit hook source: `noctusai/templates/template-workspace-pre-commit.sh`.
- README template: `noctusai/templates/template-workspace-README.md`.
- Workspace resolver: `noctusai/mcp/noctusai/workspace.py`.
- Promotion tool: `noctusai/mcp/noctusai/tools/promotion.py`.
- Memory entry: `~/.claude/projects/-Users-rapha-Documents-repository-NoctusAI-noctusai/memory/feedback_template_cannot_modify_noc.md`.
