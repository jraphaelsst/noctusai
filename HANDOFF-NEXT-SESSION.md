# HANDOFF — 2026-08-31 (session 2, post-promotion) → next session

> **You are the tech-lead.** Contextualize first (`/contextualize`), then read this.
> Everything below is verified state, not expectation. Where something is unverified,
> it says so explicitly.
>
> **Nothing is in flight. Prod is current and verified. There is no outstanding
> release work.**

---

## 0 · THE PROMOTION IS DONE — VERIFIED, NOT ASSUMED

The previous handoff's §0 ("prod is ~35 commits behind") is **closed**. 36 commits were
blessed and promoted, and all 7 live products were deployed and verified on 2026-08-31.

| ref | sha | meaning |
|---|---|---|
| `origin/dev` | `0e13ea71` | tree clean, no stashes, primary worktree only |
| `origin/main` | `0e13ea71` | ✅ blessed |
| `origin/prod` | `0e13ea71` | ✅ promoted |
| `origin/prod-backup` | `34a0c4c4` | ✅ previous prod — the rollback pointer |

**The live fleet deliberately runs the OLDER `34a0c4c4` images, and that is
correct.** The 8 commits promoted after it touch only MCP tooling, KB, docs and
ledgers — `git diff --name-only 34a0c4c4..0e13ea71` contains zero `products/`,
`seed/` or `core/` paths. `release stage=promote` reported `rebuild.needed:
false`, and `deploy_verify` classifies every product as steady state ("13 files
changed … but NONE touch this product's build inputs"). Images rebuild only when
their build scope changes. **Do not "fix" this by redeploying** — it is the
designed behaviour, and a needless swap is downtime for nothing.

**Evidence, each leg observed on `34a0c4c4` itself:**

| gate | result |
|---|---|
| CI (`Tests & Build`) | ✅ green — run `33419899008`, `headSha` confirmed = `34a0c4c4` |
| `predeploy_check` × 7 live | ✅ all `ready`, exit 0, 7/7 sub-checks each |
| GHCR fleet build on `prod` ref | ✅ success — run `33422383724` (this is what moves `:latest`) |
| `deploy_image` × 7 | ✅ all `deployed` + healthy, swap-verify matched running image id AND revision |
| `deploy_verify` | ✅ `verified` — 0 missing / 0 drifted / 0 degraded / 0 unverifiable |
| `spa_smoke` | ✅ 7/7 serving a real JS bundle, deep link `/login` → 200 |

Every live product reports `startup_hook_error: null`. Deploy order was
**canary-then-fan-out**: social-wiring first (it carried the most change), fully verified
on all three witnesses, then the remaining six in batches, `core` last.

**Rollback, if ever needed:** `prod-backup` is `d5f492a2`, and every product has a
`:previous` image tag snapshotted from this deploy.

---

## 1 · THREE CORRECTIONS TO THE PREVIOUS HANDOFF

Recorded because each one would have cost the next session time.

1. **The dev tip was `34a0c4c4`, not `32fb55fe`.** The previous handoff was written one
   commit before its own final docs commit. CI was already green on `34a0c4c4`, so the
   promotion never needed a new CI run — the "check its result, do not assume it"
   instruction was right, and checking is what revealed the tip had moved.
2. **The `build-scope.txt` fallback warning was a false alarm.** `deploy_verify` warns
   that it fell back to the 2026-08-17 snapshot when `SUPABASE_URL` /
   `SUPABASE_SERVICE_ROLE_KEY` are absent from the MCP server's env. Checked against the
   **live catalog** via `--refresh-build-scope` with the root `.env` sourced: the snapshot
   matches exactly (same 7 live, same 5 inactive). The warning is about *roster staleness
   risk*, not an observed mismatch. **The MCP server is started without those two vars**,
   so this warning will recur every session until that changes — it is not new drift.
3. **The two leftover stash entries are NOT empty.** The previous handoff called them
   "two now-empty stash entries." They hold 3 + 2 lines of
   `project-history/auto-improvement.ndjson` — the 5 recovered ledger rows themselves. The
   *conclusion* was right (safe to drop) and is now **verified**: all 5 rows were matched
   by exact `ts` against the committed ledger and are present. They are redundant
   duplicates, not empty. Dropping them (`git stash drop` ×2) is a local write and was
   deliberately left to the owner.

---

## 2 · STILL OPEN, NOT ASSIGNED

Carried forward unchanged from the previous handoff — none of these were touched.

- **`cli.py` rc=0 on a crashed dispatch — UNREPRODUCED.** Highest value; it undermines
  every other gate. Observed once: `--auto-improvement-query` under a bare `python` raised
  `ModuleNotFoundError`, printed a traceback, and still exited 0. An AST sweep of every
  `except` in `main()` found only two, both `sqlite3.Error`, neither matching.
  **Do not treat the cause as known.** Suggested structural backstop when someone next
  touches `main()`: wrap the `if __name__ == "__main__"` dispatch in a top-level
  `try/except Exception: traceback.print_exc(); sys.exit(1)`.
  **Workaround meanwhile: always use `venv/bin/python3`.**
- **Outline-corpus baseline tolerance.** ±5% relative is wrong for small files — one
  legitimate export is 25% on a 4-symbol file, so it keeps firing on the files it has
  least to say about. An absolute floor (±1 symbol regardless) fits its stated intent.
  Loosening a guard is a deliberate decision, not a side effect of a red build.
- **Cat C remainder:** orbity (63) and therapy-platform (25) untouched; 8 erp hooks
  unaudited (`useCertidoes`, `useComissoes`, `useGamificacao`, `useImpostos`,
  `useManutencao`, `usePropostas`, `useSeguros`, `useMatches`).
- **`IGIG_COFRE_KEY`** — igig has the same latent shape as `ENCRYPTION_KEY` but was
  **deliberately left undeclared**: no evidence the key is set in prod, and a wrong
  declaration is an **outage**, not a warning. Verify via the VPS `.env` first, then add
  `required_prod_config` to `products/igig/backend/app/main.py`.
- **p-studio migration `009`** is committed but **unapplied** — applying it is the
  owner's call. (Verified previously: `p-studio` org has 0 members, `noctusai` has 1.)
- **Duplicate MCP tool registration:** `noctus.dev.agent_context` and
  `noctus.dev.dispatch_budget_summary` emit "Tool already exists" on every
  `build_server()`.
- **Dead code found in passing:** `orbity/hooks/useClients.ts` (zero consumers),
  `useMetaAds.ts::useCampaignMetrics`,
  `personal-finance/useRecorrentes.ts::useProximasContas`.
- **3 `ChartCard`-mocking test files** (`Corretores`/`Origens`/`Empreendimentos`) drop the
  `loading` prop entirely, so they structurally cannot catch a gate regression.
- **The MCP server must be RESTARTED to pick up the divergence-loop fix** (§5). It
  runs whatever it imported at startup, so `task_branch cleanup` will keep
  reporting `salvage_pushed: false` in any session started before the fix landed.
- **MCP server env:** started without `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`, which
  is why catalog-backed tools fall back (see §1.2). Worth fixing at the server-launch
  layer so `deploy_verify` reads the live catalog directly.

---

## 3 · MCP SERVER DEATH — NOW WITH LIVE EVIDENCE

`a186dd9b` fixed the **second** death mechanism. The previous handoff flagged it as
unit-tested and measurement-backed but **never having run a live session**. That caveat is
now discharged.

**This session ran the fixed server for the entire promotion** — including 4 and then 3
concurrent `predeploy_check` calls (each running a vite build + pytest), 3 concurrent
`deploy_image` swaps, and a full `deploy_verify` + `spa_smoke` sweep. **The server never
stalled or died.** Long calls backgrounded cleanly at the 120s boundary and returned
correct results; the stdio channel stayed responsive throughout.

Recap of why there were two mechanisms, since it is the useful part:

- `39e4256f` wrapped sync tools in `anyio.to_thread.run_sync`. That genuinely fixes
  **I/O-bound** blockers (SSH sleeps, subprocess waits) because those release the GIL.
- It does nothing for **CPU-bound** ones — threads share the GIL. Measured at incident
  scale (6 concurrent ~15s calls): I/O-bound control avg **0.3 ms** round-trip; CPU-bound
  avg **22.2 s**, max **40.2 s**, 100% single-core, full serialization.
- `a186dd9b` re-execs the graph rebuild as a **subprocess**, whose blocking OS wait
  releases the GIL. The gate sits at the one call that does the heavy work, so every
  current and future caller inherits it with no per-tool bookkeeping (a per-tool registry
  would be the "hand-maintained lists drift" shape).

**The subprocess path itself is now production-exercised too.** A `task_branch
action='cleanup'` at the end of this session triggered a real rebuild inside the live MCP
server: `rebuild: full`, 39,747 nodes / 63,880 edges in **11.6s**, and the server stayed
responsive and answered the very next tool call normally. So both the in-sync fast path
and the heavy subprocess path have now run in a live session.

Still not observed: a heavy rebuild triggered *concurrently with* several other in-flight
tool calls. That is the precise incident shape, and it remains inferred from the
measurement rather than witnessed in production.

---

## 4 · KNOWN-GOOD COMMANDS

```
VENV=/Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python3
$VENV mcp/noctusai/cli.py --predeploy-check <slug>          # value form, NOT --product
$VENV mcp/noctusai/cli.py --verify-kb-sync --check-claude-md-router
$VENV mcp/noctusai/cli.py --deploy-image <slug> --deploy-image-confirm
$VENV mcp/noctusai/cli.py --deploy-verify --spa-smoke
set -a && . ./.env && set +a   # gives catalog-backed tools their Supabase creds
```

**Traps that have actually cost time — all still live:**
- Verify by **exit code** captured as `rc=$?`. `cmd | tail` returns *tail's* status.
- Fresh worktrees have **no `node_modules`** — use `task_branch action='start'
  wire_env=True`, or every vitest/vite/tsc run fails with `ERR_MODULE_NOT_FOUND` and looks
  like a real break.
- **Never run `pytest mcp/noctusai/tests` unbounded** — `TestSeedCompliance` /
  `TestAIFeatureCompleteness` are documented at 25–50+ minutes locally.
- **`primary_write_guard` and shell redirects:** a redirect target containing a shell
  variable (`> "$dir/f$i.txt"`) cannot be statically parsed, so the guard judges the
  command against the primary checkout and refuses — even for a read-only check. Write the
  path literally, or restructure to avoid the redirect. This is guard-working-as-designed,
  not a false positive to route around.
- A backgrounded or timed-out `deploy_image` is **`unverified`, not success** — always
  confirm with `deploy_verify`, which is an independent witness with zero dependency on
  `deploy_image` having run.


---

## 5 · THE PRIMARY/ORIGIN DIVERGENCE LOOP — ROOT-CAUSED AND FIXED (`d0170d92`)

The loop the previous handoff catalogued in §3c ("the ledger helper's rebase leg
cannot run against a dirty tree, and the cost-log hook dirties that very file on
every commit") is **fixed at the tool level**. It had been hand-cleared once per
session and had accumulated **five prior ledger entries, all marked closed**,
because each one fixed an adjacent symptom while the cause survived.

**Cause.** `_ledger_push.commit_and_ff_push_ledger` rebases onto `origin/dev`
before FF-pushing. `git rebase` refuses on ANY dirty file, and the cost-log
pre-commit hook dirties `project-history/vector-costs.ndjson` on essentially every
commit — including the ledger commit made one line earlier. The rebase was
refused, the helper returned `committed_locally=True, pushed=False`, and the
primary was left diverged.

**The fix already existed one level up.** `task_branch.integrate` solved the
identical wall on 2026-05-28 ("Bug C", logged N=5+) by classifying dirty files
benign-vs-real and auto-stashing the benign ones. The 2026-06-30 DRY lift moved
the *idiom* into `_ledger_push` and left the *hardening* behind — silently
un-fixing the copy. Both now share `tools/noctus/dev/_benign_stash.py`.

Real in-progress work still blocks, but as an explicit `status="dirty_blocked"`
naming the files, not a mystery divergence. No `--force`/`--autostash` shortcut is
issued; only the known-benign set is stashed, popped in a `finally`.

**Two lessons worth more than the fix:**
- **Extracting shared code without its accumulated fixes silently un-fixes the
  copy.** Lift the hardening with the idiom, from every site that shares the leg.
- **A fake that cannot express the failure will pass forever.** Every
  `_ledger_push` test used a runner whose `rebase` returned a scripted rc
  regardless of tree state, so no fake-based test could have caught this. Pinned
  in `test_ledger_push_realgit.py` against REAL git, with a control run confirming
  the old code fails the same scenario (1↔1 divergence, row never lands).

Also hardened: the porcelain parser's fixed 3-char offset silently TRUNCATED any
non-canonical `git status` line into a *different* path, which then misclassified
as real work. That truncation is what made 7 `branch_pointer` tests fail on first
contact with the shared helper.

Depth: `KB § PATTERNS/common/self-branching-mode.md` §12.

⚠️ **Restart the MCP server to get this.** A server started before `d0170d92` still
runs the old module, so cleanup keeps reporting `salvage_pushed: false` and you
keep reconciling by hand with
`git -c rebase.autoStash=true rebase origin/dev && git push origin HEAD:dev`.
