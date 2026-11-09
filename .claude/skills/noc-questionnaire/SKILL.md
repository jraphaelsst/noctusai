---
name: noc-questionnaire
description: Use BEFORE asking the owner anything — triggers "question me", "ask me along the way", "questionnaire", "clarify with me", "confirm with me", "confirm via WhatsApp", "pergunte-me", "me pergunte", "check with the owner", or any moment you are blocked on a decision that is the owner's to make. Reduces every ask to the simplest human decision, batches it, sends it on the right channel (local chat or WhatsApp), and records the answer durably.
version: 1.1.0
---

# noc-questionnaire — every owner ask is the simplest human decision

The owner's attention is the scarcest resource on the platform. A question is a cost you
charge them; this skill makes each one cheap to answer and impossible to lose.

## Workflow

1. **Filter — is it really theirs?** Drop the question if code, memory, the product catalog,
   a KB pattern or a sensible default answers it (`noctus.dev.memory_search`, `kb_search`).
   Then decide + say in one line what you assumed. Only these are the owner's: money, prod
   exposure, deleting something with no recovery path, customer-facing wording, priority
   between two goals, and taste.
2. **Reduce — to the simplest human decision.** Each surviving question must be answerable
   in ≤ 3 seconds without opening anything:
   - **Yes/No** if possible; else **pick one of 2–4**; free text only when nothing else fits.
   - **Recommended option first**, labelled `(Recommended)`.
   - Each option = what happens + its cost in one clause. No jargon the owner didn't use.
   - **Self-contained**: name the thing being decided inside the question (the owner may
     see only the dialog / the WhatsApp message).
   - **Default-on-silence** stated: "if no answer, I'll do X" — so silence never blocks.
   - **Council before you recommend** (any pick-one with a `(Recommended)` option). The agent
     tends to agree with the owner and with its own first idea, so run five lenses on EACH
     option first: contrarian (what breaks), first principles (is the premise right),
     expansionist (what bigger win is missed), outsider (would a newcomer get it), executor
     (what exactly changes now). Each option's description then carries its **strongest
     argument against** in one clause, the recommended one included. In one session this is
     the single-chat version (one model, one context); say so once, never hide the limit.
     The same council runs in `noc-iterate` step 4 before a refine.
3. **Batch** — ≤ 4 questions per round, highest-leverage first. Keep working on everything
   that does not depend on the answer (never idle on a question).
4. **Channel**
   - Owner is in the session → `AskUserQuestion` (one call, ≤ 4 questions).
   - Owner is away / asked for WhatsApp → `noctus.dev.notify channels=["whatsapp"]`
     (dry-run, then `confirm=True`) with the format below; read the reply with
     `waha_message_list phone=<owner>` on the next turn/wakeup.
   - Not answered by the end of the session → write an owner reminder
     (`MEMORY-reminders.md` row + `reminder_<slug>.md`), so it resurfaces next session.
5. **Record** — the answer is the asset:
   - A durable decision (shapes future work) → memory (`project`/`feedback` type, absolute
     date, the question + chosen option + why) in the matching `MEMORY-<topic>.md`.
   - A divergence accepted → `KB § PATTERNS/common/accept-with-rationale.md`.
   - A one-shot answer → just act; no paperwork.

## WhatsApp format (pt-BR, one message per round)

```
❓ <assunto em ≤6 palavras>
1) <pergunta>  → A) <opção recomendada> ✅  B) <opção>
2) <pergunta>  → Sim / Não
Responda ex.: "1A 2Sim". Sem resposta até <quando>: sigo com as recomendadas.
```

## Guardrails
- Never ask what you can verify. Never ask "should I proceed?" — proceed or name the risk.
- Never ask the same decision twice: `memory_search` the question first.
- A WhatsApp send is outward-facing — only to the owner's own number (the default
  `notification_recipients` row), never to a customer/lead chat.
- A destructive or prod action approved on WhatsApp still needs the literal option chosen in
  the reply quoted back in your log line (verdict-channel integrity).

## Depth
`KB § PATTERNS/common/owner-questionnaire.md` (why + the decision taxonomy) · `noc-triage`
(the F/R/A verdict the owner ratifies) · `KB § PATTERNS/devops/prod-exposure-consent.md`.
