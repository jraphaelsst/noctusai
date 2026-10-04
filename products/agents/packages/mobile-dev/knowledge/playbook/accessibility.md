---
titulo: "Accessibility checklist (review every screen against it)"
tipo: sintese
proveniencia:
  origem: "limiar-app agents/mobile-dev/knowledge/06-accessibility.md (v0.1.0)"
  notas: "Sintetizado em 2026-10-03 a partir da sessão de desenvolvimento do limiar-app."
---
# Accessibility checklist (review every screen against it)

- Touch targets ≥ 48 pt (use `hitSlop` for smaller visuals).
- Every icon-only control has `accessibilityLabel`; decorative shapes are hidden
  (`accessibilityElementsHidden` + `importantForAccessibility="no-hide-descendants"`).
- Roles: `button`, `link`, `header` (headings), `radio`/`radiogroup` (single choice),
  `checkbox` (multi choice), `image` for logos. Selected/checked/disabled go in `accessibilityState`.
- Async results and errors use `accessibilityLiveRegion` (polite for status, assertive for errors).
- Contrast: text ≥ 4.5:1, large text ≥ 3:1, functional borders/icons ≥ 3:1 — computed, not eyeballed.
  Inactive tab labels are text (4.5:1), a common miss.
- Never `allowFontScaling={false}`; layouts must grow (no fixed heights on text containers).
- Status never by colour alone: colour + words (+ icon).
- Respect reduce-motion for any animation.
- Numbers that matter (phone lines, prices) must be unambiguous in the chosen font (see lining figures).
- Display important numbers as selectable text even when there's a call button: `tel:` may fail.
