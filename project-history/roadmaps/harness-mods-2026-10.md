# Roadmap · Harness mods (`noc-harness`) — 2026-10

**Slug:** `harness-mods` · **Branch:** `feat/harness-mods` (off `origin/dev`) · **Pattern:** `KB § PATTERNS/common/harness-mods.md`

## Goal
Use Claude Code mods (function-hook plugins) to make the methodology visible and cheap to follow. The mod is a UX + reliability layer over the canonical Python gates, never a gate itself.

## Why (owner, 2026-10-05)
The owner asked how mods could improve "our interface and methodologies and gates and scripts". They chose to implement every proposal, ship it to prod the same night, and keep a clear rollback that won't hurt parallel work.

## Shipped — 2026-10-06, `dev` range `17fc14d53..d9e6a55bc` (linear, five commits)
| Commit | What |
|---|---|
| `625f07a5f` | `noctus.dev.harness_status` / `harness_event` + `cli.py --harness-status [--hs-full] [--hs-cwd]` / `--harness-event` |
| `83c68ec78` | PreToolUse guards **fail closed** (`scripts/hooks/_guard_failclosed.py`: crash, 8 s deadline or bad payload ⇒ deny); every deny is marked `[noc-guard:<name>]`; auth false-green is denied at **write** time (`auth_false_green_predicate.py`, shared with the keeper); `claude-guard-executor-dispatch.py` |
| `678753989` | Keeper `check_harness_mod_integrity` (`--check-harness-mod`, pre-commit leg) |
| `2eb05d1d5` | The mod `.claude/mods/noc-harness` (inert: `enabledPlugins=false`), the repo marketplace, the KB pattern plus every referencing layer, and the CLAUDE.md §1 Gate↔methodology line; `cli.py` venv self-heal now probes `noctusai_lib` |
| `d9e6a55bc` | **ACTIVATION, alone, in `.claude/settings.json` only:** `enabledPlugins["noc-harness@noctusai"]=true` + the `Agent\|Task` PreToolUse executor-dispatch guard |

## Shipped — batch 2, 2026-10-06 (`1a10cd492`, `dcfeaeee6..791f59258`)
| Commit | What |
|---|---|
| `1a10cd492` | Fix for the CI red on `f52e8917e`: `[carve:hook]` manifest rows plus accept-with-rationale 9f for `_guard_failclosed.py` and `claude-guard-executor-dispatch.py` |
| `dcfeaeee6` | `noctus.dev.harness_panel` (vectors · baselines · codify · gates) and `harness_route`; `harness_event` now reports the real publish outcome |
| `adf2845e2` | CI `harness-mod-tests` job (`claude plugin validate`/`test` + `--check-harness-mod`, CLI pinned 2.1.291); closes `NOC-REMEDIATE[harness-mod-ci]` |
| `791f59258` | Mod 0.2.0: live panels, invalid-harness alerts, `agent.offer` for executors, semantic routing (off by default) |

## Held — owner decision
- **Write redirect** (primary-checkout Edit/Write rewritten into the session's worktree): the harness permission classifier refused the dispatch as self-modification of a safety guard. The two guard false-positive fixes that rode in the same brief are held with it: `cd $VAR` expansion, and the post-hook suggesting `rm` after an index-only restore.
- **`main` bless:** the `dev` range carries a peer rider whose `predeploy_check social-wiring` is BLOCKED (`schema_drift`: `ig_media`, `ig_media_snapshots` and `ig_profile_snapshots` are missing in the live DB). Options:
  - Wait for the peer to apply that migration, then bless normally.
  - Or `release mode=cut` our commits. That needs the owner's typed ship-consent phrase and adds a backmerge merge commit on `dev`.

## Rollback (in order of blast radius)
1. **One UX feature:** the plugin's `/config` row, or `pluginConfigs` in `settings.local.json`.
2. **The whole mod, one session:** `NOC_HARNESS_OFF=1`.
3. **The mod and the executor-dispatch guard, fleet-wide:** `git revert d9e6a55bc`. It touches one file, is conflict-free and linear (no merge commit), and leaves the fail-closed guards in place.
4. **Batch 2:** `git revert dcfeaeee6^..791f59258`. Mod 0.2.0, panels, CI job; leaves batch 1 in place.
5. **Everything from tonight:** revert batch 2, then `git revert 625f07a5f^..d9e6a55bc`, plus `1a10cd492` (doc rows only).

## Open (named destinations)
- [x] **CI for mod tests:** shipped in `adf2845e2`.
- [ ] **Lesson:** never push to `dev` while waiting on a CI verdict (a push cancels the running run). Run the FULL toolkit suite before pushing: the narrow local selection missed `test_compliance_hygiene` and `dev` went red once. Locally, a full run takes about 21 min and is unreliable while peers mutate shared git state; CI is the verdict.
- [ ] **Findings logged as s1** (auto-improvement, `source=noc-harness-mod`, session 3e354d14):
  - The primary-write PostToolUse guard reads an index-only restore as new dirt and advises `rm` of the owner's files.
  - The noc-graph freshness keeper takes about 40 s because it walks `.claude/worktrees/`.
  - Cache keepers read stale or fresh depending on the tree root.
  - Nothing enforces the EXECUTOR/ADVISOR marker on agents, so an unmarked executor slips past the dispatch guard.
  - `harness_event` reports the legacy `ledger_path`.
  - `release manifest` misattributes projects.
  - `task_branch start` rejects role `tech-lead` silently.
- [ ] **Fast-mode budget:** `harness_status` fast is about 0.4 s, mostly interpreter start. If that is too slow per turn, add a long-lived helper (the engineer's suggestion).
- [ ] **Dev loop note:** in the session that wrote the mod, the dev-mods hot-reload copy and the marketplace copy can both load after `/reload-plugins`; new sessions load only the marketplace copy.
