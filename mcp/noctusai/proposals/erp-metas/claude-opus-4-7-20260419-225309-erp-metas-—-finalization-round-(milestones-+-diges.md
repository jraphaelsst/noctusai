# Proposal: ERP Metas — finalization round (milestones + digest + badge + contextual + seed)

**Agent:** claude-opus-4-7
**Origin:** project:erp-metas:finalization-2026-04-19
**Generated:** 2026-04-19 22:53
**Severity:** low
**Effort:** medium
**Affected products:** erp-imobiliario, seed
**Status:** pending

---

## 1. Context

This round closed the 5 items the METAS-PLAN had tagged as 'still pending' after the consolidation round: milestone notifications at 50/80/100% VGV, biweekly digest email, agent rank badge surfaced via layout-enrichment, contextual MetaEventoIndicator on source pages, and the idempotent team-seed script. Migration `019_metas_milestones.sql` was applied via Supabase MCP; the new trigger + table + helper function are live. ERP 1765✓/29 skipped, frontend build green.

---

## 2. Situation

Five systemic observations worth capturing: (1) the milestone trigger runs once per meta_eventos INSERT even when the progress hasn't changed — could short-circuit when the agent's realized VGV is already past 100%; (2) the digest endpoint accepts any `recipient` — no allow-list of org-associated emails, making it technically spammable by an admin; (3) the rank-in-roleLabel injection fetches all rankings for every page render — a dedicated `/api/metas/my-rank` endpoint would be cheaper; (4) MetaEventoIndicator is ERP-specific but the pattern is generic — graduation to `@noctusai/lib/design-system/AIIndicator` would let every product use it; (5) seed_metas_teams.py hardcodes the 3 team names — a config file would let the pilot agency customize without editing Python.

---

## 3. Proposed Solution

### 3.1 Linkage — why this solution fits this situation

Each improvement is a small hardening step that the current shipping code works without but will appreciate having when the first production org lands. None block the AI-EXPANSION project from advancing.

### 3.2 Application instructions

#### 1. Short-circuit milestone trigger when pct already capped

**Linkage:** Every meta_eventos INSERT runs fn_meta_progresso + 3 EXISTS checks. When agent is already past 100%, subsequent inserts still run the full sequence. Early return saves DB work.

**Steps:**
1. In fn_check_milestone, after reading v_progresso, check EXISTS for the 100 milestone first
2. If already inserted, RETURN NEW immediately

**Risks:** Low — preserves correctness; only skips work when nothing can change.

*Independent:* can be applied without other bundled improvements.

#### 2. Allow-list digest recipients from the org members

**Linkage:** `POST /api/metas/digest/{periodo_id}?recipient=` accepts any address. An admin could accidentally send company data to an external recipient by typo.

**Steps:**
1. Validate that `recipient` matches one of: the org owner's email, a member's email, or the authenticated user's email
2. Return 400 when it doesn't match
3. Add a `--force` override header for the n8n cron (with a shared-secret auth)

**Risks:** Medium — breaks the current n8n pattern until the cron passes the force header.

*Independent:* can be applied without other bundled improvements.

#### 3. Dedicated `/api/metas/my-rank` endpoint for Header injection

**Linkage:** useERPLayoutEnrichment now calls useRankings() on every page. That pulls the full top-N. A light endpoint returning just `{rank, score, period_label}` would be ~20× cheaper.

**Steps:**
1. Add service function `my_rank(user_id, periodo_id)` that runs one query
2. Add router endpoint `/api/metas/my-rank?periodo_id=`
3. Replace the useRankings call in useERPLayoutEnrichment with the new hook
4. Keep the full useRankings for dashboard pages

**Risks:** Low — parallel addition; existing hook keeps working.

*Independent:* can be applied without other bundled improvements.

#### 4. Graduate MetaEventoIndicator → AIIndicator in shared lib

**Linkage:** Pattern P1 in AI-EXPANSION §5a. Each product that wants a contextual indicator currently has to copy the ERP component. Promoting to `@noctusai/lib/design-system` with a configurable `useOutputFor(refType, refId)` hook lets every §5 opportunity drop in a 3-line indicator.

**Steps:**
1. Create `seed/frontend/lib/src/design-system/AIIndicator.tsx`
2. Accept `refType, refId, hook, renderChip` props
3. Migrate ERP MetaEventoIndicator to use it (1-line render call + the ERP-specific chip renderer)
4. Document in KB / design-system index

**Risks:** Low — additive; ERP keeps working on the wrapper until migrated.

*Independent:* can be applied without other bundled improvements.

#### 5. Move team seed data out of the script into a config file

**Linkage:** Hardcoded DRAGÃO/LEÃO/ÁGUIA. A pilot agency with different team names has to edit Python to seed. A YAML/JSON config keeps the script generic.

**Steps:**
1. Accept `--config teams.yaml` CLI arg
2. Default to the hardcoded 3 teams when no config given
3. Document a starter config in `docs/` or README

**Risks:** None

*Independent:* can be applied without other bundled improvements.

### 3.3 Seed APIs / shared lib involved

N/A — change is local to the product.

### 3.4 Risks before applying

Low — additive or small-optimization; no contract changes.

### 3.5 Alternatives considered

N/A — the situation dictates the fix.

---

## 4. Effects

When this is applied, these change:

- **Behavior:** Milestones fire exactly once per threshold per period per agent
- **Coverage:** Contextual AI indicator pattern proven; generalization unlocked
- **Ergonomics:** Agent rank visible globally via Header without touching pages
- **Risk profile:** Digest endpoint vulnerable to mis-typed recipient — addressed in improvement #2

---

## 5. Acceptance Criteria

- [ ] Fix applied to every affected product (not just the one that triggered detection)
- [ ] `python mcp/noctusai/cli.py --validate` shows 100/100 for the affected product(s)
- [ ] `python mcp/noctusai/cli.py --review --product erp-imobiliario` files no new proposals for this issue
- [ ] Backend tests still pass for the affected product(s)
- [ ] If the change touched shared code, `python mcp/noctusai/cli.py --catalog` shows no new orphans or duplicate candidates
- [ ] Documentation updated KB-first, CLAUDE.md second (per `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md → Docs stay in sync`)
- [ ] Milestone trigger does <= 1 EXISTS check when agent already at 100%
- [ ] Digest endpoint returns 400 for non-member recipients (unless override header set)
- [ ] AIIndicator shipped in `@noctusai/lib/design-system` and consumed by ERP

---

## 6. Related files

- `products/erp-imobiliario/backend/migrations/019_metas_milestones.sql` — Milestone trigger + dedup table
- `products/erp-imobiliario/backend/app/services/metas_digest_service.py` — HTML+text digest renderer
- `products/erp-imobiliario/backend/app/routers/metas_digest.py` — Admin-only send endpoint
- `products/erp-imobiliario/backend/app/routers/meta_eventos.py` — Lookup endpoint for indicators
- `products/erp-imobiliario/frontend/src/hooks/useLayoutEnrichment.ts` — Rank-in-roleLabel injection
- `products/erp-imobiliario/frontend/src/components/MetaEventoIndicator.tsx` — ERP-specific indicator (P1 pattern)
- `products/erp-imobiliario/backend/scripts/seed_metas_teams.py` — Idempotent seed script
- `AI-EXPANSION-PROJECT.md` — Enriched with Pattern Catalog §5a + X4-X8 cross-cutting
