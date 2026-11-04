# Owner questionnaire — the simplest human decision

> Procedure: skill `noc-questionnaire`. This doc holds the WHY and the taxonomy.
> Born 2026-11-03 (owner request: "reason on the simplest human decision and the simplest
> human decision shall be part of the questionnaire, so we have a clear pattern").

## 1 · Why

Agents asked the owner the wrong things in the wrong shape: open-ended questions that need
the owner to open files, "should I proceed?" confirmations, the same decision re-asked in a
later session, and questions that blocked all work while waiting. Each costs owner attention
— the one resource that does not scale with the fleet.

## 2 · Which decisions are the owner's (the only ones worth asking)

| Class | Example | Shape |
|---|---|---|
| Money | spend, pricing, a paid plan | pick-one with cost per option |
| Prod exposure | promote to `main`, register a surface | Yes/No (literal consent phrase) |
| Unrecoverable delete | data with no git/salvage path | Yes/No, naming what is lost |
| Customer-facing words | a template, a contract clause | pick-one of drafts |
| Priority | two goals compete for the same slot | pick-one, recommended first |
| Taste | visual / naming / tone | pick-one with preview |

Everything else (facts, conventions, recoverable actions, technical choices with a canonical
answer in the seed/KB) is the agent's — decide, state the assumption in one line, move on.

## 3 · The simplest-human-decision rule

A question is well-formed when the owner can answer it in ≤ 3 s without opening anything:
binary > pick-one (2–4, recommended first) > free text; self-contained; each option names its
consequence; a default-on-silence is stated so silence never blocks.

## 4 · Channels and durability

Local session → `AskUserQuestion`; away → WhatsApp via `noctus.dev.notify` (owner's own
number only), reply read back via WAHA; unanswered at session end → owner reminder in
`MEMORY-reminders.md`. Durable answers land in memory (dated) or the accept-with-rationale
register — a decision that lives only in a chat transcript is a decision we will ask again.
