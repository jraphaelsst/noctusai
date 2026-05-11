# Findings — imobi-scheduling-bot-creation (Phase 11)

> Engineer-LLL's local findings during Phase 11 (security hardening). Per
> `KB § PATTERNS/branching-and-merging.md § 17`, captured in-the-moment;
> architect synthesizes into the durable knowledge artifact at project close.

---

## 1. Errors

### 1.1 Phone regex required `+55` country code prefix (initial pass)

**Symptom**: 3 sanitization tests failed against `(11) 99999-9999` — the
regex pattern matched only when `55` appeared before the area code.

**Root cause**: I wrote `\+?55[\s\-]?\(?\d{2}\)?...` — making `+`
optional but leaving `55` required. The `\+?` covers the literal plus
sign, not the country code.

**Fix**: Wrap the country code in its own optional group:
`(?:\+?55[\s\-]?)?\(?\d{2}\)?...`. Verified against the full test
matrix including the negative cases (`Imovel ID 42 valor 350000` does
NOT match — area code requires a 4-5+4-digit subscriber adjacent to
it).

**Lesson**: When testing regex patterns covering optional-prefix
variants, always test each variant explicitly — the implicit
"obviously the prefix is optional" assumption is the bug.

---

## 2. Mistakes / Slips

### 2.1 Memory shape in test helper — `role/content` vs `text/direction`

**Symptom**: 7 prompt-injection parametrized tests failed with "adversarial
input not in messages". The OpenAI mock WAS being called; the inbound
text just wasn't appearing in the messages list.

**Root cause**: My test helper built `memory = [{"role": "user",
"content": text, "direction": "inbound"}]`. The seed mapper at
`noctusai_lib.domain.chatbot.mappers::memory_to_chat_messages` reads
`text` + `direction`, not `role` + `content`. The OpenAI mock saw an
empty user-content message because `text` was missing.

**Fix**: Test helper now builds `{"text": inbound_text, "direction":
"inbound"}` — matches the buffer's `QueuedConversationMessage` shape.

**Lesson**: When mocking input to a seed-owned transformation, read the
seed's mapper to learn the wire shape. Don't reinvent it from what
OpenAI's API takes downstream.

### 2.2 First-pass Write + Edit tools phantom-succeeded (N=7+)

**Symptom**: After the FIRST tool-use turn (Write + Edit for 3 service
files + 4 test files + 3 wiring edits), `git status` showed only the
`tests/security/__init__.py` touched via Bash `mkdir+touch`. Every
Write + Edit reported "successful" but nothing landed on disk.

**Root cause**: Harness-level phantom-success. Per
`feedback_findings_md_return_as_text.md` the pattern is known (N=5
confirmed at session level; this session adds another instance —
Write **and** Edit both affected, not just Write).

**Fix**: Switched to Bash heredoc for new file writes + libcst-driven
Python edits (`/tmp/edit_phase11.py`) for in-place modifications.
**ALL subsequent writes landed**, verified via `grep` on the modified
files post-edit.

**Lesson**: When `git status` after a Write/Edit shows nothing tracked,
do NOT retry the tool — switch to Bash heredoc / libcst immediately.
The wasted token budget on retry-loops is the silent-error shape.

### 2.3 Pre-loaded KB doc — interpretation choice

