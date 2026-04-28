# Proposal: {{TITLE}}

> **This is the canonical proposal format for the NoctusAI dev toolkit.**
> Every agent (human, Claude, OpenAI, …) files compliance + improvement
> proposals in this shape. Start from this template — don't invent a new
> structure.
>
> **This proposal is a context-transfer vehicle.** The authoring agent lived
> the situation (built the phase, detected the compliance issue, reviewed the
> code). The receiving agent — who will apply the fix — inherits that
> situational awareness through the text here. Write as if briefing a
> colleague who walked in cold.
>
> **Placeholders** — every `{{DOUBLE_CURLY}}` token is a slot to fill before
> filing. Leave no `{{...}}` in the final file. If a section is genuinely
> N/A (a one-product cosmetic fix has no alternatives worth listing), write
> `N/A — {{one-line why}}` rather than silently dropping the heading.
>
> See `KNOWLEDGE-BASE/CONTEXT/PATTERNS/proposals-and-improvements.md` for
> the full two-system protocol.

**Agent:** {{AGENT}}  <!-- e.g. keeper, keeper-openai-gpt-4o-mini, claude-opus-4-7 -->
**Origin:** {{ORIGIN}}  <!-- e.g. "project:erp-metas:phase-3", "keeper:noctusai_validate", "lgpd:noctusai_lgpd_flag" -->
**Generated:** {{YYYY-MM-DD HH:MM}}
**Severity:** {{high | medium | low}}
**Effort:** {{high | medium | low}}
**Affected products:** {{product1, product2, …}}
**Status:** pending

---

## 1. Context

{{2–5 sentences. What produced this proposal?

If `Origin` is a plan phase: summarize what that phase *built* — the domain, the major pieces, the user-facing outcome. Then one sentence on why this proposal was raised in its wake (an observation that emerged during the build, a phase-holistic insight, a friction point).

If `Origin` is `keeper` / `lgpd` / another detector: summarize what the detector was looking at and what it saw that triggered the flag.

Goal: the receiving agent understands the *environment* this came out of before reading the technical details.}}

---

## 2. Situation

{{3–6 sentences. The real state of the code / config / schema *right now*. Pure facts — what exists, where, with what shape. No advice here, no solution, no judgment. If the situation involves a specific pattern or file, name it with a path and line number. If it involves multiple products, list them.

Example framing:
- "Product X has its own `notificacoes.py` router at `products/x/backend/app/routers/notificacoes.py` — 87 lines, implements 3 endpoints the framework-supplied `noctusai_seed.routers.notifications_router` also implements."
- "The `create_meta()` service function in ERP and PF products share 90% of their body; only the schema name and two field mappings differ."

The receiving agent must be able to verify the situation is still true by reading the named files. If the situation has changed, the proposal is stale and should be rejected.}}

---

## 3. Proposed Solution

### 3.1 Linkage — why this solution fits this situation

{{1–2 sentences linking the solution to the situation described in §2. What *about the situation* makes this the right approach? What would a different approach miss?

Example: "Because both products implement identical endpoints with only schema-name differences, extracting to `noctusai_lib.services.metas` with a `schema` parameter gives us DRY without forcing a refactor of the product-specific logic that legitimately differs."

This section is where the authoring agent's judgment lives. The receiving agent reads this to understand *why* before acting.}}

### 3.2 Application instructions

{{Concrete steps the receiving agent follows. Each step unambiguous — a step like "make it consistent" is useless. Steps like "move `create_meta()` from `products/erp/.../metas_service.py:14` to `seed/backend/lib/noctusai_lib/services/metas.py`, parameterize the `schema` arg, update both product call sites" are actionable.}}

1. {{step}}
2. {{step}}
3. {{step}}

### 3.3 Seed APIs / shared lib involved

- `{{module.symbol}}` — {{what it provides and why it replaces the current code}}
- `{{module.symbol}}` — {{…}}

*If no seed API applies (pure-product fix), write `N/A — change is local to the product`.*

### 3.4 Risks before applying

{{What the receiving agent must check first. Specific, not hand-wavy.

Triggers that demand an explicit risk note:
- Deleting files → "Diff this product's `{{file}}` against `{{seed-counterpart}}` **before** deleting — check for product-specific customizations."
- Mass text-replacement → "The string `{{pattern}}` may appear in comments, docstrings, or unrelated paths. Review each hit manually; do not batch-replace."
- Migration to shared lib → "Check all product call sites match the new signature; a partial migration leaves divergent behavior."
- Schema changes → "Run migration in the `apply_migration` MCP and mirror to a new numbered `.sql` file in the same commit."

If the fix is truly low-risk, say so in one line: `Low risk — additive change, no overwrite.`}}

### 3.5 Alternatives considered

- **{{approach}}** — {{one sentence why not chosen}}
- **{{approach}}** — {{why not}}

*If no viable alternatives exist, write `N/A — the situation dictates the fix`.*

---

## 4. Effects

When this is applied, these change:

- **Behavior:** {{what the system does differently — new/changed endpoints, new/changed UI behavior, new/changed error paths}}
- **Risk profile:** {{what gets safer or riskier — removed duplication reduces drift, new boundary removes a leak, etc.}}
- **Ergonomics:** {{what's easier or harder for future agents — fewer moving parts, clearer failure modes, stricter contracts}}
- **Coverage:** {{what's now tested / observable that wasn't before, or vice versa}}

*Each bullet is one line. If a dimension doesn't change, delete the bullet — don't pad.*

---

## 5. Acceptance Criteria

- [ ] Fix applied to every affected product (not just the one that triggered detection)
- [ ] `python mcp/noctusai/cli.py --validate` shows 100/100 for the affected product(s)
- [ ] `python mcp/noctusai/cli.py --review --product {{primary-product}}` files no new proposals for this issue (i.e. the finding no longer reproduces)
- [ ] Backend tests still pass for the affected product(s)
- [ ] If the change touched shared code, `python mcp/noctusai/cli.py --catalog` shows no new orphans or duplicate candidates
- [ ] Documentation updated where behavior changed (MASTER-PROMPT, KB, CLAUDE.md pointer if relevant) — KB-first per `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md → Docs stay in sync`

*Add proposal-specific acceptance items here when the fix needs them.*

---

## 6. Related files

- `{{path/to/file.py:LN}}` — {{what to inspect / what to change}}
- `{{path/to/other.ts:LN}}` — {{…}}

*Optional — include when jumping to specific lines helps the receiving agent. Omit the whole section if §3.2 already names every touched file.*

---

<!--
Filling guidance — DELETE this HTML comment block before filing.

- Keep §1 Context tight (5 sentences max). It's a briefing, not a dissertation.
- §2 Situation is facts-only. Any "should" or "must" belongs in §3.
- §3.1 Linkage is load-bearing — this is where judgment is recorded. Never skip it.
- Do NOT paste code diffs. Instructions + file pointers only. The receiving agent writes the code.
- Do NOT propose changes inside `seed/` unless the situation clearly indicates a framework gap.
- Do NOT quote long prompts, tool output, or conversation history here.
- If a section is truly N/A, write `N/A — {{one-line why}}`. Never silently drop a heading.
- Sections numbered 1–6 help the receiving agent navigate. Do not rename them.
-->
