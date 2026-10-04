---
nome: review-mobile-screen
descricao: "Reviews a React Native/Expo screen or component for mobile correctness: layout and safe areas, typography (font loading, weights, numerals, accents, scaling), icons, tokens, navigation behaviour, state/persistence, accessibility and loading/empty/error states. Use before shipping UI or when a screen 'looks wrong on the phone'."
ordem: 30
---
## When to use
Any UI change before it ships, or a visual/behaviour bug on device. Product copy, scope and brand rules belong to the project's domain agent.

## Before you start
Read the screen file and every component it uses, the theme tokens, and how it's reached (route, guards). Ask for a device screenshot when the issue is visual.

## Procedure
1. Layout: safe areas, gutter, long text wrapping, font scaling (no fixed heights on text), pinned footer vs scroll.
2. Typography: tokens only; each weight its own family; lining numerals where numbers matter; accent rendering checked on device.
3. Interaction: touch targets ≥ 48, pressed/disabled states per variant, no fake affordances (a row without action has no chevron).
4. Accessibility checklist (playbook accessibility).
5. Navigation/state: back with no history, guards, persistence validated, errors visible where the user acted.
6. Classify findings: **must fix** / **should fix** / **nice to have**, each with file:line and the concrete change.

## Repertoire
Tab bar 64 + bottom inset; Phosphor per-icon imports; `CheckItem mark="dot"` for negative statements; Alert doesn't work on web — confirm in-screen.

## Deliverable
Findings table (severity · file:line · problem · fix), then what must be verified on a real device.

## Pitfalls
Approving from a web screenshot alone; missing inactive-tab label contrast; literal colours bypassing tokens.

## Go deeper
Playbook: ui-typography-icons, navigation-state, accessibility, device-testing.
