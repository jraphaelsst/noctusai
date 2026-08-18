# lead-card-hub — reference screenshots

> Companion assets for `project-history/roadmaps/lead-card-hub-2026-08.md`.
> **Read the roadmap first** — it holds the 17 ratified decisions. This folder holds
> the pictures those decisions were made against.

## Why these files exist here

The roadmap's §4 says *"11 screenshots supplied 2026-08-07"* and then describes them in
prose. **The images themselves were never saved** — they lived only inside the session
transcript (`85891023-…​.jsonl`). A design record that points at evidence it does not hold
is one `/clear` away from being unverifiable, and the next agent to pick this up has to ask
the user to re-send them.

They were recovered from that transcript on **2026-08-18** and committed here so the
roadmap's UI claims stay checkable against the thing they describe.

## `trello-reference/` — the 11 supplied 2026-08-07

The explicit reference model for the card. Trello in **pt-BR**, dark theme.

| File | What it fixes about our design |
|---|---|
| `01-board-overview.jpeg` | Board/column layout; card faces in situ. Note the **colour strip** above the title on labelled cards, and the per-column card count. |
| `02-card-detail-two-pane.png` | **The core layout**: content pane left, *"Comentários e atividade"* pane right. Title + circular status control top-left; action row (`+ Adicionar` · Etiquetas · Datas · Checklist · Membros); `Descrição` section with an `Editar` affordance. |
| `03-card-detail-activity-pane.png` | The right pane in detail — comment composer (*"Escrever um comentário…"*), `Mostrar Detalhes` toggle, and system events rendered as first-class entries (*"X adicionou este cartão a <lista>"* + timestamp). This is **D9's one thread**. |
| `04-adicionar-popover.png` | The `+ Adicionar` popover — the card's extension menu: Etiquetas / Datas / Checklist / Membros / **Anexo**, each with a one-line explainer. |
| `05-etiquetas-popover-colorblind.png` | Labels: search box, colour swatches with optional text, per-label edit, *"Criar uma nova etiqueta"*, and *"Habilitar o modo compatível para usuários com daltonismo"* — the colour-blind mode **D6** inherits. |
| `06-datas-popover-recorrente-lembrete.png` | Dates: month calendar, **Data de início** + **Data de entrega** (date *and* time), **Recorrente**, and **Definir lembrete** (`1 dia antes`) with the note that reminders go to all members and followers. Our substrate has `follow_up_data` but **no reminder mechanism at all** — this shot is the spec for P3.2. |
| `07-adicionar-checklist.png` | Checklist creation — just a `Título`. Confirms checklists are user-created objects, not a fixed schema (**D11**'s ad-hoc half). |
| `08-membros-popover.png` | Members: search + *"Membros do Quadro"* list with avatars. Maps to corretor-responsável (**D10**), and is why corretores must become real users. |
| `09-card-with-label-due-anexos.png` | A **populated** card: `Etiquetas` chip row with a `+`, `Data Entrega` pill carrying a state badge (*"Entregar em breve"*), description with `Mostrar mais` collapse, then the `Anexos` section. |
| `10-anexos-and-multiple-checklists.png` | Attachments as a file list (type icon / thumbnail, name, *"Adicionado há…"*, open + per-file `…` menu) and **two checklists on one card**, each with its own `%` progress bar and `Adicionar um item`. Multiple checklists per card is a requirement, not an accident. |
| `11-card-face-badges.png` | **The card face** — the densest single spec here. Colour strip · title · due-date pill (yellow) · description glyph · attachment count (`📎 3`) · checklist progress (`☑ 0/6`). This is the badge row the roadmap's last Trello-map row calls *"build new"*. |

## `social-wiring-2026-08-09/` — our own app, 2026-08-09

Ten shots of Social Wiring taken two days later in the same initiative — the *before*
state the card work is measured against. Kept for the same reason: the roadmap argues
from what our UI does today, and that claim should be checkable.

## Provenance

- Recovered 2026-08-18 from `~/.claude/projects/-Users-rapha-…/85891023-b16f-4f79-a00e-6fe696e30ecd.jsonl`
  (the 2026-08-07 roadmap-authoring session; 21 images total — 11 at `19:01:49` = the Trello set,
  10 on 2026-08-09 = the app set).
- Filenames were assigned at recovery time to describe content; the transcript carried no names.
- Sequence within the Trello set is the order the user sent them.
