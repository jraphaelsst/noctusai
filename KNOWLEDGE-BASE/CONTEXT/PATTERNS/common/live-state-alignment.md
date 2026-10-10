# Live-state alignment — org/product state never goes stale

> **Rule (owner, 2026-10-07).** When an org or product changes, docs (auto-memory, KB, the product's help-chat guide, the catalog) and code are aligned **in the same change**, and **VERIFIED against the live source of truth** (Supabase / the code) before the work counts as done. A doc that states live state is a cache; a cache is not the source.

## Why

The product guide is the help-chat AI's ENTIRE knowledge, so a stale guide means the AI confidently lies to a customer. Four incidents, one shape (a fact changed in one place, its description in another did not):

1. **Memory said "Giovanna needs her OWN org"** — false since 2026-10-01 (org `df6c3ace` exists, she is its owner). Nobody checked memory against `public.organizations`.
2. **`guia-igig.md` §13.2 said "até 1200 tokens"** after seed commit `96ff4e488` moved the cap to 4096 + continuations, without touching the guide.
3. **igig features `d714b6182` / `2bfc0ee39` / `b5d3b7e64` shipped** and the guide caught up only in a later commit (`1ad3f616e`) — the assistant described the old behaviour in between.
4. **The igig README described the product wrongly for weeks.**

## The mechanisms (code = WHAT; this doc = WHY)

- **Keeper `check_product_guide_cochange`** (commit-time, high severity, wired in `scripts/hooks/commit-msg` because only that hook can read the message). Over the STAGED diff: a commit that stages non-test behaviour files of a product with a help-chat guide (`products/<slug>/backend/app/**`, `products/<slug>/frontend/src/**`) — or the seed `noctusai_lib/domain/help_chat/**` (affects every consumer's guide) — must also stage that guide. Guides are **derived**, never listed: every `create_help_chat_router(..., knowledge_path=...)` call under an active product backend is a consumer; the path expression is statically evaluated (`Path(__file__)…/"knowledge"/"x.md"`); an unresolvable one is reported as a warning, never dropped.
- **CI leg** `check_product_guide_cochange_range` (job `commit-range-keepers` in `.github/workflows/test.yml`, `cli.py --check-product-guide-cochange --guide-range BASE..TIP`, added 2026-10-10): every NON-merge commit of the pushed / PR range is judged on its own diff and its own message, exactly as the hook would have — so a clone without `bash scripts/install-hooks.sh` cannot push a behaviour change without its guide. Each commit stands alone: a guide landing in a LATER commit does not excuse an earlier one. Merges are skipped (integration is rebase + fast-forward; a merge's combined diff is not one author's change). Guides are derived from the checkout CI runs in (the range tip). An unreadable range fails closed. Commits that predate the leg and would fail it go in `_GUIDE_COCHANGE_ACCEPTED_HISTORICAL` (none at introduction — the last 200 dev commits were clean).
- **Escape hatch** for a genuine no-behaviour change (refactor, test-only-adjacent, copy that the guide does not describe): a commit-message trailer `Guide-Unaffected: <reason>` — the reason is mandatory (an empty trailer does not count). Use it honestly; "the guide is long" is not a reason.
- **Tool `noctus.dev.scan_live_state_claims`** (advisory, read-only, `--scan-live-state-claims`). Extracts live-state claims from auto-memory, `02-LANDSCAPE.md`, product READMEs and guides — org UUIDs / 8-hex prefixes near "org", emails, prod SHAs — and resolves each against `public.organizations`, `public.noctus_users` (via the `migrate_product` `SqlExecutor` seam: Fake + Real + `make_sql_executor`) and the `origin/prod` tip. Per claim: `file:line · claim · live value · ok|mismatch|unknown|unverifiable`. No credentials ⇒ `unverifiable`, never a faked `ok`. Dated/"shipped" lines are history, not claims of current state (`unverifiable`). Heuristic by design: it surfaces, a human judges.

## The verify-before-done step

Before calling an org/product/state change done: (1) run `noctus.dev.scan_live_state_claims` and fix every `mismatch` (and read the `unknown`s that touch what you changed); (2) confirm the guide, memory, KB and catalog row were updated in the same change; (3) for a guide, read the changed section against the code, not against your memory of it. `noc-wrap-up` carries this as a step.

## When to override

The trailer is the only sanctioned override of the keeper. Never bypass the hook (`--no-verify` is forbidden, `CLAUDE.md` §1). The scan is advisory: an `unknown` on a cliente/product name that happens to sit next to an org id is expected noise — leave it, do not "fix" the doc to silence the tool.

## Composes with

`KB § PATTERNS/common/doc-discipline-family-index.md` (doc-propagation sync is the parent rule) · `KB § PATTERNS/common/eight-way-sync.md` · `KB § PATTERNS/common/gate-methodology-sync.md` · the help-chat organ (`noctusai_lib.domain.help_chat`) whose guide this protects.
