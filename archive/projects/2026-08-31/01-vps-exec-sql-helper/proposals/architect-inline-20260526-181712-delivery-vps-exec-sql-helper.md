# Proposal: vps-exec-sql-helper — Phase 1+2 delivery

**Agent:** architect-inline (claude-opus-4-7)
**Note kind:** delivery
**Origin:** project:vps-exec-sql-helper:phase-1-2
**Generated:** 2026-05-26 18:17
**Severity:** medium
**Effort:** low
**Affected products:** none (methodology + operational tooling — touches mcp/noctusai/tools/noctus/dev + tests + projects/cache-pg-vps-bringup/PROJECT.md)
**Status:** pending

---

## 1. Context

Closes the `scoped-improvement` surfaced in the `cache-pg-vps-bringup` delivery note (commit `74811b01`): the heredoc-through-SSH-through-docker-exec path failed silently during schema init, and the working `docker cp + docker exec psql -f` idiom was discovered via trial-and-error. User instruction: *"scoped-improvement surfaced for future <- implement now."* — overriding the N=1 codify defer.

Bundled with: W2 — recommendations for cache-pg connectivity (the prior delivery note's "DEFERRED — architectural decision needed" item). User instruction: *"W4 — Deferred (architectural decision needed) <- follow with recommendations."*

---

## 2. Situation (as-shipped state)

### W1 — `noctus.vps.exec_sql` MCP tool

New module `mcp/noctusai/tools/noctus/dev/vps_exec_sql.py` implements the working 4-step idiom:

1. SSH heredoc writes SQL to `/tmp/noctus-exec-sql-<uuid>.sql` on VPS host (uses a UUID-marked heredoc terminator to make body-collision virtually impossible).
2. `docker cp` the tmp file into the container.
3. `docker exec <container> psql -U <user> -d <db> -f <path>`.
4. Cleanup (host + container `rm -f`, try/finally guarantees execution even on failure).

API: `exec_sql(sql, container, db, user?, host?, cleanup?, ssh_runner?)`. Defaults: `user = db` (PG convention for noctus-cache-pg) · `host = "noctus-vps"` · `cleanup = True` · `ssh_runner = real subprocess`. Returns `{ok, returncode, stdout, stderr, container, db, user, tmp_path, step, cleanup_ok, cleanup_err}`.

**Why a separate module from `vps.py`:** `vps.py` bans the `exec` token in emitted commands (per-module `_BANNED_TOKENS` colocated test) — the ban exists to prevent arbitrary-exec abuse via the operate-layer tools. `exec_sql` is a fixed, narrow command (`psql -f`) — the legitimate carve-out. Separate module keeps `vps.py`'s ban tight + tests deterministic.

Registered as MCP tool `noctus.vps.exec_sql`. CLI flag `--vps-exec-sql SQL_FILE CONTAINER DB` (+ `--vps-exec-sql-user`, `--vps-exec-sql-host`, `--vps-exec-sql-no-cleanup`). **16/16 unit tests pass** (FakeSshRunner injection — no real SSH/docker needed in test) + **real integration smoke succeeded against live cache-pg** (`SELECT count(*) ... = 6` matching the prior bringup).

### W2 — Cache-pg connectivity recommendations (`projects/cache-pg-vps-bringup/PROJECT.md`)

§7 expanded with:
- **§7a Resolved: VPS environment audit** — confirmed no `/opt/noctus/.venv/`, no `psycopg2` / `pgvector` on system python, port 5432 free on VPS host, `noctus-cache-pg:5432` reachable only inside docker network.
- **§7b 6-route trade-off table** (Routes A through F) with Phase 2 fit / Phase 3 fit / effort / pros / cons per route.
- **§7c Recommended sequence**: Phase 2 = Route F.2 (VPS-side venv + `127.0.0.1:5432:5432` host-loopback compose change) · Phase 3 = Route A (GH Actions deploy key + same compose change). The same compose change covers both phases.
- **§7d Routes-not-taken table** (B, C, D, E, F.1, F.3) with rationale per the dispatch-with-PROJECT-and-notes §4a.3 convention.

No code change in W2 — pure decision-space artifact for user accept/reject/adapt.

---

## 3. Proposed Solution

Delivery — sections 3.1-3.5 record HOW.

### 3.1 Linkage

The vps_exec_sql wrapper closes a real recurrence trap: SSH-through-docker-exec heredoc fails SILENTLY (no error code, no stderr). Future schema operations now have a one-call tool that uses the verified-working idiom — preempts the trial-and-error pattern. The connectivity recommendations table closes the user's "follow with recommendations" instruction: 6 routes scored on Phase 2 + Phase 3 fit, one recommended sequence proposed, awaits user go/no-go.

### 3.2 Application instructions (HOW)

1. Authored `vps_exec_sql.py` (~190 lines, full docstring, injection seam, try/finally cleanup discipline, UUID-marked heredoc, validation on inputs).
2. Registered in `tools/noctus/dev/__init__.py` (import + `.register(server)` call).
3. CLI flag added next to `--codify-source-ref` (handler block placed after the codify_log handler).
4. Tests authored (`test_vps_exec_sql.py`) covering: empty-input validation paths (4) · happy-path 4-call sequence with command-shape assertions (5) · user defaults + overrides + custom host (3) · failure paths with cleanup discipline (4) · cleanup-toggle (1) · tmp filename uniqueness (2). Total 16/16 pass.
5. Real smoke against live cache-pg via `--vps-exec-sql /tmp/smoke.sql noctus-cache-pg noctus_cache` — verified `count(*)` query returns 6 (matching the prior schema-init).
6. W2 §7 rewrite in `projects/cache-pg-vps-bringup/PROJECT.md` — VPS env audit → trade-off table → recommended sequence → routes-not-taken table.
7. Change log entry added to that PROJECT.md §11.

### 3.3 Seed APIs / shared lib involved

- `subprocess.run(["ssh", host, cmd], ...)` — same pattern as `vps.py:_run_remote_default` (consistency).
- `shlex.quote(...)` — for safe shell-quoting of all variable substitutions.
- No new dependencies.

### 3.4 Risks before applying

Low risk. The tool is additive — no existing call site changes. Validation paths preempt empty-input misuse. The `ssh_runner` injection seam means tests never touch real network. The heredoc UUID marker prevents body-collision with the SQL content.

The real integration smoke passed against the live cache-pg — confirms end-to-end correctness.

### 3.5 Alternatives considered

(All captured in `projects/cache-pg-vps-bringup/PROJECT.md §7d` — routes-not-taken.)

---

## 4. Effects

- **Behavior:** new MCP tool `noctus.vps.exec_sql` + CLI flag `--vps-exec-sql`. No existing behavior changed.
- **Risk profile:** SAFER — the working idiom is now encoded; future schema ops can't trial-and-error past the heredoc-fail recurrence trap. Tmp-file cleanup is mandatory (try/finally).
- **Ergonomics:** schema init becomes a one-liner from any context (local dev, CI, scripts). The `cleanup=False` toggle is available for debug-time inspection.
- **Coverage:** +16 tests · real integration smoke passing.

---

## 5. Acceptance Criteria

- [x] `noctus.vps.exec_sql` MCP tool registered
- [x] CLI flag `--vps-exec-sql SQL_FILE CONTAINER DB` works
- [x] All tests green (16/16)
- [x] Real integration smoke against live cache-pg passing
- [x] Recommendations doc updated in `cache-pg-vps-bringup/PROJECT.md §7`
- [x] Self-codify_log s4 entry filed (via the new tool itself — recursive dogfood)
- [x] This delivery note filed
- [ ] Keeper gates green (verified in W3)
- [ ] Commit + push + FF-merge dev (W3 in flight)

---

## 6. Related files

- `mcp/noctusai/tools/noctus/dev/vps_exec_sql.py` (NEW)
- `mcp/noctusai/tools/noctus/dev/__init__.py` (register)
- `mcp/noctusai/cli.py` (CLI flag + handler)
- `mcp/noctusai/tests/test_vps_exec_sql.py` (NEW, 16 tests)
- `projects/cache-pg-vps-bringup/PROJECT.md` (§7 rewrite)
- `projects/vps-exec-sql-helper/PROJECT.md` (dispatch brief)

---

**Codification events emitted (this slice):**
- s1-emergent: was already at s1 (from cache-pg-vps-bringup delivery note's scoped-improvement)
- s2-memory: none (skipped — same-commit s2→s4 compression per user "implement now" override)
- s3-codified: none — the tool IS the codification at this stage; KB doc reference in tool docstring + `KB § PATTERNS/devops/containerization-operations.md` link (existing parent pattern carries the idiom now via tool reference)
- s4-keeper: `noctus.vps.exec_sql` MCP tool. The tool is the structural enforcement of the working idiom — future authors don't pick a path, they call the tool.

**drift-found:** (none observed)

**scoped-improvement:** The W2 §7 recommendations table is the FIRST documented use of the routes-not-taken §4a.3 convention applied to an OPEN question (not pre-execution). Other projects could benefit from this shape — turning "open questions" into "structured-options + recommended sequence + rejected routes" tables, ready for user accept/reject/adapt. **Codify candidate** — surface for future. N=1 today.

**Routes-not-taken encountered + chose-not-to-surface:**
- Could have made `exec_sql` accept multiple statements as a list and run them in a single transaction — `psql -f` already runs the whole file in a single connection; YAGNI for now.
- Could have added a `--dry-run` mode that prints the SQL + commands without executing — defer; the `cleanup=False` debug path already lets you inspect what landed.
- Could have generalized to `noctus.vps.exec_command(cmd)` for non-SQL ops — N=1 today; YAGNI per recurrence rule.
