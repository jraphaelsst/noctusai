# tmp-artifact-cleanup — automated sweep of retired engineer-dispatch patches

> 🔒 **Caller-scope rule.** `noctus.dev.tmp_cleanup` is **orchestrator-only** — the
> `orchestrator-operator` agent invokes it as a standing end-of-tick step with `dry_run=False`.
> Specialist agents (backend / frontend / devops / compliance / security / architect /
> engineer-seed) MUST NOT call it. Same shape as `release` / `deploy_pull` / `archive` — call
> restriction is doc-discipline + the tool's own description banner, not a runtime guard.
> devops-engineer OWNS this KB doc (the *what + why + how*) but does NOT invoke the *tool*.

## Why this pattern exists

The **engineer-brief-patch-file-first** pattern (see `KB § PATTERNS/common/dispatch-engineer-tuning.md` — the dispatch-tuning protocol the patch-file-first rule is part of; the standalone authority lives today as memory `feedback_engineer_brief_patch_file_first.md` — NOC-REMEDIATE[kb-doc-missing]: 2026-05-27, promote memory → KB doc so this composes-with cite resolves to a peer KB pattern, not a sibling protocol) instructs every dispatched engineer to write its diff to `/tmp/<slug>.patch` **BEFORE** attempting return-text generation. This survives the harness watchdog (~600s) killing the return — the architect can salvage the work from the patch file. The cost: `/tmp/*.patch` accumulates across many sessions, and macOS's passive `periodic` daily sweep (3-day TTL) is timer-based, not semantic.

**Semantic policy:** a patch is *retired* (safe to delete) the moment we can prove its content landed OR the dispatch is old enough to be dead. That's our policy — not the OS clock's.

## The tool

`noctus.dev.tmp_cleanup` (`mcp/noctusai/tools/noctus/dev/tmp_cleanup.py`):

```python
tmp_cleanup(
    glob_root="/tmp",
    pattern="*.patch",
    max_age_days=14,
    dry_run=True,
    repo_root=None,
) -> dict
```

**Retirement verdict** for each `/tmp/*.patch`:

| Reason | Trigger | Action |
|---|---|---|
| `landed-patch-id` | `git patch-id --stable` matches a patch-id reachable from `origin/dev` (last 500 commits) | delete |
| `aged-out` | `mtime ≥ max_age_days` AND no patch-id match | delete |
| `malformed` | `git patch-id --stable` cannot parse the file | delete |
| `kept-fresh` | none of the above | keep |

500-commit lookback on `origin/dev` is wider than `max_age_days` so the patch-id branch always wins over age when content actually landed (a stale patch whose content landed gets `landed-patch-id`, not `aged-out`).

CLI: `python mcp/noctusai/cli.py --tmp-cleanup [--force] [--tmp-cleanup-max-age-days N]`. Dry-run unless `--force`.

## Orchestrator wiring

The `.claude/agents/orchestrator-operator` runs `tmp_cleanup(dry_run=False)` as a **standing end-of-tick step**, after draining the dispatcher inbox + before returning the summary. The operator surfaces one line in its return:

```
Hygiene: <N> patches purged (<M> bytes freed); <K> kept-fresh.
```

If the tool errors, the operator surfaces `Hygiene: FAILED — <error>` and does NOT block the tick.

The sweep is bounded by design:
- Scope: `/tmp/*.patch` only.
- Untouched: `/tmp/claude-501/.../tasks/` (harness-managed) + any other `/tmp/*` pattern + any worktree/repo file (that's `cleanup_stale_worktrees`).

## Composes with

- `KB § PATTERNS/common/dispatch-engineer-tuning.md` — the dispatch-tuning protocol the patch-file-first rule is part of (the *why* patches exist in `/tmp/`). The standalone authority lives as memory `feedback_engineer_brief_patch_file_first.md` today; NOC-REMEDIATE[kb-doc-missing] above tracks promoting it to a KB peer.
- `KB § PATTERNS/common/storage-hygiene.md` — sibling: worktree + branch cleanup.
- `KB § PATTERNS/common/dispatch-engineer-tuning.md` — sibling: the dispatch protocol that produces these patches.
- `KB § PATTERNS/common/scoped-auto-improvement.md` — the standing-sweep shape this follows.

## Why not just `find /tmp -mtime +N -delete`?

- **No patch-id check.** OS-timer doesn't know which patches' content has actually landed; it deletes by clock alone, leaving fresh-but-orphaned patches around and gambling on still-relevant ones.
- **No visibility.** The operator's return summary is the only place where the user sees what got swept, and a `find` invocation can't structure that.
- **No MCP exposure.** `noctus.dev.*` tools are agent-callable + audit-friendly + the methodology layer's standing shape (`KB § PATTERNS/architect/mcp-first-scripts.md`).

## Failure modes + safety

- **Network/git unavailable** → `_landed_patch_ids` returns empty set; the patch-id branch never fires; only `aged-out` + `malformed` purge. Conservative degradation.
- **Permission denied on unlink** → captured in `delete_failed` list, never raised. The next tick retries.
- **`/tmp/<f>.patch` is from a different repo's dispatch** → its patch-id won't match `origin/dev`; if it is also fresh, it is kept. Cross-repo poisoning is impossible because the only deletions on the no-match path require age.

## Tuning knobs

| Knob | Default | When to change |
|---|---|---|
| `glob_root` | `/tmp` | tests; OS where `/tmp` is elsewhere |
| `pattern` | `*.patch` | NEVER extend without a sibling KB doc |
| `max_age_days` | 14 | shorten if salvage window is tighter; lengthen if a long-running dispatch produces patches that need preservation |
| `dry_run` | True | False only when caller is the orchestrator OR `--force` CLI |

## History

- 2026-05-27 — codified after v4.0 ship: 38 `/tmp/*.patch` files accumulated, oldest 4 days. Built `noctus.dev.tmp_cleanup` + wired orchestrator-operator end-of-tick step. Owner: `devops-engineer`.
