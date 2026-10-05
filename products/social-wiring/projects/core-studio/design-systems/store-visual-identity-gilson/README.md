# Store Visual Identity

Editorial collage for real-estate content: cream paper, navy ink and gold foil, with grayscale photo cut-outs that turn one headline into one visual metaphor. Built from the 5 reference posts in `projects/store` (group **References** in Assets).

The look in one sentence: **a serious financial-magazine cover made with scissors**. Premium and a little ominous, never cheerful.

## Who it talks to

- **Buyers and renters** weighing a property decision (rent vs. buy, waiting for rates to drop, what you can and cannot change in a property).
- **Real-estate brokers (corretores)** about their own performance and habits.

Language is Brazilian Portuguese. The posts are hooks for Stories / Reels covers and carousels.

## Content fundamentals (voice)

- **Hook first, consequence second.** The serif headline states the provocation; the sans deck finishes the sentence and lands the consequence. Read together they form one sentence:
  - "O QUE ACONTECE **COM O DINHEIRO**" + "de alguém que paga aluguel por 10 anos é assustador."
  - "Você pode **mudar** quase tudo em um imóvel," + "menos o mais importante."
  - "3 hábitos que **destroem**" + "sua performance como corretor."
  - "Esperar os juros **baixarem**" + "pode fazer você pagar **muito mais caro** pelo imóvel."
- **Loss aversion and urgency**: assustador, destroem, mais caro, the mistake you are making now. Speaks directly to *você*.
- **Numbers as hooks**: "10 anos", "3 hábitos", years on calendar pages.
- **Exactly one gold keyword in the headline**: the verb or noun that carries the threat or the action (DINHEIRO, MUDAR, destroem, baixarem). The deck may hold one gold phrase too (`keyword-small`).
- **The deck ends with a period.** Short lines, 2-3 of them.
- No emoji, no hashtags, no exclamation marks on the art.

## Visual foundations

### Color

Three colors and grayscale photography. Nothing else.

| Role | Token | Hex | Where |
|---|---|---|---|
| Ground | `paper` | #f2eadd | Default background, aged paper with grain |
| Ink | `ink-navy` | #0b1530 | Headline and deck text |
| Slab | `navy` | #142a3f | Torn panels, floor planes, side strips |
| Night | `midnight` | #061727 | Full-bleed dark ground (inverted posts) |
| Gold | `gold` | #b08d57 | Foil disc, keyword, rule, line accents |
| Photo | `concrete` | #8d8983 | Midtone of the desaturated photos |

- Proportion on a paper post: about 55% paper, 25% navy, 10% gold, 10% grayscale photo.
- **Two themes, same system.** *Paper* (4 of 5 references) is the default. *Midnight* (post 01) inverts it: navy ground, cream headline, cream torn slab. Use Midnight for the darker, scarier topics.
- Gold on paper is only 2.6:1. That is the source's choice and it works because the keyword is huge. Below about 80px use `gold-deep` on paper, or put the gold text on navy.
- Photos are **always grayscale**, high contrast, slightly gritty. The only color in the image is navy and gold. A hint of brass in metal objects (hourglass, keys) is allowed.

### Typography

- **Display: Playfair Display, 800-900.** A high-contrast didone serif. Two modes:
  - `display-caps`: all caps, 2-4 lines, leading about 0.95.
  - `display-mixed`: sentence case, very tight tracking (-0.045em) and leading (0.86) so lines nearly touch. A leading numeral (`display-numeral`) is set larger.
- **Deck: Montserrat 500.** Geometric sans, sentence case or caps (`deck-caps`, +0.03em). Emphasis is Montserrat 700 in gold.
- Both faces are the closest Google Fonts matches to the references, not confirmed originals. If the real files exist, swap them in `type.families`.
- Text is **always flush-left** on `margin-x`, never centered.

### Layout (1080 × 1920 canvas)

