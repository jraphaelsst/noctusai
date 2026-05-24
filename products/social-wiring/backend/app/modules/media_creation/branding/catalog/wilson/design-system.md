# Design System — Wilson Real Estate (Granja Viana)

> **Filosofia:** Premium, sóbrio, alto padrão. A imagem sugere mais do que afirma. O leitor olha e sente *exclusividade*, não *promoção*.

This is the **skeleton** — composition, hierarchy, color roles, slide structure — locked across all posts. The **per-post params** (exact photography, accent shapes, headline text, slide count) are decided per brief.

---

## Two variants

| Variant | When to use | Mood |
|---|---|---|
| **Premium** (default) | Sales, authority, market insight, market commentary | Alto padrão, sofisticado, contemplativo |
| **Educational** (lite) | Tutorial, listicle, dicas, didático | Acessível, claro, escaneável |

> Use **Premium** by default. Switch to **Educational** only when the brief is explicitly tutorial/listicle.

---

## Canvas — locked

- **Format:** Instagram carousel, **1080 × 1350 (4:5)**
- **Safe area:** 96 px margins all sides → inner canvas 888 × 1158
- **Grid:** 12 columns, 24 px gutter
- **Slide count:** 3–7 (default 5 — cover + 3 develop + CTA)

---

## Palette — Premium variant (locked)

| Role | Hex | Use |
|---|---|---|
| `bg-primary` | `#2A2620` | Default slide background — warm dark olive |
| `bg-deep` | `#1A1612` | CTA slide, ultra-dark moments |
| `accent-gold` | `#C5A55E` | Highlights, key words, accent shapes, location pin |
| `accent-gold-bright` | `#E0C076` | Hover state, ultra-emphasis (CTA button) |
| `text-primary` | `#F5F1EA` | Headlines and body text on dark |
| `text-muted` | `#A89B85` | Subtitles, supporting text, brand handle |
| `divider` | `#3D362B` | Subtle dividing lines on dark bg |
| `photo-overlay` | `rgba(26, 22, 18, 0.65)` | Gradient overlay on photography |

**Photo overlay direction:** when photo bleeds full-canvas, overlay is `linear-gradient(90deg, bg-primary 0%, transparent 60%)` or `linear-gradient(180deg, transparent 0%, bg-deep 100%)` depending on text position.

## Palette — Educational variant (locked)

| Role | Hex | Use |
|---|---|---|
| `bg-light` | `#E8E5F0` | Lavender-grey background |
| `bg-dark` | `#3A4FB8` | Navy royal blue background |
| `accent-yellow` | `#F0E63A` | Number circles, key word highlights |
| `text-on-light` | `#3A4FB8` | Navy text on lavender bg |
| `text-on-dark` | `#F5F1EA` | Off-white text on navy bg |

---

## Typography — locked hierarchy

| Token | Family | Weight | Size | Line | Letter | Use |
|---|---|---|---|---|---|---|
| `display-xl` | serif | 400 | 96 px | 1.05 | -0.01em | Cover headline (1–4 words) |
| `display-lg` | serif | 400 | 72 px | 1.1 | -0.01em | Cover headline (5–8 words) |
| `display-md` | serif | 400 | 56 px | 1.15 | 0 | Internal slide headline |
| `display-sm` | serif | 400 | 40 px | 1.2 | 0 | Internal sub-headline |
| `body-lg` | sans | 400 | 28 px | 1.45 | 0 | Body paragraphs |
| `body-md` | sans | 400 | 22 px | 1.5 | 0 | Bullet items, captions |
| `accent-sm` | sans | 500 | 18 px | 1.4 | 0.04em uppercase | Location pin, eyebrow text |
| `handle` | sans | 400 | 16 px | 1 | 0 | Brand handle (low contrast) |

**Font families:**
- **Serif (display):** `"Cormorant Garamond"`, fallback `Georgia`, `"Times New Roman"`, serif
- **Sans (body):** `"Inter"`, fallback `system-ui`, `-apple-system`, sans-serif

**Italic rule:** display serif uses italic only for **single highlighted words** within a headline (e.g. *Granja*), not full headlines. Body sans never italic.

**Gold word highlight:** in a display headline, 1–2 words may be set in `accent-gold` to draw the eye to the key term. Choose the word that holds the meaning of the slide.

---

## Slide layout roles — locked structure, flexible content

Every slide has one of 4 roles. The role determines composition.

### Role A — COVER
The contract that promises the carousel's payoff. Must stop the scroll.

```
┌──────────────────────────────────────┐
│ [photo full-bleed, dark overlay 50%] │
│                                      │
│  ┃                                   │
│  ┃ HEADLINE  (display-lg/xl, serif)  │
│  ┃ 2–3 lines, 1 word may be gold     │
│  ┃                                   │
│  ─── (gold rule, 80px)               │
│                                      │
│  Subtitle (body-lg, text-muted)       │
│  1–2 lines                            │
│                                      │
│                                      │
│                                      │
│  @wilson_one2022       📍 GRANJA     │
└──────────────────────────────────────┘
```

Photography is **full-bleed**, never cropped to a window. The dark overlay sits on the left ~60% so text reads, leaving the right side of the photo visible.

### Role B — DEVELOP (split arch)
Develops the idea. Photo lives behind a **curved arch mask** on one side; text on the other.

```
┌──────────────────────┬───────────────┐
│  ┃ Eyebrow           │ ╱ photo with  │
│  ┃                   │ ╱ curved      │
│  Headline (display-md)│ ╱  arch mask │
│  2 lines             │ │  on left    │
│  ─── (gold rule)     │ │             │
│                      │ │             │
│  Body bullets:       │ │             │
│  ✦ item              │ │             │
│  ✦ item              │ │             │
│  ✦ item              │ │             │
│  ✦ item              │ ╲             │
│                      │ ╲             │
│  "Frase destaque"    │ ╲             │
│  (display-sm italic) │                │
│                      │                │
│  @wilson_one2022                      │
└──────────────────────┴───────────────┘
```

