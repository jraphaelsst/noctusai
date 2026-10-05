# Nós no Limiar

Paper, ink and one wine: a calm, literary identity for a guide through a new phase of adult life. This system is the identity v0.1 of 3 October 2026, built for the Nós no Limiar app (Expo, iOS and Android, pt-BR) and kept in step with `limiar-app/src/theme`.

## Who it talks to

Adults in a life transition (the empty nest, more time for themselves), invited to rediscover who they are now through small activities: create, go out, learn, connect. The tone is warm and unhurried. It speaks to *você*, plainly, never clinical and never cheerful-marketing.

## Principles

- **Wine means "act".** Primary buttons, the active tab, selected states. Never decoration.
- **Serif speaks, sans operates.** Cormorant for what the brand says, Lora for reading, Inter for what you tap.
- **Collage is imagery, never UI.** Text, icons and controls stay native. Nothing is baked into a bitmap. The welcome screen uses collage, no photography.

## Content fundamentals (voice)

- Short, kind invitations: "Uma nova fase.", "Mais tempo para você", "Olá, que bom ter você aqui!".
- Activities are concrete and doable, with their cost stated up front: "Mapa da casa da infância", "Turista no próprio bairro", meta like `10–15 min · papel e caneta`, "Energia baixa", "Em casa".
- Questions as doors: "Quem sou eu agora?".
- Status copy says what happened and what to do: "Guardado. A atividade está em Salvos." / "Não foi possível salvar agora. Tente de novo em instantes."
- Sample copy comes from the spec's activity seeds.

## Visual foundations

### Logo

| File | Ink | Use |
|---|---|---|
| `logo-lockup.png` | ink | On `offWhite` or `sand` grounds |
| `logo-lockup-light.png` | offWhite | On `wine` |
| `logo-mark.png` | ink | Compact spaces |

240 pt wide on the welcome screen, 176 pt in headers. Clear space of at least the height of the "N" on every side, never under 16 pt. Never retype the wordmark in a font, stretch it or add effects. Only `ink` #222222 or `offWhite` #F3F0EA. A vector SVG of the logo is still open.

### Color

| Group | Tokens |
|---|---|
| Ground | `offWhite` app background · `paper` cards, search, rows · `linen` neutral tile · `sand` chips, featured ground |
| Tints | `rose` highlighted tile, badges · `tan` warm tile · `hairline` divider · `border` input outline |
| Text | `ink` headlines · `stone` body · `ash` captions, inactive tabs · `charcoal` dark chip |
| Accents | `wine` primary action · `wineDeep` pressed · `wineBright` emphasis icon · `sun` illustration only |
| Status | `moss` success · `brick` error · `ochre` warning |

Contrast, as measured in the identity:

| Pair | Ratio | Use |
|---|---|---|
| `ink` on `offWhite` | 13.99 | any text |
| `stone` on `paper` | 6.35 | body text |
| `ash` on `offWhite` | 4.97 | captions, tabs |
| `offWhite` on `wine` | 10.71 | button label |
| `offWhite` on `charcoal` | 7.62 | chip |
| `ink` on `rose` | 11.58 | badges |
| `border` on `paper` | 3.55 | input outline |
| `stone` on `sand` | 4.25 | never: use `ink` on `sand` |
| `ash` on `sand` | 3.54 | never |

### Typography

Three voices: **Cormorant Garamond** 500/600 for headlines, titles and buttons; **Lora** 400/500 for paragraphs and steps; **Inter** 400/500/600 for labels, chips and tabs. Sizes follow the phone's text-size setting. Cormorant's small x-height is why its sizes sit above a typical serif's; check them on a real iPhone before locking them in.

### Space and shape

A 4-point rhythm. Gutter 24 pt (16 below 360-pt width); 32 between sections, 16 from a title to its content, 12 between cards. Touch targets at least 48 pt; buttons 56; fields 52. Radii: 8 small, 12 tile, 16 card, 24 panel, pill for buttons, chips and search.

### Iconography

Phosphor, light weight; filled only for the active tab. Icons take `ink`, `ash` (inactive), `wine` (active or emphasis) or `offWhite` on wine.

## Components

Drawn at 1 pt = 1 px, the size they have on a 390-pt-wide phone: Button, Chip (with icon buttons), SearchCategories, ContentCard, ListRow, TabBar, StatusMessage.

## Still open before v1.0

- Logo as vector SVG.
- Layered collage assets for production.
- Dark mode.
- Type scale checked on a real iPhone.
- Confirm "spec wins" on conflicts C1–C12 (e.g. the tab says "Salvos" with a bookmark, following the spec).
- Social-post templates (feed, carousel, Reels cover) are not part of identity v0.1.