```
 ┌───────────────────────────┐
 │                       ▓▓▓ │  ← optional navy torn strip at the right edge
 │  HEADLINE SERIF       ▓▓▓ │  text-top 200px, margin-x 96px
 │  LINE TWO (gold word) ▓▓▓ │  text block uses ~0-45% of height
 │  deck in sans,            │
 │  ends with a period.      │
 │  ▬▬▬                      │  gold rule 120×8, 64px below the deck
 │            ◯ gold disc    │
 │       [grayscale hero     │  hero object overlaps the disc,
 │        cut-out object]    │  disc sits behind, center-right
 │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │  navy floor plane, diagonal torn edge
 └───────────────────────────┘
```

1. **Top ~40%**: type block (headline, deck, gold rule). Keep it clear of art.
2. **Bottom ~60%**: the scene. One hero object, grayscale, cut out, sitting in front of the gold disc.
3. **Navy slab**, one or both of: a vertical torn strip down the right edge (posts 03, 04, 05), and/or a floor plane across the bottom with a diagonal or torn edge (02, 03, 05).
4. Keep the bottom ~250px free of key content (Instagram UI).

### Signature elements

- **Gold foil disc.** Flat gold circle with crinkled-foil texture, the "sun" behind the hero. Present in all 5 references. One per post.
- **Short gold rule** under the text block. Present in all 5.
- **Torn paper.** Ragged edges with white paper fibre showing, between cream and navy. Layers overlap like a real collage.
- **Gold hairlines** (`hairline`, 2px): an orbit ellipse or curved arrow around the hero (02, 04, 05), thin crop/registration lines (02), a zig-zag downward trend arrow (03), kintsugi cracks in the navy floor (05).
- **Texture everywhere**: paper grain on cream, fine speckle on navy, crinkle on gold. Nothing is perfectly flat.

### Imagery and metaphor

Each post makes the headline **literal** with one object:

| Headline | Metaphor |
|---|---|
| Rent money over 10 years | A house sinking in a sea of banknotes, a hand reaching up |
| You can change everything but… | A giant hand lifting a house off its lot (location can't move) |
| 3 habits that destroy performance | Broker seen from behind, hand on head; downward gold arrow |
| (carousel slide 2) the 3 habits | The house balanced on three bricks engraved with the habits |
| Waiting for rates to drop | Hourglass with a house in the sand; hand tearing calendar pages 2024-2026 |

Recurring props: a house (gable roof, chimney, either old wood or modern concrete), human hands, broker in a dark suit, desk with laptop and coffee mug, keys with a house keychain, paperwork, money. People are shown from behind or as hands: **no faces looking at the camera**.

### Carousels

Slide 1 is the hook. Later slides **repeat the same headline block** and change the scene to the reveal (03 → 04). Words that are content of the reveal are set *inside* objects with `engraved-label`, never as a bullet list.

## Don'ts

- No color photos, no gradients, no drop shadows on type, no rounded cards, no icons or emoji.
- No centered text. No more than one gold word in the headline.
- No second accent color. Status colors (red/green) are not part of this identity; a fall is shown with a gold arrow.
- No stock "happy family with keys" smiles. The tone is cautionary.

## Image-generation prompt template

The references read as AI-assisted collage. Use this as the base when generating the scene (type is set afterwards in layout, never by the image model):

> Vertical 9:16 editorial mixed-media collage, vintage magazine cut-out style. Aged cream paper background with subtle grain. Torn deep-navy (#142a3f) paper panels with ripped white fibre edges [on the right edge / as a floor plane with a diagonal edge]. A large flat gold-foil disc (#b08d57) with crinkled metallic texture behind the subject, center-right. Subject: [ONE METAPHOR OBJECT], black-and-white high-contrast halftone photograph, cut out. Thin gold line accents: [orbit ellipse / curved arrow / zig-zag down arrow / kintsugi cracks]. Upper 40% of the frame left empty cream paper for text. Muted, premium, serious mood. Only navy, gold, cream and grayscale. No text, no faces toward camera.
