# ENGINE — the tool engine contract (draft v0.2, 2026-11-02)

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


## 5 · Who is who (identity — DECISIONS D9/D10)

| Actor | Account | Reaches | Through |
|---|---|---|---|
| **Clinician** (Mônica) | noc user, **member** of her org, clinician role | catalog, editor, every assignment + result of her org | Nós no Limiar staff UI |
| **Staff** (future: secretary…) | noc user, org member, non-clinician role | assignment **status** only, never answers | Nós no Limiar staff UI |
| **Patient** | noc user, **not** an org member; linked to one `clients` row per practice | only their own linked record's assignments, results, consents | patient area (name TBD) |

The patient link is the seed organ **`client-portal`**: an invite issues a one-time token, then
account creation or sign-in, then `client_portal_links (org_id, client_id, user_id)`. Every
área do paciente (nome a definir) request resolves `user_id → (org_id, client_id)` server-side. A link from a
message never authorizes anything by itself.

## 6 · Assignment lifecycle

```
sent ──open (signed in)──▶ opened ──answer──▶ in_progress ──finish──▶ completed
                                              │   ▲
                                     pause ◀──┘   └── resume (same step)
                                              │
                                   quick exit ▼
                                           exited ──next sign-in──▶ patient chooses:
                                                                      keep → in_progress
                                                                      discard → answers DELETEd, fresh start
                                                     (no choice in 30 days → auto-discard)
idle/unopened 30 days → expired (answers deleted, metadata kept)
Mônica: revoke (closes it) · resend (same assignment, new notification)
```

- **Pause.** Answers are saved on the server after every step. Pausing just closes the page,
  and resume is at the saved step. Every tool has it.
- **Quick exit**, on every tool (button, or Esc key / double-tap), runs in order:
  1. Instant neutral screen.
  2. `sendBeacon` marks the assignment `exited`.
  3. The server responds with `Clear-Site-Data` and ends the session.
  4. `location.replace` to a neutral site.

  Exited answers are **hidden from the clinician** until the patient chooses keep. What we
  cannot erase (the WhatsApp message, notifications, keyboard learning, screenshots) is
  disclosed honestly in the consent text.
- **Sensitivity** has a single source, the tool's `sensitivity: normal | sensitive`.
  Sensitive adds the opening warning and the clinician's confirmation before sending.
- **The opening GET has no side effects** (preview crawlers must not mark `opened`). `opened`
  is set by an authenticated POST.

## 7 · Data model (seed organs; per-product schema; every table has `org_id`; service-role only + RLS)

| Table | Key columns |
|---|---|
| `tool_definitions` | `id`, `org_id NULL` (null = shipped by us), `slug`, `version`, `status draft\|published\|retired`, `sensitivity`, `theme`, `definition jsonb` (validated), `clinician_guide jsonb`, `created_by` |
| `tool_assignments` | `id`, `org_id`, `client_id`, `tool_id`, `tool_version`, `status`, `sent_via`, `sent_at`, `opened_at`, `last_activity_at`, `expires_at`, `exited_at`, `completed_at`, `revoked_at` |
| `tool_responses` | `assignment_id`, `org_id`, `answers` (choice ids **and** free text; app-level encrypted), `current_step`, `updated_at` |
| `tool_notes` | `assignment_id`, `org_id`, clinician private notes (encrypted) |
| `tool_consents` | `org_id`, `client_id`, `user_id`, `consent_version`, `accepted_at` |
| `tool_read_audit` | append-only: `org_id`, `actor_user_id`, `assignment_id`, `at` (never content) |
| `client_portal_links` *(organ `client-portal`)* | `org_id`, `client_id`, `user_id`, `invited_at`, `accepted_at`, `revoked_at` |

- Results render from `answers` + the pinned `tool_version`, so an old result always looks exactly as it did.
- Discard and patient deletion are real `DELETE`s, cascading through every table above.
- Logs never contain answers. The patient side never receives other patients' data, the clinician guide or any executable content.

## 8 · Surfaces

- **Nós no Limiar (clinician):**
  - catalog: search by theme / patient moment / duration
  - tool page with the clinician guide
  - **tool editor**: draft → preview → publish = new version
  - "try it" preview (saves nothing)
  - patient record: **Convidar para a área do paciente**, send a tool (WhatsApp/e-mail), tab "Ferramentas" (status + results), result view with private notes
- **área do paciente (nome a definir) (patient, web, signed in):** invite → account → consent (first time) → home (my tools, my results) → tool runner → result. The diary arrives in release 2. The native app later uses the same organ APIs.
- **Seed organs:**
  - `guided-tools`: schema + validators (Pydantic), runner + renderers (5 question components, 6 block components), editor, assignment service.
  - `client-portal`: invite, account link, external-user authorization, consent capture.
  - Sending goes through the product's existing WhatsApp / e-mail adapters.
