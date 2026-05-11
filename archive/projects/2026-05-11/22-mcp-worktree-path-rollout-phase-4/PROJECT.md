# MCP worktree-path rollout — Phase 4 — Project Document

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 1 ready — audit complete, single residual gap identified
- **Owner / stakeholders:** USER · Engineer RRR (dispatched)
- **Related docs:**
  - `projects/mcp-worktree-path-resolution/` — origin design (2026-05-10)
  - Memory entry `feedback_mcp_write_tools_resolve_caller_root` — N=7+ recurrence
  - `mcp/noctusai/workspace.py::resolve_caller_root` — canonical helper
  - `mcp/noctusai/tests/test_worktree_rollout_phase4.py` — 25-test regression sweep covering 8 high-impact tools
- **Project slug:** `mcp-worktree-path-rollout-phase-4` (lives at `projects/<slug>/` — platform-infra rollout, not product-bounded)

---

## 1. Context & Purpose

The MCP server boots with one fixed cwd (typically noc main worktree) and `os.getcwd()` inside any tool returns the SERVER's cwd, not the caller's. The MCP protocol does not transmit caller-cwd per call. Therefore write tools that need to land their output in a caller-specific worktree MUST accept an explicit `worktree_path` argument — auto-detection is fundamentally impossible.

The original gap surfaced 2026-05-10 (`projects/mcp-worktree-path-resolution/`). Phase 1-3 of the rollout adopted 8 high-impact tools (catalog/improvements/master_prompts/promotion/review/three_way_sync/build/absorb_file plus scaffold_product/scaffold_migration/archive/file_proposal/history_record/lgpd_flag from earlier waves). This dispatch (RRR) is **Phase 4** — close the remaining gap.

Recurrence count this session **N=7+** (UU, WW, VV, YY, III-3, LLL + the meta-fact this brief encodes). The methodology amendment surface area is structural — every write tool either accepts the param or breaks isolation.

---

## 2. Confirmed constraints

- **Scope** — `mcp/noctusai/tools/**/*.py` write-side functions only. Read-only tools out of scope (they read the same fixed-cwd content, but no destructive side-effect). *(Limits blast radius.)*
- **Backwards compat** — `worktree_path=None` MUST preserve existing module-default behavior. *(Architects calling from noc main keep working.)*
- **No silent fallback** — invalid `worktree_path` raises `ValueError` per `resolve_caller_root` contract. *(Silent-error rule.)*
- **AST-first** — libcst for Python edits per CLAUDE.md universal rule. *(But the changes here are mechanical schema-additions; libcst is the right hammer when feasible; localized edits via `Edit` are equivalent for trivial param additions.)*
- **Phase-learnings tracker exempt** — `phase_learnings.py` writes to a centralized gitignored SQLite (`mcp/noctusai/data/`); by design local-only / per-machine. Per the exemption test, a fake here would not exercise different code than the real, and the data is intentionally session-local. *(Documented in §3a litmus.)*

---

## 3. Design principles

1. **Audit-then-adopt.** Read every write tool first, classify by adopted/gap status, then plan edits only on confirmed gaps. Avoids redundant work.
2. **Canonical 3-tier resolution.** Every tool: explicit test seam > `worktree_path` > module default. Mirrors the `resolve_caller_root` contract.
3. **One regression test per new param.** Each adopted tool gets: (a) worktree_path-redirects-writes test, (b) invalid-path-raises test. Optional: explicit-seam-wins test.

---

## 3a. Seed-first analysis

This is a **platform-infra rollout**, not a product feature. The seed itself is unaffected — the change lives in the MCP toolkit (`mcp/noctusai/tools/**`) which is the platform's exposure layer. The seed-first six-question checklist resolves cleanly:

1. **Identical contract per product?** N/A — this is a per-tool methodology rollout, not a product feature.
2. **Data source product-specific?** N/A.
3. **Placement product-specific?** N/A.
4. **Visibility / permission rule the same?** N/A.
5. **Seam exists in seed?** YES — `resolve_caller_root` in `mcp/noctusai/workspace.py` is the canonical helper, already consumed by 8 tools.
6. **Default-on or opt-in?** Default-on for adopters; backwards-compat (None) is the opt-out.

**Litmus — per-product code count:** **0 lines.** Pure platform-infra concern; lives entirely in MCP toolkit. No product code touched.

---

## 4. Scope

**In scope:**
- Audit every write tool in `mcp/noctusai/tools/**/*.py`
- Adopt `worktree_path` on `proposals.py::update_proposal_status` (single residual gap from audit)
- Regression test for the new param
- Memory rule amendment to reflect Phase 4 close

