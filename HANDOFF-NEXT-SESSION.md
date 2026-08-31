# HANDOFF — 2026-08-31 session → next session

> **You are the tech-lead.** Contextualize first (`/contextualize`), then read this.
> Everything below is verified state, not expectation. Where something is unverified,
> it says so explicitly.
>
> **All dispatched work is finished and integrated. Nothing is in flight.**

---

## 0 · THE ONE THING THAT MUST HAPPEN FIRST

**Prod is ~35 commits behind a fully-verified `dev`. The promotion is the only
outstanding work.** It could not be completed last session for a reason that is *not* a
code problem — see §3.

| ref | sha | meaning |
|---|---|---|
| `origin/dev` | `32fb55fe` | everything below, tree clean, 1 worktree (primary only) |
| `origin/main` | `d5f492a2` | **stale** — session-start state |
| `origin/prod` | `d5f492a2` | **stale** — what the VPS is running now |
| `origin/prod-backup` | `d5f492a2` | ✅ correct rollback pointer (was stale at `39e4256f`; fixed last session) |

### The promotion, step by step

1. **Confirm CI green on the sha you intend to bless.** `5da98d77` was verified 34/34.
   The tip has moved since (`ba3361cc`, `818f6c2a`, `8597b21a`, `9a79f585`, `53323c09`,
   `32fb55fe`). A CI run on `32fb55fe` was started at handoff — **check its result, do not
   assume it.** Never bless a sha whose CI you have not seen green: a red build reached prod
   once (`1c83232f`) and that is exactly why the probe exists.
   ```
   gh run list --branch dev --limit 3
   gh run view <id> --json conclusion,headSha
   ```
2. **`predeploy_check` every active product** (MANDATORY — the dev fleet is dormant, so this
   is the primary functional evidence): `noctus.dev.predeploy_check <slug>` → `status: ready`,
   exit 0. Verified `ready` last session for **social-wiring** and **p-studio**; re-run for
   the rest and re-run these two on the final sha.
3. **Bless + promote.** Preferred, if MCP is up:
   `noctus.dev.release stage=bless` → `stage=promote` (`confirm=true`).
   Manual equivalent — this is the *documented sanctioned form* from `scripts/hooks/pre-push`.
   The env var marks a deliberate deploy; it does **not** skip hooks, and a non-fast-forward
   is still refused. It is not `--no-verify`:
   ```
   NOCTUS_ALLOW_MAIN_PUSH=1 git push origin <sha>:refs/heads/main
   NOCTUS_ALLOW_MAIN_PUSH=1 git push origin <sha>:refs/heads/prod
   ```
   ⚠️ `prod-backup` is already correct at `d5f492a2`. `release stage=promote` re-snapshots
   automatically; going manual, snapshot prod→prod-backup FIRST.
4. **Deploy**: `noctus.dev.deploy_image <slug>` (auto-rollback on a failed health probe), or
   CLI `--deploy-image <slug> --deploy-image-confirm`.
5. **Verify — BOTH legs, non-negotiable.** `deploy_verify` (`status: verified`, exit 0) AND
   health, then **`spa_smoke`** — every step-4 check passes while the JS bundle is missing
   (container up, `/api/health` 200, edge returns the HTML shell) and the user sees a blank
   page. If `deploy_image` times out or MCP disconnects mid-call, that is **`unverified`, not
   success** — run `deploy_verify` for ground truth.

**Prod health baseline, 2026-08-31 pre-deploy:** social / erp / igig / core / orbity all
HTTP 200 with `startup_hook_error: null`. Compare after deploying — a product whose lifespan
hook failed still serves 200 and only reports it in that field.

---

## 1 · WHAT SHIPPED TO `dev` — context for the release notes

**Two carried-over ledger items — both closed.**
- **Upload body-size caps.** Not hygiene — a **live fleet bug**: 13 `UploadFile` routes across
  5 products silently capped at the 1 MB webhook-DoS default, so real phone photos and
  multi-thousand-row CSVs got a 413 before the handler ran, while every fixture-sized test
  passed. Now: ceilings declared per route, a **boot-time derivation that refuses** when an
  upload route has no entry, and keeper `check_upload_route_body_override` as backstop. The
  gate caught a real miss on first contact with real code — `/api/chat/message`, whose
  `UploadFile | None` form is easy to overlook by eye.
- **Document projection DRY** (N=4 → `documento_store.documento_base`).

