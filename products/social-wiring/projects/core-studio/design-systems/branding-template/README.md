# Branding Template

The canonical model for every client branding we create. Copy it, fill every section and token, delete nothing: a section that does not apply says why in one line. It merges the two systems built so far: **Store Visual Identity** (Gilson, content-first: posts, headline stack, collage, image prompt) and **Nós no Limiar** (Mônica, identity-first: logo rules, contrast table, screen components).

Values in `tokens.json` are neutral placeholders. Every `usage` note that starts with `FILL:` must be rewritten with the brand's real value and its source.

## How to build a branding from this template

1. **Gather sources** and list them in `tokens.json` `meta.source`: reference posts, an existing identity page, a mockup, a codebase theme, brand files. Never invent a value; when a value is chosen rather than measured, say so (`measured`, `derived`, `chosen for contrast`, `added`).
2. **Logos and references first**: upload them unchanged to the `Logos` and `References` groups. No logo yet: write "no logo; plain type" in the Logos README.
3. **Tokens**: fill every colour role, the three type families, the spacing and radius scales, the canvas sizes.
4. **Check contrast** and fill the contrast table: text 4.5:1 (3:1 at 24px+ and for control borders). Keep a failing source pair only with a flag in its usage note.
5. **Write the brand book** below, section by section, with real copy examples.
6. **Components**: keep HeadlineStack, PostFrame and Accents; add the brand's own (buttons, cards, tabs) when it also has an app or site.
7. **Cover last**.

## Required sections of a brand book

### 1. Who it talks to
Audience, their situation, the language (pt-BR by default), the formats the brand publishes (feed post 4:5, Stories / Reels cover 9:16, carousel).

### 2. Principles
Three one-line rules that decide every case (e.g. "Wine means act", "Exactly one gold keyword").

### 3. Content fundamentals (voice)
How a headline is built (hook + consequence), the words the brand uses and avoids, how emphasis works, punctuation rules, 3–4 real examples.

### 4. Logo
Files and which ground each goes on, minimum size, clear space, don'ts.

### 5. Color
A role table (ground, ink, accent, slab or secondary, status if any), the proportion on a typical post, the theme variants (e.g. a light and a dark ground), and the **contrast table** (pair, ratio, use).

### 6. Typography
Display, body and UI families with weights; the type scale on the post canvas; casing and alignment rules.

### 7. Layout and canvas
Canvas sizes, margins, safe zones (keep the bottom ~250px free on 9:16), the zone diagram of a post.

### 8. Signature elements
The 2–5 shapes or textures that make the brand recognizable, and how many may appear per post.

### 9. Imagery
Photo treatment, recurring props and metaphors, what is never shown.

### 10. Carousels and series
What repeats from slide to slide and what changes.

### 11. Components
HeadlineStack, PostFrame, Accents, plus app/site components when they exist.

### 12. Don'ts
A short list of hard bans.

### 13. Image-generation prompt
The base prompt for generating scenes (type is set afterwards in layout, never by the image model), with the brand's hex values in it.

### 14. Still open
Decisions not yet made, each with an owner.