**Out of scope (for now — with reason):**
- `phase_learnings.py` write side — exempt by design (gitignored centralized SQLite; per-machine local-only).
- Read-only tools that resolve `PRODUCTS_DIR` at module level — no write side-effect; out of immediate scope but cataloged as accept-with-rationale candidate.
- Phase 5+ rollout (none scheduled — surface only is closed once `update_proposal_status` lands).

---

## 5. Architecture / Data Model

No new data shape. Mechanical adoption pattern per tool:

```python
def update_proposal_status(
    filename,
    status,
    reason="",
    product=None,
    *,
    products_dir: Path | None = None,   # NEW — test seam (3-tier)
    worktree_path: str | Path | None = None,  # NEW — caller-aware
):
    if products_dir is not None:
        base_products = products_dir
    elif worktree_path is not None:
        base_products = resolve_caller_root(worktree_path) / "products"
    else:
        base_products = PRODUCTS_DIR
    # ... existing body, using base_products instead of PRODUCTS_DIR
```

MCP tool wrapper `_set_status` (in `register(server)`) exposes `worktree_path: str | None = None` to the agent.

---

## 6. Implementation phases

### Phase 0 — Audit current state ✅
- [x] List every MCP write tool via grep for `write_text|with open`
- [x] Per tool: classify worktree_path adoption status
- [x] Confirm `resolve_caller_root` handles explicit > env > default
- [x] Identify residual gap: `proposals.py::update_proposal_status` (`set_proposal_status` MCP)

**Improvements:**
- The audit revealed Phase 1-3 already covered all 8 priority tools. Phase 4 is much smaller than the brief implied — only one residual write tool gap remains.
- `phase_learnings.py` is a legitimate exemption (centralized SQLite by design); documenting the exemption rather than wiring it through avoids cargo-cult adoption.

### Phase 1 — Adopt `update_proposal_status` ✅
- [x] Add `products_dir: Path | None = None` + `worktree_path: str | Path | None = None` kwargs to `update_proposal_status`
- [x] Body resolves `base_products` from 3-tier priority
- [x] MCP `_set_status` wrapper passes through new kwarg
- [x] Backwards-compat test: existing call shape (no worktree_path) still passes
- [x] New test: `worktree_path=` redirects writes correctly
- [x] New test: invalid worktree_path raises ValueError

### Phase 2 — Documentation amendment ✅
- [x] Update `feedback_mcp_write_tools_resolve_caller_root` memory rule with N=7+ recurrence + Phase 4 adoption count
- [x] Spot-check KB depth (no dedicated KB doc; memory rule is the source-of-truth)
- [x] Catalog `list_proposals` (read-side, module-level PRODUCTS_DIR) as accept-with-rationale to keep the absence explicit

### Phase 3 — Regression sweep ✅
- [x] Run full `tests/` to confirm no regressions
- [x] Run `test_worktree_rollout_phase4.py` to confirm continued green
- [x] Verify new tests pass

---

## 7. Open questions

1. **Should `list_proposals` honor `worktree_path`?** — Read-only, but agent calling from worktree gets the wrong cross-product result if MCP server boots from noc main and worktree has different products. **Recommendation:** catalog as accept-with-rationale; if N=2 read-side gaps surface, formalize. Not in this dispatch's scope.
2. **Should `phase_learnings.py` adopt worktree_path?** — Currently centralized gitignored SQLite (per-machine local). **Recommendation:** keep central; document exemption. (Done in §2 + §4.)

---

## 8. Dependencies & blockers

- `resolve_caller_root` helper already exists (added 2026-05-10).
- No external dependencies.

---

## 9. Success criteria

- All write tools in `mcp/noctusai/tools/**` accept `worktree_path` OR are documented exemptions.
- `pytest mcp/noctusai/tests/` green.
- Memory rule `feedback_mcp_write_tools_resolve_caller_root` reflects N=7+ + Phase 4 close.

---

## 10. How to use this plan

Standard project execution rules.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | Initial plan drafted; Phase 0 audit complete; single residual gap (`update_proposal_status`) identified | Engineer RRR |
| 2026-05-11 | Phase 1 complete: `update_proposal_status` adopts worktree_path; 3-tier priority wired; backwards-compat preserved; 3 new tests pass | Engineer RRR |
| 2026-05-11 | Phase 2 + 3 complete: documentation amended; full regression sweep green | Engineer RRR |
