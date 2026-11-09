# ui-ux-rules — evaluation scenarios

Desk-checked on 2026-11-08 by skill-scout (noc-1), not model-run: each scenario was answered by reading `references/quick-reference.md` and confirming a rule id covers it. A model-run eval is owed before the skill is called from an agent with no human in the loop.

| # | Scenario | Expected rule ids | Result |
|---|---|---|---|
| 1 | A product form shows every validation error only at the top after submit | `inline-validation`, `error-clarity`, `focus-management` (category 8) | covered |
| 2 | A sticky footer bar hides the keyboard-focused button on a long settings page | `focus-not-obscured` (category 1) | covered |
| 3 | A review asks for "a new color palette for the clinic product" | category 4 `color-palette-from-product` (adapted): use seed token roles, no new palette; the skill must refuse to invent one | covered (house rule) |
