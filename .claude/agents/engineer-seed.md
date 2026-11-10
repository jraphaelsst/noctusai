---
name: engineer-seed
description: DEPRECATED alias of product-engineer (the engineer-seed protocol was absorbed into product-engineer 2026-11-09). Kept for one release so stale dispatches and docs still resolve; delegates entirely to product-engineer. Dispatch product-engineer instead.
# Same tools/model as product-engineer (alias, not a new role). Least-privilege allowlist, no `Agent`.
tools: Bash, Read, Edit, Write, Grep, Glob, mcp__noctusai__*
model: sonnet
owns_kb: []
deprecated: "alias of product-engineer; retire after release 4.1.0 (check_agent_names_resolve warns on every reference)"
---

# engineer-seed — DEPRECATED alias

DEPRECATED alias, retire after release 4.1.0. Follow `.claude/agents/product-engineer.md` in full (worktree, commit-own-branch, file-disjoint, AST-first, scoped verification, short-form return, decision rights); this file adds nothing. New briefs dispatch `product-engineer`.
