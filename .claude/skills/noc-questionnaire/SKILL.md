---
name: noc-questionnaire
description: Use whenever a decision, scope, preference or meaning is not 100% known — triggers "act as a questionnaire", "questionnaire", "question me", "question me thoroughly", "interview me", "me entreviste", "quero que você me pergunte", "never assume", "don't assume", "ask me along the way", "clarify with me", "confirm with me", "confirm via WhatsApp", "pergunte-me", "me pergunte", "check with the owner". Never-assume interview: research first, ask every unknown in AskUserQuestion rounds, keep a live Claude Doc spec, then plan and wait for "go".
version: 2.1.0
---

# noc-questionnaire — never assume, interview until the context is complete

Owner rule (2026-11-07, 2026-11-09): never infer, guess, assume or act on doubt. Every
unknown becomes a question; the owner's time is spent deliberately to buy a complete context.

## Workflow

1. **Open the live spec.** Create a Claude Doc (claude.ai Docs connector) FIRST, with a
   pending section per area: How to read / Decisions / Research facts / one section per topic
   (open items as `- [ ]` tasks) / Plan. Fill one section per call while the owner watches.
   Decisions = a table (date, decision, chosen option).
2. **Research before asking.** Dispatch background research (primary/reliable sources) and
   check code, memory, KB, catalog. Verifiable facts are shown as facts in the doc/question,
   never asked. If the owner's stated assumption is wrong, correct it with the source.
3. **Ask every decision, preference, scope and meaning** via `AskUserQuestion`: 2-4 options
   (auto "Other" = free text), up to 4 questions per call, as many rounds as needed.
   - Options self-contained, recommended first labelled `(Recommended)`; each names its
     consequence AND its strongest argument against.
   - **Council** (five lenses per option: contrarian, first principles, expansionist,
     outsider, executor). Single-chat version, say so once; for high-stakes questions run
     the independent `noc-council` skill first (stage `owner_question`).
4. **Ambiguous / compound / contradicting answer** → restate the interpretation and confirm
   it next round; never resolve silently. A new answer overriding an earlier one: say which
   decision it replaced (and update the Decisions table).
5. **Channel.** In session → `AskUserQuestion`. Owner away → `noctus.dev.notify
   channels=["whatsapp"]` (dry-run, then `confirm=True`), format below; read the reply with
   `waha_message_list`. Unanswered → keep working ONLY on what does not depend on it; at
   session end write an owner reminder (`MEMORY-reminders.md` row + `reminder_<slug>.md`).
6. **Record.** Durable decisions → memory (dated) in the matching `MEMORY-<topic>.md`;
   accepted divergence → `KB § PATTERNS/common/accept-with-rationale.md`.
7. **Close.** Completeness check: every open item closed or explicitly parked by the owner.
   Then write the Plan, present it ready to go, and wait for the owner's "go". Copy the doc to
   `project-history/<slug>/SPEC.md` on the repo branch.
8. **Learn.** Append a 3-line method note (question shapes that worked / failed) with
   `noctus.dev.auto_improvement_log` (scope, kind, target, description).

## WhatsApp format (pt-BR, one message per round)

```
❓ <assunto em ≤6 palavras>
1) <pergunta>  → A) <opção recomendada> ✅  B) <opção>
2) <pergunta>  → Sim / Não
Responda ex.: "1A 2Sim".
```

## PEER MODE — the asked party is another agent/session, not the owner

Decision 2026-11-10 (`project-history/assistant-chatbot/queue-lifecycle-decision.md`). The steward uses this when it needs information about an ejected entry. The method stays (research first, reduce to the simplest decision, batch, record); the owner-interview machinery does not apply.

- **One batched question,** reduced to the simplest decision (e.g. "already fixing? yes/no; if no, which of A/B?"), with the evidence (run URL, file:line) attached so no research is asked of the peer.
- **Channel:** an inbox `needs_info` record addressed to the requester's ROLE (role registry, resolved at send time; owner fallback when the role has no live session), TTL one CI cycle (~25 min). The answer is read with `release_steward action=mine` and recorded durably (inbox + steward memory file). Silence at TTL is an answer too: the steward proceeds to the rescue.
- **No Claude Doc, no `AskUserQuestion`, no waiting for "go"**; keep working on other queue items meanwhile.
- **Go-live:** the inbox `needs_info`/TTL fields ship with build 4 (noctusai-b5). Until then, INTERIM: `SendMessage` to the role's current session + the steward inbox notes field, labelled interim.
- Rule it serves: `KB § PATTERNS/devops/release-steward.md` § 7a.

## Guardrails
- Silence is not consent: never act on an unanswered question.
- Never ask what you can verify; never ask "should I proceed?" before the Plan is done.
- Never ask the same decision twice: `memory_search` first.
- WhatsApp only to the owner's own number, never a customer/lead chat.
- A destructive or prod action approved on WhatsApp: quote the literal chosen option in the log.

## Depth
`KB § PATTERNS/common/owner-questionnaire.md` · `noc-council` · `noc-triage` · `KB § PATTERNS/devops/prod-exposure-consent.md`.
