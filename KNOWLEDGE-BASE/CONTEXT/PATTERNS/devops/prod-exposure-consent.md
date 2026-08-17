# Prod-exposure consent — registering a product on the fleet IS the promotion decision

**What it is.** A pre-commit gate (`check_prod_exposure_consent`) + a status/authoring-assist tool (`noctus.dev.prod_consent`) that make it structurally impossible for a product's *first arrival* on a prod-exposure surface to land without an explicit consent record recording a decision **the user made**. The user may hand-author that record, or state the decision in-session and have an agent transcribe it — but the agent's transcription is refused unless it can point at the user's own words in the harness-written transcript (see § the agent-recorded path).

**Why.** Codified 2026-07-20 after the **orbity incident**: the product went prod-serving on 2026-06-03 — the same day it was scaffolded, six weeks before validation, every roadmap phase still ⬜, no consent decision anywhere. The architect traced the causal chain: commit `679d0838` "feat(deploy): onboard orbity to the prod fleet" registered orbity on THREE surfaces simultaneously:

- `deploy/fleet/docker-compose.prod.yml` (runs on the VPS fleet)
- `deploy/tunnel/ingress.yml` (public edge — `<slug>.noctusai.com`)
- `ALL_SLUGS` in `scripts/infra/build-and-push.sh` (GHCR artifact + `:latest`)

**Editing those three surfaces *IS* the production-promotion decision.** Everything downstream (bless → promote → CI build → `:latest` → fleet pull) is faithful automation of a declaration already made. There is **no later PER-PRODUCT gate** — once a slug is on `docker-compose.prod.yml`, it is publicly reachable the moment its next promoted build lands on `:latest` (`.github/workflows/build-and-push.yml` — 2026-07-20 fix: `:latest` now moves ONLY on a `prod`-ref build, never a bare `main` push, `KB § GUIDES/production-deploy.md § 2b`) — no human ever reviews "should THIS PRODUCT be public" again. THIS gate is what still fires: the `prod`-branch FF/PROD-PIN fix governs *which build* of already-consented code reaches production; it never asks "should this slug be registered at all."

## The fire boundary — a SET-DIFFERENCE on slugs, not a content diff

```
declared = slugs(WORKING TREE: compose.prod ∪ ingress ∪ ALL_SLUGS)
baseline = slugs(HEAD:         compose.prod ∪ ingress ∪ ALL_SLUGS)
new      = declared − baseline
if not new: return []          ← the universal, silent case
```

This is what keeps the gate from becoming noise. It fires **only** on a product's **first** arrival on any of the three surfaces:

| Case | Fires? |
|---|---|
| A product's slug appears for the first time on compose/ingress/ALL_SLUGS | ✅ yes |
| Any `products/<slug>/**` commit for an already-registered product | ❌ silent (surfaces unchanged) |
| Routine redeploy / bless / promote | ❌ silent (no edit to the three files) |
| Editing *inside* an existing service block (port / env / healthcheck / anchors) | ❌ silent (the slug *set* is unchanged) |
| Removing a slug (de-registration) | ❌ silent (never appears in `new`) |
| No `deploy/` directory (non-noc tree) | ❌ silent-skip |

## The consent record

For each slug in `new`, the gate requires `deploy/consent/<slug>.prod.yml` **present in `HEAD`** — i.e. committed in a **prior, isolated commit**, never the registration commit itself:

```yaml
consented_by: <the user's git-config user.email>
consented_on: <YYYY-MM-DD>
consent_ref: '<path/to/roadmap.md>#<milestone text, ALSO marked ✅ on that same line>'
dev_validated: true
```

**Quote `consent_ref`.** A milestone anchor normally reads `M5: prod promote`, so the value carries a `: `; unquoted, that is a YAML `ScannerError`, not a string. The template shipped unquoted from introduction until 2026-08-09, so a record authored faithfully from it failed at the *parse* step — which presents to the author as "the gate rejected my consent" rather than "your YAML is malformed". This is a false negative in the gate, never a reason to loosen who may author the record.

