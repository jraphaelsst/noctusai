# NoctusAI

Night sky, one luminous accent: **intelligence that works while you sleep**. Calm, precise, always on. This system is the noctusai.com website identity as built on 2026-09-22/23. Its values are the **bootstrap** set: the structure is settled, while the logo, faces, exact colours and 3D motif wait for the rebrand exploration. When the rebrand lands, the values change and the names stay.

## Who it talks to

Brazilian small and mid-size businesses, mid-market and enterprise, developers, and freelancers or solo founders. Positioning is hybrid: ready products plus custom builds. pt-BR first, with an EN toggle.

## Content fundamentals (voice)

- Confident and technical, plus visionary.
- A headline makes one concrete claim in 15 words or fewer, pt-BR first.
- Each section may carry one visionary line.
- No hype adjectives ("revolucionário", "incrível").
- Numbers only when they are real; social proof ships hidden until it exists, never fabricated.

## Visual foundations

### Color

Three layers: **primitive** ramps (`night-0`…`night-12`, `accent-3`…`accent-9`, `cyan-6`, `action-7`), **semantic** roles (`bg`, `fg`, `accent`, `action`…), and component tokens only where a component truly needs one. Components use semantic tokens only.

| Role | Light | Dark |
|---|---|---|
| `bg` | night-0 #f7f8fc | night-11 #07080f |
| `fg` | night-11 | night-0 |
| `fg-muted` | night-6 #3c4256 | night-3 #b6bccf |
| `accent` | violet #8b5cf6 | violet #a78bfa |
| `action` | cyan #06b6d4 | cyan #22d3ee |
| `bg-inverse` | night-11 (always dark) | night-11 |

- **Action is reserved for the primary CTA.** One per view. Label in `action-fg` #04252b.
- **Accent** marks emphasis: eyebrows, available badges, and the one highlighted headline word.
- **Accent gradient** (the signature device): `linear-gradient(90deg, accent-7, cyan-6)` clipped to the text of ONE word per headline. Use it or a weight contrast, never both.
- **Always-dark band**: the hero and one AI band sit on `bg-inverse` in both themes, with `fg-inverse` text; fields inside the band use `night-9`.
- Themes: light and dark, plus "Sistema" in a 3-state switch, applied before first paint.

### Typography

Two families. **NX Sans** (bootstrap: Inter 400/600/700, self-hosted) for display and text; **NX Mono** (bootstrap: JetBrains Mono 400) for eyebrows, labels, badges, numbers and code. Headings 600 with negative tracking (−2% to −3%); the hero display is 500 at −3%. The final faces come from the rebrand and must be licensed for the web.

### Layout and shape

12-column grid, content max 1280px, 16px mobile gutter, sections 96px (160px from 768px) with a hairline top border. Modular sections on a visible **hairline cell grid**: hiding a section never leaves a hole. Flat surfaces, 6–12px radii, hairlines instead of shadows; pills only for badges and hero module links.

### Motion

Minimal outside the hero: 150–250ms opacity and transform on hover and focus. Content is visible without JavaScript. Reduced motion keeps only colour and opacity changes. No scroll-jacking, preloaders or auto-advancing carousels.

### Imagery

Faux-UI panels (DOM/SVG) first, real screenshots second. The 3D hero (constellation, aurora or night-city direction, still to be chosen) sits behind the HTML text with a contrast scrim and reads the `scene-*` tokens.

### Logo

No logo yet: the header sets "NoctusAI" in NX Sans 700, 18px, −0.01em. The rebrand delivers a wordmark and symbol.

## Components

Button, Eyebrow (with the accent word), Panel (faux-UI), Badge, HairlineGrid.

## Still open (rebrand)

Wordmark and symbol · final two-family type system · final colour values (AA in both themes) · the art-direction motif for the hero, posters, OG images and blog covers · product imagery style. App adoption is a later, separate project: the logged-in apps keep the seed tokens until then.
