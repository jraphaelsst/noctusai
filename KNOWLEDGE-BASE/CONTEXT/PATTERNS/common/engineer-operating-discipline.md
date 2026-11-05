# Engineer operating discipline — the senior engineer's craft, for every executor

**What it is.** How a dispatched engineer turns a brief into a change a reviewer can trust: understand the ask, plan the slice, prove behaviour test-first, change the code, review your own diff, commit in reviewable units, check the consumers of shared code, and know when you are done. It is the shared craft reference for every executor lens — `engineer-seed`, `backend-engineer`, `frontend-engineer`, `devops-engineer` — and for the tech-lead when it works inline.

**Why it exists.** The 2026-11-05 audit (`projects/agent-refinement/audits/audit-architect-engineer-seed.md`, agent-refinement project) found `engineer-seed.md` excellent as a *safety and integration* protocol (worktree, base, commit, no bypass, the return contract) and thin as a *craft* discipline. It did not say how to understand the ask, write the test first, keep a commit reviewable, review your own diff, or know you are done. The measured misses of the 2026-11-04 Sonnet trial are all craft misses, not safety misses (`KB § PATTERNS/architect/dispatch-engineer-tuning.md` §4·1, :89-93).

**How to use it.** `.claude/agents/engineer-seed.md` carries one line per rule with a pointer here; open the section when its situation arises. The house mechanism wins over the general canon. Git and integration **mechanics** — worktree, base check, branch pointer, `git add <paths>`, never push, `task_branch integrate` — are **not** restated here: they live in `engineer-seed.md` §1/§3/§4 and `KB § PATTERNS/architect/branching-and-merging.md`. This doc is the craft; those are the plumbing.

| Standard term | House term | Where the house version lives |
|---|---|---|
| requirements clarification | restate the ask + `interpretation:` return line | §2 here |
| vertical slice / small CL | file-disjoint slice | `engineer-seed.md` §2; §3 here |
| TDD, red-green-refactor | red-first | §4 here; `KB § PATTERNS/common/methodology-execution-discipline.md` §4, §8 |
| test double via dependency injection | test through the seam (never self-monkeypatch) | `KB § PATTERNS/compliance/testing.md` § No self-monkeypatching (:486); `KB § PATTERNS/backend/di-test-seam.md` |
| opportunistic refactoring | fix-on-contact (inside the slice) / `drift-found:` (outside) | §5 here; `KB § PATTERNS/common/drift-fix-on-contact.md` |
| author self-review | self-review as the reviewer | §6 here |
| small CLs, separate refactorings | tidy vs behaviour commits | §7 here |
| Conventional Commits → SemVer | commit subject + `!` / `BREAKING CHANGE:` | §7 here; `KB § PATTERNS/common/versioning.md` § Conventional Commits integration |
| Hyrum's law consumer check | consumer check before touching a seed/lib export | §5 here; `KB § PATTERNS/architect/architecture-craft-canon.md` §10 |
| Definition of Done | DoD checklist (mirrors `BEFORE_RETURNING_BLOCK`) | §8 here |
| definition of the integration | "done means committed" + the tech-lead's merged-tip gates | `engineer-seed.md` §3 |

---

## 1 · Scope — executor craft, not integration mechanics

In scope: everything between reading the brief and writing the return. Out of scope, by pointer only: worktree and base verification, the branch pointer, commit staging rules, the pre-commit hook, "prove it landed", never push, integration (`engineer-seed.md` §1, §3); dispatch knobs and brief shape (`dispatch-engineer-tuning.md` §4d); merge mechanics (`KB § PATTERNS/architect/branching-and-merging.md`).

---

## 2 · Understand the ask — restate it before the first edit

**Principle.** Most expensive rework comes from building the wrong thing well. Before writing code, restate what "done" means in your own words, and name each word that changes the meaning.

**House evidence.** The deciding gap in the 2026-11-04 same-brief A/B was one word: the brief said *latest* score rows; the Sonnet run averaged all of history, which made the feature's purpose — showing progress — invisible. Opus honoured the window (`dispatch-engineer-tuning.md` :80). The escalation rule now lists "semantics hidden in one word of the brief (a window, an ordering, 'latest', 'only', 'per X')" as trigger #1 (:83).

