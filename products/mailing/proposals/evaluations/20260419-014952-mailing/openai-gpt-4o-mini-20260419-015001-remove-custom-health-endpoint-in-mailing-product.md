# Proposal: Remove custom health endpoint in mailing product

**Agent:** openai-gpt-4o-mini
**Origin:** keeper:noctusai_validate:mailing
**Generated:** 2026-04-19 01:50
**Severity:** warning
**Effort:** low
**Affected products:** mailing
**Status:** pending

---

## 1. Context

The compliance detector flagged a custom health endpoint in the mailing product. The framework already provides a health check through `noctusai_seed.routers.health_router`.

---

## 2. Situation

The file `backend/app/routers/health.py` contains a custom health check function `health_check()` that returns a status. This function is mounted at the same endpoint `/api/health` that the framework provides. The file exists solely for compliance evaluation and is not intended for production.

---

## 3. Proposed Solution

### 3.1 Linkage — why this solution fits this situation

Removing the custom health endpoint aligns with the framework's design and prevents redundancy. The existing framework functionality should be utilized instead.

### 3.2 Application instructions

1. Delete the file `backend/app/routers/health.py`
2. Ensure no references to this custom endpoint remain in the codebase

### 3.3 Seed APIs / shared lib involved

- `noctusai_seed.routers.health_router` — provides a standardized health check endpoint that should be used instead

### 3.4 Risks before applying

Low risk — additive change, no overwrite.

### 3.5 Alternatives considered

N/A — the situation dictates the fix.

---

## 4. Effects

When this is applied, these change:

- **Behavior:** removes redundant health check endpoint

---

## 5. Acceptance Criteria

- [ ] Fix applied to every affected product (not just the one that triggered detection)
- [ ] `python mcp/noctusai/cli.py --validate` shows 100/100 for the affected product(s)
- [ ] `python mcp/noctusai/cli.py --review --product mailing` files no new proposals for this issue
- [ ] Backend tests still pass for the affected product(s)
- [ ] If the change touched shared code, `python mcp/noctusai/cli.py --catalog` shows no new orphans or duplicate candidates
- [ ] Documentation updated KB-first, CLAUDE.md second (per `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md → Docs stay in sync`)

---

## 6. Related files

- `backend/app/routers/health.py` — contains the custom health check implementation