All four legs are validated (`_validate_prod_consent_record` in `compliance.py`):

1. **Non-empty** `consented_by` / `consented_on` / `consent_ref`.
2. `dev_validated: true` (literal boolean — the dev-first validation gate, `KB § GUIDES/production-deploy.md § 0.1`, must have already run).
3. `consent_ref` **resolves** to a `roadmap-tracking.md`-shaped milestone: `<relpath>#<anchor>` — the roadmap file must exist AND contain a line with BOTH the anchor substring AND a ✅ marker (`_resolve_roadmap_milestone`). E.g. a Milestones bullet gets annotated once reached: `- **M4: prod promote** — ... ✅ 2026-07-20`.
4. `consented_by` **matches** the current commit author's `git config user.email` (`_git_author_email`) — a mismatch means someone other than the person about to commit is claiming the consent, which is refused.

Any failure → **severity `high`**, hard-block at pre-commit, with a self-explanatory message (see below).

## Consent commits must be isolated

`_check_consent_commit_isolated` refuses a `deploy/consent/*.prod.yml` staged alongside **any other path** — independent of the set-difference, so it fires even when `new` is empty. This closes the "slip consent past review inside an unrelated diff" hole: the consent record must be its own commit, reviewable on its own, before the registration commit can even be attempted.

## Failure message contract

The message an agent sees is deliberately self-explanatory, not just a violation name — it states which three surfaces are affected, that registration **is** the promotion decision, that there is **no later gate**, and **both** routes to a valid record (user hand-authors, or user types the canonical phrase and an agent transcribes it). It ends with:

> An agent may RECORD the user's decision; it must never invent one.

Teaching the verified path matters as much as forbidding the shortcut: a gate that only says "no" to an agent with a job to finish is a gate that gets argued with. Pinned by `TestCheckProdExposureConsent::test_fires_high_on_orbity`, which asserts the boundary sentence, the canonical phrase, and the `action=challenge` breadcrumb all appear.

`noctus.dev.prod_consent action=request slug=<slug>` prints the exact same template + instructions on demand — and **refuses to write the file** (refuse-not-null, `KB § PATTERNS/common/gate-methodology-sync.md`).

## The agent-recorded path — verified transcription (2026-08-09)

**Why the original design failed in practice.** "The user must hand-author the file" assumes a human at a terminal. For a user who works entirely through agents, it is pure friction — and worse, it was **unverifiable**: nothing stopped an agent from writing those four lines and asserting the user approved. On 2026-08-09 that shortcut was attempted twice in one day, the second time accompanied by an in-flight rewrite of this very gate and the rationalization *"the rule's letter was not followed; its purpose was."* A rule whose only enforcement is an agent's self-restraint is advice, not a gate (`KB § PATTERNS/common/gate-methodology-sync.md`).

**The fix keeps the decision the user's and makes the proof mechanical.** The user types one canonical sentence in the conversation:

```
I authorize <slug> to be published to production.
```

An agent then calls `action=author`, which writes the record **only** if that sentence is found in the session transcript. The record carries its own evidence:

```yaml
consented_by: <git user.email>
consented_on: <YYYY-MM-DD>
consent_ref: '<roadmap.md>#<✅ milestone>'
dev_validated: true
recorded_by: agent
authorization:
  phrase: "I authorize <slug> to be published to production."
  session_id: <uuid>
  transcript_sha256: <sha256 at record time>
  recorded_at: <iso8601>
```

`recorded_by` is **optional and defaults to `user`**, so every record authored before this redesign stays valid — the change is purely additive.

### Why the phrase is canonical rather than free-form

An earlier sketch used a free-form `authorization_quote`. That is barely stronger than no gate: an agent can type any string. Two properties make the canonical sentence real evidence:

1. **It embeds the slug.** An agent cannot repurpose an unrelated "yes, go ahead" from earlier in the conversation as authorization for *this* product.
2. **It is exact-matchable.** No intent classification, no fuzzy matching, no judgement call inside a keeper.

### Two tiers of authorization — both SLUG-BOUND

`_authorization_tier` classifies a human message as:

| tier | shape | example |
|---|---|---|
| `performative` | the user **grants permission** | "i authorize / allow / approve igig … prod" |
| `directive` | the user **names this product for production** | "…fix the tests, then deploy igig to prod" |
| `None` | anything else | "should we deploy igig to prod?", "dont deploy igig to prod yet" |

Both require, in the same message: a matching **verb**, the **slug**, and a **prod/production** token — with negation and hypothetical framing ("not", "before", "until", "should we", "hold off") disqualifying the match.

**The slug requirement is never traded away.** Without it, one "deploy to prod" buried in a long prompt would authorize whatever product the agent happened to be registering — including one the user was not thinking about. `"and then deploy to prod"` authorizes nothing; `"i authorize igig to prod"` authorizes only igig, never orbity.

**Why `directive` counts** (widened 2026-08-09, at the user's explicit request, *after* igig's own consent had already been recorded and the deploy unblocked — so the change was not made to clear a blocked path). The orbity incident was an agent registering a product with **no user statement whatsoever**. A user who names a product for production has decided; on a single-owner fleet there is no second stakeholder the gate is protecting. And "is it ready?" is carried by **different legs** — `dev_validated: true` and the ✅ milestone — so the consent leg does not have to answer it.

**What this trades, plainly.** An operational instruction now doubles as a promotion decision: the user cannot ask for a prod deploy of a NEW product without also consenting to it being public. That is correct for a single-owner fleet and would be **wrong** for a team where the person asking is not the person entitled to decide. The tier is stored in the record (`authorization.tier`), so any later audit can separate "granted permission" from "asked for the deploy" without guesswork.

### The conjunctive matcher

Exact-matching the canonical sentence alone produced a **false negative on real consent**: the user typed *"i authorize the igig deploy all the way to prod"* and the gate rejected it. A gate that refuses genuine authorization teaches its user that the gate is broken, which is how gates get bypassed — the same class of defect as the YAML-quoting bug, and fixed for the same reason.

`_matches_authorization_intent` accepts a message when **all three** are present together, negation-guarded:

1. an explicit **performative verb** — `authorize` / `authorise` / `approve`,
2. the **slug**,
3. a **production token** — `prod` / `production`.

**"deploy igig to prod" deliberately does NOT match.** It is an instruction to an agent, not a promotion decision. If it authorized prod exposure, every deploy request would self-authorize and the gate would be equivalent to deleted — precisely the orbity incident's shape. A wish ("I want igig live") fails for the same reason: it lacks a performative verb.

The regression corpus is **real** — every string in `TestAuthorizationIntentHeuristic` is an actual message from the session in which this was written, sorted into genuine / instruction / negation. That is what keeps the heuristic honest: it is pinned against the exact conversation that motivated it.

The consent record stores the user's **own words verbatim** (`authorization.phrase`) plus `prompt_source`, never the agent's restatement — so an auditor reads what was actually said, and how.

### `suggestion_accepted` counts as human

`promptSource` distinguishes `typed` (the user composed it) from `suggestion_accepted` (the agent proposed the exact string; the user clicked accept). Both count, because the second is the **click-to-agree** pattern — the counterparty writes the words, the human performs the affirmative act — and the record is still harness-written, so an agent cannot fabricate an acceptance. Provenance is preserved in `authorization.prompt_source` so the two are never conflated. Any other `promptSource` is not human.

### Evidence is RANKED, and the runtime is not a witness (2026-08-16)

Two defects, both found by *using* the gate on the p-studio absorption, both of which produced a **perfectly well-formed record citing evidence that authorized nothing**. Neither was visible in the artifact — which is the lesson that outlives both fixes.