**Procedure.**
1. Read the brief and, for a project-scoped brief, the whole `projects/<slug>/PROJECT.md` — §4a is your row, its routes-not-taken are closed doors (`KB § PATTERNS/common/dispatch-with-project-and-notes.md`).
2. Restate the **Acceptance** in one or two sentences.
3. List every **load-bearing qualifier** and the interpretation you chose: *latest / newest* (by which timestamp? one row or a window?), *only* (exclusive of what?), *per X* (grouped by which key?), *ordering* (ascending by what, ties broken how?), *window* (inclusive bounds? timezone?), *all* (including asleep products? archived rows?), *each* (each product, each org, each call?).
4. State assumptions you are making that the brief does not settle.
5. If two interpretations lead to materially different code and the brief, PROJECT.md and the codebase do not decide between them, **stop and surface** (`noctus.dev.surface_to_tech_lead`; `KB § PATTERNS/common/surface-and-resume-tooling.md`). If one interpretation is clearly intended, proceed and record it.
6. Echo the result in the return as one `interpretation:` line (format in `engineer-seed.md` §4).

**Checklist.** Acceptance restated · qualifiers listed with chosen meaning · assumptions stated · ambiguity surfaced or resolved with a reason · `interpretation:` line written.

**Anti-patterns.** Coding from the goal sentence alone. Resolving an ambiguity silently in the cheaper direction. Asking about something the codebase answers (`CLAUDE.md` §1 "Codebase is source of truth").

---

## 3 · Plan the slice — smallest vertical increment, time-boxed

**Principle.** Google's *Small CLs* guide: the ideal change is "one self-contained change" that addresses just one thing — often a slice of a feature rather than the whole feature. Fowler's *Yagni*: do not build capability for a presumed future need.

**House rules (by pointer).** Touch only the brief's `Files-to-modify`; a needed extra file ⇒ STOP and surface (`engineer-seed.md` §2 "File-disjoint"). Time-box 2-3 h unless the brief says otherwise; over ⇒ ship a focused subset and **name what was deferred and why** — never shrink silently (`engineer-seed.md` §2 "Time-box").

**Procedure.**
1. Find prior art first — cache-first (`noctus_dev_{kb,code,memory}_search`, `noctus_graph_*`, `keeper_pattern_lookup`), then confirm with grep/Read. A correct fix for a solved problem ships as a fork (`methodology-execution-discipline.md` §5).
2. Write the plan as an ordered list of steps, each ending in something you can run.
3. Order: test that fails → smallest change that passes → tidy → docs → wire.
4. Note what you will **not** do; that list becomes the deferred-with-reason line if the time-box bites.

**Anti-patterns.** Designing a mechanism before searching for the existing one. Widening scope to fix something adjacent without surfacing it. A plan whose first runnable step is at the end.

---

## 4 · Test-first where it fits — red first, through the seam

**Principle.** Fowler's *TestDrivenDevelopment*: write a failing test, make it pass, refactor. *SelfTestingCode*: a suite you trust enough that a green run means the code works. Vocke's *Practical Test Pyramid* and *Software Engineering at Google* ch. 11-12: many small fast tests, fewer large ones; test behaviour through public interfaces, not implementation details.

