# Owner questionnaire: never assume, interview until the context is complete

> Procedure: skill `noc-questionnaire` (v2.0.0). This doc holds the WHY and the shape.
> Born 2026-11-03; replaced 2026-11-09 by the never-assume interview (owner rules of
> 2026-11-07 and 2026-11-09).

## 1 · Why

An agent that fills gaps with defaults builds the wrong thing quietly. The owner's time is
spent deliberately, up front, to buy a complete context; only then is the plan written and
the owner says "go". Never infer, guess, assume or act on doubt.

## 2 · What is asked, what is researched

| Kind | Handling |
|---|---|
| Verifiable fact (code, memory, KB, catalog, public docs) | researched, shown as a fact; never asked |
| Decision, preference, scope, meaning, priority, taste, money, prod exposure | always asked |
| Owner's stated assumption that research contradicts | corrected with the source, then confirmed |

Research runs first (background, primary sources) so questions carry verified context.

## 3 · The interview shape

`AskUserQuestion`: 2-4 options (auto "Other" = free text), up to 4 questions per call, as many
rounds as needed. Options are self-contained, recommended first, each naming its consequence
and its strongest argument against. Ambiguous, compound or contradicting answers are restated
and confirmed next round; an override names the decision it replaced. Unanswered: work only on
what does not depend on it, and write an owner reminder at session end (silence is never
consent). The spec is a live Claude Doc (How to read / Decisions table / Research facts /
topic sections with `- [ ]` open items / Plan), copied to `project-history/<slug>/SPEC.md` at
close. Close = completeness check, Plan, owner "go". Each interview ends with a 3-line method
note via `noctus.dev.auto_improvement_log`.

**Council before a recommendation** (owner yes, 2026-11-09). The asking agent is a model that
leans toward agreeing with the owner and with its own first idea, so a bare `(Recommended)`
label hides the case against it. Before recommending, the agent runs five lenses on every
option — contrarian, first principles, expansionist, outsider, executor — and each option
then states its strongest argument against in one clause, the recommended one included.
Inside one session this is a single-chat council (one model, one context): it surfaces
counter-arguments but is not independent review, and the agent says so rather than hiding it.
The same council is step 4 of `noc-iterate` (before a refine), so owner decisions and loop
refinements are argued the same way.

For high-stakes questions the independent council runs first: skill `noc-council`
(`KB § PATTERNS/common/council.md`, stage `owner_question`).

## 4 · Channels and durability

Local session → `AskUserQuestion`; away → WhatsApp via `noctus.dev.notify` (owner's own
number only), reply read back via WAHA; unanswered at session end → owner reminder in
`MEMORY-reminders.md`. Durable answers land in memory (dated) or the accept-with-rationale
register — a decision that lives only in a chat transcript is a decision we will ask again.

## 5 · Superseded (v1, 2026-11-03)

v1 minimized questions: it dropped any question a default could answer ("decide and state the
assumption"), limited asks to money/prod/delete/wording/priority/taste, and carried a
"default-on-silence" rule. Replaced because acting on a default or on silence is assuming, and
the owner prefers a longer interview to a wrong build. Kept from v1: the council, the channels,
verify-before-asking, batching, durable recording.
