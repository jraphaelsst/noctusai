# VPS-exec-sql-helper — Project Document

> Closes the scoped-improvement from `cache-pg-vps-bringup` delivery note (commit `74811b01`): the `docker exec psql <<EOF` heredoc path failed silently during schema init; the working `docker cp + docker exec psql -f` idiom was discovered by trial-and-error. A small wrapper prevents recurrence.

- **Created:** 2026-05-26
- **Last updated:** 2026-05-26
- **Status:** ⏳ in progress
- **Owner / stakeholders:** rapha · architect (tech-lead, this session)
- **Related docs:** `KB § PATTERNS/devops/prod-cache-container.md` · `KB § PATTERNS/devops/containerization-operations.md` · `projects/cache-pg-vps-bringup/PROJECT.md` (parent surface)
- **Project slug:** `vps-exec-sql-helper`

---

## 1. Context & Purpose

The `cache-pg-vps-bringup` slice surfaced a usability gap: piping SQL into `docker exec psql` over SSH via heredoc (`ssh vps "docker exec ... psql <<EOF ... EOF"`) silently fails because at least one layer (SSH or docker exec input forwarding) munges the stream. The working pattern is:

```
(1) write SQL to /tmp/X.sql on VPS via SSH heredoc
(2) docker cp /tmp/X.sql container:/tmp/X.sql
(3) docker exec container psql -f /tmp/X.sql
(4) cleanup
```

User instruction: *"scoped-improvement surfaced for future <- implement now."* This slice ships the wrapper.

---

## 2. Confirmed constraints

- **Reuses existing `noctus.vps.*` infrastructure** — the project already has `noctus.vps.ps`/`recreate`/`prune` running via SSH; this slice adds one more capability.
- **Idempotent + safe** — SQL is written to `/tmp` (transient), copied in, executed, cleaned up. No persistent state left.
- **Authentication via SSH config** — the tool consumes the existing `~/.ssh/config noctus-vps` host alias; no new auth model.
- **Real integration test optional** — primary tests mock subprocess; integration smoke runs only if `NOCTUS_VPS_TEST=1` env var is set.

---

## 3. Design principles

1. **One-shot, no daemon** — each call is a complete SSH session (no persistent connection management).
2. **Cleanup is mandatory** — `/tmp/<file>.sql` MUST be removed even on failure (try/finally + `; rm` chained).
3. **Return shape mirrors subprocess** — `{ok, stdout, stderr, returncode, container, db}` so callers can branch on the same fields they already know.

---

## 3a. Seed-first analysis

1. **Identical contract across products?** YES — every VPS schema op uses the same idiom.
2. **Data product-specific?** NO — generic shell automation.
3. **Placement product-specific?** NO — `noctus.vps.*` namespace.
4. **Visibility / permission rule the same?** YES — same `noctus-vps` SSH host.
5. **Seam exists in seed?** PARTIAL — `noctus.vps.*` namespace exists; this is a new tool in it.
6. **Default-on?** N/A — no default invocation.

**Litmus:** 0 per-product. ✅

---

## 4. Scope

**In scope:**
- W1: `mcp/noctusai/tools/noctus/vps/exec_sql.py` (new module) — `exec_sql(sql, container, db, user?, host?, cleanup?)` Python helper + `noctus.vps.exec_sql` MCP tool + CLI flag.
- W1: Tests in `mcp/noctusai/tests/test_vps_exec_sql.py` (mocked subprocess + optional integration).

**Out of scope:**
- A general-purpose `vps_exec_command` wrapper — `exec_sql` is the surfaced N=1; generalization waits for N≥2.
- Multi-statement transactional control — psql `-f` is sufficient for current use.
- Connection-pooling / persistent SSH — single-shot is correct for the use case.

---

## 4a. Dispatch routing

### 4a.1 Slice → Lens table

