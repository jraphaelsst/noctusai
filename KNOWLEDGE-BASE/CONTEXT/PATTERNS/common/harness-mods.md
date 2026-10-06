# Harness mods — a UX + reliability layer over the canonical Python gates

**The rule.** A Claude Code *mod* (a function-hook plugin under `.claude/mods/<name>/`) makes the methodology **visible and cheap to follow**. It is **never a gate itself**. Gates stay canonical in Python: `scripts/hooks/claude-guard-*.py` → `noctus.dev.*` logic, plus keepers in `compliance.py`. The mod renders what `cli.py --harness-*` answers and records friction, so every clone without the mod is still fully guarded. Codified 2026-10-06 with the first mod, `noc-harness`.

**Why.** A gate inside a mod would be a gate that a `userConfig` toggle, an early-access API change, or a session without the plugin can switch off without anyone noticing. That is the silent-error shape (`KB § 01-PHILOSOPHY.md`). A mod that only *shows* gates loses nothing when it is off. And when it is on, it turns every refusal into a visible learning event (`KB § PATTERNS/common/learning-posture-family-index.md`).

## Anatomy

| Path | What |
|---|---|
| `.claude/mods/<name>/.claude-plugin/plugin.json` | Manifest. `userConfig` holds the per-feature **UX** kill switches. `types` points at the `$.state` contract. |
| `.claude/mods/<name>/hooks/hooks.json` | `{"modules": ["./register.tsx"]}`, the one hooks module. |
| `.claude/mods/<name>/hooks/register.tsx` | `register(on, options)`: every hook, plus every function that receives `$`. |
| `.claude/mods/<name>/hooks/*.ts` | Pure helpers with no `$`: formatting and matching. Unit-tested. |
| `.claude/mods/<name>/hooks/*.test.ts` | `claude plugin test .claude/mods/<name>`. |
| `.claude-plugin/marketplace.json` (repo root) | Marketplace `noctusai`, one entry per mod folder (`source: "./.claude/mods/<name>"`). |
| `.claude/settings.json` | `extraKnownMarketplaces.noctusai` (directory source `./`) and `enabledPlugins["<name>@noctusai"]` set to true or false, so every clone gets the mod with no setup step. |

Engine-laid files (`.claude-plugin/types/`, `tsconfig.json`) are build-specific and gitignored.

## `noc-harness` features

Each feature has its own `userConfig` switch. None of them decides a gate.

| Feature | Hook | Source of truth |
|---|---|---|
| Status line: tree/branch (warns when the primary is on a shared branch), dirty, dev ↑↓ vs origin, main+N, stale caches, open s1/s2, inbox, section errors | `$.ui.status` after `session.start`, every `turn.complete`, and the timer | `noctus.dev.harness_status` |
| Reminders band (owner reminders, wrap-up nudge, degraded notice) | `ui.render` `AbovePrompt` | `harness_status.reminders` (MEMORY-reminders.md) |
| Orchestration pane, `/noc-pane`: branch pointers, worktrees, inbox, top open s1/s2, cache staleness, refusals this session | `ui.render` `Pane` | `harness_status --hs-full` |
| Friction ledger: a toast on every guard refusal, recorded as an auto-improvement event | `tool.call` (observes the result) | `[noc-guard:<name>]` marker → `noctus.dev.harness_event` |
| Memory-topic routing: a pointer to the matching `MEMORY-<topic>.md` | `prompt.submit` context | The MEMORY.md topic table (derived, never a keyword list) |
| Compaction capture: the summarizer is told what it must keep, and learnings in flight are recorded | `session.compact` | `harness_event kind=compaction_capture` |
| Wrap-up nudge: after a turn that committed without `noc-wrap-up`, the band offers it | `tool.call` + `turn.complete` | — |

Other commands: `/noc-band` (show the band again) and `/noc-refresh`.

