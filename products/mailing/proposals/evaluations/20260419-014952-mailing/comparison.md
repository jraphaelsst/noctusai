# Evaluation Comparison — Mailing `health.py` Proposal

**Date:** 2026-04-19
**Compared by:** claude-opus-4-7 (in-session, authored own version)
**Inputs:** `issues.json` — one induced compliance issue (mailing has its own `health.py`).

**Proposals under comparison:**
- `openai-gpt-4o-mini-20260419-015001-remove-custom-health-endpoint-in-mailing-product.md` — headless mode, OpenAI `gpt-4o-mini`, ~$0.001 / ~7 seconds / 1 API call
- `claude-opus-4-7-20260419-015135-remove-product-level-health.py-in-mailing-—-delega.md` — in-session, Claude Opus 4.7 with full conversation context, ~60 seconds of composition, $0 marginal (already in session)

---

## 1. Axis-by-axis honest comparison

### §1 Context

**OpenAI:** 1 sentence. "Compliance detector flagged a custom health endpoint. Framework provides one." Generic.

**Claude:** 5 sentences. Names the evaluation induction explicitly, then generalizes: "three of the four `check_seed_compliance` router checks target `health.py`, `notificacoes.py`, `team.py` — this pattern is a recurring violation category." Cites the detector's source file.

**Winner:** Claude, by a wide margin. This is the axis where session context pays. I know the induction story from our conversation; I know the detector's rules because I read `compliance.py` earlier. OpenAI knows only what the issue dict says.

### §2 Situation

**OpenAI:** 3 sentences. File path ✓, handler name ✓, notes "exists solely for compliance evaluation." Doesn't name the framework counterpart's path or explain mount-order ambiguity.

**Claude:** 6 sentences. Named file + line count + exact framework counterpart path (`seed/framework/backend/noctusai_seed/routers.py::health_router`), called out FastAPI mount-order ambiguity, added history (pre-seed-v3 habit).

**Winner:** Claude. The receiving agent can jump directly to both sides of the comparison from my text; from OpenAI's they'd have to discover the framework file themselves.

### §3.1 Linkage (the judgment section — load-bearing per the template)

**OpenAI:** 1 sentence. "Removing aligns with framework design, prevents redundancy."

**Claude:** 2 sentences. Cites CLAUDE.md §1 rules by name ("Seed first — always", "No quick fixes"). Explains the next-seed-evolution-break risk.

**Winner:** Claude. OpenAI's linkage is the kind of platitude the template warns against ("prevents redundancy" — no kidding); it doesn't actually record judgment, which is the whole point of this section.

### §3.2 Application instructions

**OpenAI:** 2 steps. "Delete the file. Ensure no references remain."

**Claude:** 6 steps. Diff-before-delete, delete, grep for imports, check `main.py` for explicit `include_router`, verify via `curl`, check product-level tests.

**Winner:** Claude — and this is the axis that matters most for quality assurance. An agent following OpenAI's 2-step playbook would delete without diffing, potentially erasing legitimate customization. They'd also miss the `main.py` `include_router` line, which can leave an `ImportError`.

### §3.3 Seed APIs

**OpenAI:** 1 entry. Correct.

**Claude:** 2 entries with file locations and mount-mechanism notes.