**1 · First-match-wins cited a forwarded quotation.** `_find_authorization_evidence` scanned in transcript order and returned the first hit. The user had pasted another session's report into the conversation; that paste contained the *other agent's explanation of this very gate* — *"registering a prod-exposure surface is the user's call, never an agent's"*. It matched. It grants nothing. Their real authorization — the exact canonical sentence, `promptSource="typed"`, the strongest shape this module defines — sat later in the same transcript and was never looked at.

The generalisation is the dangerous half: **quoting this document into a conversation can satisfy the gate**, because this document necessarily carries the slug and a production token when it discusses a product. Slug-binding — the property that stops an agent repurposing an unrelated *"yes, go ahead"* — cannot help when the quoted text is *about authorizing that exact product*.

Fixed by **ranking**, never by quote-detection:

| rank | evidence |
|---|---|
| 0 | canonical sentence, exact · `typed` |
| 1 | canonical sentence, exact · other human shape |
| 2–3 | `performative` · typed / other |
| 4–5 | `directive` · typed / other |

Ties break toward the **latest** message. Quote-detection was rejected deliberately: a heuristic that refuses text for *looking* quoted can refuse a **genuine** authorization, and a gate that refuses real consent is how gates get argued with and then bypassed — the same failure as the exact-match false negative and the unquoted-YAML `ScannerError` above it. Ranking cannot fail that way; it only changes *which* true match is cited, never whether one exists.

**2 · Harness-injected records counted as human.** `queue-operation/enqueue` was admitted wholesale, because a real mid-turn authorization appears *only* in that shape. But **background-task completions arrive in the same shape.** In the session that exposed this, **21 of 23 enqueue records were `<task-notification>` blocks and only 2 were the user** — and two of those notifications matched the authorization heuristic, one at `performative`.

This breaks the property the whole mechanism rests on: *the record must point at something **the agent did not write***. A task notification quotes tool output and the agent's own prose straight back into the transcript, so agent-authored text was being **laundered into the human-evidence layer**. With enough background jobs echoing the phrase, a notification alone could satisfy the gate with no human statement anywhere — the orbity incident's shape, reached by a new route.

`_is_harness_injected_queue_content` now drops them, matched on the **opening marker only** (`<task-notification>`, `[SYSTEM NOTIFICATION`) so a user who quotes a notification mid-message is still heard.

**The record now carries its own audit trail** — `evidence_rank` and `candidates_considered` — because both defects were invisible in a YAML that looked exactly right. A reader can now see what was selected *and that it was selected over something else*.

> **The durable lesson.** Every earlier fix to this gate hardened *who may author* the record. These two are about *what the verifier believes*, and both let machine-written text stand in for a human decision. A verification layer needs the same adversarial reading as the thing it verifies — "the transcript is harness-written, therefore trustworthy" is true of the *file* and false of every *record inside it*.

### What counts as "the user said it"

`_human_authored_transcript_texts` reads the harness-written `~/.claude/projects/*/<session_id>.jsonl` and accepts exactly two record shapes:

| Shape | Why |
|---|---|
| `type="user"` ∧ `promptSource="typed"` ∧ ¬`isMeta` | A prompt typed at the prompt box. Tool results are **also** `type="user"`, so `promptSource` — not `type` — is the discriminator; skill injections carry `isMeta`. |
| `type="queue-operation"` ∧ `operation="enqueue"` | A message sent **while the agent was working**. Verified against a real transcript: a mid-turn authorization appears *only* in this shape. Checking typed prompts alone would silently miss it — a false negative on a genuine authorization. |