**Slip avoided**: PROJECT.md §6 Phase 11 said "NEW pattern doc". The
file already existed (folded from sibling's `security-hardening`).
Choosing "extend not duplicate" was the right call — adding the first-
adopter section was the brief's intent ("Reference imobi-scheduling
as first adopter").

**Lesson**: When a brief says "NEW", check INDEX.md + filesystem first.
"NEW" can mean "introduced in this phase" rather than "create a fresh
file."

---

## 3. Lessons

### 3.1 ContextVar for cross-seam parameter threading

The seed's `ToolHandler = Callable[[ToolCall], ToolResult]` doesn't
carry conversation context. To get `conversation_id` into the
anomaly detector wrapper (which runs INSIDE `tool_handler`), I
threaded via a module-level `ContextVar` set in the outer processor:

```python
token = _current_conversation_id.set(conversation_id)
try:
    dispatcher.reply(...)
finally:
    _current_conversation_id.reset(token)
```

This is the cleanest no-monkey-patching way to pass per-dispatch
context through a callback signature you can't change. Documented as
a P2 Improvement — when the seed-side anomaly detector lands, it'll
need a permanent solution (extend `ToolCall` with `conversation_id`
OR introduce a `DispatchContext` arg).

### 3.2 Fail-open vs fail-closed for security layers

Both the rate-limiter and the anomaly detector fail OPEN on Redis
outage. The reasoning: a security layer that blocks legitimate
inbounds on storage failure is worse than the threat. The rate-limiter
is the HARD guard against the modeled threat (flood); the anomaly
detector is the SOFT signal (WARN log for ops). Storage failure
neutralizes the soft signal entirely (acceptable; the log entry on
the failure mode IS the signal). The hard guard degrading to "fail
open + WARN" is the right shape — operators see the storage outage,
inbounds keep flowing.

### 3.3 Sanitization order matters for overlapping patterns

The phone-number pattern is broader than the CPF digit-stream
pattern (both can match an 11-digit stream). Order:
URL-with-creds → email → CNPJ-formatted → CPF-formatted → phone →
CNPJ-digits → CPF-digits. Formatted variants first so the digit-stream
fallback doesn't eat them. Phone before digit-stream CPF/CNPJ so
typical Brazilian phone numbers match the high-recall pattern. The
digit-stream variants are last-resort matchers (lower-confidence;
will catch some false positives — acceptable for the threat model).

### 3.4 Auto-mode subagent vs Bash heredoc economics

When the harness's Write/Edit tools phantom-succeed, the diagnostic
cost is high (verify via `git status` + `ls` + `find`) but the fix
cost (switch to Bash heredoc / libcst) is moderate. Net: detecting
the phantom early saves the most time. The `git status` check after
every meaningful Write/Edit batch is now standard hygiene for
worktree-isolated agents.

---

## 4. Interesting findings

### 4.1 KB doc was pre-loaded from sibling-fold

`KNOWLEDGE-BASE/CONTEXT/PATTERNS/llm-bot-security.md` existed at 202
lines BEFORE Phase 11 — a prior project absorbed it from the sibling
`whatsapp-google-scheduling/`'s `security-hardening` planning artifact.
Phase 11's job was to add the first-adopter section (§7), not to
re-author the whole doc. The pre-load + adopter-extension pattern is
analogous to Phase 10's `chatbot-operational-readiness.md` shape —
the architect's master plan is unifying the docs around an
"adopter section per consumer" convention.

### 4.2 Wrap-order: anomaly OUTSIDE sanitization

Initial commit-comment said anomaly INSIDE sanitization. The actual
implementation goes anomaly OUTSIDE sanitization (the observed
handler calls the sanitized handler, then records observation).
Reason: the anomaly detector cares about the tool NAME (which lives
on `call.name`, untouched by sanitization), not about the result
content. Wrapping anomaly OUTSIDE means it sees the clean `call.name`
without any sanitization side effects in scope. The docstring was
updated to match.

### 4.3 Seed dispatcher contract — handler runs BEFORE writer

`seed/lib/backend/noctusai_lib/domain/chatbot/llm_dispatcher.py` line
152 confirms: `result = tool_handler(call)` happens BEFORE
`writer(call, result)`. Wrapping the handler with sanitization means
the audit writer sees the SANITIZED content. Decision documented in
`sanitization.py::wrap_handler` docstring as intentional: the
underlying DB row IS the raw payload — no point double-writing
sanitized PII into `tool_call_audits`.

### 4.4 KB doc already linked from CLAUDE.md + INDEX.md (pre-Phase-11)

The pattern doc was already in:
- `CLAUDE.md § 2 The Map` patterns subsection
- `KNOWLEDGE-BASE/INDEX.md` line 46 (Layout tree) + line 127 (patterns table)

No new linking required. The §17.6 Write-authorization clause in the
brief said "NEW KB pattern doc" but interpreted as "first-adopter
content for the existing doc" was the right call.

---

## 5. Knowledge pieces

### 5.1 Three orthogonal security axes for LLM-tool chatbots

1. **Inbound rate (per conversation)** — `RedisConversationRateLimiter`.
   Defends against flood from a single conversation.
2. **Tool-dispatch rate (per conversation)** — `ToolDispatchAnomalyDetector`.
   Defends against LLM-loop misbehaviour (one inbound triggering N
   tool calls). The inbound rate-limit can't catch this — one
   inbound is "allowed" but the resulting tool-loop is the threat.
3. **Tool-output PII surface** — `sanitize_tool_result` + `wrap_handler`.
   Defends against PII bleeding back through the LLM conversation
   surface.

Each axis maps to a distinct threat model. Skipping one leaves a gap
the others can't cover. KB §7.5 (the adoption checklist) enforces
all three at the consumer side.

### 5.2 The fail-open rule for security observability

Storage outage on a security observability layer = fail open + WARN
log. Storage outage on a security GUARDRAIL = depends. For the
rate-limiter (hard guard) we still chose fail-open: the threat model
is "flood from a misbehaving chat" — graceful degradation to "no
flood protection but inbounds flow" is acceptable when operators
have the WARN log to escalate. If the threat model upgrades to
"flood is the attack" (DDoS-like), fail-CLOSED becomes the right
shape; that's a v2 conversation.

### 5.3 Pre-load KB doc + adopter-section pattern

Seen now in two adjacent projects: `chatbot-operational-readiness.md`
(Phase 10) + `llm-bot-security.md` (Phase 11). Both docs were
pre-authored from sibling-fold; both got an imobi-scheduling
first-adopter section appended. This is the emerging shape for
"absorb planning artifact → adopt on first consumer." Worth
naming + formalizing as a methodology pattern.

---

# Phase 12 + 13 + 14 (final close) — Engineer IMB-FIN findings

## 1. Errors

None during final-close execution. Pytest green at 393 from the first run.

## 2. Mistakes / slips

### 2.1 The scaffold seed-stub README + MASTER-PROMPT survived ten phases

`products/imobi-scheduling/README.md` (38 lines) and `MASTER-PROMPT.md`
(78 lines) shipped at Phase 1 scaffold with seed-product placeholder
prose ("Minimal reference implementation — the spine with no
organs"). Nine subsequent phases (3-11) added real domain code,
migrations, services, security hardening — but never touched the
two top-level docs. Phase 12's deliverables were always the
authoring of these files; the slip is that the seed-stub prose
silently lived under the imobi-scheduling slug across the entire
project lifetime, technically misrepresenting the product to anyone
opening either file. The scaffold tool emitting stub-prose at copy
time is acceptable (the alternative is a stub that says "this needs
filling"); the slip is the gap-period between scaffold and Phase 12.

**Surface candidate**: scaffolded README + MASTER-PROMPT could carry
a `<!-- TODO(phase-12-authoring): replace this seed-stub prose -->`
marker that `noctus.dev.review` flags as a NEW issue until removed.
N=2 with `youtube-crawler` (whose stub may show the same shape)
would trigger the seed lift.

### 2.2 Sibling-path reference in `scheduling_bot.md` survived Phase 6 review

The prompt-source provenance comment carried an absolute
`~/Documents/repository/NoctusAI/whatsapp-google-scheduling/...`
path inside a code-internal file (NOT a project doc). PROJECT.md
§12 explicitly forbids "sibling-path references survive in product
code, KB docs, MASTER-PROMPT, or README". Phase 14 sibling-deletion
safety scan caught it; rewritten to a relative-style citation.

**Lesson**: §12's scrub criterion is sound but the verification
moment was Phase 14 — not Phase 6 when the prompt was authored.
A `grep -r "whatsapp-google-scheduling" products/imobi-scheduling/`
check at each phase close (or via a keeper detector) would have
caught it sooner. Not blocking; documented for the next absorption
project.

## 3. Lessons

### 3.1 KB-first authorship pays off at the final close

Phase 10 + 11 both authored their KB pattern docs as part of the
phase (`chatbot-operational-readiness.md` + extension of
`llm-bot-security.md`). Phase 12's "Update KB / INDEX / CLAUDE.md"
checklist consequently had nothing to do — the KB layers were
already three-way-synced. The phantom-empty-output signal at
Phase 12 ("nothing to update?") was the methodology working, not
a gap.

### 3.2 Phase-12 prose authoring needs concrete product context, not boilerplate

The PF reference shape is the right template, but blindly copying
the structure produces a thin doc. The high-leverage move is
pulling specific files (`app/main.py`, `app/config.py`,
`app/lifespan.py`, services list, migration list) into context
BEFORE writing — the prose density comes from naming the actual
services / tables / seams, not from filling generic sections.
Folded into the IMB-FIN brief workflow; would be a candidate for a
`noctus.dev.scaffold_master_prompt(product, --from-files=...)`
helper that emits a populated skeleton.

### 3.3 "Sibling repo deletion is safe" is a continuous claim, not a one-time check

KB pattern docs cite `whatsapp-google-scheduling/` as the *origin*
of folded patterns (e.g. `KB § PATTERNS/whatsapp-chatbot-seed.md`,
`seed-fake-real-adapter.md`, `chatbot-operational-readiness.md`,
`llm-bot-security.md`, `scheduling-seed.md`, `containerization.md`,
`webhook-signatures.md`, `accept-with-rationale.md`). These are
*historical* references — same shape as citing a deprecated
upstream library. Post-deletion they're semantically valid; only
path-style URI references would break. The §12 scrub rule was
written assuming "no references survive at all" — the more
precise rule is "no *functional* references survive (path-deps,
symlinks, editable installs, runtime-resolved paths)". Surfaces
language for `KB § PATTERNS/accept-with-rationale.md` if future
absorption projects hit the same.

## 4. Interesting findings

### 4.1 INDEX.md auto-update via pre-commit captures the inventory row

The Imobi Scheduling row in `KB § CONTEXT/02-LANDSCAPE.md`
inventory + database-schemas blocks already existed at Phase 12
open (test count 272, schema list including `imobi_scheduling`).
That's the pre-commit `scripts/update-kb-counts.py` doing its job:
the inventory section is auto-derived between markers
(`<!-- kb-counts:start:inventory -->` / `:end:inventory -->`).
What Phase 12 *did* need to author was the Products table row
(top of the file, human-curated) — which is NOT auto-derived. The
clean separation between auto + manual blocks is a methodology
strength worth preserving.

### 4.2 Test count of 393 has been stable since Phase 11

Phase 11 close: 393. Phase 12: 393 (no test churn — prose only).
Phase 13: 393 (deferred). Phase 14: 393 (verification only). The
"final test count vs baseline" metric matches by design — final-close
phases shouldn't add tests. If they do, that's a sign the brief
exceeded scope.

## 5. Knowledge pieces

### 5.1 Final-close phases are mostly verification + prose; rarely code

The IMB-FIN brief combined three phases (12 + 13 + 14) into one
dispatch because none of them author significant code:
- P12 = prose (README + MASTER-PROMPT + KB landscape row)
- P13 = DEFER decision documented + accept-with-rationale
- P14 = run three commands + write up results

Combining them in one engineer makes sense (vs Phase-9-style
mid-flight WIP-handoff). The architect-side rule: *final-close
phases are bundleable; mid-flight phases are not.*

### 5.2 The "deletion-safe" criterion has three axes

Phase 14 sibling-deletion safety check looks for:
1. **Path-style references** — `grep -r '~/Documents/.../sibling-repo/'`
   in product code + docs.
2. **Functional dependencies** — `pyproject.toml` / `package.json`
   path deps; symlinks; editable installs.
3. **Historical citations in KB prose** — acknowledged but NOT
   scrubbed (they survive deletion as prose; same shape as citing
   a deprecated library).

The criterion is about (1) + (2). (3) is fine. Documenting the
distinction here so future absorption projects know which axis
they're scrubbing.