**House rules.**
- **A bug gets a failing test before the fix.** The test must fail on the pre-fix code and pass on the fix (`KB § PATTERNS/compliance/testing.md` § Regression tests in practice, :243-262, trigger #1).
- **A guard is proven by watching it refuse.** Break the guarded property and watch the guard fail, then restore (`methodology-execution-discipline.md` §4 "Prove the check can FAIL", :31-54; §8 "a guard is verified only by observing it REFUSE", :379). A new keeper ships its `Test<DetectorCamel>` class (`check_detector_has_regression_test`).
- **Test through the seam; never patch our own module.** `monkeypatch.setattr(<our_module>, …)` / `patch.object(<our_module>, …)` neuter the logic the test claims to verify. Use dependency injection (default), the `inserted_payloads` read side, or patch only an *external* boundary (`testing.md` :486-605; `di-test-seam.md` § The fix). Gated at write time by the `test_seam_guard` PreToolUse hook and at commit by `check_no_self_monkeypatch` (`CLAUDE.md` §1). This was the most frequent measured Sonnet miss — 3 of 12 slices (`dispatch-engineer-tuning.md` :90).
- **Auth tests assert strict `== 401`** — never `in (401, 404|422)` (`KB § PATTERNS/compliance/auth-boundary-false-green.md`; `check_auth_boundary_false_green`).
- **Pin the status code, not just the body** (`testing.md` § Status-code-assertion rule, :417).

**When strict TDD does not fit** (exploratory UI, configuration, a spike): you still owe a proof that the check can fail. For UI, a vitest that fails when the state is wrong (loading, empty, error, success); for config, a keeper or test that goes red on the bad value; for a spike, label it as a spike and do not merge it as product code.

**Test sizes.** Prefer the smallest test that exercises the behaviour: a unit test through the seam, a router test with seeded mock data (`testing.md` § Picking the pattern, :587), and only then an integration or browser test.

**Anti-patterns.** A test written after the fix that would also pass on the broken code. A guard that has only ever been run, never seen to fail. A test that patches the function it is testing. A green suite that cannot go red.

---

## 5 · Make the change — fix-on-contact inside, `drift-found` outside, consumers first

**House rules (by pointer).** AST-first for anything a parser reads (`KB § PATTERNS/common/ast.md`); MCP toolkit first, and new automation is a `noctus.dev.*` tool (`KB § PATTERNS/architect/mcp-first-scripts.md`); heavy runs go through the hardware gate (`KB § PATTERNS/devops/hardware-admission-budget.md`).

**Fix-on-contact vs file-disjoint.** These two rules look like they conflict. They don't — the slice boundary decides:
- A defect **inside** your slice's files, or one your change trips over: fix it (Fowler, *OpportunisticRefactoring*), in **its own commit** (§7), and mention it in `scoped-improvement:`.
- A defect **outside** your slice's files: do not touch it; report it as one `drift-found:` line with evidence (`KB § PATTERNS/common/scoped-auto-improvement.md`).

**Consumer check before touching a seed or lib export (Hyrum's law).** "With a sufficient number of users of an API … all observable behaviors of your system will be depended on by somebody" (hyrumslaw.com). Before you change an exported seed/lib symbol, a seed default, a shared SQL function or a shared route shape:
1. List the consumers — `noctus.graph.neighbors` / `noctus.dev.refs` / `code_search`. Do not guess.
2. Prefer **additive** (new symbol, new optional kwarg with the old default). Additive seed exports caused zero non-pilot breakage in the evidence behind the pilot rule (`KB § PATTERNS/architect/project-execution.md` §2.12, :625).
3. If it cannot be additive, apply **expand → migrate → contract** (`architecture-craft-canon.md` §10), and say which step this commit is.
4. Validate on the pilot products before fan-out (`project-execution.md` §2.12, :619); a non-pilot adaptation is a later wave, never a half-done edit left in the tree.
5. Mark a breaking change in the commit (§7).

**Wire what you add.** A capability is not done until the system can reach it:

| You added | Wire it to | Evidence of the miss |
|---|---|---|
| a `check_*` keeper | the hook or CI step that runs it, plus its regression test | "shipping a keeper without wiring it into a hook" (`dispatch-engineer-tuning.md` :92); `check_guard_hooks_registered` |
| an MCP tool parameter | `toolkit_freshness._MAPPED_PARAMS` (`mcp/noctusai/tools/noctus/dev/toolkit_freshness.py` :491) | "adding a tool param without registering it" (:93) |
| a CLI capability | its `cli.py` flag | — |
| a gate | its compliance-by-construction mechanism | `KB § PATTERNS/common/gate-methodology-sync.md` |
| a seed IO module | Fake + Real + factory | `KB § PATTERNS/backend/seed-fake-real-adapter.md` |
| a hook in a page | its stub in the page's test harness | ImovelDetalhes, §11.2 |
| a KB doc | its `KB § INDEX.md` row (and owner `owns_kb:` or the unowned allowlist) | `kb_sync`, `check_agent_kb_alignment` |

---

## 6 · Self-review — read your diff as its reviewer would

**Principle.** Google's reviewer guide, *What to look for in a code review*, names: **design, functionality, complexity, tests, naming, comments, style, consistency, documentation, every line, context, good things**. The author who checks these before asking is the reviewer's best friend (Google *Developer guide*; *Software Engineering at Google* ch. 9). The reviewer standard is "code health improves", not "perfect".

**Procedure.** Run `git diff origin/dev...HEAD` (or `git -C <wt> diff` before committing) and read every line, then walk this list:

| Item | Ask |
|---|---|
| Design | Does this belong here? Is there a seam or organ that already does it (4-question test, `KB § 03-SEED-ARCHITECTURE.md` :51)? |
| Functionality | Does it do what the restated ask says — every qualifier (§2)? Edge cases: empty, one, many, missing, duplicate, concurrent? |
| Complexity | Could a reader understand it quickly? Anything built for a future need (Yagni)? |
| Tests | Did a test fail before the change? Does each test fail if the behaviour breaks? Through the seam? |
| Naming | Do names say what, in the context's language (pt-BR domain terms stay pt-BR)? |
| Comments | Do comments explain **why**, not what? No stale comment left above changed code? |
| Leftovers | No `print` / `console.log`, commented-out code, TODO without a `NOC-REMEDIATE[<class>]` marker (`KB § PATTERNS/common/remediation-markers.md`), unused import, debug flag? |
| Errors | No `except: pass`, no silent fallback (`check_silent_errors`; `KB § 01-PHILOSOPHY.md` no silent errors)? |
| Docs | Every doc the change makes stale updated in the same commit (`KB § PATTERNS/common/doc-staleness-gate.md`)? |
| Wiring | Everything added is reachable (§5 table)? |
| Late rename | Renamed anything after the last test run? **Re-run the tests** — "not re-running tests after a last-minute rename" is a measured miss (`dispatch-engineer-tuning.md` :91). |

**Anti-patterns.** Reviewing the plan instead of the diff. Skimming generated or "trivial" files. Treating a green hook as a review.

---

## 7 · Commits — small, reversible, and they say why

**Principle.** Google *Small CLs*: "It's usually best to do refactorings in a separate CL from feature changes or bug fixes." Beck (*Tidy First?*): separate **tidyings** (structure changes that do not alter behaviour) from **behaviour changes**, so each is easy to review and to revert. Beams, *How to Write a Git Commit Message*: separate subject from body with a blank line, keep the subject short, imperative mood, no trailing period, wrap the body at 72, and use the body to explain **what and why** rather than how. Conventional Commits 1.0.0: `type(scope): description`; a breaking change is marked by `!` immediately before the `:` and/or a `BREAKING CHANGE: <description>` footer, and correlates with a SemVer MAJOR.

**House rules.**
- Subject: Conventional Commits, lower-case type, house style `feat(scope): …` (`engineer-seed.md` §3). The Conventional Commits prefix wins over Beams' "capitalize the subject"; the other Beams rules apply as written.
- One logical change per commit. Several commits per slice is normal.
- **Tidy and behaviour in separate commits.** A rename, a move or an extract goes first, with no behaviour change, then the behaviour commit. A fix-on-contact inside the slice gets its own commit (§5).
- **The body says why.** Two or three lines: the problem, the cause, why this fix. The diff already says how.
- **Breaking change**: `feat(seed)!: …` and/or a `BREAKING CHANGE: <what consumers must do>` footer. That is the input to the version bump (`KB § PATTERNS/common/versioning.md` § Conventional Commits integration; source of truth `/VERSION`).
- Trailers: the attribution trailer the brief names; `Docs-Reviewed: <doc> — <why still accurate>` when a doc the staleness gate lists is still correct (`doc-staleness-gate.md`).

**Example (shape, not a real commit).**

```
refactor(finance): extract settlement amount rounding into _round_cents

No behaviour change; prepares the installment-interest fix.

fix(finance): book installment interest as its own receivable

The DRE needs interest on its own line and the Simples base always counts
it; booking it inside the principal hid it from both.
```

**Anti-patterns.** "wip", "fix stuff", "address review". A behaviour change hidden in a formatting commit. A breaking seed change with no `!` or footer. A body that narrates the diff.

---

## 8 · Definition of Done — one checklist

**Principle.** The Scrum Guide calls the Definition of Done "a formal description of the state of the Increment when it meets the quality measures required for the product" — work that does not meet it is not part of the increment. One shared list, applied every time, beats per-task judgment.

**The house DoD.** The mandatory core is the `### Before returning` block, whose single source of truth is `BEFORE_RETURNING_BLOCK` in `mcp/noctusai/tools/noctus/dev/engineer_brief_compose.py` (:415). Read it there; this list **references** it and adds the craft items around it. It does not copy it, because a copy drifts: on 2026-11-05 `engineer-seed.md` §3 listed three items while the composer had four.

A slice is done when:
1. **Acceptance met**, as restated (§2), with every qualifier honoured.
2. **Interpretation stated** — the `interpretation:` return line.
3. **Red-first evidence** — a failing-then-passing test for a bug, a seen-to-refuse proof for a guard (§4).
4. **`BEFORE_RETURNING_BLOCK` satisfied** — every item in the composer's block (full suite of each touched product/package; doc-staleness clean from the worktree — `--check-doc-staleness --doc-range origin/dev..HEAD`, each listed doc updated or carried by a `Docs-Reviewed:` trailer, and note that `kb_sync` / `--verify-kb-sync` is a different check; detector regression test when a `check_*` was added; everything committed and the commands reported).
5. **Self-review done**, including the re-run after any late rename (§6).
6. **Docs updated** in the same commit as the code they describe.
7. **Wired** — everything added is reachable (§5 table).
8. **Committed and landed** — `git -C <wt> show --stat HEAD` lists your files (`engineer-seed.md` §3 "Prove it landed"; "Done means committed").
9. **Return legs written** — `codification-events`, `drift-found`, `scoped-improvement` present even when clean, because absence is a positive claim (`engineer-seed.md` §4; `KB § PATTERNS/common/scoped-auto-improvement.md`).

---

## 9 · Reporting — honest status

- `Status: ready` only when the DoD holds. `partial` when a subset shipped — name the deferred part and why. `blocked` when you stopped to surface.
- Report the commands you ran and their result counts, not "tests pass". A verdict you read from a pipe's tail or a watcher is not the verdict of the command you were judging (`methodology-execution-discipline.md` §6).
- A red from an invalid harness (missing deps, dead dev-server, stale tree) is evidence about the setup, not your code — say so (`methodology-execution-discipline.md` §10).
- Not clean ⇒ the 5-category block (Errors · Mistakes-slips · Lessons · Interesting · Knowledge) + an architect-followup line (`engineer-seed.md` §4).

---

## 10 · Measured-misses ledger

The trial behind Sonnet-by-default recorded these recurring executor misses (`dispatch-engineer-tuning.md` §4·1, :89-93). Each is pre-empted by a section of this doc:

| Measured miss | Pre-empted by |
|---|---|
| semantics hidden in one word ("latest") | §2 restate the qualifiers |
| patching our own module attributes in tests even when a seam exists (3 of 12 slices) | §4 test through the seam |
| not re-running tests after a last-minute rename | §6 late-rename row |
| shipping a keeper without wiring it into a hook | §5 wire what you add |
| adding a tool param without registering it in `toolkit_freshness._MAPPED_PARAMS` | §5 wire what you add |

The ledger is live, not frozen: `noctus.dev.engineer_brief_compose` renders a `### Your recent misses (do not repeat)` block per agent from open auto-improvement rows and the weakest RUBRIC_V1 dimensions in `slice-scores.ndjson` (`dispatch-engineer-tuning.md` §4d). Read that block first; it is about you.

---

## 11 · Worked examples

### 11.1 "Latest score rows" — restate the qualifier

**Brief (paraphrased from the trial).** Show each agent's progress from its *latest* score rows.

**What happened.** The Sonnet run averaged every row in `slice-scores.ndjson`; the result was a mean that barely moved, so the feature could not show progress. The Opus run read *latest* as a recent window and the trend became visible (`dispatch-engineer-tuning.md` :80).

**With §2 applied, before the first edit:**

```
Acceptance: per agent, a progress view whose numbers move when recent slices improve.
Qualifiers:
  latest  -> the N most recent rows per agent by timestamp (N from the brief, else surface),
             NOT all history; ties by ts then slice id
  per X   -> per agent name as recorded in the row
Assumption: rows with no timestamp are excluded and counted in a warning, not silently dropped.
interpretation: "latest" = last N rows per agent by ts; all-history mean rejected because it hides the trend.
```

The return's `interpretation:` line lets the reviewer catch a wrong reading in one line instead of in the diff.

### 11.2 ImovelDetalhes page harness — scoped green, full-suite red

**What happened (2026-10-24).** A social-wiring slice added four hooks to the ImovelDetalhes page (`useDescricaoImovel`, `useConfirmarDescricaoImovel`, `useSalvarCertidaoManual`, `useRemoverCertidaoManual`). The slice's own tests passed. The page's test harness renders without a `QueryClient` and stubs each hook it knows about. The new hooks had no stubs, so 13 tests threw "No QueryClient set", and `dev` went red in CI. Fix commit `bcbbbf7b6` (`products/social-wiring/frontend/src/pages/ImovelDetalhes.test.tsx`, +5 lines).

**Lesson.** A scoped check proves your change; only the full suite of the touched product proves you did not break a neighbour that depends on you. That is why DoD item 4 (via `BEFORE_RETURNING_BLOCK`) requires the full `vitest run` / `pytest` of every product or package you touched, and why `task_branch integrate` re-runs touched-product vitest on the merged tip (commit `00e68fc93`). It also adds a row to the §5 wiring table: a hook added to a page is wired only when the page's harness stubs it.

### 11.3 A self-monkeypatched test refactored to the DI seam, red first

**Before** (illustrative — the shape `check_no_self_monkeypatch` flags; `testing.md` :486-490):

```python
def test_session_end_happy_path(monkeypatch):
    monkeypatch.setattr(ai_pipeline, "assemble_transcript", lambda *a, **k: "ok")   # our own module
    result = asyncio.run(ai_pipeline.process_session_end("appt-001", db=db))
    assert "summaries" in result
```

The test passes even if `process_session_end` never calls the transcript step correctly, because the step was replaced.

**Refactor** (Pattern 1, `testing.md` :492-530; reference adopter `products/therapy-platform/backend/app/services/ai_pipeline.py`):

```python
# production: the dependency is a kwarg that defaults to the real one
async def process_session_end(appointment_id, db, *, core_db=None, transcribe=None):
    core_db = core_db or get_core_client()
    transcribe_fn = transcribe or transcription_service.assemble_transcript
    ...

# test: inject, never patch
async def test_process_session_end_happy_path():
    async def fake_transcribe(*_a, **_kw):
        return "Transcrição completa."
    result = await ai_pipeline.process_session_end("appt-001", db=db, core_db=db, transcribe=fake_transcribe)
    assert "summaries" in result
```

**Red first.** Before trusting the new test, break the behaviour on purpose — make `process_session_end` skip the transcript, or seed bad data — and watch the test fail. Then restore it (`testing.md` § Refactor procedure step 5, :597-605; `methodology-execution-discipline.md` §4). Commit the production kwarg as a tidy commit, then the test change, and re-run the keeper to confirm the count dropped (step 6).

---

## 12 · Anti-patterns

- Coding before restating the ask; resolving ambiguity silently.
- A test that cannot fail; a test that patches the code under test.
- "Works on my scoped run" reported as done.
- Fixing outside the slice without surfacing; leaving inside-slice debt unfixed and unreported.
- Changing a seed export without a consumer list.
- A behaviour change hidden in a tidy commit; a commit body that narrates the diff.
- Adding a capability nobody can reach (unwired keeper, unregistered param, unstubbed hook).
- Copying `BEFORE_RETURNING_BLOCK` into another doc instead of pointing at it.
- `Status: ready` with uncommitted work, or with any of the three return legs missing.

---

## Sources

Accessed 2026-11-05. Each URL was fetched and confirmed for the agent-refinement audit (`audits/audit-architect-engineer-seed.md` § Sources); those marked ✅ were re-fetched while writing this doc.

- Google eng-practices, *The CL author's guide to getting through code review* — https://google.github.io/eng-practices/review/developer/ — author guide (§6).
- Google eng-practices, *Small CLs* — https://google.github.io/eng-practices/review/developer/small-cls.html — one self-contained change; refactorings in a separate CL (§3, §7). ✅
- Google eng-practices, *Writing good CL descriptions* — https://google.github.io/eng-practices/review/developer/cl-descriptions.html — the description says why (§7).
- Google eng-practices, *The standard of code review* — https://google.github.io/eng-practices/review/reviewer/standard.html — code health improves, not perfection (§6).
- Google eng-practices, *What to look for in a code review* — https://google.github.io/eng-practices/review/reviewer/looking-for.html — the self-review items (§6). ✅ (fetched for this doc; not in the audit list)
- *Software Engineering at Google*, ch. 9 Code Review — https://abseil.io/resources/swe-book/html/ch09.html (§6).
- *Software Engineering at Google*, ch. 11 Testing Overview — https://abseil.io/resources/swe-book/html/ch11.html (§4).
- *Software Engineering at Google*, ch. 12 Unit Testing — https://abseil.io/resources/swe-book/html/ch12.html (§4).
- Conventional Commits 1.0.0 — https://www.conventionalcommits.org/en/v1.0.0/ — `!` and `BREAKING CHANGE:` correlate with SemVer MAJOR (§7). ✅
- Semantic Versioning — https://semver.org/ (§7).
- Chris Beams, *How to Write a Git Commit Message* — https://cbea.ms/git-commit/ — the seven rules (§7). ✅
- Martin Fowler, *TestDrivenDevelopment* — https://martinfowler.com/bliki/TestDrivenDevelopment.html (§4).
- Martin Fowler, *SelfTestingCode* — https://martinfowler.com/bliki/SelfTestingCode.html (§4).
- Ham Vocke, *The Practical Test Pyramid* — https://martinfowler.com/articles/practical-test-pyramid.html (§4).
- Martin Fowler, *OpportunisticRefactoring* — https://martinfowler.com/bliki/OpportunisticRefactoring.html — fix-on-contact (§5).
- Kent Beck, *Tidy First?* newsletter — https://tidyfirst.substack.com/ — tidy vs behaviour separation (§7). Book: Kent Beck, *Tidy First?*, O'Reilly, 2023, ISBN 978-1-098-15124-9.
- Scrum Guide — https://scrumguides.org/scrum-guide.html — Definition of Done (§8). ✅
- Martin Fowler, *Yagni* — https://martinfowler.com/bliki/Yagni.html (§3).
- Martin Fowler, *TechnicalDebtQuadrant* — https://martinfowler.com/bliki/TechnicalDebtQuadrant.html — deliberate vs inadvertent debt; the lens for fix-on-contact vs `drift-found:` (§5).
- Hyrum's Law — https://www.hyrumslaw.com/ (§5). ✅

## Composes with

`.claude/agents/engineer-seed.md` (the protocol that points here) · `KB § PATTERNS/architect/dispatch-engineer-tuning.md` (the measured misses and the brief composer) · `KB § PATTERNS/common/methodology-execution-discipline.md` · `KB § PATTERNS/compliance/testing.md` · `KB § PATTERNS/common/gate-methodology-sync.md` · `KB § PATTERNS/common/versioning.md` · `KB § PATTERNS/architect/architecture-craft-canon.md` (the architect's half: reversibility, expand/contract, fitness functions).
