# Build-learn-cache mindset (not only during dev)

> **The rule.** Every artifact we build or touch — component / page / functionality / integration / function / organ — accumulates KNOWLEDGE: known facts, errors encountered, drifts surfaced, alternatives considered and abandoned, manual validation feedback, integration test status, e2e test paths + status, bugs fixed during dev. **All of it gets CACHED alongside the artifact itself, in real-time AS WE BUILD** — and continues to accumulate during refactor / bug-fix / integration / deploy. The cache becomes the source of truth for "what we've learned about this thing." Future builders query the cache BEFORE building or modifying anything similar, see the accumulated journey, and avoid past mistakes.

This is the **DRY rule for artifact knowledge** — the third sibling that closes the recurrence-codification triad:

| Surface that recurs | Rule | Codified form | Anchor |
|---|---|---|---|
| **Code** (function / module / shape) | DRY — the recurrence rule | extract function / class / seed primitive | `KB § PATTERNS/architect/project-execution.md § 2.7` |
| **Procedure** (orient→act sequence) | Repetitive procedure → skill at N≥2 | `.claude/skills/noc-<verb-noun>/SKILL.md` skill | `KB § PATTERNS/common/repetitive-task-skill-codification.md` |
| **Methodology / doc / prose** (rule / discipline) | Methodology codification pipeline | KB pattern + CLAUDE.md §1 line + optional keeper | `KB § PATTERNS/common/methodology-codification-pipeline.md` |
| **Artifact knowledge** (component/page/integration/organ — facts + errors + drifts + alternatives + manual-validation + e2e + bugs-fixed) | **Build-learn-cache mindset** *(this doc)* | sidecar `<artifact>.knowledge.yaml` ∨ noc-graph node fields + `project-history/build-knowledge.ndjson` event | here |

The four rules cover four distinct kinds of recurrence — code, procedure, methodology, artifact-knowledge. Each has its own codified storage shape. Naming this fourth leg stops it from being silently lost in commit messages and transcripts.

---

## 1 · Why this rule exists

Today every artifact we build leaves a journey on the floor:
- The bug we hit in the third hour, fixed in the fourth, never recorded as "this integration's status_pagina row was missing and the page silently hid itself."
- The alternative we considered (TanStack Query vs. seed factory v2) and discarded — never written down, so the next builder reconsiders it from scratch.
- The user's manual report ("the dashboard renders blank when the org has zero leads") — buried in a single Slack message, then a single auto-improvement entry, but not attached to the dashboard component itself.
- The e2e test we wrote — pinned in CI, but no marker on the artifact saying "this is the path that proves you didn't break it."
- The drift we surfaced and resolved in-flight — captured in `auto-improvement.ndjson`, but not linked back to the artifact whose presence triggered it.

The result: every future agent re-discovers the same facts, re-considers the same dead alternatives, re-hits the same errors. The project-close `findings.md` (per `KB § PATTERNS/architect/project-execution.md`) catches some of this, but ONLY at project close — and only for PROJECT-scoped lessons, not for individual artifacts. The journey of the artifact itself stays uncached.

Naming **build-learn-cache mindset** as a first-class methodology rule names the missing storage shape: an artifact-scoped, queryable knowledge accumulator that lives WITH the artifact, populated WHILE we build (not only at wrap-up), and consulted BEFORE the next build of a similar artifact.

---

## 2 · The eight knowledge categories (the schema)

Every artifact's knowledge cache carries exactly these eight categories. Missing any one is incompleteness; the eighth-way (`bugs_fixed_during_dev`) is the recursive-proof category — the bugs found while building the cache itself land in the cache.