The guards the mod *observes* are canonical Python, shipped in the same change:
- They **fail closed**: a crash, an 8 s internal deadline or a bad payload produces a deny (`scripts/hooks/_guard_failclosed.py`).
- Every deny starts with the `[noc-guard:<name>]` marker.
- The executor-dispatch guard (`claude-guard-executor-dispatch.py`) refuses an executor `Agent` dispatch that names no existing `.claude/worktrees/<slug>` (and isn't `isolation: worktree`).
- Auth false-greens are refused at **write** time (`auth_false_green_predicate.py`, shared with the keeper).

## Invariants

The keeper is `check_harness_mod_integrity` (`--check-harness-mod`, pre-commit leg). It enforces:
- **(a) Consistency:** marketplace ↔ plugin.json (name and version) ↔ settings, and every mod folder is listed.
- **(b) No re-implementation:** the only process a mod may spawn is `cli.py --harness-*`. No `deny:` decision except in a `.catch` that fails the mod's *own* hook closed.
- **(c) Tests:** every mod has at least one `*.test.ts`.
- **(d) UX-only kill switches:** no `userConfig` key names a guard, gate, keeper or hook.

The engine also enforces its own rules (`claude plugin validate`):
- `$` may be passed only to functions declared at the top of the hooks module.
- `$` never crosses an import, so the bridge to `cli.py` lives in `register.tsx`.
- Module variables reset on every hot reload; state a drawing reads goes in `$.state` atoms declared in `types/index.d.ts`.

## Degrade visibly, never silently

The mods API is early access and changes between releases. When a `cli.py` call fails, the mod does not hide it: the failure lands in the `degraded` atom. The status line, the band and the pane all show it. Gates are unaffected either way.

## Kill switches and rollback

| Scope | How | Effect |
|---|---|---|
| One feature, one user | `/config` → the plugin's row, or `pluginConfigs` in `settings.local.json` | That UX feature stops. |
| Whole mod, one session | `NOC_HARNESS_OFF=1` | The mod registers nothing visible. |
| Whole mod, fleet | `enabledPlugins["noc-harness@noctusai"]: false` (the activation commit reverted) | Not loaded anywhere. Still keeper-clean, because `false` is a decision, not drift. |
| Everything from 2026-10-06 | `git revert` the recorded range (below) | The fail-closed guards revert too. Reverts are linear, so this is compatible with integrate-by-rebase. |

The work landed as one contiguous linear range on `dev`, with the activation isolated in its **last** commit. The range and the exact revert commands are in `project-history/roadmaps/harness-mods-2026-10.md`. Reverting only the activation commit turns the mod and the executor-dispatch guard off fleet-wide and touches one file, `.claude/settings.json`.

## Developing a mod

- **Edit in place:** edit under `.claude/mods/<name>/` in a worktree, then `/reload-plugins`. The marketplace is a directory, so relative-path plugins load from the folder itself.
- **Fast iteration in one session:** the `plugin-authoring` skill hot-reloads from the session's dev-mods folder. Copy the result back into the worktree; the repo copy is canonical.
- **Gates before commit:** `claude plugin validate .claude/mods/<name>`, `claude plugin test .claude/mods/<name>`, `cli.py --check-harness-mod`.
- `NOC-REMEDIATE[harness-mod-ci]`: no CI job runs `claude plugin test` yet. Until one does, the pre-commit keeper and the local test run are the gate. The `_GATED_PREFIXES` entry says PENDING.

## Anti-patterns

- Re-implementing a guard regex or a platform rule in TypeScript. Call `cli.py --harness-*`; if the answer lacks a field, extend the Python tool.
- Hand-listing topics, slugs or agent sets in the mod. Derive them (the MEMORY.md table; the agent frontmatter `EXECUTOR` marker).
- A `userConfig` switch that disables a safety check.
- Swallowing a failed bridge call. Route it to `degraded`.

## Composes with

[[gate-methodology-sync]] (mods are neither gate nor mechanism; they are the *visibility* of both) · [[eight-way-sync]] (mods are harness fabric, outside the 8-way, like `pre-commit` and `cli.py`) · [[self-branching-mode]] §11 (fail-closed guards) · [[bypass-rationalization-anti-patterns]] · [[scoped-auto-improvement]] (the friction ledger feeds it) · [[mcp-first-scripts]] (the mod's only bridge is a `noctus.dev.*` tool).