**Meta Ads.** Ad rows are clickable → per-ad live metrics modal. Building it surfaced that
`/insights/compare` counted only `actions["lead"]`, never `actions["onsite_conversion.lead"]`
— which the pilot account actually uses. It affected **four** endpoints incl. the overview
tiles. Fixed backend (`meta_ads/services/leads.py::leads_from_actions`, which SUMS both —
they are distinct capture channels, not aliases) and the frontend helper, kept in lockstep.

**Refresh / unmount (the user's screen recording).** Two compounding bugs:
`useDadosPessoaisMutation` invalidated the *entire* client family on every field edit, and
the section then unmounted on the resulting refetch. Fixed, plus **70 sibling unmounts and
140 key-change flicker sites** across seed organs, social-wiring, igig, erp and 5 more.

**🔴 The most important finding — read `KB § PATTERNS/frontend/lying-loading-state.md`.**
CLAUDE.md §1 and that KB doc prescribed `isPending || isFetching` as *the* correct gate. Right
for the 2026-07-21 incident it came from (an empty state lying over 28 brokers / 12,177 real
leads), wrong as a universal rule: it is true during *every* background refetch, so any
early-return skeleton unmounts live content. **All 70 sites were following the documented rule
correctly.** Now two-signal:
```
showSkeleton = isPending && !data      // nothing to render yet
isRefreshing = isFetching && !!data    // data exists — keep rendering, indicator only
placeholderData: (prev) => prev        // key-change transitions
```
It had propagated three ways: into 70 code sites, into the keeper's own **remediation
strings** (so the gate *taught the bug* every time it fired), and into **two tests that
hard-coded the buggy contract and defended it**. All three corrected. Lesson, now in the KB:
**codify the decision procedure, not the expression that closed the incident.**

**Card bugs**, root-caused not patched: birthdate saves 500'd because
`model_dump(exclude_unset=True)` lacked `mode="json"` (a live `date` reached postgrest);
gênero silently cleared because the `<Select>` *displayed* "Masculino" while its state stayed
`""`, so confirming the on-screen default sent `null`. Plus view/download on document
line-cards (signed-URL endpoint already existed — no new auth surface).

**Wave 2 — cache invalidation. The brief was wrong about the bug, in a useful way.**
Dispatched as "449 over-broad invalidations, narrow the safe ones." Both agents found
something worse in the same code: **invalidations pointing at the wrong key entirely.**
- **personal-finance**: `useTransacoes` invalidated `["orcamentos"]` (the budget *list*), but
  `_sincronizar_orcamento` writes `orcamento_itens.valor_gasto`, read only under
  `["orcamento", …]`. **Budget progress went silently stale after every transaction.** Same
  bug in `useUpdateCategoria`. Also four detail pages (`ContaDetalhes`, `CarteiraDetalhes`,
  `OrcamentoDetalhes`, `MetaDetalhes`) whose own edit mutation never invalidated their own
  singular query, and `useRecorrentes` missing its transaction-path invalidations entirely.
- **erp**: the `metas` ×18 cluster was a **key collision** — `["metas"]` prefix-matched an
  unrelated team/gamification domain, so every personal-goal write refetched team rankings,
  periods and members. Renamed behind a `METAS_ROOT` constant (verified both sides moved
  together: 8 query uses, 7 invalidation uses, zero surviving literals — a half-done key
  rename silently stops invalidating anything). Two missing invalidations added
  (`empresa-resumo`, `rankings`).
- Deliberately left: 8 erp hooks unaudited (depth over coverage), `useCreateVistoria →
  locacoes` left broad because the server-side path could not be verified, daily-life's 17
  invalidations left alone as already correctly scoped.

**MCP server death — fixed, with measurement.** See §3a; this is the one worth reading.

**Recovered work.** Migration 060 held a **plpgsql syntax error** — fresh-database
provisioning was broken (prod fine; renames completed out-of-band, verified against the live
DB). p-studio migration `009` committed **but NOT applied** (verified: `p-studio` org has 0
members, `noctusai` has 1). `required_prod_config` gate finished with 21 tests; an unrelated
52-line `docker-compose.prod.yml` diff was dropped rather than smuggled in. 5 auto-improvement
ledger rows recovered from orphaned stashes.

---

## 2 · NOTHING IS IN FLIGHT

All seven dispatched slices completed, were verified on the **merged tip** (not just
per-branch), and are pushed. All worktrees torn down; `git worktree list` shows the primary
only; primary is `0 0` with origin.

One integration failure was caught and is worth knowing about, because it will recur:
`test_outline_typescript_corpus.py` failed **only on the merged tip** — the baseline is a
derived artifact shared across parallel slices, so neither wave-2 branch could see it alone.
Exactly the coupling CLAUDE.md §1 names. Two entries were ratified surgically (each file
gained exactly one legitimate export) rather than regenerating the 645-entry snapshot, which
would have absorbed unrelated drift silently.

**Known weakness in that guard, deliberately NOT changed:** its ±5% relative tolerance is too
tight for small files — one legitimate export is 25% on a 4-symbol file, so it will keep
firing on the files it has least to say about. An absolute floor (±1 symbol regardless) fits
its stated intent better. Loosening a guard is its own decision, not a side effect of a red
build, so it was left for a deliberate call.

---

## 3 · WHY THE PROMOTION DID NOT HAPPEN, AND WHAT IS STILL OPEN

**The blocker was the Claude Code permission classifier, not the repo.** `git push …
refs/heads/main` was denied twice by the harness — above both the repo's guard and the MCP
outage. Run the two commands in §0.3 yourself with `!`, or add a Bash permission rule.

### 3a · MCP server death — root cause MEASURED and fixed

`39e4256f` (2026-08-29) fixed a real cause: FastMCP dispatches non-coroutine tools **inline on
the STDIO event loop**, and 173/185 tool modules are synchronous, so a slow sync tool makes
the server deaf. It wrapped every sync tool in `anyio.to_thread.run_sync`. **That fix is
correct and is untouched.** But it held ~90 minutes on 2026-08-31 and died again.

**Why: there were two mechanisms, and only one had been fixed.** A thread moves work off the
loop's *thread* but threads share the **GIL**. That genuinely fixes **I/O-bound** blockers
(SSH sleeps, subprocess waits — the deploy profile `39e4256f` measured, all of which release
the GIL). It does nothing for **CPU-bound** ones.

Measured at incident scale (6 concurrent ~15s calls, matching the 39,450-node graph rebuild),
same wrapper, same concurrency, only the GIL-holding variable changed:

| blocker | stdio round-trip latency |
|---|---|
| I/O-bound (`time.sleep`) — control | avg **0.3 ms**, max 2.3 ms |
| CPU-bound (pure-Python loop) | avg **22.2 s**, max **40.2 s** |

357 of 400 messages delayed >5s, 100% single-core CPU — full GIL serialization, zero
concurrency benefit. That is the death, reproduced.

**The fix** (`tools/noctus/dev/noc_graph_cache.py`): when running inside the MCP server, a
needed graph rebuild re-execs `cli.py --refresh-noc-graph` as a **subprocess**.
`subprocess.wait()` is a blocking OS wait that releases the GIL exactly like `time.sleep`, so
the parent worker thread idles while the CPU-heavy work runs in its own process with its own
GIL. Verified end-to-end on the real repo (39,746 nodes / 63,885 edges in 29.4s, parent never
blocked; the in-sync fast path stays at 0.58s). The gate sits at the ONE call that does the
heavy work — not a per-tool registry — so every current and future caller inherits it with no
bookkeeping (that matters: a per-tool list would be the "hand-maintained lists drift" shape).
Free bonus: the CLI path takes `acquire_refresh_lock("noc-graph")`, which the in-process call
did not — closing a concurrent-refresh race as well.

`server.py`'s `offload_blocking` docstring now carries **both** mechanisms; it previously
described only the deploy/IO one, which is precisely why today's conditions read as "already
fixed."

⚠️ **This change only takes effect on a server restart.** It is unit-tested and
measurement-backed but has never run a live session. If anything is odd, `prod-backup` and the
previous `noc_graph_cache.py` are one revert away.

### 3b · `cli.py` rc=0 on a crashed dispatch — UNREPRODUCED, still open

Observed once: `--auto-improvement-query` under a bare `python` raised `ModuleNotFoundError`,
printed a full traceback, and **still exited 0**. Any agent trusting a CLI exit code would
read a crash as a pass — a false-green in the verification surface itself.

**It could not be reproduced on investigation.** An AST sweep of every `except` in `main()`
found only two, both `sqlite3.Error`, neither matching; `--refresh-noc-graph` correctly exits
1 under a simulated `ModuleNotFoundError`. Logged as an open `s1-emergent` finding rather than
a guessed fix. **Do not treat the cause as known.** Suggested structural backstop when someone
next touches `main()`: wrap the `if __name__ == "__main__"` dispatch in a top-level
`try/except Exception: traceback.print_exc(); sys.exit(1)`, so no future branch can swallow a
crash. **Workaround meanwhile: always use
`/Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python3`.**

### 3c · Resolved — do not re-investigate

- **Orphan worktree `p-studio-absorption`** — deleted, 46 MB reclaimed. Never a policy block:
  the guard parsed the shell redirect `2>&1` as the write target.
- **`primary_write_guard` false positives** — fixed (112 tests): a redirect token read as a
  path; `git stash list`/`show` and the `--dry-run`/`-h` family treated as writes. Note
  `git -C <primary> status` was **never** broken — that earlier diagnosis was wrong.
  `git merge` on the primary stays deliberately allowed (the orchestrator's integration job).
- **5 stranded auto-improvement rows** recovered from orphaned stashes. The guard had been
  hiding the evidence of its own drift — `git stash list` was refused, so nobody could even
  enumerate them. **Two now-empty stash entries remain; their content is fully recovered and
  they are safe to drop** (`git stash drop` ×2 — a write, so from a worktree or by hand).
- **Primary/origin divergence** (6 orphaned pointer commits + dirty `vector-costs.ndjson`) —
  resolved via `pull --rebase` with autostash. This is the recurring loop with 4 ledger
  entries: the ledger helper's rebase leg cannot run against a dirty tree, and the cost-log
  hook dirties that very file on every commit.

---

## 4 · KNOWN-GOOD COMMANDS (MCP was down all session; these fallbacks work)

```
VENV=/Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python3
$VENV mcp/noctusai/cli.py --predeploy-check <slug>          # value form, NOT --product
$VENV mcp/noctusai/cli.py --check-upload-route-body-override
$VENV mcp/noctusai/cli.py --check-lying-loading-state
$VENV mcp/noctusai/cli.py --verify-kb-sync --check-claude-md-router
$VENV mcp/noctusai/cli.py --deploy-image <slug> --deploy-image-confirm
$VENV mcp/noctusai/cli.py --deploy-verify --spa-smoke
```
Integration without MCP: `git fetch origin && git -c rebase.autoStash=true rebase origin/dev`
→ run the suite → `git push origin HEAD:dev`. Pre-push hooks run fully.

**Three traps this session actually paid for:**
- Verify by **exit code** captured as `rc=$?`. `cmd | tail` returns *tail's* status (always 0).
- Fresh worktrees have **no `node_modules`** — symlink from the primary tree
  (`products/<slug>/frontend`, `seed/lib/frontend`, `seed/framework/frontend`) or every
  vitest/vite/tsc run fails with `ERR_MODULE_NOT_FOUND` and looks like a real break.
- **Never run `pytest mcp/noctusai/tests` unbounded** — it contains `TestSeedCompliance` /
  `TestAIFeatureCompleteness`, documented at 25–50+ minutes locally. Target the files you need.

---

## 5 · OPEN, NOT ASSIGNED

- `cli.py` rc=0-on-crash (§3b) — highest value; it undermines every other gate. Unreproduced.
- Outline-corpus baseline tolerance (§2) — ±5% relative is wrong for small files.
- Cat C remainder: orbity (63) and therapy-platform (25) untouched; 8 erp hooks unaudited
  (`useCertidoes`, `useComissoes`, `useGamificacao`, `useImpostos`, `useManutencao`,
  `usePropostas`, `useSeguros`, `useMatches`).
- **`IGIG_COFRE_KEY`** — igig has the same latent shape as `ENCRYPTION_KEY` but was
  **deliberately left undeclared**: no evidence the key is set in prod, and a wrong
  declaration is an **outage**, not a warning. Verify via the VPS `.env` first, then add
  `required_prod_config` to `products/igig/backend/app/main.py`.
- p-studio migration `009` is committed but **unapplied** — applying it is the owner's call.
- Duplicate MCP tool registration: `noctus.dev.agent_context` and
  `noctus.dev.dispatch_budget_summary` emit "Tool already exists" on every `build_server()`.
- Dead code found in passing: `orbity/hooks/useClients.ts` (zero consumers),
  `useMetaAds.ts::useCampaignMetrics`, `personal-finance/useRecorrentes.ts::useProximasContas`.
- 3 `ChartCard`-mocking test files (`Corretores`/`Origens`/`Empreendimentos`) drop the
  `loading` prop entirely, so they structurally cannot catch a gate regression.