```yaml
# <artifact>.knowledge.yaml — sidecar OR node fields on the noc-graph node
artifact: <stable-ID e.g. seed-organs-cache:cache_path_resolver>
kind: component | page | integration | function | organ | hook | router | adapter
stage: building | shipped | refactor | bugfix | integration | deploy | stable
last_touched: 2026-05-29T18:00:00Z
last_touched_by: tech-lead | <agent-name>

# (1) What we KNOW about this artifact — load-bearing facts.
known_facts:
  - "Reads from `<git-common-dir>/noctusai/cache/*.sqlite` (Tier-1 local shared)"
  - "Falls back to pgvector via `cache_pull` when local empty AND NOCTUS_DISABLE_AUTO_CACHE_PULL≠1"
  - "All 11 cache-path resolution sites consolidated through `cache_backend.cache_path()`"

# (2) Errors hit during dev/refactor/bugfix — for the NEXT builder to avoid.
errors_encountered:
  - when: 2026-05-29
    error: "Per-worktree `.claude/cache/` caused 50-min pre-commit stall on fresh worktree"
    resolution: "Moved to `<git-common-dir>/noctusai/cache/` (shared by all worktrees)"
    avoidable_by: "Never propose per-worktree cache inheritance"

# (3) Drifts surfaced (the auto-improvement two-leg footer's `drift-found:` ledger,
#     indexed BACK to the artifact that triggered them).
drifts_surfaced:
  - drift: "Legacy `.claude/cache/*.sqlite` paths still hardcoded in 3 sites"
    surfaced_during: "cache-portable-architecture absorb"
    resolved: true
    resolution_commit: a99c7410

# (4) Alternatives considered + WHY abandoned (so the next builder doesn't re-litigate).
alternatives_considered:
  - alt: "Symlink-per-worktree to a shared file"
    rejected_because: "Git-aware tools follow symlinks inconsistently across macOS/Linux; WAL works without symlinks"
  - alt: "Per-worktree cache copies kept in sync via post-merge hook"
    rejected_because: "N copies × M caches = N*M files; stall guaranteed at scale"

# (5) Manual validation log — the user's real reports + agent's manual probes
#     (a hybrid of automated-test + human-observed).
manual_validation_log:
  - 2026-05-29:
      probe: "User: `cache_pull` from fresh worktree should not require OpenAI re-embed"
      result: "PASS — pulled 4726 rows verbatim from pgvector, ~0 OpenAI cost"
  - 2026-05-29:
      probe: "Pre-commit timing on fresh worktree (was 50min)"
      result: "PASS — now ~15s (auto-pull-on-empty)"

# (6) Integration test status — current pass/fail + last run.
integration_test_status:
  suite: tests/test_cache_backend.py
  last_run: 2026-05-29T17:42:00Z
  result: pass | fail | skipped
  failing: []

# (7) E2E test path + status — every artifact ships AT LEAST one e2e test path.
e2e_test:
  path: "tests/e2e/test_cache_portable_e2e.py::test_fresh_clone_bootstraps"
  last_run: 2026-05-29T17:42:00Z
  result: pass | fail
  triggers: ["push", "pre-merge", "weekly"]

# (8) Bugs fixed during dev — paired with the commit that fixed them.
#     Recursive: bugs found while populating this cache itself land here.
bugs_fixed_during_dev:
  - bug: "auto-pull defaulted OFF, fresh-clone agents thought caches were broken"
    fixed_commit: a99c7410
    fixed_by: tech-lead

# Cross-links into the noc-graph + existing ledgers.
related:
  noc_graph_node_ids: ["code:mcp/noctusai/cache_backend.py:cache_path"]
  auto_improvement_refs: ["2026-05-28T..."]
  kb_patterns: ["KB § PATTERNS/common/cache-portable-architecture.md"]
```

**Storage shape.** Two options compose:
1. **Sidecar file** `<artifact>.knowledge.yaml` next to a long-lived artifact (a component, a router, a seed module). Survives refactor, queryable by grep + `noctus.dev.unified_query`.
2. **noc-graph node fields + `project-history/build-knowledge.ndjson` event stream.** For short-lived or distributed artifacts (one logical "organ" spanning multiple files), the same eight categories materialize as fields on the noc-graph node + are appended as events to `project-history/build-knowledge.ndjson` (mirrors `auto-improvement.ndjson`). Future builders query `noctus.graph.query kinds=["artifact_knowledge"]` to find similar organs and see the journey.

Both shapes carry the same schema. Pick by lifespan: sidecar for stable artifacts, event-stream for emergent organs.

---

## 3 · Build-and-cache happens DURING dev, not after

The most common failure mode of the project-close findings absorption (per `KB § PATTERNS/architect/project-execution.md`) is the **wrap-up-only trap**: the agent waits until the project closes to absorb lessons, by which time 80% of the journey is forgotten. Build-learn-cache says: **log each significant finding in real-time, not at wrap-up**.

The dispatch brief carries the obligation (sibling of the scoped-auto-improvement two-leg footer). When the engineer's brief says "build organ X," the brief MUST also say:

> **Build-learn-cache obligation.** As you build, log each of the eight categories AS THEY APPEAR — don't batch them at wrap-up. The journey IS the knowledge. Use `noctus.dev.file_proposal kind="build-knowledge"` to append each finding, OR maintain a sidecar `<organ>.knowledge.yaml` on the worktree's branch. Both surfaces compose with the two-leg footer.

The wrap-up activity becomes a **completeness check** ("did we capture all eight categories for the four organs we touched?") not the capture activity itself. Wrap-up that's only-capture is wrap-up that loses 80% of the journey.

---

## 4 · "Not only during dev" — the tail

The rule's full name is **build-learn-cache mindset (not only during dev)** because the mindset extends to every artifact-touching context:

- **Refactor** — the refactorer learns NEW facts (the artifact was actually consumed by 6 sites, not 4), surfaces new drifts, considers and rejects alternatives. All eight categories get NEW entries timestamped to the refactor pass.
- **Bug-fix** — the bug is appended to `bugs_fixed_during_dev` WITH the resolution commit. The error that motivated the fix joins `errors_encountered`. Manual validation of the fix lands in `manual_validation_log`.
- **Integration** — when this artifact is wired into a new product/page/integration, the integration's outcome (a new fact about how it behaves under load X) joins `known_facts`.
- **Deploy** — production behavior (latency, failure modes, monitoring alerts) feeds back into `known_facts` and `errors_encountered`. The dev-prod-parity rule (`KB § PATTERNS/devops/dev-prod-parity.md`) becomes mechanizable: a known_fact at dev that doesn't replicate in prod IS a drift entry.

The cache is **append-only across the artifact's lifetime**, not just its initial build window. This is what makes it the source-of-truth: every touch leaves a trace, the trace is queryable, the next toucher inherits the full history.

---

## 5 · Worked example — this project IS the worked example

The `seed-organs-cache` project active this session (`projects/seed-organs-cache/PROJECT.md`) is the body-layer companion to this rule. The project builds an organ-knowledge cache as a seed primitive (the body); this rule codifies the methodology that explains WHY (the mind). The recursion is the proof:

- **The 8 knowledge categories above** are themselves the schema the project's body layer materializes. The schema lives here (KB methodology surface); the implementation lives in the seed (code surface). Both move together — code-DRY + methodology-DRY in lockstep.
- **The knowledge cached DURING this codification session** is itself an example: the user's surfacing language ("known facts, errors encountered, drifts surfaced, alternatives, manual validation, e2e, bugs fixed") IS an entry under this rule's own `known_facts`. The codification is its own first artifact.
- **The cache_backend.cache_path() consolidation work** (commits `a99c7410` + `7a303326`) was an organ that paid for itself once via the 50-min stall lesson. Had build-learn-cache existed then, the stall would have been a `bugs_fixed_during_dev` entry queryable by the NEXT person who proposed per-worktree caches — and they would have seen "rejected because of 50-min stall on fresh worktree" before re-proposing it.

The recursive proof: **this KB doc itself is an artifact that should carry the eight categories as it accumulates use.** A sidecar `build-learn-cache-mindset.knowledge.yaml` next to this file (or a noc-graph node) starts empty today and accumulates as future agents reference, refine, and extend the rule.

---

## 6 · Anti-patterns (what NOT to do)

1. **Wrap-up-only capture.** Absorbing knowledge only at project close loses everything that happened during dev — the third-hour bug, the alternative considered and rejected at hour five, the manual probe at hour seven. The wrap-up sweep (`noc-wrap-up`) is a **completeness check**, not the capture activity. If the only capture moment is wrap-up, 80% of the journey is forgotten. The N≥2 procedure rule sibling already says "log AS YOU GO"; this rule applies the same principle to artifact knowledge.

2. **Automated tests only.** Manual validation feedback ("the user said X works but Y silently shows zeros") is real signal, not noise. CI green + zero manual validation entries = blind spot the size of the user-facing surface. The hybrid (automated `integration_test_status` + `e2e_test` AND `manual_validation_log`) is non-negotiable.

3. **Cache the artifact, lose the journey.** Saving the final code without saving the *path that produced it* loses the most expensive part. Alternatives considered and rejected are 90% of dev cost; not caching them means the next builder pays them again. The journey IS the knowledge; the artifact alone is the residue.

4. **Knowledge in commit messages only.** Commit messages are linear, not indexed by intent. "What did we learn about the cache backend?" is not answerable from `git log` — it requires reading every commit message that touched any cache file and synthesizing. The cache (sidecar yaml OR noc-graph node fields) makes the same question one query.

5. **Per-session knowledge ledgers.** Recording learnings in a single session's findings.md and never absorbing them to the artifact's durable cache means knowledge dies with the worktree. The persistent-files-absorption rule (`KB § PATTERNS/common/persistent-files-absorption.md`) already says "absorb durable findings before teardown"; this rule extends it to per-artifact (not just per-project) granularity.

6. **One-shot e2e tests with no status field.** Writing an e2e test that ran once and was never checked again is half-shipped. The `e2e_test` block REQUIRES `last_run` + `result` + `triggers` — knowing when it last passed is what makes it source-of-truth.

---

## 7 · Composes with

- `KB § PATTERNS/architect/project-execution.md § findings absorption` — the project-close findings rule THIS extends. Build-learn-cache says: don't wait for project close, and don't aggregate at project granularity. Per-artifact + real-time.
- `KB § PATTERNS/common/repetitive-task-skill-codification.md` — sibling rule at the procedure layer. Together they form the recurrence-codification triad with code-DRY.
- `KB § PATTERNS/common/methodology-codification-pipeline.md` — the s1→s4 cadence this codification follows (this rule landed s3 same-commit via `force=True`).
- `KB § PATTERNS/architect/noc-graph.md` — the storage extension this lives in. New node kind: `artifact_knowledge`. New edge kinds: `learned_from` (artifact_knowledge → artifact), `surfaced_drift` (artifact_knowledge → auto_improvement entry).
- `KB § PATTERNS/common/scoped-auto-improvement.md` — the two-leg footer (`drift-found:` + `scoped-improvement:`) is the SOURCE STREAM that feeds `drifts_surfaced` + `bugs_fixed_during_dev`. Build-learn-cache indexes those entries BACK to the artifact that triggered them.
- `KB § PATTERNS/common/persistent-files-absorption.md` — same family (absorb durable findings before teardown); build-learn-cache extends granularity from project-scoped to artifact-scoped.
- `KB § PATTERNS/common/cache-as-agent-tool.md` — the meta-rule that makes this rule operational. The build-knowledge cache becomes one of the consultable caches future agents reach for BEFORE editing similar artifacts.
- `KB § PATTERNS/common/dispatch-with-project-and-notes.md` — the dispatch contract carries the build-learn-cache obligation in the brief; engineers log to the cache during dev, return delivery notes that include category-completeness.

---

## 8 · Stage status

- **Stage 1** (emergent) — surfaced by user 2026-05-29 ("build/refactor/bug-fix/etc.… every component / page / functionality / integration… known facts, errors, drifts, alternatives, manual validation, e2e, bugs fixed… cached alongside the artifact… not only during dev.").
- **Stage 2** (memory) — `feedback_build_learn_cache_mindset.md`.
- **Stage 3** (KB + CLAUDE.md + CONTEXTUALIZE.md) — **this doc** + the §1 one-liner + the §2 mirror. Same-commit s1→s3 compression via `codify_log force=True` (user explicit ask).
- **Stage 4** (keeper detector) — **deferred** to a follow-up. Candidate `check_artifact_has_knowledge_sidecar` (advisory; audits long-lived artifacts in `products/<slug>/` + `seed-lib/` for presence of a `<artifact>.knowledge.yaml` sidecar OR a corresponding `noc-graph` `artifact_knowledge` node). Stage-4 lands AFTER the seed-organs-cache project ships the body — the storage shape has to exist first.

**Sibling pending edit (flagged, not done here)**: `projects/seed-organs-cache/PROJECT.md` should add a section pointer to this KB doc — the project's body layer + this rule's mind layer compose. Tech-lead picks this up in `feat/seed-organs-cache-project-extend-blc` (NOT this slice — file-disjoint).
