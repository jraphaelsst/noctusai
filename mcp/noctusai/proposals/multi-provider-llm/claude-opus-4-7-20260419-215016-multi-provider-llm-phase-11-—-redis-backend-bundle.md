# Proposal: Multi-provider LLM Phase 11 — Redis backend bundled improvements

**Agent:** claude-opus-4-7
**Origin:** project:multi-provider-llm:phase-11
**Generated:** 2026-04-19 21:50
**Severity:** low
**Effort:** low
**Affected products:** core, erp-imobiliario, therapy-platform, seed
**Status:** pending

---

## 1. Context

Phase 11 shipped the real `redis.asyncio` cache backend, admin flush endpoint, and framework auto-wiring when `REDIS_URL` is present. 15 tests via `fakeredis`. This proposal bundles ops-readiness gaps discovered during implementation.

---

## 2. Situation

Implementation worked first-try but left four rough edges: `fakeredis` isn't in `pyproject.toml` (ad-hoc pip install), the Redis client opens without pooling configuration, `flush_prefix` double-scans to compute a count, and audit logging for the admin flush endpoint lacks caller identity.

---

## 3. Proposed Solution

### 3.1 Linkage — why this solution fits this situation

Each bundled improvement tightens a boundary the Phase shipped loose. None block production — they clean up debt before it ossifies.

### 3.2 Application instructions

#### 1. Add fakeredis to dev-dependencies in pyproject.toml

**Linkage:** CI will fail test collection in fresh environments without it.

**Steps:**
1. Add `[project.optional-dependencies] test = ["fakeredis>=2.0"]`
2. Document in README how to install for testing

**Risks:** None

*Independent:* can be applied without other bundled improvements.

#### 2. Configure Redis connection pooling + timeouts explicitly

**Linkage:** Default `Redis.from_url` uses a global default pool. High-throughput products may hit limits silently.

**Steps:**
1. Accept `max_connections` + `socket_timeout` kwargs on RedisCacheBackend
2. Document in KB § llm cache section

**Risks:** Low — wrapping existing constructor

*Independent:* can be applied without other bundled improvements.

#### 3. Record deletion count inline instead of second SCAN

**Linkage:** `flush_prefix` does SCAN→DEL then re-SCAN to verify zero. Two passes for a count that's approximate anyway.

**Steps:**
1. Track `len(keys_to_delete)` across batches
2. Return the running total

**Risks:** Low — correctness depends on Redis not concurrently re-populating (acceptable for flush)

*Independent:* can be applied without other bundled improvements.

#### 4. Add caller identity (user_id + IP) to admin flush audit log

**Linkage:** Currently the log shows `noctus_role=admin` only; no way to trace which admin flushed.

**Steps:**
1. Pull `user.id` from `get_current_user(authorization)`
2. Include in the `admin.llm_cache.flush` log line

**Risks:** None

*Independent:* can be applied without other bundled improvements.

### 3.3 Seed APIs / shared lib involved

N/A — change is local to the product.

### 3.4 Risks before applying

Low — additive changes.

### 3.5 Alternatives considered

N/A — the situation dictates the fix.

---

## 4. Effects

When this is applied, these change:

- **Behavior:** Unchanged — improvements are structural.

---

## 5. Acceptance Criteria

- [ ] Fix applied to every affected product (not just the one that triggered detection)
- [ ] `python mcp/noctusai/cli.py --validate` shows 100/100 for the affected product(s)
- [ ] `python mcp/noctusai/cli.py --review --product core` files no new proposals for this issue
- [ ] Backend tests still pass for the affected product(s)
- [ ] If the change touched shared code, `python mcp/noctusai/cli.py --catalog` shows no new orphans or duplicate candidates
- [ ] Documentation updated KB-first, CLAUDE.md second (per `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md → Docs stay in sync`)

---

## 6. Related files

- `seed/backend/lib/noctusai_lib/llm/backends/redis_backend.py` — Real implementation
- `core/backend/app/routers/admin_cache.py` — Admin flush endpoint
