# Living findings ledgers — one mechanism, typed instances, never hand-edited

> **Why (2026-11-05).** A burn-down that is a snapshot is stale the day after, and a second hand-built tracker (Julia's mistakes, the next audit) is a fork of the first. This pattern is the ONE mechanism: a *ledger* is a typed instance of `noctus.dev.findings_ledger`. Instances: `access-tier` (security burn-down, `project-history/access-tiers/`), Julia's mistakes ledger (registers the same way). KB § PATTERNS/security/access-tiers.md is the first consumer.

## The shape

Machine-readable NDJSON (one row per line, sorted by id so branches merge line-wise) + a rendered `FINDINGS.md` next to it. **The tool is the only writer** — a hand edit is a drift the keeper fails.

- **Core fields (every ledger):** `id` (prefix + hash of the key: stable, merge-safe) · `key` · `section` · `scope` (product slug / agent key — the unit an agent works in) · `target` · `severity` · `status` (`open` | `in-progress <branch>` | `fixed <sha>` | `accepted <rationale>`) · `status_detail` · `source` · `found_by` · `found_at` · `closed_at` · `note`.
- **Typed extension per ledger:** `extra={field: allowed values | None}` — security: `tier`, `class`; Julia: `attribution` MODEL|STRUCTURAL|CONTENT, `regression_case_id`. Allowed values are validated on append.

## Registration API (a ledger plugs in, it does not fork)

```python
from tools.noctus.dev.findings_ledger import LedgerType, register_ledger
register_ledger(LedgerType(name="julia-mistakes", prefix="JM", path="project-history/julia/mistakes.ndjson",
    summary="project-history/julia/MISTAKES.md",
    extra={"attribution": ("MODEL", "STRUCTURAL", "CONTENT"), "regression_case_id": None},
    sections=("eval",), scanner=current_rows))   # current_rows(root) -> {key: {section, scope, target, severity, note, <extra>}}
```

`scanner(root)` is the ONE hook that decides whether a row is still real (a static keeper, an eval run, a prod query). `reconcile` opens rows it returns that have no live row, closes (`fixed <sha>`) live rows it no longer returns, reopens a `fixed` row that came back. `scanner=None` = manual-only (append/update, no reality check). `action=scaffold` returns the registration module for a NEW ledger (agent/product creation points at it).

## Tool `noctus.dev.findings_ledger` (CLI: `--findings-ledger-reconcile <ledger>`, `--check-findings-ledgers`)

`ledgers` · `scaffold` · `status` · `query` (scope/status/section filters, worst first) · `open_for_scope` (compact lines across ALL ledgers for a product/agent you are about to touch) · `append` · `update` (id + `new_status` + detail) · `reconcile` · `check`. Close with `new_status=fixed`, `detail=<sha>`; claim with `in-progress`, `detail=<branch>`; `accepted` needs a rationale.

## The drift keeper (one, over all ledgers)

`check_findings_ledgers` (`--check-findings-ledgers`, pre-commit when a backend/ledger surface is staged): a status that disagrees with the latest scan fails — a NEW finding with no row · a row marked `fixed` the scanner still sees · an `open`/`in-progress`/`accepted` row the scanner no longer sees (reconcile closes it). The ratchet of a scanner IS its ledger: a violation with no live row fails its own keeper.

## Compliance-by-construction: ledger visibility is injected, not opted into

A pointer someone has to remember to add is the failure mode this closes. `scripts/hooks/claude-inject-open-findings.py` runs on **SessionStart and SubagentStart** (registered in `.claude/settings.json`; UX over the gates, never a gate) and inserts the open rows of every ledger on the roster (`project-history/findings-ledgers.json`, written by the tool on every save) for the agent's target — the product(s) the worktree's branch touches (`git diff origin/dev...HEAD`), else the cwd's product, plus `.claude/agents/<name>.md` edits as scope `<name>`. A new `.claude/agents/*.md` or a new product therefore gets visibility with **zero lines added**; the dispatch brief (`engineer_brief_compose`) carries the same rows. Backstop only: `check_findings_ledger_visibility` (`--check-findings-ledger-visibility`) fails if the hook is unregistered or a ledger is missing from the roster — nobody should ever hit it. Creation paths (`noc-new-agent`, `skill-creator`, the agent-context-architecture template) state the injection and point at `action=scaffold` for an agent that needs its own ledger.

## Visibility by default

Every dispatch brief composes the scope's open rows first (`engineer_brief_compose` → "Open findings in your scope", across every ledger); agents and skills point here (`security`, `agents-security`, `backend-engineer`, `frontend-engineer`, `architect`, `noc-new-product`, `noc-contract-first`, `noc-new-agent`). Not yet wired: the agent-context cache extract and per-target noc-graph nodes (the seam is `findings_ledger.open_for_scope(scope)`; follow-up) -- the injection hook covers the same need at session/subagent start.

## Who writes

The scanners write on their own (`reconcile`); the effective-state prod tool `noctus.dev.access_tier_exposure reconcile=true` writes `eff:` rows (closes only classes it measures, only on a fully-measured run); an audit or an agent appends/updates through the tool. Never open the file in an editor.