**Winner:** Claude (marginal — OpenAI's single entry is correct, just less navigable).

### §3.4 Risks — **the biggest divergence**

**OpenAI:** `"Low risk — additive change, no overwrite."`

This is **wrong**. Deleting a file is destructive, not additive. The template's own guidance explicitly says: *"Deleting files → 'Diff this product's `{{file}}` against `{{seed-counterpart}}` **before** deleting'"* and *"If destructive, say 'diff against seed first'"*. The model defaulted to the boilerplate low-risk phrasing despite the fix being a `rm`.

This is the kind of error that makes "keeper is observation-only" a **good** design — an auto-fix path following these instructions would have executed the destructive action without the safeguard.

**Claude:** Three risk categories named specifically — accreted custom logic masked by the default shape; FastAPI mount-order leaving `ImportError` after partial fix; infra-facing nature of `/api/health` (load balancers, uptime monitors) meaning off-hours deploys matter.

**Winner:** Claude, decisively. OpenAI's risk assessment is actively misleading. This is the axis where the gap matters most.

### §3.5 Alternatives

**OpenAI:** `N/A — the situation dictates the fix.`

**Claude:** 3 substantive alternatives each with a reasoned why-not (deprecation comment, extend framework health router, rename to `/api/mailing/health`).

**Winner:** Claude. OpenAI's N/A is accurate for the simple case, but the interesting alternative — *extend the framework if custom telemetry has accreted* — is a judgment call worth recording precisely because the diff in step 1 might surface it.

### §4 Effects

**OpenAI:** 1 bullet. "Removes redundant health check endpoint."

**Claude:** 4 bullets (behavior, risk profile, ergonomics, coverage).

**Winner:** Claude. OpenAI's single bullet restates the action as the effect — it's not effects analysis, it's description.

### §6 Related files

**OpenAI:** 1 entry.

**Claude:** 5 entries including the framework counterpart, the factory, the product `main.py`, and the detector that flagged it (useful for the receiving agent who may also want to propose detector improvements).

**Winner:** Claude.

---

## 2. Overall verdict

**For in-session review during active development: Claude wins by a wide margin.**

The delta isn't just verbosity — it's three substantive errors OpenAI would lead a receiving agent into:

1. **Miscategorized risk** ("Low risk" on a destructive op) — actively dangerous for an auto-apply flow.
2. **Underspecified application steps** (no diff, no grep, no mount-order check).
3. **Treating the detector's summary as ground truth** — OpenAI has no model of "this detector could be wrong."

Those three together mean OpenAI's proposal requires a human reviewer to catch the gaps before acting. Claude's can be acted on more directly because the gaps are already closed in the text.

**For headless / CI / cron use: OpenAI is still a legitimate choice, with caveats.**

- At $0.001/call and 7s latency, it's basically free.
- An OpenAI proposal is better than no proposal at all — it still surfaces the finding.
- A triage human must read every proposal anyway; they'll catch the missing diff-before-delete guidance.
- **Hard constraint:** if the headless path ever gets wired to auto-apply accepted proposals, OpenAI's output cannot be trusted. Keep keeper observation-only regardless of authoring path.

**For the protocol the user just defined (agent-primary, headless fallback): the right call.**

The fallback is valid *as a fallback*. When an agent is in-session, it should always author — the context, the risk-calibration, and the application rigor are all noticeably better. When nobody is in-session (CI, cron), OpenAI gpt-4o-mini is a reasonable net below which no proposal shouldn't fall.

---

## 3. What this evaluation teaches us about the tooling

1. **The risk-classification instruction in the prompt is load-bearing.** OpenAI's default-to-"Low risk" miss suggests the system prompt should contain an explicit decision tree: *"If `application_steps` contains a `delete`, `rm`, mass-replacement, or schema-drop verb, `risks` MUST start with 'diff before'."* Consider adding this to `ai_brain.review_compliance_issue`'s prompt.
2. **The template's §3.1 Linkage is the weak point for LLM filling.** LLMs default to restating the fix as the linkage. A better prompt might require linkage to *name a specific rule from CLAUDE.md* being violated — forces the model to reason about constraints, not platitudes.
3. **Effects section benefits from required dimensions.** OpenAI's 1-bullet effects suggests the prompt should require each of `Behavior | Risk profile | Ergonomics | Coverage` to be addressed (or explicitly `unchanged`). Currently it's optional.
4. **Alternatives section gets padded to N/A.** Making alternatives required with at least one entry (even if paired with a rejection) would surface judgment that's currently skipped.

These would land as separate proposals (source: `keeper-eval-2026-04-19`) filed via `noctusai_file_proposal`.

---

## 4. Recommended disposition

- **Accept Claude's proposal.** It's the one a receiving agent can act on without secondary research.
- **Reject OpenAI's proposal, reason:** "Superseded by agent-authored version in same eval folder. Missed the destructive-fix risk classification; application steps too thin to be safely actionable."
- **Keep both files** as the eval artifact — don't delete. Future agents comparing authoring paths inherit this as a reference case.
- **The improvements in §3 above** (risk decision tree in prompt, required linkage-to-rule, required effect dimensions, required alternative) should be filed as four separate proposals against `mcp/noctusai/tools/ai_brain.py::review_compliance_issue` — not rolled into this comparison doc.
