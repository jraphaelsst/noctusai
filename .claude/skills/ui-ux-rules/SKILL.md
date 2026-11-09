---
name: ui-ux-rules
description: Use when reviewing or finishing a screen, mockup or UI component for usability — triggers "UI review", "UX audit", "is this screen usable", "check the interaction", "pre-delivery UI check", "revisar a tela", "auditoria de UX". A 10-category checklist (accessibility, touch, performance, style, layout, typography and color, animation, forms, navigation, charts) to scan in priority order. Seed tokens and the house design canon win over it.
license: MIT (see LICENSE; vendored, adapted)
metadata:
  version: "1.0.0"
  origin: "github.com/nextlevelbuilder/ui-ux-pro-max-skill@4f2dbb67e64969a9a30ab00742f2d55d66ddec2b"
---

<!-- vendored: github.com/nextlevelbuilder/ui-ux-pro-max-skill@4f2dbb67e64969a9a30ab00742f2d55d66ddec2b (references/quick-reference.md only) · MIT · adapted 2026-11-08 -->

# ui-ux-rules — the UI review checklist

## Workflow

1. **Know what wins.** The seed design tokens, `KB § PATTERNS/design/design-craft-canon.md` and `KB § PATTERNS/design/accessibility.md` decide first. This checklist only adds what they don't cover. On a conflict, follow the house rule and note the conflict in the review.
2. **Scan in priority order.** Open `references/quick-reference.md` and walk the categories by priority: 1 Accessibility and 2 Touch & Interaction (critical), then 3 Performance, 4 Style, 5 Layout, 9 Navigation (high), then 6 Typography & Color, 7 Animation, 8 Forms (medium), and 10 Charts (low). Read only the categories the screen touches.
3. **Report by rule id.** For each problem, cite the rule id (for example `focus-not-obscured`, `inline-validation`), the element, and the fix. Group by category, most severe first.
4. **Don't invent palettes or fonts.** Category 4 and the color rules of category 6 choose among seed token roles. A new palette, font pairing or "design system" file is out of scope.

## Guardrails
- Web SPA scope: the upstream `pro-rules.md` targets native mobile apps and was not vendored. Native-only rules here (Apple HIG or Material references) apply to our web apps only where the web has the same behaviour.
- The upstream search tool and its CSV data were not vendored, so there is nothing to run.
- Evals: `evals.md` (three desk-checked scenarios).

## Depth
`KB § PATTERNS/design/design-craft-canon.md` · `KB § PATTERNS/design/accessibility.md` · register row in `KB § PATTERNS/common/vendored-skills.md` §6a.
