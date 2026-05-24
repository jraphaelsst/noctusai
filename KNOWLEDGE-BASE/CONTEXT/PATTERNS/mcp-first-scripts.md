# MCP-first scripts — new automation defaults to an MCP tool

> Specialization of `KB § 01-PHILOSOPHY.md § MCP-first` for the `scripts/` surface. MCP-first says *agent-exposable capabilities default to the MCP server*. A new automation script **is** an agent-exposable capability — so the default home for new automation is a `noctus.dev.*` MCP tool, **not** a `scripts/*.sh|*.py` one-off. Shell is allowed only for three named structural carve-outs, each with written rationale. Keeper-enforced via the manifest below.

---

## 1. The rule

**New automation → `noctus.dev.*` MCP tool first.** When you need a new repo-automation capability (analysis, codegen-from-canonical, hygiene, history/ledger, count-refresh, smoke-check, …), author it as an MCP tool under `mcp/noctusai/tools/noctus/dev/` with a `cli.py` flag + colocated `Test*` — the same shape every other dev tool has. A bare `scripts/<name>.sh|.py` is the slip the MCP-first boundary rule already names: a capability with a plausible second consumer (another agent, another session, Claude Code) written as a private one-off.

**Why MCP not shell:** single source of truth · testable through `noctus.dev.pytest` · agent-callable + toolkit-discoverable · `cli.py` flag preserves muscle-memory invocation · no flat-folder accretion. Promotion is cheap (`scaffold_mcp_tool` emits the skeleton); a shell one-off is the demotion.

**Carve-outs (shell allowed, rationale REQUIRED).** Exactly three structural categories where shell is correct because the MCP runtime is structurally unavailable or wrong:

- **`[carve:hook]` git-hook entry** — git invokes `.git/hooks/*` as a shell process directly; it cannot call MCP. The *logic* is absorbed into an MCP tool; the hook becomes a thin dispatcher (`exec "$PY" mcp/noctusai/cli.py --<flag>`). The thin shim is the carve-out, not the logic.
- **`[carve:bootstrap]` pre-venv bootstrap** — runs *before* the Python venv the MCP lives in exists (it *creates* that venv). Chicken-and-egg: cannot depend on the toolkit. Stays shell whole.
- **`[carve:docker]` thin docker-orchestration** — a script whose entire body is `docker build`/`compose` plumbing with no extractable logic. Absorbing yields a Python wrapper that just shells out — negative value. Stays shell whole.

A script outside these three → MCP tool. A carve-out claim without a manifest entry + accept-with-rationale catalog entry is a silent error (`§ No silent errors`).

---

## 2. Operational shape

1. Default: `noctus.dev.<action>` MCP tool + `cli.py --<flag>` + colocated `Test<CamelCase>` (`feedback_regression_test_the_detector`). Use `scaffold_mcp_tool`.
2. Namespace: extend the existing `noctus.dev.*` (user decision 2026-05-18 — no separate `noctus.ops.*`).
3. Pre-commit-invoked logic absorbed into MCP, the script kept as a thin `cli.py` shim (so the hook keeps a stable shell entry while the logic is single-sourced + tested).
4. Already-shell capability with a *plausible* second consumer = bystander MCP-first opportunity → apply-now or defer-with-destination (`KB § 01-PHILOSOPHY.md § Flag MCP-first / AST-first opportunities proactively`).

---

## 3. Classification manifest (durable single source of truth)

Every `scripts/**/*.sh` / `scripts/**/*.py` file MUST have a row here, **matched by BASENAME** (Phase-6 intent-folders: `scripts/{hooks,bootstrap,infra}/` — the keeper `rglob`s and basename-matches so rows are path-stable across folder moves; `codemods/`, `__pycache__/`, `init-local-db/` excluded by construction). **A file on disk with no row = an undecided new script = the keeper violation** (`check_new_script_lacks_mcp_analog`, `warning`). `bucket` ∈ `A` genuine-dup · `B` heavy-port · `C` pure-logic · `[carve:hook]` · `[carve:bootstrap]` · `[carve:docker]`. Absorb rows (A/B/C) are the live backlog — the row is **removed when the script is deleted/absorbed**; carve-out rows are permanent and pair 1:1 with an entry in `KB § PATTERNS/accept-with-rationale.md`. Layout post-Phase-6: `hooks/{pre-commit,install-hooks.sh}` · `bootstrap/{setup,first-time-setup,bootstrap-worktree,bootstrap-seed-workspace,build-init-local-db}.sh` · `infra/build-base-images.sh`. The `scripts/setup.sh` + `scripts/install-hooks.sh` top-level entries are 2-line forwarding shims (the fresh-clone `bash scripts/setup.sh` contract) — same basename as the real bootstrap/hooks files, so one manifest row covers both.

