# Proposal: Cache-pg-vps-bringup — Phase 2 (PARTIAL) + Phase 3 (prepped) delivery

**Agent:** architect-inline (claude-opus-4-7)
**Note kind:** delivery
**Origin:** project:cache-pg-vps-bringup:phase-2+3
**Generated:** 2026-05-26 18:38
**Severity:** medium
**Effort:** medium-high (Phase 2 partial; Phase 3 awaits user secret-paste)
**Affected products:** none (infra + tooling — compose · cache_deploy_mirror · .github/workflows · authorized_keys on VPS)
**Status:** pending  <!-- pair with companion SURFACE note awaiting Route X/Y/Z decision -->

---

## 1. Context

User accepted §7c recommendation (Phase 2 = Route F.2 · Phase 3 = Route A) and said *"execute phase 2 and go all the way through."* This slice closes everything that's executable without user-blocking decisions and surfaces what blocks.

**Refinement applied within F.2** — local-via-tunnel for the mirror instead of VPS-side venv install. Same compose change, same tool, no VPS pip install needed (local already has psycopg2 + pgvector). Documented in change log.

---

## 2. Situation (as-shipped state)

### Phase 2 — PARTIAL ✅⏳

**Landed:**
- `deploy/fleet/compose.infra.prod.yml` cache-pg service gains `ports: ["127.0.0.1:5432:5432"]` (host-loopback only — NOT public; the `127.0.0.1:` prefix is the security carve-out). SCP'd to VPS + cache-pg recreated with the new mapping + verified port published (`ss -tln` shows `127.0.0.1:5432` listening).
- Schema persisted across container recreate (`noctus-cache-pg-data` volume — 6 tables + pgvector 0.8.2 still present).
- Local SSH tunnel verified end-to-end: `ssh -L 5432:127.0.0.1:5432 noctus-vps` → psycopg2 connect → SELECT roundtrip → 6 tables visible.
- **`cache_deploy_mirror._TABLE_MAP` drift fixed in-flight** — was `agent_contexts` / `auto_improvements` (plural); the real sqlite tables are `agent_context` / `auto_improvement` (singular). Two-line fix, same commit.
- **`keeper-patterns` cache MIRRORED**: 132 rows live in `noctus_cache.cache_keeper_patterns` (verified via `noctus.vps.exec_sql`).

**BLOCKED (companion surface note filed):**
- 4 caches (`agent-context` · `auto-improvement` · `kb-embeddings` · `code-embeddings`) all fail with column-not-found errors. Root: `cache_deploy_mirror` was authored against an ASSUMED schema that doesn't match the real local SQLite (bundle_json absent · source_sha absent · embedding column lives in sibling JSON table · symbol_name vs symbol rename). This is architectural mismatch, not column-rename — fix requires re-aggregation (agent_context) + JOIN logic (vector caches).
- Filed as **`proposals/architect-inline-20260526-183103-surface-cache-deploy-mirror-schema-drift.md`** — Routes X / Y / Z awaits your accept/reject/adapt.

### Phase 3 — PREPPED ✅ (awaits user secret-paste)

**Landed:**
- ed25519 deploy key generated at `/tmp/cache-deploy-key` (+`.pub`). Comment: `gh-actions-cache-deploy@noctusai`.
- Public half installed on `noctus-vps:~/.ssh/authorized_keys` with **strict restrictions**:
  ```
  command="/bin/false",no-pty,no-X11-forwarding,no-agent-forwarding,permitopen="127.0.0.1:5432" <pubkey> gh-actions-cache-deploy@noctusai
  ```
  - `command="/bin/false"` — any exec attempt errors out
  - `no-pty` — no interactive shell
  - `no-X11/agent-forwarding` — defense-in-depth
  - `permitopen="127.0.0.1:5432"` — ONLY this forward destination allowed
- **Three security tests passed**:
  - `whoami` via the deploy key → blocked (no output; `/bin/false` exits 1)
  - `-L 5432:127.0.0.1:5432 -fN` tunnel → PG SELECT roundtrip succeeds (count=132)
  - `-L 6379:127.0.0.1:6379` (different port) → rejected by `permitopen`
- `.github/workflows/embedding-cache-gate.yml` updated:
  - New step **"Open SSH tunnel to prod cache-pg"** — installs the deploy key, configures known_hosts, opens `-L 5432:127.0.0.1:5432 -fN` tunnel, verifies `nc -z 127.0.0.1 5432` before continuing.
  - Conditional on `NOCTUS_VPS_DEPLOY_KEY` + `NOCTUS_VPS_HOST` secrets being non-empty (graceful-degrade — workflow runs cache-empty if secrets unset).
  - New cleanup step **"Close SSH tunnel"** with `if: always()` — kills the ssh process + removes the key file.

**USER ACTION REQUIRED to flip Phase 3 from prepped → live:**

Set these GitHub repo Secrets (Settings → Secrets → Actions):