Arch direction alternates slide-to-slide for rhythm (slide 2 photo-right, slide 3 photo-left, etc.) **or** stays consistent — decided per post.

### Role C — INSIGHT (full text, no photo)
Pure typographic slide for a moment of contemplation or a strong claim.

```
┌──────────────────────────────────────┐
│                                      │
│  ?                                   │
│  (gold icon)                         │
│                                      │
│  Headline (display-md)               │
│  2–4 lines, may include a gold word  │
│                                      │
│  ─── (gold rule)                     │
│                                      │
│  Body (body-lg)                       │
│  2–3 short lines                      │
│                                      │
│                                      │
│                                      │
│  @wilson_one2022                     │
└──────────────────────────────────────┘
```

Use sparingly — max one Insight slide per carousel.

### Role D — CTA
Drives the action. Ultra-dark bg, glow accent, explicit ask.

```
┌──────────────────────────────────────┐
│ [photo bg, very dim ~80% overlay]    │
│                                      │
│  Hook headline (display-md)          │
│  2–3 lines                           │
│                                      │
│  ─── (gold rule)                     │
│                                      │
│  Lead-in line (body-md, muted)        │
│                                      │
│  ┌──────────────────────────┐         │
│  │   ACTION WORD (gold bg)  │         │
│  │   (display-sm, bg-deep)  │         │
│  └──────────────────────────┘         │
│                                      │
│  @wilson_one2022     📍 GRANJA       │
└──────────────────────────────────────┘
```

The action word (e.g. "VALORIZAÇÃO") is a **golden pill button** — gold bg, dark text, uppercase, letter-spaced.

---

## Photography rules — Premium variant

| Rule | Definition |
|---|---|
| **Subject** | Architecture, interiors, landscape, location lifestyle. **Never** real estate agent posing, never stock-photo people-on-laptop. |
| **Color grade** | Warm dark tones — amber/olive shadows, golden highlights. Avoid cool blues. |
| **Lighting** | Golden hour, interior dimmed warm, or moody twilight. Avoid bright daylight unless intentional contrast. |
| **Framing** | Wide. Composition has depth — foreground, midground, background. |
| **Negative space** | Mandatory. The photo must have ~30–40% breathable space for typography to inhabit. |
| **People** | Allowed if blurred, distant, or silhouetted. Never a clear face that competes with the typography. |

**Forbidden:**
- Generic stock real estate (handshakes, keys-in-hand)
- Bright over-saturated marketing photography
- Real estate agent portraits (Wilson's headshot lives in the bio, not the carousel)
- People-front-and-center posing

---

## Brand handle — locked

`@wilson_one2022` appears on every slide, set in `handle` token (`text-muted`, low contrast). Position: **bottom-left**, 96px from edges.

Location pin "📍 GRANJA VIANA" optional, bottom-right on Cover and CTA slides only, set in `accent-sm` gold.

---

## Accent shapes — flexible per post

The accent vocabulary draws from a small set. Each post picks 1–2; never all.

| Shape | Visual | Use |
|---|---|---|
| **Gold vertical rule** | `┃` 4px wide, 60–120px tall | Left-side anchor before headlines |
| **Gold horizontal rule** | `───` 1px, 80px wide | Below headline, before body |
| **Curved arch** | Quarter-circle SVG path | Photo mask in Develop role |
| **Gold question mark** | Stylized `?` 64px | Insight role icon |
| **Gold dot row** | 5 small dots, varying opacity | Optional bottom-corner decoration |
| **Gold pill button** | Rounded rect with text inside | CTA action word only |

---

## Per-post parameters (flexible — set in the brief)

When designing a new post, the brief must specify:

1. **Topic / angle** — what the carousel is about
2. **Slide count** — 3–7 (default 5)
3. **Photography theme** — interior architecture / exterior landscape / neighborhood lifestyle / market-data graphic
4. **CTA action word** — the gold pill word (e.g. `VALORIZAÇÃO`, `GRANJA`, `INVESTIR`)
5. **Gold word in cover headline** — which word inherits `accent-gold`
6. **Variant** — `premium` (default) or `educational`
7. **Arch direction strategy** — `alternating` or `consistent-right` or `consistent-left`

Everything else (palette, typography, layout, handle, photography rules) is inherited from this document.

---

## Skeleton vs. flexibility — quick map

| Locked (skeleton) | Flexible (per post) |
|---|---|
| Canvas size 1080×1350 | Slide count 3–7 |
| Palette tokens (premium + educational) | Which 1–2 accent shapes |
| Typography hierarchy + families | Which word gets gold highlight |
| 4 slide roles (Cover/Develop/Insight/CTA) | Order of roles within the carousel |
| Photo rules (subject, grade, framing) | Specific photo subject per slide |
| Brand handle position + size | Location pin presence (optional) |
| CTA pill button structure | CTA action word |
| Arch as photo mask | Arch direction (alternating/consistent) |

---

## How a new post applies this system

1. Read the brief (topic + slide count + variant)
2. Map content to slide roles (Cover → Develop × N → CTA)
3. For each slide, pick: photo subject (from rules), accent shape, gold word
4. Generate SVG per the role template
5. Write photo prompt for the placeholder zone (rendered later via Nano Banana or GalilAI)
6. Verify: every slide carries the handle, premium palette is intact, no forbidden photography

The `image-prompt-generator` skill uses this document as its source of truth for visual decisions.
