# ENGINE — the tool engine contract (draft v0.1, 2026-11-02)

> Design goal: **few concepts, each doing one thing, freely combined.** The reference app grew
> a new special case for almost every tool: about 16 ad-hoc interaction shapes, flags kept in
> 3 places, answers keyed by display text, logic and content fused into server-sent code. We do
> the opposite. A tool is a validated document. The engine is the only code. Anything a tool
> cannot express is a missing engine concept to add deliberately, never a per-tool exception.

## 1 · Vocabulary (the whole model)

| Concept | One line |
|---|---|
| **Tool** | A versioned definition: what the patient goes through + what Mônica sees. Immutable once published. |
| **Step** | One screen. Either an `info` screen or one **question**. |
| **Question kind** | What the patient does on that screen. Exactly **5** kinds (§2). |
| **Modifier** | A way to reuse a question without a new kind. Exactly **3** (§3). |
| **Result block** | One piece of the summary. Exactly **6** (§4). |
| **Assignment** | One tool sent to one patient: link + status (§5). |
| **Response** | The patient's answers for an assignment, pinned to the tool version (§6). |

## 2 · Question kinds — 5, and only 5

| Kind | The patient… | Config | Answer shape |
|---|---|---|---|
| `choose` | picks option(s) | `options[]`, `min`, `max` (1/1 = single, else multi), `allow_other` | `option_id[]` (+ `other` text) |
| `write` | writes text | `size: short\|long`, `max_chars`, `placeholder` | `string` |
| `group` | places items into groups | `items[]`, `groups[]`, `require_all` | `{item_id: group_id}` |
| `order` | puts items in order | `items[]`, `top_n` (rank only the first N) | `item_id[]` |
| `distribute` | spreads N points across items | `items[]`, `total` | `{item_id: int}` summing to `total` |

Every option, item and group has a **stable `id`** plus a display `label`. Answers store ids,
never labels, so a label can be reworded without breaking anything.
Validation is declarative and derived from the config (`min`/`max`/`required`/`total`). The
UI uses it to guide, and the **server re-validates** against the pinned version. A disabled
button is not validation.

## 3 · Modifiers — 3, applied to any question

| Modifier | Does | Example |
|---|---|---|
| `for_each: <list>` | repeats the question once per item; answers keyed per item | 8 situations × "how do I talk to myself here?"; 7 weekdays × "how was the day?" |
| `when: <condition>` | shows the step only if a condition on earlier answers holds | free-text follow-up only for situations answered "harsh" |
| `options_from: <step>` | builds options/items from earlier answers | "of the people you placed close, who would you call first?" |

`for_each` also takes `layout: list | one_per_screen`, which is presentation only.
Conditions use one small expression form (`any`/`all`/`count` over answer ids), not code.

### How the 16 reference shapes collapse into ours

single / multi / chips → `choose` · per-item scale / per-item multi / week grid → `choose` +
`for_each` · buckets → `group` · ranking → `order` · split points → `distribute` · "add your
own" → `allow_other` · derived options → `options_from` · conditional + branching paths → `when`
· one-card-at-a-time → `for_each.layout` · redraw while answering → engine feature (result
blocks can preview live). **Nothing left over.**

## 4 · Result blocks — 6

| Block | Shows | Fed by |
|---|---|---|
| `tally` | descriptive counts ("4 of 8 situations…"), **never a score** | `choose` (+`for_each`) |
| `map` | each item coloured by its answer, with a legend | `choose` + `for_each`, `group` |
| `chart` | one of a **fixed** chart set: `bars` · `share` · `circles` · `scale` | `distribute`, `group`, `order`, `choose` |
| `quotes` | the patient's own words, beside the item they relate to | `write` |
| `reflection` | a closing paragraph written for this tool (static text) | — |
| `session_questions` | 2–4 questions to bring to the session | — |

Blocks may carry a `when`. A new kind of picture means adding a chart type to the engine,
reviewed once and available to every tool. There are no per-tool drawings.

## 5 · Assignment lifecycle

```
sent ──open──▶ opened ──answer──▶ in_progress ──finish──▶ completed
                                  │   ▲
                         pause ◀──┘   └── resume (same step)
                                  │
                       quick exit ▼
                               exited ──next open──▶ patient chooses:
                                                      keep → in_progress
                                                      discard → answers erased, starts fresh
Mônica may: revoke (link dies) · resend (same assignment, new link)
```

- **Pause.** Answers are saved on the server after every step, and pausing just closes the
  page. Reopening the link resumes at the saved step. Available on every tool, not a per-tool flag.
- **Quick exit** (on `sensitive` tools, as a button or the Esc key / double-tap) does these in order:
  1. Instantly replace the page with a neutral screen.
  2. `location.replace`, so Back doesn't return.
  3. Clear every device-side trace (storage, cache keys).
  4. Mark the assignment `exited` on the server.

  Answers stay on the server until the patient chooses keep or discard on the next open.
- **Sensitivity** lives in one place, the tool's `sensitivity: normal | sensitive`. Sensitive adds:
  - a gentle warning on the opening screen
  - a confirmation for Mônica before sending
  - the quick-exit control

## 6 · Data model (seed organ; per-product schema, RLS by `org_id`)

| Table | Key columns |
|---|---|
| `tool_definitions` | `id`, `org_id NULL` (null = shipped by us), `slug`, `version`, `status draft\|published\|retired`, `sensitivity`, `theme`, `definition jsonb` (validated), `clinician_guide jsonb` |
| `tool_assignments` | `id`, `org_id`, `client_id` (→ `clients` organ), `tool_id`, `tool_version`, `token_hash`, `status`, `sent_via`, `sent_at`, `opened_at`, `completed_at`, `revoked_at` |
| `tool_responses` | `assignment_id`, `answers jsonb` (ids only), `current_step`, `updated_at` |

- The link carries an opaque random token. Only its hash is stored, and it can be revoked.
- Results are rendered from `answers` + the pinned `version`, so old results always render exactly as they were.
- The patient side never receives other patients' data, Mônica's clinician guide, or any executable content.

## 7 · Surfaces

- **monica (Mônica):** catalog (search by theme / patient moment / duration) · tool page with the clinician guide · "try it" preview (saves nothing) · send from the patient record via monica's WhatsApp · patient record tab "Ferramentas" (status + results) · result view with private notes.
- **Entre sessões (patient, web, no login):** personal link → consent (first time) → tool runner → result → done. The diary lives in the same area later. The native app later consumes the same organ API.
- **Seed organ:** schema + validators (Pydantic), runner + renderers (5 question components, 6 block components), assignment/token service, WhatsApp send via the product's existing adapter.
