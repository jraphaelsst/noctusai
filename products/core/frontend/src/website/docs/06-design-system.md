# 06 · Design system & rebrand brief

> **Status.** The *structure* below (token architecture, roles, rules) is settled. The *identity values* (logo, faces, exact colours, 3D motif) are **the output of the rebrand exploration**. That exploration uses Higgsfield **only with explicit owner permission per session** ([13](13-tooling-and-mcp-policy.md)). Until the owner approves an identity, the build uses the neutral bootstrap values marked *bootstrap*.

## Brand premise

- **Name → idea.** *Noctus* comes from *nocturnal*: the hours when work keeps happening. The brand idea is **"intelligence that works while you sleep"**: calm, precise, always on. That gives a night-sky palette with a single luminous accent.
- **Voice.** Confident & technical + visionary ([01](01-brief-and-decisions.md#brand--visuals)):
  - Headlines make one concrete claim in 15 words or fewer, in pt-BR first.
  - Each section may carry one visionary line.
  - No hype adjectives ("revolucionário", "incrível").
  - Numbers only when they're real ([P7](04-pattern-synthesis.md#p7-honest-proof-before-social-proof)).
- **What the rebrand must deliver:**
  1. Wordmark + symbol, legible from favicon size up to 180 px.
  2. Two-family type system.
  3. Neutral ramp + one brand accent + one action colour, AA in both themes.
  4. One **art-direction motif** that runs through the 3D hero, the static poster, section art, OG images and blog covers ([P1/P2](04-pattern-synthesis.md#p1-text-is-html-the-spectacle-sits-behind-it), with Cerebrium's ribbon and AI in Design's flowers as precedents).
  5. Product imagery style.
- **Exploration directions** (for Higgsfield moodboards; the owner picks one):
  - **A · Constellation.** Nodes and links forming products, like a star map. The hero is an explorable constellation whose stars are the product "modules", with HTML HUD labels.
  - **B · Aurora.** Soft volumetric light ribbons over deep night. Close to Cerebrium, so it must be clearly differentiated. The most calming option.
  - **C · Night city grid.** A wireframe city at night whose lit windows are running AI processes. It leans into "while you sleep" and the BR SMB concreteness.

## Scope isolation (website-only rebrand)

- All website tokens live under a **website root scope** (`[data-surface="site"]` on the website's root element) in the website's own CSS entry. **None are defined on `:root`** of the app shell. The logged app keeps its current tokens untouched.
- Token *names* follow the seed design-system naming, so the later app adoption is a value swap rather than a rename.

## Token architecture

Three layers:
- **Primitive** (raw ramps): `--nx-night-0..12`, `--nx-accent-3..9`, `--nx-action-…`.
- **Semantic** (role): the tokens listed below.
- **Component**: only where a component truly needs its own.

Components consume **semantic tokens only**.

| Semantic token | Role |
|---|---|
| `--bg`, `--bg-elevated`, `--bg-inverse` | Page, raised surfaces, the always-dark band |
| `--fg`, `--fg-muted`, `--fg-subtle`, `--fg-inverse` | Text levels (muted and subtle must still pass AA for their size) |
| `--border`, `--border-strong`, `--hairline` | 1 px rules, the hairline grid (Aspen) |
| `--accent`, `--accent-fg`, `--accent-gradient` | Brand emphasis; the highlighted headline word |
| `--action`, `--action-fg`, `--action-hover` | **Primary CTA only** (P4) |
| `--chapter-<product>` | Optional per-product colour field, used only inside that product's section and page |
| `--focus-ring` | Visible focus, 3:1 against adjacent colours |
| `--scene-bg`, `--scene-accent`, `--scene-fog` | Read by the WebGL scene, so the theme recolours the canvas |

**Radii & elevation.** Flat, with 0–8 px radii (larger only on big section panels) and hairlines instead of shadows. That matches the Awwwards consensus and avoids the pill-heavy BR look, which would read as "another BR SaaS".

## Theming

- Themes are `data-theme="light" | "dark"` on the website root. The **3-state header switch** (Sistema / Claro / Escuro) persists in `localStorage`.
- An **inline `<head>` script** applies the theme before first paint (no flash), reading the stored choice and falling back to `prefers-color-scheme`.
- The seed `useTheme` currently reads `localStorage` inside `useState`, which crashes under server rendering. The SSR guard is **a seed fix, not a website fork** ([08 §4](08-technical-architecture.md#4-prerendering)).
- The switch updates the scene uniforms live (see 3D hero).
- **Always-dark band.** The hero and one "IA" band use `--bg-inverse` in both themes (a narrative device). In light theme they read as a deliberate dark panel with rounded seams (Cerebrium).

## Typography

- **Two families:**
  - Display/text **sans**: a grotesk with tight-tracking support and pt-BR diacritics.
  - **Mono**: eyebrows, labels, buttons, numbers, code.
- *Bootstrap* until the rebrand: Inter (sans) + JetBrains Mono (mono), both OFL. The final faces are chosen during exploration, and **must be licensed for web** (Cerebrium's Trial-font mistake).
- **Scale:**

  | Role | Size / line-height | Weight | Tracking |
  |---|---|---|---|
  | Display (home hero) | clamp(56 px, 8vw, 128 px) / 0.95 | 400–500 | −3% to −4% |
  | H1 (pages) | clamp(40 px, 5vw, 72 px) / 1.0 | — | −2.5% |
  | H2 | 32–48 px / 1.1 | — | — |
  | H3 | 22–28 px | — | — |
  | Body | 17–18 px / 1.6 | — | — |
  | Small | 14 px | — | — |
  | Mono labels | 12–13 px, uppercase | — | +4–6% |

- **Signature device:** one word per headline in `--accent-gradient`, or a weight contrast within the line. Pick one of the two and use it everywhere.
- **Loading:** self-hosted, subset (Latin + Latin-ext for pt-BR), `font-display: swap`, with metric-matched fallbacks (`size-adjust`) so fonts don't shift the layout (CLS ≤ 0.05).

## Layout

- 12-column grid, max content width about 1280 px, 16 px mobile gutters, generous vertical rhythm (section padding 96–160 px on desktop).
- **Modular sections.** Every home section is a self-contained block on a visible **hairline cell grid** (Aspen). Hiding a section via admin never leaves a hole or a broken seam.
- Components: header, mega-menu, CTA pair (primary + attached arrow cell, as Sharplink does), audience card, product chapter, faux-UI panel, feature index, architecture diagram, pricing card + comparison table, FAQ accordion, post card (shared by blog and Novidades), consent bar, locale bar, WhatsApp float, footer. They are built for the website; each gets a later **seed-promotion review** (componentize-everything rule).

## Motion

- **Everywhere except the hero, motion is minimal:** 150–250 ms opacity and transform transitions on hover and focus, and a one-time *enhancement* fade on entry. **Content is visible without JavaScript**: nothing starts hidden in the SSR output ([P11](04-pattern-synthesis.md#p11-seo-is-structural-not-a-plugin)).
- Allowed micro-effects: the mono text-scramble on one eyebrow *after* paint (L.I.S.A., used small); number tick-ups that **start from the real final value** in the SSR output.
- `prefers-reduced-motion` disables everything except colour and opacity state changes.
- **Banned:** scroll-jacking and smooth-scroll libraries (Lenis), pinned scroll-scrubbed stages, preloaders, auto-advancing carousels without pause.

## 3D hero

- **Composition.** The HTML H1 + subhead + CTA pair go bottom-left or centred over the scene (Cerebrium), with a contrast scrim. The scene is framed so the text area stays calm.
- **Interactivity (desktop).** The pointer parallax-orbits the scene. Hovering or focusing a product "module" highlights it and shows an **HTML HUD label** linking to that product's page (Sharplink). Keyboard: the modules are reachable as a list of HTML links that mirrors the scene.
- **Delivery:**
  1. The poster (AVIF/WebP, light and dark, same camera as frame 0) is the LCP.
  2. On `requestIdleCallback` plus the hero being in view, `import()` the scene chunk and cross-fade it in.
  3. Mobile, `saveData`, `deviceMemory` ≤ 4 or reduced motion: stay on the poster and show an "Explorar em 3D" button.
  4. Pause rendering when off-screen or the tab is hidden.
  5. Cap DPR at 1.5–2.
- **Budget:** ≤ 300 KB gzipped JS for the scene chunk (three.js core + scene code) and ≤ 1.5 MB compressed geometry and textures (Draco/Meshopt + KTX2). No video in the hero.
- **Tech:** three.js (react-three-fiber optional; decided in the build slice, using Context7 for current APIs). Tree-shaken imports only. Shaders read the `--scene-*` tokens.
- **Assets.** The scene model and textures come from the approved motif. Poster renders come from the scene itself, which guarantees the poster matches frame 0. Higgsfield may produce concept and product imagery (owner-approved), **not** the runtime scene.

## Imagery

- **Product visuals:** DOM/SVG faux-UI panels first (P10). Real screenshots second. Higgsfield-generated product imagery for hero-grade shots, only when the owner approves and always marked as illustrative, never passed off as a customer's data.
- **Blog covers and OG images:** generated at build time from the motif template (title plus the motif render), per page and per language.
- Every image carries alt text in both languages. Decorative images use `alt=""`.