| script (basename) | bucket | disposition |
|---|---|---|
| `pre-commit` | [carve:hook] | `hooks/pre-commit`; thin dispatcher → `cli.py --<flag>` per step (logic in `noctus.dev.*`) |
| `install-hooks.sh` | [carve:bootstrap] | `hooks/install-hooks.sh` (+ root shim); symlink installer, clone time |
| `setup.sh` | [carve:bootstrap] | `bootstrap/setup.sh` (+ root shim); creates the venv the MCP runs in |
| `first-time-setup.sh` | [carve:bootstrap] | `bootstrap/first-time-setup.sh`; pre-venv repo setup |
| `bootstrap-worktree.sh` | [carve:bootstrap] | `bootstrap/bootstrap-worktree.sh`; pre-venv worktree hydrate |
| `bootstrap-seed-workspace.sh` | [carve:bootstrap] | `bootstrap/bootstrap-seed-workspace.sh`; pre-venv workspace hydrate |
| `build-init-local-db.sh` | [carve:bootstrap] | `bootstrap/build-init-local-db.sh`; regenerates init-local-db SQL pre-venv |
| `build-base-images.sh` | [carve:docker] | `infra/build-base-images.sh`; thin `docker build` of seed base images |
| `build-and-push.sh` | [carve:docker] | `infra/build-and-push.sh`; thin `docker build --target runtime` + push of the fleet to GHCR (the CI build/deliver step). Relocated here from `projects/production-deploy-migration/` 2026-05-24 — a permanent CI surface must live outside `projects/` (durable-refs gate). |

> Manifest parsed by `check_new_script_lacks_mcp_analog` (`compliance.py`). The keeper does NOT require disposition fidelity — it asserts only *presence of a row* per disk file: it catches the "someone added `scripts/foo.sh` without a bucket decision" slip. Disposition is human-curated. Non-script `scripts/` entries (`codemods/` lib, `init-local-db/*.sql` data, `*.log`, `README.md`, `.DS_Store`) are out of scope by construction (only top-level `*.sh`/`*.py`). Carve-out rows pair 1:1 with `KB § PATTERNS/accept-with-rationale.md`.

**Absorbed + deleted 2026-05-18** (durable landing record — these are now `noctus.dev.*` MCP tools + `cli.py` flags, NOT dangling): `mole.sh`→`noctus.dev.mole` · `verify-kb-sync.sh`+`update-kb-counts.py`→`tools/kb_sync.py` (`noctus.dev.kb_sync`, `--verify-kb-sync`/`--update-kb-counts`) · `archive-clean.sh`→`noctus.dev.archive_clean` · `disk-usage-monitor.sh`→`noctus.dev.check_disk_usage` · `check-framework-deps.py`→`noctus.dev.check_framework_deps` · `cleanup-stale-worktrees.sh`→`noctus.dev.cleanup_stale_worktrees` · `merge-debt-monitor.sh`→`noctus.dev.check_merge_debt` · `render-project-history.py`+`backfill-project-history.py`→`history.py` (`noctus.dev.render_project_history`/`backfill_project_history`) · `gen-promotions-index.py`→`noctus.dev.gen_promotions_index` · `sync-seed-template.sh`→`noctus.dev.sync_seed_template` · `stamp-seed-version.sh`→`noctus.dev.stamp_seed_version` · `propagate-{composes,dockerfiles}.sh`→`noctus.dev.propagate` · `smoke-fleet.sh`→`noctus.dev.smoke_fleet`. Each has a `cli.py --<flag>` (`python mcp/noctusai/cli.py --help`).

---

## 4. Companion rules

- `KB § 01-PHILOSOPHY.md § MCP-first` (parent rule — this is its `scripts/` specialization)
- `KB § 01-PHILOSOPHY.md § Flag MCP-first / AST-first opportunities proactively` (bystander trigger)
- `KB § PATTERNS/accept-with-rationale.md` (carve-out rows pair 1:1)
- `KB § PATTERNS/dev-toolkit-scaffolders.md` (`scaffold_mcp_tool` emits the default skeleton)
- `KB § PATTERNS/methodology-codification-pipeline.md` (this rule reached `s4` 2026-05-18 — keeper shipped same session as the doc)
