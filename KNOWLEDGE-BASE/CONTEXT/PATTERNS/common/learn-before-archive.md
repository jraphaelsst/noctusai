# Learn-before-archive — mandatory pre-delete salvage gate

> Generalizes `persistent-files-absorption` + `salvage-before-delete` into
> ONE enforced gate. Cross-links: `storage-hygiene.md` · `persistent-files-absorption.md`.

## The rule

**Before ANY destructive op — branch delete / worktree remove / file delete /
project archive / temp-file purge — ask: "what would be LOST, and is it
preserved elsewhere?"**

If the answer is "something durable and not already captured" → capture it first,
THEN delete. If everything is already on dev/KB/memory → delete without ceremony.

## Five categories to preserve

| Category | Destination | Skip condition |
|---|---|---|
| **Code / diffs** | `git format-patch` → `project-history/<archive>/` (re-appliable via `git am`) | Content patch-equivalent on origin/dev (git-cherry returns zero `+` lines) |
| **Lessons / decisions** | KB (`KNOWLEDGE-BASE/...`) or memory (`feedback_*` / `reference_*`) | Already in KB/memory verbatim |
| **Commands / runbooks / one-off scripts** | Relevant KB doc OR `scripts/` (never a dangling temp pointer) | Command is trivial / already documented |
| **Pointers / refs** | Recovery-pointer entry in `project-history/worktree-salvage.ndjson` | Always write — even integrated content gets a pointer |
| **Docs** | Absorb into canonical doc tree before the source is deleted | Already merged to main tree |

## Enforcement ladder

| Stage | Shape | Status |
|---|---|---|
| 1 | **Principle** — this KB doc + CLAUDE.md §1 rule | Shipped (2026-05-30) |
| 2 | **Tool** — `noctus.dev.salvage_before_delete(target, kind)` — extraction + logging | Shipped (2026-05-30) |
| 3 | **Keeper** — `check_dangling_remote_branches` flags unique-old remotes | Shipped (2026-05-30) |
| 4 | **Strict keeper** — flag a delete in recent history with no matching salvage-log entry | Deferred — needs git-log pattern + scope definition |

## Tool: `noctus.dev.salvage_before_delete`

```
salvage_before_delete(target, kind, dry_run=True)
  target: str   — branch name | worktree slug | file path | project slug
  kind:   str   — 'branch' | 'worktree' | 'path' | 'project'
  dry_run: bool — True = report only (default); False = write archives + ledger
```

Returns:
```json
{
  "ok": true,
  "dry_run": false,
  "target": "feat/some-branch",
  "kind": "branch",
  "preserved": ["recovery-pointer: origin/feat/... @ abc123 (3 unique commits)",
                "patch-archive: 3 patches written to project-history/orphan-remote-archive-2026-05-30/feat_some-branch/"],
  "ledger_entry_written": true,
  "warnings": []
}
```

Call pattern before `delete_integrated_remote`:
```
1. salvage_before_delete(target="feat/x", kind="branch", dry_run=False)
2. delete_integrated_engineer_remote(branch="feat/x", dry_run=False)
   → guard checks the ledger entry from step 1 before proceeding
```

## Scope of the gate

Fire for:
- Remote branches (`origin/*`) — any delete, including integrated ones
- Local worktrees (`.claude/worktrees/<slug>/`) — before task_branch cleanup
- Files under `projects/` — before project archive
- KB doc deletions — before removing a KB file (rare; absorb first)
- `/tmp/*.patch` files — already handled by `tmp_cleanup` (out-of-scope for this gate)

Do NOT fire for:
- Regenerable build artifacts (`node_modules/`, `__pycache__/`, cache SQLite files)
- `.env` files (secrets — never commit, never patch-archive)
- Automatic cache refreshes

## Anti-patterns

- **Blind delete** — `git push origin --delete feat/x` without salvage → content loss
- **Salvage-log skip for integrated branches** — even integrated content deserves a
  recovery pointer (the pointer is cheap; re-finding a branch SHA months later is not)
- **Absorption-last** — absorbing docs AFTER the delete means the source of truth
  is gone; absorb WHILE THE FILE EXISTS
- **Dangling temp pointer** — a command captured as `see /tmp/my-notes.txt` with
  the file then deleted is equivalent to not capturing it

## Composes with

- `persistent-files-absorption.md` — this rule generalizes it (artifact-scoped + any-kind)
- `storage-hygiene.md` — sibling (mole handles build artifacts; this handles content)
- `remote_branch_hygiene.py` — the MCP implementation of branch salvage + delete
- `salvage_before_delete.py` — the `noctus.dev.salvage_before_delete` tool
- `tmp-artifact-cleanup.md` — sibling for `/tmp/*.patch` lifecycle
- `dispatch-with-project-and-notes.md` — delivery-note absorption on dispatch close

## Decision log

- **2026-05-30:** Born after 330 dangling remote branches were discovered and the
  user asked: *"solve this FUCKING problem on our methodology — not losing important
  content to deleted files."* P3.1 of the branch-hygiene-and-learn-before-archive
  roadmap (see `project-history/roadmaps/branch-hygiene-and-learn-before-archive-2026-05.md`).
- **2026-05-30:** Scope limited to artifacts with unique content; regenerable
  artifacts (caches/builds/node_modules) are explicitly excluded.
- **2026-05-30:** Salvage-log requirement gated into `delete_integrated_engineer_remote`
  as a guard — dry_run=True default prevents accidental bypass.
