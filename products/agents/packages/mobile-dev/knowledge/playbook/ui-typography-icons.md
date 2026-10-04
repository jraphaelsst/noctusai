---
titulo: "UI: tokens, typography, icons"
tipo: guia
proveniencia:
  fonte: "limiar-app agents/mobile-dev/knowledge/03-ui-typography-icons.md (v0.1.0)"
  data: "2026-10-03"
---
# UI: tokens, typography, icons

## Tokens first
- One `tokens.ts`: raw `palette` (named for what the colour IS) + semantic `color` roles (what it's FOR).
  Components use semantic roles only. Spacing (4-pt), radius, sizes, motion, one optional shadow.
- Measure colours from the approved mockup (pixel-median of flat patches) when no design file exists;
  record provenance per token. Compute WCAG contrast for every text/background pair you ship and
  encode "never" pairs as rules (e.g. body grey on sand fails → ink on sand).

## Fonts
- Bundle via `@expo-google-fonts/<family>` (works offline; SIL OFL). Load with `useFonts` in the root
  layout; keep the splash screen up until loaded; **throw** font errors instead of rendering fallbacks.
- RN has **no weight synthesis**: each weight is a separate family name (`Inter_500Medium`). Map
  roles → family names in one `fonts.ts`.
- Check glyph coverage and OpenType features with fontTools before committing to a face:
  `getBestCmap()` for the language's accented letters; `GSUB` feature tags (`lnum`, `onum`, `tnum`, `ss01…`).
- **Old-style numerals:** some serifs (Cormorant Garamond) default to old-style figures — "192" reads
  as "1g2". Set `fontVariant: ['lining-nums']` on those styles; show critical numbers (emergency lines)
  in a sans.
- **Accents:** Cormorant draws á/ê/ó high and offset right. It's the face's design, not a bug
  (verified by rendering the TTF with PIL) — a brand decision, check on device.
- Small x-height serifs need sizes ~15 % above a typical serif. Approve the scale **on a real phone**
  (ship a dev-only type-specimen screen).
- Never disable OS font scaling.

## Icons
- One set, one place: `src/components/ui/icons.ts` re-exports what the app uses.
- **Phosphor** (`phosphor-react-native`): `light` weight by default, `fill` for active/selected.
- Import per icon: `export { HouseIcon as House } from 'phosphor-react-native/src/icons/House'`.
  The package root pulls in ~1,500 icons: web bundle went **7.1 MB → 1.4 MB** after switching.

## Components that held up
`AppText` (variant + semantic colour; headings get `accessibilityRole="header"`) · `Button`
(primary/secondary/quiet; quiet = text link; disabled styles differ per variant) · `IconButton`
(label REQUIRED) · `Chip` (non-interactive) · `Screen` (safe area, gutter, max width, optional pinned
footer) · `ListRow` (no `onPress` ⇒ informational: no chevron, not a button) · `CheckItem`
(`mark="dot"` for neutral/negative statements — a ✓ next to "we don't ask your CPF" reads backwards).