| Slice | Lens | Files | Time-box | Dispatched as |
|---|---|---|---|---|
| W1 build tool | backend-engineer · devops-engineer | `mcp/noctusai/tools/noctus/vps/exec_sql.py` (new) · `mcp/noctusai/tools/noctus/vps/__init__.py` (register) · `mcp/noctusai/cli.py` (flag) · `mcp/noctusai/tests/test_vps_exec_sql.py` (new) | 45 min | inline-empersonation |
| W2 recommendations | devops-engineer | `projects/cache-pg-vps-bringup/PROJECT.md` (§7 update) | 30 min | inline-empersonation |

### 4a.2 Codification expectations per slice

| Slice | s1 | s2 | s3 | s4 | Why |
|---|---|---|---|---|---|
| W1 | yes (already in prior delivery note) | no | no | yes (the tool IS the keeper-equivalent — codifies the working idiom) | This is the s4 promotion event for the docker-exec-sql pattern. |
| W2 | no | no | no | no | Pure decision-space analysis; no codification (user picks the route). |

### 4a.3 Routes-not-taken (pre-rejected)

| Route | Why rejected |
|---|---|
| Build `noctus.vps.exec_command(cmd)` generic wrapper | N=1 today; generalize on N≥2 per recurrence rule. |
| Use Fabric/Paramiko Python SSH library | Adds dependency; the `subprocess.run(ssh, ...)` path is already used by `noctus.vps.*`; consistency wins. |
| Embed SQL as base64 in the SSH command (avoid the /tmp file) | Adds encoding/decoding step + harder to debug; the /tmp-file path matches how `cache_deploy_mirror` schema init works manually. |
| Skip the cleanup step (leave /tmp file for inspection) | Silent debt; cleanup is the contract. Add `cleanup=False` toggle for explicit debug-time use. |

### 4a.4 Notes — surface + delivery

One delivery note at end of W3. No surface notes expected.

---

## 5. Architecture / Data Model

```
mcp/noctusai/tools/noctus/vps/
  __init__.py             ← + register exec_sql
  exec_sql.py             ← NEW: exec_sql() + register()
mcp/noctusai/tests/
  test_vps_exec_sql.py    ← NEW (mocked subprocess; optional integration)
mcp/noctusai/cli.py       ← + --vps-exec-sql flag
```

API:
```python
def exec_sql(
    sql: str,
    container: str,
    db: str,
    user: str | None = None,
    host: str = "noctus-vps",
    cleanup: bool = True,
    ssh_runner: callable | None = None,  # injection seam for tests
) -> dict:
    """Returns {ok, returncode, stdout, stderr, container, db}."""
```

---

## 6. Implementation phases

### Phase 1 — Tool + tests ⏳

- [ ] Write `exec_sql.py` (helper + MCP registration)
- [ ] Register in `noctus/vps/__init__.py`
- [ ] CLI flag in `cli.py`
- [ ] Tests covering: empty SQL → error · happy path (mocked) · cleanup runs on failure · cleanup=False preserves file · custom user · ssh failure surfaces as returncode≠0 · psql failure surfaces stderr
- [ ] Self-codify_log s4 entry

**Improvements:** _NOC-FILL-IMPROVEMENTS_

### Phase 2 — Recommendations doc ⏳

- [ ] Update `projects/cache-pg-vps-bringup/PROJECT.md` §7 Open Q #1 with full trade-off table
- [ ] Recommend a sequence: Phase 2 (mirror NOW) + Phase 3 (CI sustainable)

**Improvements:** _NOC-FILL-IMPROVEMENTS_

---

## 7. Open questions

None — scope is fully specified.

---

## 8. Dependencies & blockers

None.

---

## 9. Success criteria

- [ ] `noctus.vps.exec_sql` MCP tool registered
- [ ] CLI flag `--vps-exec-sql` works
- [ ] All tests green
- [ ] Recommendations doc updated in cache-pg-vps-bringup project
- [ ] Self-codify_log s4 entry for `noctus.vps.exec_sql`
- [ ] Delivery note filed

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-26 | Initial draft + Phase 1+2 in flight | architect (tech-lead) |