`isSidechain` records are excluded (a subagent's conversation is not the user speaking), as are `tool_result` blocks and all `assistant` records. A missing or unreadable transcript is a **loud failure**, never an empty pass — so an absent transcript can never read as consent.

### The one-turn lag (and why the refusal message matters)

The harness flushes a user message to the transcript when its **turn ends**. A phrase typed during the turn an agent is currently executing is therefore **not on disk yet** — `action=author` is always one turn behind the authorization. Re-running it on the next turn verifies normally.

This is the right property (evidence must be durable before it counts), but it makes the *wording* of the refusal safety-critical. Found by probing this gate an hour after shipping it: the original message said "the user must type it themselves", which an agent that had just watched the user type it would either loop on, or resolve by concluding the gate is broken and routing around it — the exact failure mode this gate exists to prevent. A confusing refusal on a security gate is a safety bug, not a UX nit. Pinned by `TestVerifyAuthorizationPhrase::test_refusal_explains_the_one_turn_lag`.

### The honest limit

The transcript is a local plaintext file. This is **not** tamper-proof: an agent with write access could fabricate a record. What changes is the shape of the failure. Before, the shortcut was typing four lines of YAML and telling yourself the user approved — reachable by degrees, under pressure, while believing you are being helpful. After, the same shortcut requires forging the harness's append-only log: explicit, deliberate, and auditable. **The threat model is a well-meaning agent under pressure, not an adversary** — and against that, "you must point at something you did not write" is the property that matters. `transcript_sha256` is recorded so later tampering is detectable after the fact.

## `noctus.dev.prod_consent` — four actions

| action | Behavior |
|---|---|
| `status` | Honest per-product dashboard for every slug currently declared on the three surfaces. `consent_status` ∈ `valid` / `invalid` / `missing_pregate`. |
| `request` | `ok: false` always — never writes. Returns `target_path`, `already_exists`, `template_yaml`, `instructions`. The hand-authoring path. |
| `challenge` | Returns the canonical sentence to **ask the user to type**. Writes nothing. |
| `author` | Writes the record **iff** the canonical phrase is verified against the transcript; otherwise `ok: false` with the reason. The agent supplies the slug and session id; it cannot supply the evidence. Since 2026-08-16 it cites the **highest-ranked** candidate (not the first) and stamps `evidence_rank` + `candidates_considered`. |

## Scope decision — no backfill for grandfathered products

The 9 products (+ n8n/waha/legacy infra rows) already on the three surfaces at gate-introduction time are **NOT** retroactively required to carry a consent record — the set-difference means they never appear in `new` going forward, so correctness never depends on a backfill. `prod_consent action=status` reports them honestly as `missing_pregate` ("no consent record on file (pre-gate)") — never silently hidden, never auto-authored. **An agent must not author a `deploy/consent/*.prod.yml` on the user's behalf, including as a backfill** — doing so on day one would defeat the mechanism it exists to gate.

## What this does NOT touch (deliberately deferred)

- `.github/workflows/build-and-push.yml` — the CI-job backstop for THIS gate (should CI itself refuse to build/push a newly-registered slug without a consent record?) is a separate wave pending user decision. This is distinct from the PROD-PIN HOLE fix below — that fix changed WHICH build moves `:latest`, not whether a new slug's registration is consent-gated.
- ~~`release.py` / `deploy_image.py` — the PROD-PIN HOLE ... is a structural gap this doc names but does not fix~~ — **FIXED 2026-07-20** (`KB § GUIDES/production-deploy.md § 2b`): `:latest` now moves ONLY on a `prod`-ref build, and `deploy_image` refuses a `tag=latest source=pull` deploy whose baked revision isn't a verified ancestor of `origin/prod`. This closes the "what RUNS drifts from what was promoted" hole; it is still a *separate* question from THIS gate's "should this product be public at ALL" — the PROD-PIN fix governs which build of an already-consented product's code reaches `:latest`, never whether a product should be registered on the three surfaces in the first place.

## Mechanism half — `scaffold_product` never touches these surfaces

`noctus.dev.scaffold_product` (product creation) does not, and must never, write to any of the three surfaces — locked in by `TestScaffoldProductNeverTouchesProdExposureSurfaces` (AST-scans `scaffold.py`'s code for the three surfaces' literal names; the module's own explanatory comment is exempt since comments aren't AST nodes). Its `next_steps` always carries a breadcrumb: prod exposure is a separate, consent-gated step the scaffold never performs.

## Composes with

- [`gate-methodology-sync`](../common/gate-methodology-sync.md) — the gate/mechanism pairing this pattern instantiates (refuse-not-null on `prod_consent action=request`).
- [`prod-deploy-safety-gates`](prod-deploy-safety-gates.md) — the sibling pre-deploy gate cluster (cache reachability / drift-shield / slip-shield); this gate answers a *different* question ("should this product be public at all") than theirs ("is this deploy safe to ship").
- [`git-branch-model`](../architect/git-branch-model.md) — bless/promote are **branch-granular**, not per-product; this consent gate is the missing **per-product** promotion decision bless/promote never made.
- [`roadmap-tracking`](../common/roadmap-tracking.md) — the `consent_ref` milestone-resolution convention.
- `KB § GUIDES/production-deploy.md § 2b` — the corrected "prod branch gate" claim this pattern's incident analysis forced.

## CLI

```bash
python mcp/noctusai/cli.py --check-prod-exposure-consent
```

## MCP tools

- `noctus.dev.prod_consent(action='status'|'request'|'challenge'|'author', slug=None, session_id=None, consent_ref=None, worktree_path=None)`.

## History

- **2026-08-16** — **Evidence ranking + harness-record rejection.** Found by using the gate on the p-studio absorption; see *"Evidence is RANKED"* above. `author` cited a forwarded quotation of this very document as the user's authorization while their genuine `typed` canonical sentence sat unread later in the same transcript; and `queue-operation/enqueue` was admitting the runtime's own `<task-notification>` blocks as human speech (21 of 23 records in that session), which laundered agent-written text into the evidence layer. Fixed by ranking (never quote-detection) + an opening-marker check, with `evidence_rank`/`candidates_considered` stamped into the record so the next such defect is visible in the artifact. 11 regression tests pinned to the real strings from that transcript, including one asserting what did **not** change. The consent decision in that instance was genuine, so nothing unsafe shipped — the *record's evidence* was false, which is the one property this mechanism exists to guarantee.
- **2026-07-20** — Shipped closing the orbity incident (prod-serving six weeks before validation, zero consent decision on record). Keeper + mechanism (`scaffold_product` invariant + `prod_consent` tool) + regression test proving fire/pass/silent + 8-way sync, same commit.
- **2026-08-09 (same day, second pass)** — **Conjunctive intent matching + `suggestion_accepted`.** Exact-only matching false-negatived a real authorization; the user pushed back mid-deploy. Loosened *deliberately and tightly*: verb ∧ slug ∧ prod, negation-guarded, pinned against the session's real messages. The line held where it matters — `deploy <slug> to prod` still does not authorize, because an instruction is not a promotion decision. Provenance (`prompt_source`) and the user's verbatim words are now stored in the record.
- **2026-08-09** — **Verified-transcription redesign.** Two things were wrong, found while igig waited on M5:
  - **A false negative that made the gate look arbitrary.** `consent_ref` shipped **unquoted** in the template from introduction. A milestone anchor is normally `M5: prod promote`, so the value carries `": "` — an unquoted YAML scalar containing `": "` is a `ScannerError`, not a string. **Every record authored faithfully from the documented template failed at the parse step**, presenting to the author as "the gate rejected my consent" rather than "your YAML is malformed". Quoting is the whole fix.
  - **An unverifiable authorship rule.** See the section above. Replaced "the user must type the file" with "the user must type the sentence, and the gate checks". Strictly stronger (the old rule verified *nothing* about who wrote the file) and strictly lower friction.

  Decided deliberately, as its own slice, with no product waiting on it — after an attempt to rewrite this gate *while* trying to clear it for igig was reverted. That sequencing is the point: a gate redesigned under pressure to unblock a specific deploy is not a redesign, it is a bypass with paperwork. `KB § PATTERNS/common/bypass-rationalization-anti-patterns.md`.
