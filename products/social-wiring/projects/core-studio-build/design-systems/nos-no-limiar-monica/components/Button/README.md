# Button

Pill buttons: one wine primary per screen, a quiet offWhite secondary, and two text-only actions.

## Variants
- **Primary** — `wine` ground, `offWhite` label (10.71:1), height `button-h` (56), side padding 28, `radius-pill`, label in the `cardTitle` style (Cormorant 600, 20/24), optional trailing arrow. Pressed: `wineDeep`. Full width up to 360 on welcome screens.
- **Secondary** — `offWhite` ground, `ink` label, height 44, side padding `space-20`, Cormorant 600 18.
- **Link** — Inter 500 15, `ink`, underlined (offset 3). E.g. "Já tenho uma conta".
- **Text arrow** — Inter 500 15, `stone`, ends with "→". E.g. "Ver todos →".

## Rules
- Wine means act: never use the primary style for decoration or a second primary on the same screen.
- Focus: 3px `wine` outline, offset 3.
- Labels are verbs: "Começar agora", "Ler agora →".