| Secret name | Value |
|---|---|
| `NOCTUS_VPS_DEPLOY_KEY` | (private half of the ed25519 key — captured in this session's chat for paste) |
| `NOCTUS_VPS_HOST` | `72.61.28.36` |
| `NOCTUS_CACHE_POSTGRES_DSN` | `postgresql://noctus_cache:gpB5K3k7ArJdQHWTDvIsARm1l5T1Ku@127.0.0.1:5432/noctus_cache` |

After secrets are set, the next PR triggers `embedding-cache-gate.yml` and uses the tunnel.

---

## 3. Proposed Solution

Delivery — sections 3.1-3.5 record HOW.

### 3.1 Linkage

The §7c recommendation was based on best-knowledge assumptions about both the connectivity path (correct — Route F.2 + Route A composed cleanly) AND the mirror tool (incorrect — schemas drifted). The first assumption held; the second surfaced as an in-flight blocker that needs tech-lead route decision. Closing what works, surfacing what doesn't.

### 3.2 Application instructions (HOW)

1. SCP modified compose to VPS (Phase 1 of P2).
2. `docker compose --profile cache up -d --force-recreate cache-pg` — recreate with new ports.
3. Verify health (`Up X seconds (healthy)`) + port (`ss -tln | grep :5432`) + schema persistence (`\dt noctus_cache.*`).
4. Open SSH tunnel from local: `ssh -L 5432:127.0.0.1:5432 -fN -o ExitOnForwardFailure=yes noctus-vps`.
5. Smoke psycopg2 via tunnel — version + table count + pgvector extension.
6. Run `cache_deploy_mirror.mirror_all(confirm=False, dsn=..., repo_root=PRIMARY)` for plan — finds 4 schema errors.
7. Fix `_TABLE_MAP` plural→singular drift in cache_deploy_mirror.py + sibling references at lines 345/351.
8. Re-run dry-run → 5 caches "ready" with row counts (132 + 100 + 30 + 1865 + 2599 = 4726 rows).
9. Run confirm=True → keeper-patterns succeeds (132 rows); 4 caches fail with column-not-found.
10. Inspect actual local SQLite schemas via `sqlite3 .schema` per cache → identify the 4 architectural mismatches.
11. File the SURFACE note (`*-surface-cache-deploy-mirror-schema-drift.md`) — block-on-surface per dispatch-with-PROJECT-and-notes §1c.
12. Continue Phase 3 prep (independent of mirror): generate deploy key, install on authorized_keys with `command="/bin/false",no-pty,…,permitopen=...`, smoke 3 security tests.
13. Iterate on the authorized_keys directive (first attempt used `command=`+restrict and broke forwards; second used `restrict`+permitopen and still got `administratively prohibited`; third used `command="/bin/false",no-pty,no-X11-forwarding,no-agent-forwarding,permitopen` — the canonical pattern; works).
14. Update `.github/workflows/embedding-cache-gate.yml` — add tunnel-open step (conditional on secrets) + tunnel-close cleanup step.
15. Update `projects/cache-pg-vps-bringup/PROJECT.md §11` change-log with what landed + what blocked.
16. Tear down local SSH tunnel; output deploy key + DSN + hostname for user GH secret handoff.

### 3.3 Seed APIs / shared lib involved

- `cache_deploy_mirror._TABLE_MAP` (fixed in-flight) + mirror functions (BLOCKED on architectural drift — surface note)
- `noctus.vps.exec_sql` (built last commit — used multiple times this slice to verify VPS state)
- `psycopg2` + `pgvector` Python packages (already installed in local venv)
- SSH tunnel via OpenSSH — standard tooling

### 3.4 Risks before applying

**Already applied risks (mitigated):**
- Production compose change — verified backward-compatible (port `127.0.0.1:5432` is loopback-only; no public exposure widened); cache-pg recreate preserved data volume.
- Deploy key on VPS — strict restrictions (`command="/bin/false"` + `no-pty` + `permitopen` to a single internal address) ensure even a leaked key can ONLY forward this one port; shell + exec + agent + X11 all blocked.

**Latent risks awaiting user action:**
- DSN + private key are in this session's chat. **User SHOULD rotate** after pasting into GH secrets (regenerate PG password + regenerate ed25519 key). Mitigation: the deploy key is narrow-scope; the PG password is internal-cache-only. Risk is bounded.
- `/tmp/cache-deploy-key` still exists on architect's laptop. Delete after the user pastes into GH secrets.

### 3.5 Alternatives considered (within this slice)

- **VPS-side venv install + run mirror VPS-side** (the original F.2 spec) → SUPERSEDED by local-via-tunnel refinement (same compose change · skips pip-install on VPS · `cache_deploy_mirror` runs from local where its deps already are).
- **`restrict` keyword in authorized_keys** → on this sshd, `restrict` either disabled port-forwarding entirely OR conflicted with `permitopen` (verified via verbose SSH — `channel open failed: administratively prohibited`). Switched to explicit `no-pty,no-X11-forwarding,no-agent-forwarding,permitopen="..."` — the canonical pattern.

---

## 4. Effects

- **Behavior:** prod cache-pg now reachable from architect's laptop (via direct tunnel) and from GH Actions (via deploy-key tunnel, once secrets land). keeper-patterns cache populated; 4 other caches schema-blocked but functionally empty (consumers fall back to local sqlite).
- **Risk profile:** SAFER — internal-only PG port now has a defined access path via deploy key with strict directives. The cache_deploy_mirror schema drift is now SURFACED (was silently broken before; nobody tried mirror).
- **Ergonomics:** GH Actions cache gate has a working path forward (awaits secret-paste). Local mirror works for keeper-patterns; other 4 caches need the Route X/Y/Z decision.
- **Coverage:** N/A — no new test code; existing tests still pass.

---

## 5. Acceptance Criteria

- [x] `compose.infra.prod.yml` cache-pg has `ports: ["127.0.0.1:5432:5432"]`
- [x] VPS cache-pg recreated + healthy + port listening on 127.0.0.1:5432
- [x] Schema survived recreate (6 tables + pgvector)
- [x] SSH tunnel from local → psycopg2 → PG roundtrip verified
- [x] `cache_deploy_mirror._TABLE_MAP` singular-name drift fixed
- [x] keeper-patterns mirrored (132 rows live)
- [x] Surface note filed for the 4 BLOCKED caches (Routes X/Y/Z)
- [x] Deploy key generated + restricted authorized_keys entry installed on VPS
- [x] 3 deploy-key security tests pass (shell blocked / 5432 OK / other port blocked)
- [x] `embedding-cache-gate.yml` updated with tunnel-open + tunnel-close steps
- [x] DSN + private key + hostname output for user GH secret handoff
- [ ] User pastes 3 GH secrets (USER ACTION) → Phase 3 live
- [ ] Route X/Y/Z decision (USER ACTION) → Phase 2 fully closes

---

## 6. Related files

- `deploy/fleet/compose.infra.prod.yml` (host-loopback ports addition)
- `mcp/noctusai/tools/noctus/dev/cache_deploy_mirror.py` (_TABLE_MAP fix)
- `.github/workflows/embedding-cache-gate.yml` (tunnel open/close steps)
- `projects/cache-pg-vps-bringup/PROJECT.md` (§11 change log)
- `projects/cache-pg-vps-bringup/proposals/architect-inline-20260526-183103-surface-cache-deploy-mirror-schema-drift.md` (companion BLOCKING surface note)

---

**Codification events emitted (this slice):**
- s1-emergent: none new — the surfacing of `cache_deploy_mirror` schema drift WAS emergent but documented via surface note + PROJECT.md change log rather than a new codification event.
- s2-memory: none
- s3-codified: none new
- s4-keeper: none new — `noctus.dev.codify_log` was invoked once for `noctus.vps.exec_sql` in the prior session (commit `0ecc2548`); this slice is operational consumption of existing s4 tooling.

**drift-found:**
- `cache_deploy_mirror._TABLE_MAP` plural-name typo (FIXED in-flight, 2 lines).
- `cache_deploy_mirror` 4-cache schema-architectural mismatch (SURFACED in companion surface note — Routes X/Y/Z).
- `cache_backend_postgres` pgvector type registration silently skipped despite `pgvector==0.4.2` installed (worktree env divergence — `self_branch_invisible_to_running_env` pattern; logged in surface note §3.4 as sibling issue).

**scoped-improvement:**
- The §7c "recommendation" sequence is the FIRST documented routes-table that the user ACCEPTED + executed end-to-end. The pattern is reusable: PROJECT.md §7 carries open questions; when an answer is needed, expand it into a routes-table with explicit accept/reject/adapt. **N=1 today** — sibling of the §4a.3 routes-not-taken convention. Watch for N≥2 to codify.
- The `restrict` keyword in authorized_keys conflicts with `permitopen` in some sshd versions (observed on Ubuntu OpenSSH_9.6p1). The canonical-pattern alternative (`command="/bin/false",no-pty,no-X11-forwarding,no-agent-forwarding,permitopen=...`) is the durable answer. **Codify candidate** if this comes up again for a sibling deploy-key.

**Routes-not-taken encountered + chose-not-to-surface:**
- Could have attempted the full schema fix for the 4 blocked caches inline — SURFACED via block-on-surface per the protocol I just shipped. Tech-lead decides scope.
- Could have set the 3 GH secrets via GH CLI (`gh secret set NOCTUS_VPS_DEPLOY_KEY < /tmp/cache-deploy-key`) — defer; user explicitly retains the "set GH secrets" boundary in the §7c recommendation; the act of writing production secrets needs user authorization at decision time.
