# Project History Ledger — Global Changelog + Token-Tracking Mechanism

> **This is a living document, not a rigid checklist.**
> Filed 2026-05-02 mid-session when the user proposed the idea. The
> user explicitly said *"this change log project has to be filed as a
> project. We're gonna come back here to refine and work on it."*
> The project's job today is to **preserve the idea + the open
> questions** so when re-activated, the next agent inherits the full
> reasoning instead of a blank slate.
>
> **Status: ⏳ EXECUTING — design questions resolved 2026-05-10.**
> §7 Q1-Q4 stamped by orchestrator (defaults accepted under user
> signal "resolve the 5 blocked ones"); §6 drafted. Phase 0 dispatched.

- **Created:** 2026-05-02
- **Last updated:** 2026-05-10
- **Status:** ⏳ EXECUTING — §7 Q1-Q4 ✅ resolved (orchestrator defaults stamped); §6 drafted 2026-05-10; Phase 0 ✅ shipped 2026-05-10 (scaffold + tokenizer smoke-test green); Phase 1 ✅ shipped 2026-05-10 (MCP tool `noctus.dev.history_record` + Pydantic schemas + 30 unit tests green + N=2 tokenizer absorption via `tools/_tokens.py`); Phase 2 ✅ shipped 2026-05-10 (close-workflow integration — `archive` stamps ledger before git mv; default-on; `skip_history` opt-out; 13 new tests green; KB § 11.2 + memory updated); Phase 3 (renderer) pending dispatch.
- **Owner / stakeholders:** Raphael · future zero-context execution agent
- **Related docs:** `CLAUDE.md`; `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md`; `templates/PROJECT-TEMPLATE.md`; **interlocks with** `projects/methodology-extraction/PROJECT.md` Phase 5 (which currently uses rough token estimates — this project's token-tracking tool would let Phase 5 measure precisely); **interlocks with** `projects/methodology-mirror-and-workspaces/PROJECT.md` (which would feed measured per-workspace token cost into the ledger if and when it ships).
- **Project slug:** `project-history-ledger` — cross-product / platform-infra scope, lives at root `projects/`.

---

## 1. Context & Purpose

The user wants a **global, persistent, machine-readable record of
every project this repo has shipped** — beyond what `git log` or the
per-project `§11 Change log` already captures. Two motivations:

1. **Documented timeline of project evolution.** Today, a project's
   life ends with the folder being deleted (`apply-inline-then-delete`
   + `clean-folder principle`); the only surviving evidence is the
   commit history. The user explicitly wants a first-class artifact —
   *part of the project itself, not derived from git* — that
   summarizes each closed/deleted project: short summary, steps in a
   short review, token cost.
2. **Future AI training data.** The user is planning AI training
   that consumes this ledger to predict **cost-efficiency** and
   surface **proven-solutions × cost** patterns. That gives the data
   shape constraints — entries need to be structured enough for an
   ML pipeline to ingest, not just narrative prose.

For the cost dimension to be meaningful, the methodology needs a
**token-tracking mechanism**: a tool/process that measures tokens
spent at project granularity (and ideally per-step / per-phase).
That's the second deliverable inside this project's scope. With it
in place, every closed project lands its token cost in the ledger
automatically (or near-automatically); without it, the cost column
stays empty and the AI-training motivation collapses.

This is filed today as **Concept — interrogation pending** because
the user signalled *"we're gonna come back here to refine and work on
it"*. The §7 questions catalog the architectural decisions still
ahead; the next agent's first move on reactivation is to interrogate
those, not draft phases.

---

## 2. Confirmed constraints (what the user *has* said)

> **Source note:** the bullets below paraphrase user statements from
> the 2026-05-02 conversation that produced this file. Future agents:
> if a constraint feels ambiguous, ask the user to confirm.

- **One global ledger, not per-project.** The artifact is a single
  document/file that records every project. *(Rules out a
  decentralized model where each project leaves its own breadcrumb
  somewhere.)*
- **Records closed AND deleted projects.** Both terminal states
  count. *(Implication: an entry must be written BEFORE folder
  deletion, since deletion erases the source of truth otherwise.)*
- **Each entry carries: short summary, steps reviewed shortly, token
  count.** Three fields are non-negotiable. Other fields (slug,
  dates, owner, etc.) are TBD in §7.
- **Token tracking is part of the methodology.** The user said *"we're
  gonna have to add a token tracking mechanism to our methodology, so
  projects and steps get their counts."* This isn't an optional
  bolt-on — it's a methodology change that future projects must
  honor. Implication: the protocol for closing a project must
  include "stamp the token count" as a standard step.
- **Two consumers, two formats.** The ledger serves (a) humans
  reviewing project history and (b) future AI training. *(Probable
  implication: a structured machine-readable file + a human-readable
  Markdown rendering; the human form is generated from the
  structured form so they can't drift.)*
- **AI training is for predicting cost-efficiency and proven-
  solutions-vs-cost.** That shapes the data model: each entry needs
  enough features for the model to learn from — likely beyond the
  three minimum fields. §7 Q4 explores what.
- **Acknowledged that git already records this.** The user said
  *"I know we can do that by checking commit history, but i want
  this as part of the project itself."* — explicitly rejecting "just
  use git log" as a substitute. The ledger is intentionally a first-
  class methodology artifact.
- **Defer execution.** The user said *"this change log project has
  to be filed as a project. We're gonna come back here to refine and
  work on it."* Do not start drafting §6 phases without explicit
  reactivation.

---

## 3. Design principles (provisional — confirm with §7 answers)

1. **Write-before-delete.** A project's ledger entry is a hard
   prerequisite for closing/deleting the folder. The
   `apply-inline-then-delete` rule already requires careful close-
   out; this adds one more step.
2. **Machine-readable first, human-rendered second.** The canonical
   storage is structured (YAML/JSON/SQLite — TBD §7 Q2). The Markdown
   ledger is a generated view, not the source of truth, so the two
   never drift.
3. **Token count is multi-grain.** At minimum: per-project total. If
   feasible: per-phase, per-step. The richer the granularity, the
   more useful for future training — but the harder to capture
   automatically. Default to per-project; pursue per-phase only if
   measurement cost is low.
4. **Keep entries terse.** "Short summary" + "short review" — not
   essays. The full detail already lives in commits + the project
   doc up to deletion. The ledger is the *index*, not the corpus.
5. **No per-product code.** This is a methodology / tooling artifact,
   like `KNOWLEDGE-BASE/` and `mcp/noctusai/`. Per-product code-count
   litmus: **0**.
6. **Cost-efficiency is the editorial through-line.** Every field
   that doesn't contribute to "cost vs outcome" reasoning has to
   justify its presence. The whole point of this ledger is to make
   that comparison cheap to do later.

---

## 3a. Seed-first analysis

Mandatory per CLAUDE.md. This project is **explicitly about** the
methodology layer (project-execution protocol + MCP toolkit) — there
is no "should this live in product or seed?" question. Both
deliverables land at the platform layer:

- **Token-tracking mechanism** → `mcp/noctusai/tools/` (a new tool;
  potentially backed by Anthropic API usage records or a tokenizer
  library).
- **Global historical changelog** → either repo root
  (`PROJECT-HISTORY.md` or similar) or `KNOWLEDGE-BASE/HISTORY/`
  (TBD §7 Q1).

Per-product code-count litmus: **0**.

---

## 4. Scope

**In scope** (once §7 is resolved):

- A token-tracking MCP tool that can:
  - count tokens in a file (Anthropic-tokenizer-compatible)
  - sum tokens for a project folder (PROJECT.md + improvements.md +
    proposals/* + delta of files this project's commits actually
    touched, where measurable)
  - emit a structured record on demand
- A canonical structured ledger file (format TBD §7 Q2) with one
  record per closed/deleted project.
- A human-readable Markdown rendering of the ledger (auto-generated;
  not hand-edited).
- Methodology updates: closing protocol gets one new step ("stamp the
  ledger entry") that fires before folder deletion. CLAUDE.md +
  KB + memory three-way sync per the standing rule.
- Backfill of currently closed/deleted projects (TBD §7 Q5 — best-
  effort from git history, no heroic archeology).
- Documentation in KB describing the workflow end-to-end.

**Out of scope:**

- Live session-level token telemetry (i.e. capturing every Anthropic
  API call's token usage in real time). That requires harness-level
  hooks; out of scope unless §7 Q3 resolves toward it.
- Replacing per-project `§11 Change log`. Those stay; the ledger is
  the *index across projects*, not a substitute for any project's
  own log.
- Cost in dollars (vs tokens). Token count is the canonical unit;
  $/token mapping is a downstream concern.
- The future AI training pipeline itself. That consumes the ledger;
  this project produces it.

---

## 5. Architecture / data model — sketch

```
┌─────────────────────────────────────────────────────────────────┐
│ Closing a project (existing protocol + 1 new step)              │
│                                                                  │
│  Phase N ✅ → Bundled proposal → Apply inline → Delete proposal  │
│           → [NEW] Stamp ledger entry ──────────────────┐         │
│           → Apply-inline-then-delete sweep              │         │
│           → Folder deletion (if project fully closed)   │         │
└─────────────────────────────────────────────────────────┼────────┘
                                                          │
                                                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ STRUCTURED LEDGER (canonical source of truth)                    │
│   format: TBD §7 Q2 (YAML / JSON / SQLite / NDJSON)              │
│   location: TBD §7 Q1 (repo root / KB / dedicated dir)           │
│                                                                  │
│   one record per project, fields (provisional):                  │
│     slug                                                         │
│     scope (cross-product / single-product / core-control)        │
│     status_at_close (✅ shipped / ❌ abandoned / 🔀 split / ⏸ deferred) │
│     dates: created, closed (or deleted)                          │
│     phases: [ {name, status, tokens?, notes_short} ]             │
│     short_summary (1-3 sentences)                                │
│     short_review (steps in 5-10 bullets max)                     │
│     token_count: {                                               │
│       project_doc_tokens: int                                    │
│       improvements_tokens: int                                   │
│       proposals_tokens: int                                      │
│       code_delta_tokens: int? (estimated from commits)           │
│       total: int                                                 │
│     }                                                            │
│     outcome_signals: [user-facing wins / measured deltas]        │
└─────────────────────────────────────────────────────────────────┘
                                                          │
                                                          ▼ (rendered)
┌─────────────────────────────────────────────────────────────────┐
│ PROJECT-HISTORY.md  (human view, auto-generated)                 │
│  | date | slug | status | tokens | summary |                     │
│  ...                                                              │
│  Plus per-project narrative blocks below the table.              │
└─────────────────────────────────────────────────────────────────┘
```

The token-tracking tool feeds the `token_count` field. Today, the
methodology-extraction Phase 0 used rough estimators (~4 chars/tok
and ~0.75 words/tok) — this project's tool should use a real
tokenizer (Anthropic-aligned) for precision. Once shipped, Phase 5
of methodology-extraction can re-measure with this tool for honest
numbers.

---

## 6. Implementation phases

**Drafted 2026-05-10 after §7 Q1-Q4 resolution** (orchestrator-stamped defaults under user signal "resolve the 5 blocked ones"). Each phase ≤ ½ session.

### Phase 0 — Scaffold + tokenizer ✅ (2026-05-10)

- [x] Create `project-history/` directory at repo root (per Q1=B).
- [x] Create `project-history/README.md` (1-page convention doc — points back to this PROJECT.md, explains NDJSON format + columns).
- [x] Create `project-history/ledger.ndjson` (empty marker; gitignore-tracked-as-existing).
- [x] Create `project-history/PROJECT-HISTORY.md` (placeholder header — rendering filled in Phase 3).
- [x] Pick tokenizer: **`tiktoken`** for static counting (Anthropic-compatible cl100k_base encoding). Install via `pip install tiktoken` to `mcp/noctusai/.venv/`. **Already installed** (`tiktoken==0.12.0`, already declared in `mcp/noctusai/requirements.txt` for `cost_evaluation`); no install needed — discovered on inspection. Reuses the same encoding the cost_evaluation tool uses.
- [x] Smoke-test tokenizer: count tokens of one archived `PROJECT.md` file; confirm sane number. **Result**: `archive/projects/2026-05-10/06-pf-metas-seed-wiring/PROJECT.md` = **5369 tokens** (cl100k_base). Sanity-checked against chars/4 rough estimator (5347) — diverge by 0.4%, well within tolerance. `enc.encode('hello world') == [15339, 1917]` confirms encoder loads.

**Improvements:**

- **tiktoken already in requirements.txt** — Phase 0 expected to install; was a no-op. Saves dependency churn but worth noting: any agent reading PROJECT.md without inspecting `requirements.txt` would assume the install step ran. Folded into Phase 1's brief automatically since `noctus.dev.history_record` simply `import tiktoken`s.
- **chars/4 estimator is honest** — 0.4% divergence on a representative PROJECT.md means previous projects' rough estimates (methodology-extraction Phase 0) are well-grounded; the precise tokenizer isn't an order-of-magnitude correction, just a precision improvement. Document this in §5 or Phase 5 close.
- **cl100k_base vs o200k_base / Claude-native tokenizer** — `tiktoken` is OpenAI's tokenizer; Anthropic's official tokenizer is shipped via `anthropic.tokenizer` in the Python SDK. Q3=I resolved to `tiktoken` for speed-to-ship; the Anthropic tokenizer would be measurably more accurate for Claude-cost reasoning. **Defer-to-Phase-5-close as a v2 swap candidate**. The encoding choice is encapsulated in one call (`tiktoken.get_encoding('cl100k_base')`); swapping is local.

### Phase 1 — Schema + writer ✅ (2026-05-10)

- [x] `mcp/noctusai/tools/noctus/dev/history.py` — MCP tool `noctus.dev.history_record(project_path, status_at_close, summary_md, review_md, outcome_signals)` that:
  - Reads the PROJECT.md + improvements.md + proposals/*.md from `project_path`.
  - Static-tokenizes each (per Q3=I) via the shared `tools._tokens.count_tokens_in_text` helper.
  - Walks `git log --all --grep <slug> --shortstat` for the project's commits (best-effort via slug grep in commit messages) → counts code-delta tokens via `(insertions + deletions) * 8` heuristic (~8 tokens/line of code).
  - Writes a single NDJSON record (per Q2=c) with the Q4 standard field set: slug, scope, status_at_close, dates {created, closed}, phases [{name, status, tokens?}], short_summary, short_review, token_count {project_doc_tokens, improvements_tokens, proposals_tokens, code_delta_tokens, total, tokenizer_used}, outcome_signals.
  - Appends to `project-history/ledger.ndjson` (NDJSON — one JSON object per line, append-only; re-stamping the same slug appends a new line — the ledger is the history of stampings, not a uniquely-keyed store).
- [x] Pydantic record schema for type-safety (`HistoryRecord` + `HistoryDates` + `HistoryPhase` + `HistoryTokenCount` — `extra="forbid"` per archive.py sibling consistency).
- [x] Unit tests at `mcp/noctusai/tests/test_history.py` — 30 tests covering record-shape, JSON round-trip, idempotency on re-run, append-not-overwrite, multi-project shared ledger, self-contained-JSON-per-line, tokenizer-call-counted (4 calls per project for the standard PROJECT.md + improvements.md + 2 proposals shape), status / scope validation, missing-file tolerance, phase regex extraction + explicit override, scope inference, shortstat parsing, custom ledger-path injection, MCP registration.
- [x] **N=2 tokenizer absorption applied**: extracted `mcp/noctusai/tools/_tokens.py` (`count_tokens_in_text` + `get_default_encoder` + `count_tokens` + `DEFAULT_TIKTOKEN_ENCODING` + `APPROX_LABEL`). Both `cost_evaluation.py` and `history.py` import from this shared module. The encoder choice + fallback cascade live in one place. Future Anthropic-tokenizer swap (deferred from Phase 0) lands in `_tokens.py` and propagates automatically.

**Improvements:**

- **Phase regex needed a bullet-marker tweak.** Initial regex matched `Phase N` only at heading-style line starts (`### Phase 1` / `Phase 1`); a normal markdown bullet (`- Phase 1`) silently dropped to zero phases. Caught by `test_phases_extracted_from_review` on first run. Fix was one alternation: `(?:[-*]\s+|#+\s*)?`. Lesson: every PROJECT.md I've seen uses bullets for the review summary — the bullet form should have been the default, not the edge case. Documented in `findings.md` (return-as-text per §17.6.1).
- **N=2 tokenizer absorption was N=2-at-authoring-time, not at-N+1-time.** This was the right shape — the recurrence rule says "N=2 → triage time"; engineer F's Phase 0 finding flagged tiktoken-already-installed (= N=1 caller plus future N=2). Phase 1 made it N=2 and immediately formalized via `_tokens.py`. No silent shipping of the second call site. Confirms the rule's authoring-time corollary: see the duplicate coming → fix at duplication time, not at N=3.
- **NDJSON append-only vs. dedupe-by-slug decision.** Picked append-only (documented in tool docstring + tests). Rationale: a project may legitimately have multiple records (e.g. split → shipped, or backfill historical + later live-stamp). The renderer (Phase 3) is the right place to dedupe-by-slug for the human view if desired; the structured store stays the full history.
- **`code_delta_tokens` heuristic is rough — flag in Phase 5 close.** `(insertions + deletions) * 8` is rule-of-thumb. Precise per-commit tokenization would require `git show` per revision + tokenize each diff. Cost: high (N commits × M files). Benefit: precision the AI-training pipeline doesn't yet need. Defer to Phase 5 close decision: keep heuristic + document in `PROJECT-HISTORY.md` rendering, OR replace if Phase 4 backfill surfaces a calibration delta worth fixing. **Cataloged in `KB § PATTERNS/accept-with-rationale.md` (deferred until Phase 5 retrospective)** — current shape is intentional, not an oversight.
- **`tiktoken` import is implicit via `_tokens.py`** — no module-level import in `history.py` itself. The helper module gates `ImportError` and returns `None` from `get_default_encoder()`, falling through to the chars/4 approximation. This means the tool works on a fresh clone before `pip install -r mcp/noctusai/requirements.txt` runs (with degraded precision), instead of crashing at import. The cascade also means a future Anthropic-tokenizer swap doesn't need to touch `history.py`.
- **Phase 0's deferred "Anthropic tokenizer v2 swap" is still deferred** — Phase 1 doesn't address it (rightly so, single dispatch). Surface it in Phase 5 close: the encoding choice is encapsulated in `tools/_tokens.py::get_default_encoder()`, swap is local.

### Phase 2 — Close-workflow integration ✅ (2026-05-10)

- [x] Amend `noctus.dev.archive` to **optionally** call `noctus.dev.history_record` first (when invoked with `mode="project"`, default-on; can opt-out with flag). Order: stamp ledger → then git-mv to archive/.
- [x] Update `KB § PATTERNS/project-execution.md § 11.2` to mention the ledger-stamp side-effect.
- [x] Update `feedback_archive_system.md` memory entry to mention the ledger.

**Improvements:**

- **Default `status_at_close="shipped"` is the right ergonomics** — archive's most common trigger is project close. Forcing every archive caller to specify status would generate friction on the happy path; explicit override (e.g. `status_at_close="abandoned"`) is the one-line addition for the minority case. Tests cover both code paths.
- **Default summary derivation skips headings + blockquotes** — `_derive_default_summary` walks PROJECT.md line-by-line skipping `#` (headings) and `>` (blockquotes — PROJECT.md uses these for status notes near the top), stripping leading bullet prefixes. Lands on the first sentence of `## 1 Context & Purpose` in practice. Fallback string `"(no summary available)"` rather than raising — archive should not block on a missing summary; the human-precision summary lives in `review_md` (defaulting to full PROJECT.md body) anyway.
- **Fault-injection test uses real validation path, not monkey-patching** — initial draft patched `tools.noctus.dev.archive.history_record` to a `_boom` lambda. Caught by the no-monkey-patching-of-our-own-code rule. Refactored to pass an invalid `status_at_close="not-a-valid-status"` which triggers `history_record`'s own `ValueError` validation — the real error path the production code takes. Same assertion (source folder untouched after raise) survives, and the test now exercises the actual contract.
- **`history_result` surfaced in archive's return dict** — `{"archived_to": ..., "mode": ..., "next_NN": ..., "history": <dict|None>}`. Lets callers (Phase 5 close, future renderers) verify the stamp happened without re-reading ledger.ndjson. `None` when `skip_history=True` or mode≠project — makes the conditional explicit.
- **No silent skip on stamp failure** — `history_record(...)` is invoked unconditionally for project archives; if it raises, the `git mv` never runs. Source folder stays in place; caller sees the original error. Aligns with the no-silent-errors rule. Test `test_stamp_failure_aborts_archive_no_git_mv` pins this with the real validation path.
- **Phase 3 renderer can now produce the human view** — `project-history/ledger.ndjson` is no longer hypothetical; every project archive produces one well-formed line. The dev-team or a follow-up engineer can build the renderer against real data from the moment Phase 5 stamps this very project.

### Phase 3 — Renderer

- [ ] Script `scripts/render-project-history.py` — reads `ledger.ndjson`, emits Markdown table to `project-history/PROJECT-HISTORY.md` sorted by closed_at DESC. Idempotent.
- [ ] Add to pre-commit hook (alongside `update-kb-counts.py`) — regenerate on commit if ledger.ndjson changed.

### Phase 4 — Backfill from archive/ (optional)

- [ ] Walk `archive/projects/*/*/PROJECT.md` and stamp ledger records for past archives (`status_at_close="historical"` flag).
- [ ] Spot-check rendered PROJECT-HISTORY.md against `git log` for completeness.

### Phase 5 — Close

- [ ] Tests green; render verified; archive system updated.
- [ ] `noctus.dev.archive` this very project (which stamps its own ledger entry — meta!).

---

## 7. Open questions — ✅ Q1-Q4 resolved 2026-05-10 (orchestrator-stamped defaults)

**User signal:** *"please resolve the 5 blocked ones, then unblock the deps on it"* — orchestrator stamped each recommendation as the resolution. User can override later by amending §6.

Each question paired with a recommendation, now marked with its resolution.

1. **Where does the canonical ledger live on disk?**
   - **(A)** repo root: `PROJECT-HISTORY.md` (human view) + `.project-history.json` (data)
   - **(B)** dedicated dir: `project-history/` with `ledger.json` +
     `PROJECT-HISTORY.md`
   - **(C)** KB: `KNOWLEDGE-BASE/HISTORY/` with both files
   *Recommendation: **(B) dedicated dir** — keeps repo root clean
   (per the clean-folder rule), avoids putting derived data inside
   `KNOWLEDGE-BASE/` (which is a knowledge anchor, not a data store),
   and makes the boundary obvious.*

2. **Structured ledger format.**
   - **(a)** YAML — readable, easy to hand-edit if needed
   - **(b)** JSON — machine-friendly, no ambiguity
   - **(c)** NDJSON — one project per line, append-only, ML-friendly
   - **(d)** SQLite — queryable, harder to read, requires tool to inspect
   *Recommendation: **(c) NDJSON** — append-only matches "write-
   before-delete" naturally; ML pipelines parse it trivially; humans
   can still read it line-by-line. The Markdown rendering is the
   human-readable view; the structured form doesn't need to be
   pretty.*

3. **Token-counting mechanism.**
   - **(I)** Static — count tokens of files (PROJECT.md, improvements,
     proposals, plus a delta over committed code) using a tokenizer
     library. No live telemetry.
   - **(II)** Dynamic — capture per-session token usage from
     Anthropic API responses (usage records) via a harness hook,
     accumulate into the project's running total.
   - **(III)** Hybrid — static for the artifact tokens; dynamic for
     conversation tokens. Maximally informative.
   *Recommendation: **(I) static, ship first**, with a clear
   extension point for (II) later. Static is achievable with no
   harness changes — just a tokenizer (Anthropic ships one for
   Claude); dynamic requires user-environment integration we may not
   control.*

4. **Minimum viable record fields.**
   The user's three required fields: short summary, short review,
   token count. What other fields earn their place?
   - slug, scope (cross-product / single-product / core), status_at_close
   - dates: created, closed
   - phase list (each with status + optional tokens)
   - outcome signals (e.g. "ERP backend pytest 1816/1816 green",
     "CLAUDE.md trim 38%")
   - linked artifacts (PR URLs, KB anchors created)
   - tags (e.g. `methodology`, `seed`, `migration`, `lgpd`,
     `infrastructure`) — useful for ML grouping
   *Recommendation: ship the user's three required + slug + dates +
   scope + status_at_close + tags. Defer outcome_signals and linked
   artifacts to v2 unless backfill data has them readily.*

5. **Backfill scope for existing projects.**
   The repo currently has multiple projects in
   `projects/{adconnect-migration, execution-workflow-codequality-rollout,
   keeper-warning-triage, mcp-scaffold-sql-templates-integration,
   methodology-extraction, repo-commit-followup,
   repo-state-consolidation, strict-mode-migration, ...}` plus per-
   product `projects/`. Some are active, some closed-but-not-deleted.
   - **(α)** backfill all closed-or-deleted projects (best-effort)
   - **(β)** backfill only fully-deleted projects (the ones with no
     surviving folder — recoverable from git)
   - **(γ)** no backfill — start the ledger from this project's close
   *Recommendation: **(α) best-effort backfill of all closed-or-
   deleted** — token counts will be approximate for older entries, but
   having the timeline matters more than precision. Mark backfilled
   entries with `backfilled: true` so future ML training can choose
   to weight them down.*

6. **Trigger event(s) for ledger entries.**
   - **(p)** project close (status flips to ✅ Done) — entry added
   - **(q)** project deletion (folder removed) — entry added
   - **(r)** project split into siblings (e.g. today's
     methodology-extraction → mirror split) — entry added per side
   *Recommendation: **(p) AND (q) AND (r)** — every terminal
   transition writes an entry; the `status_at_close` field
   distinguishes them. This means a single project may have multiple
   entries (e.g. status `🔀 split` + later one of `✅ shipped`).*

7. **Human-readable rendering — auto-generated only?**
   - **(x)** auto-generated entirely; never hand-edited
   - **(y)** auto-generated but with a hand-edited prose section per
     entry for "narrative review"
   *Recommendation: **(x) auto-generated only** — drift between the
   structured store and the human view is the first failure mode we'd
   hit. If a project deserves prose narrative, that lives in its own
   `§11 Change log` while the project still exists.*

8. **AI-training data shape — what gets exposed?**
   The user mentioned predicting cost-efficiency and proven-solutions
   × cost. That implies, at minimum:
   - tokens spent
   - some categorical "outcome" label (shipped / abandoned / split /
     superseded)
   - tags/scope features (so the model learns conditional patterns)
   - dependencies on prior projects (which projects this one cited
     as related, so the model sees evolution chains)
   *Recommendation: include a `prior_projects: [slug]` field per
   entry (cite related-project links from PROJECT.md `Related docs`).
   This unlocks dependency-graph features for the ML model.*

9. **Tokenizer choice (interlock with §7 Q3).**
   Anthropic ships an official tokenizer (`@anthropic-ai/tokenizer`
   for JS, `anthropic.tokenizer` in Python SDK). Alternatives include
   `tiktoken` (OpenAI-compatible, close-but-not-identical) or
   character/word approximations.
   *Recommendation: **Anthropic's official tokenizer**, since the
   intended consumer (future AI training) is Anthropic-aligned.
   Falls back to char/word approximation only if the tokenizer is
   unavailable in the environment.*

---

## 8. Dependencies & blockers

- **methodology-extraction Phase 5 wants this project's tool.** Phase
  5 will re-measure the auto-load surface; today's rough estimates
  (chars/4 and words/0.75) are good enough as a baseline but a real
  tokenizer would let Phase 5 produce honest numbers. If this
  project's token tool ships before Phase 5, Phase 5 uses it; if not,
  Phase 5 ships with rough numbers and this project re-stamps the
  ledger when it lands.
- **Backfill (§7 Q5) depends on the structured-format decision (§7
  Q2).** Don't start backfilling until Q1 + Q2 + Q4 lock.
- **The `apply-inline-then-delete` + `clean-folder` rules already
  enforce close discipline.** Adding "stamp ledger entry" as a step
  in close protocol is a small CLAUDE.md / KB amendment — but it's a
  three-way-sync change, so it follows that rule.

---

## 9. Success criteria

When this project ships, the user can:

- See a single file (Markdown) listing every project this repo has
  shipped, in reverse-chronological order, with a one-line summary
  and token count per project.
- Query the structured ledger (NDJSON / chosen format) to filter by
  scope, status, tag, or token-count range.
- Trust that every project closing from now on stamps an entry as
  part of its close protocol — no missing rows.
- Feed the structured ledger into a future AI training pipeline that
  predicts cost-efficiency and proven-solutions × cost.

---

## 10. How to use this project

- **Don't draft §6 phases until §7 resolves.** The user deferred this
  *"to come back here and refine and work on it"*. The next session's
  first move is to ask the §7 questions in order.
- **Read §1 + §2 + §7 in one pass.** Those carry the load-bearing
  reasoning.
- **When reactivating, START with Q1, Q2, Q3.** Those three lock the
  storage model and the tokenizer choice — everything else (fields,
  backfill, trigger events) hangs off them.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-02 | **Project filed.** User directive: *"also lets add a historical change log globally. This must contain a short-phrased summary of closed and deleted projects, the steps in a short review, and its token count. So for that, we're gonna have to add a token tracking mechanism to our methodology, so projects and steps get their counts. The idea of this is to have documented a historical timeline of the project's evolution."* + *"this change log project has to be filed as a project. We're gonna come back here to refine and work on it."* + *"for future ai training that im thinking of, so we can predict cost-efficiency and already proven solutions x cost"*. Filed at root `projects/project-history-ledger/` (cross-product / platform-infra scope). §1-§5 + §7 + §10 populated; §6 intentionally empty pending §7 resolution + user reactivation. **Interlock noted with `methodology-extraction` Phase 5** — that phase needs precise per-turn token counts and currently uses rough estimators; this project's token tool would replace them. | Claude Opus 4.7 |
| 2026-05-10 | **§7 Q1-Q4 resolved (orchestrator-stamped defaults)** under user signal "resolve the 5 blocked ones". **Decisions**: Q1=B (dedicated `project-history/` dir at repo root), Q2=c (NDJSON append-only), Q3=I (static tokens via tiktoken; dynamic deferred), Q4=standard fields (slug + scope + status_at_close + dates + phases + summary + review + token_count + outcome_signals). §6 drafted: Phase 0 (scaffold + tokenizer) → Phase 1 (schema + writer) → Phase 2 (close-workflow integration) → Phase 3 (renderer) → Phase 4 (backfill, optional) → Phase 5 (close). Phase 0 dispatched. | claude-opus-4-7 |
| 2026-05-10 | **Phase 0 ✅ shipped.** Engineer in isolated worktree. Created `project-history/` at repo root with `README.md` (1-page convention doc) + `ledger.ndjson` (0-byte append target) + `PROJECT-HISTORY.md` (placeholder header). `tiktoken==0.12.0` already installed in `mcp/noctusai/.venv/` (declared in `requirements.txt` for cost_evaluation); no install needed. Smoke-test green: `archive/projects/2026-05-10/06-pf-metas-seed-wiring/PROJECT.md` = 5369 tokens (cl100k_base); chars/4 estimator 5347 (0.4% divergence — rough estimator is honest). Improvements logged. Phase 1 (schema + writer MCP tool) is a separate dispatch. | claude-opus-4-7 (engineer) |
| 2026-05-10 | **Phase 1 ✅ shipped.** Engineer in isolated worktree. Authored `mcp/noctusai/tools/noctus/dev/history.py` (MCP tool `noctus.dev.history_record`) + Pydantic schemas (`HistoryRecord`/`HistoryDates`/`HistoryPhase`/`HistoryTokenCount`, `extra="forbid"` for sibling consistency with archive.py) + 30 unit tests at `mcp/noctusai/tests/test_history.py` (all green). **N=2 tokenizer absorption applied**: extracted `mcp/noctusai/tools/_tokens.py` (shared `count_tokens_in_text` + `get_default_encoder` + cascade); `cost_evaluation.py` refactored to delegate (45 cost_evaluation + tiktoken + archive tests still green — confirms non-breaking). Smoke-stamped `archive/projects/2026-05-10/06-pf-metas-seed-wiring`: PROJECT.md=5369 tokens (matches Phase 0 exactly), proposals=3404 tokens, code_delta=840 tokens (git shortstat × 8 heuristic), total=9613 tokens, label=`tiktoken-cl100k_base`. Ledger reset to 0-byte empty marker after smoke-stamp (live ledger awaits Phase 2 close-protocol integration). Improvements logged. Phase 2 (close-workflow integration) is a separate dispatch. | claude-opus-4-7 (engineer) |
