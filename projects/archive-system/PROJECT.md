# archive-system — Project Document

> **This is a living document, not a rigid checklist.**
> As we build and learn, this project evolves. Revise phases, fold in optimizations, update §11.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** Filed → Phase 1 (archive folder bootstrap) ready
- **Owner / stakeholder:** rapha (joaoraphaelsst@gmail.com)
- **Related docs:** `KB § PATTERNS/project-execution.md § 11 Clean-folder principle` (current "delete on close" rule being amended), `KB § PATTERNS/project-execution.md § 11.1 Features` (closure section being amended), `feedback_no_auto_commit.md` (mentions "after folder deletion" — needs amendment), `feedback_apply_inline_delete_proposals.md` (apply-inline-then-delete pattern — extends to apply-inline-then-archive), `feedback_no_silent_errors.md` (archive must be visible, never silent).
- **Project slug:** `archive-system` — cross-cutting / platform methodology project per `KB § PATTERNS/project-execution.md §1`. Lives at root `projects/<slug>/`.
- **Branch:** `archive-system` (per "branch this request" trigger order).

---

## 1. Context & Purpose

Today's closure methodology auto-deletes deliverables when projects/features close. Per the apply-inline-then-delete pattern (`feedback_apply_inline_delete_proposals.md`) and the project-close gate (`feedback_no_auto_commit.md`), the project folder gets `git rm -r`'d as the last step. The deleted content lives in git history but is not browseable as filesystem state.

User directive 2026-05-03, verbatim:
> *"lets also change our project post-deliver deletion, instead of deleting it, they should be moved to root/archive/projects/<today>/{01-project, 02-project,...}, same for features, they should be moved to root/archive/features/<today>/{01-feature, 02-feature,...} and the same pattern for everything that gets auto-deleted. Not when explicitly asked for deletion, then it should be deleted. But this archive system also works when i ask explicitly to archive something. if doesnt already have a stablished pattern-folder, archive on root/archive/<date time name> as is. branch this request and handle 100%"*

**Two threads in the directive:**

1. **Auto-archive on close** — projects → `archive/projects/<today>/<NN>-<slug>/`; features → `archive/features/<today>/<NN>-<slug>.md`; same pattern for any other auto-deleted artifact.
2. **Explicit-archive command** — when user explicitly asks to archive something (project, feature, ad-hoc artifact), use the same archive system. Ad-hoc (no established category) → `archive/<datetime>_<name>/` as-is.

**Carve-out**: explicit deletion stays as deletion. The auto-archive replaces auto-deletion only.

The win: closed work is browseable on filesystem (faster than `git log` archaeology); chronological ordering by close date is preserved; `<NN>-<slug>` numbering captures within-day sequence. No content is lost. Aligns with `feedback_safety_nets_become_learnings.md` — closing isn't erasure; it's preservation.

---

## 2. Confirmed constraints

- **Auto-deletion → auto-archive (NOT silent change).** Every place that currently `git rm -r`'s a closed deliverable becomes a `git mv` to the archive location. The methodology amends, not replaces; the archive lifecycle has the same close-gate semantics. *(Drives §6 Phase 2 + Phase 4.)*
- **Explicit deletion is preserved.** When the user says "delete X" / "remove X", that's deletion — not archive. Archive is the new auto-default; deletion is the explicit override. *(Drives §3 principle 2.)*
- **Archive is git-tracked.** The archive folder lives in the repo; archived content is committed. `archive/` is NOT gitignored. The point is browseable + searchable + version-controlled archives, not local-only retention. *(Drives §6 Phase 1.)*
- **Numbering is per-day-incrementing.** First archived project on a given day is `01-<slug>`; second is `02-<slug>`; etc. Resets daily. Preserves within-day chronological order without timestamp clutter on every name. *(Drives §6 Phase 4 — the MCP tool computes NN.)*
- **"Branch this request and handle 100%"** — *user directive*. Branched first per the new trigger order; project filed; all phases executed in this session; orchestrator merge to main at close. *(Drives §6 cadence.)*

---

## 3. Design principles

1. **Archive is a `git mv`, not a delete + create.** Preserves git history for the archived content. `git log --follow archive/projects/2026-05-03/01-foo/PROJECT.md` walks back through the project's full life.
2. **Explicit deletion is the override, not the default.** The user's "delete" intent must be unambiguous in the request. Default-archive prevents accidental loss; explicit-delete preserves the user's right to actually delete.
3. **The archive itself is browseable + structured, not a junkyard.** Date folders, numbered prefixes, predictable categories. Future-you (or another agent) browsing `archive/projects/2026-05-03/` should immediately see what closed that day in what order.
4. **One MCP tool, multiple modes.** `noctus.dev.archive(target, mode="project|feature|ad_hoc")` — auto-detects category from path when mode is omitted. Cleaner than three sibling tools; matches the convention of single-purpose dev tools with multiple call shapes.
5. **No retroactive archive.** Previously-deleted projects' content lives in git history; we don't restore-and-move them. The archive system applies forward from this project's close.

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

1. **Is the contract identical for every product?** N/A — this is platform-level methodology + tooling, not product code.
2. **Is the data source product-specific?** N/A.
3. **Is the placement product-specific?** N/A. The archive is a single repo-root folder.
4. **Is the visibility / permission rule the same?** N/A.
5. **Does the seam already exist in seed?** No — this is dev-toolkit + KB methodology territory.
6. **Default-on or opt-in?** **Default-on once landed.** The archive replaces auto-delete platform-wide.

**Litmus — per-product code count this design requires:** [x] **0 lines** in any `products/<x>/` tree. All work lands in `archive/` (new top-level folder), `mcp/noctusai/tools/noctus/dev/`, `KNOWLEDGE-BASE/`, `CLAUDE/`, agent memory.

**Phase plan implications:** §6 phases work in repo-root folders + dev toolkit + KB + CLAUDE. **No phase walks through products.** Correct shape.

---

## 4. Scope

**In scope:**

- Phase 1 — Archive folder bootstrap (`archive/` + `archive/projects/.gitkeep` + `archive/features/.gitkeep` + `archive/README.md`).
- Phase 2 — Methodology amendments in KB + CLAUDE: `KB § PATTERNS/project-execution.md § 11` (clean-folder principle becomes "clean-folder + archive-on-close"); §11.1 features closure rule amended; §0 execution workflow amended; CLAUDE/projects.md commit-cadence + features bullets amended.
- Phase 3 — Memory updates: amend `feedback_no_auto_commit.md` (close-gate is archive, not delete); amend `feedback_apply_inline_delete_proposals.md` (becomes apply-inline-then-archive for closure deliverables; apply-inline-then-delete still applies to proposal files); amend `feedback_features_methodology.md` closure section; new `feedback_archive_system.md` covering the system end-to-end.
- Phase 4 — MCP tool `noctus.dev.archive` (Pydantic schema, mode param: project | feature | ad_hoc; auto-numbering for date folders; `git mv` under the hood). Plus CLI access via existing cli.py wrapping.
- Phase 5 — Tests for the archive tool: numbering correctness, date-folder creation, ad-hoc category, git-mv preservation, idempotent re-archive guard.
- Phase 6 — Project close: this project's own close uses the new archive system (canonical first dogfood). Orchestrator merge to main.

**Out of scope (for now — with reason):**

- **Retroactive archive of previously-deleted projects.** Their content lives in git history; restoring-and-archiving them is significant work for low value. The system applies forward.
- **Compression / archival cleanup beyond a date threshold** (e.g. "archives older than 1 year get tarred up"). Future concern; not needed at v1.
- **Cross-machine archive sync** (e.g. shared S3 bucket of archives). The archive is git-tracked already; remote repo IS the cross-machine shared state.
- **Archive search tooling** (e.g. an MCP tool that searches across archived projects). Future enhancement; for now `grep -r archive/` works.
- **Per-product archives** (`products/<x>/archive/`). Single repo-root archive is simpler; products can move closed product-scoped projects under the root archive's `projects/` category.

---

## 5. Architecture / Data Model

### 5.1 Archive folder structure

```
archive/                        ← NEW top-level folder; git-tracked.
├── README.md                   ← documents the archive convention; brief.
├── projects/                   ← category: closed projects.
│   ├── .gitkeep                ← empty days don't need to exist; .gitkeep ensures the dir is in git.
│   └── <YYYY-MM-DD>/           ← per-day folder; created on first archive of that day.
│       ├── 01-<project-slug>/
│       │   ├── PROJECT.md
│       │   └── proposals/      ← preserved as-is from project folder.
│       ├── 02-<project-slug>/
│       │   └── ...
│       └── ...
├── features/                   ← category: closed features (single .md files).
│   ├── .gitkeep
│   └── <YYYY-MM-DD>/
│       ├── 01-<feature-slug>.md
│       ├── 02-<feature-slug>.md
│       └── ...
└── <YYYY-MM-DD>_<HH-MM-SS>_<name>/   ← ad-hoc archive (no established category).
    └── <whatever was archived>
```

### 5.2 Numbering convention

- Per-day, per-category. `<NN>-<slug>` where `NN` is zero-padded 2-digit incrementing from `01`.
- First archive of a given day in a category → `01-<slug>`. Second → `02-<slug>`. Etc.
- Resets daily (next day starts at `01-` again).
- The MCP tool computes the next NN by listing the date folder and finding `max(NN) + 1`.
- 99 archives in one day in one category is a soft cap (3-digit numbering kicks in at 100 if needed; unlikely to hit).

### 5.3 Date / time format

- **Date folder**: `YYYY-MM-DD` (ISO-8601 short form). Sortable lexicographically.
- **Ad-hoc datetime prefix**: `YYYY-MM-DD_HH-MM-SS_<name>`. ISO date + underscore + zero-padded 24h time with dash separators (filesystem-safe) + underscore + descriptive name.
- All times in local timezone (the repo's working timezone — `America/Sao_Paulo` per `noctusai_lib.api.scheduler` convention). Not UTC; the human-readable date matters more than UTC strict ordering for archive purposes.

### 5.4 MCP tool — `noctus.dev.archive`

Pydantic-free direct args (per the dev umbrella convention — see `KB § PATTERNS/mcp-tool-conventions.md` + memory `feedback_branching_methodology.md` Phase 3-4 learning):

```python
def _archive(
    target_path: str,                     # path to the project folder, feature .md, or ad-hoc artifact (relative to repo root or absolute)
    mode: str | None = None,              # "project" | "feature" | "ad_hoc" | None (auto-detect)
    name: str | None = None,              # ad-hoc only — the descriptive name in <date>_<time>_<name>; ignored for project/feature
) -> dict:
    """Move the target to the archive folder per the archive system.

    Returns:
        {
          "archived_to": "<archive/relative/path>",
          "mode": "project|feature|ad_hoc",
          "next_NN": 3,   # for project/feature mode; null for ad_hoc
        }
    """
```

**Auto-detect rules:**
- `target_path` ends in `PROJECT.md` OR is a directory containing `PROJECT.md` → `mode=project`.
- `target_path` ends in `.md` AND lives under `features/` or `products/<x>/features/` or `core/features/` → `mode=feature`.
- Else → `mode=ad_hoc` (requires explicit `name` param).

**Idempotency guard:** if `target_path` already lives under `archive/`, refuse — return `{"error": "already archived"}`. Don't archive an archive.

**Implementation:** `pathlib` for path manipulation; `subprocess.run(["git", "mv", src, dst])` for the actual move (preserves history). Date computed from `datetime.now(tz=ZoneInfo("America/Sao_Paulo")).date()`; ad-hoc time from same `.strftime("%H-%M-%S")`.

### 5.5 Methodology amendments needed

| Doc | Section | Current | Amended |
|---|---|---|---|
| `KB § PATTERNS/project-execution.md` | §0 execution workflow | "PROJECT CLOSE (folder deletion → final commit + push as the literal last step)" | "PROJECT CLOSE (folder ARCHIVE via `noctus.dev.archive` → final commit + push as the literal last step)" |
| `KB § PATTERNS/project-execution.md` | §11 Clean-folder | "A completed project's folder is not auto-deleted. The PROJECT.md + improvements.md are the durable record. The folder lives on..." | Amend to: "A completed project's folder is auto-ARCHIVED on close per `KB § PATTERNS/archive-system.md` (or §11.2). Archive ≠ delete; content moves to `archive/projects/<today>/<NN>-<slug>/` and remains git-tracked + browseable. Explicit deletion is the override (user says 'delete'), archive is the default close gate." |
| `KB § PATTERNS/project-execution.md` | §11.1 Features closure | "single commit / multiple, branch-to-main FF or merge, file-deletion vs file-retention" | "single commit / multiple, branch-to-main FF or merge, file-ARCHIVE via `noctus.dev.archive` (default) or file-deletion (explicit-override only)" |
| `CLAUDE/projects.md` | Commit-per-phase bullet | "(2) at project close (after folder deletion), stage anything still uncommitted and `git push`" | "(2) at project close (after folder ARCHIVE via `noctus.dev.archive`), stage anything still uncommitted and `git push`" |
| `CLAUDE/projects.md` | Features bullet | (closure language) | Add: "On feature close: archive via `noctus.dev.archive` to `archive/features/<today>/<NN>-<slug>.md` (default); explicit user 'delete' overrides to deletion." |
| New section | `KB § PATTERNS/archive-system.md` | (none) | NEW pattern doc covering folder structure + numbering + tool + auto-vs-explicit semantics + ad-hoc shape. Or extend §11 instead. **Decision: extend §11** — the archive system IS the clean-folder principle's close-gate amendment; same conceptual home. |

---

## 6. Implementation phases

Branched-project workflow per `KB § PATTERNS/branching-and-merging.md § 11`. Phase commits go to the `archive-system` branch; final commit + push at close lands on branch; orchestrator-merges branch tip to main at project close.

### Phase 0 — File this project ✅

- [x] Branch `archive-system` created from origin/main (per "branch this request" trigger).
- [x] `projects/archive-system/PROJECT.md` filed.
- [x] `projects/archive-system/proposals/.gitkeep` created.
- [x] Initial commit on branch.

**Improvements:**
- **applied (mid-Phase 0):** `git add` failed first attempt because the `proposals/` folder didn't exist yet — `mkdir -p` is required before `touch .gitkeep`. Captured for the future archive tool — Phase 4's `noctus.dev.archive` should `mkdir -p` the date folder lazily on first call (already in §5.4 spec).
- **deferred → branching methodology amendment:** discovered single-worktree contention when the projects-cleanup subagent's `git checkout -b` switched my worktree mid-flight. The branching methodology shipped today implicitly assumes parallel-agent work is possible, but a single git worktree means agents on different branches CONTEND for the checkout. Real fix: `git worktree add` for true parallelism, OR explicit sequential coordination protocol. Will document in `KB § PATTERNS/branching-and-merging.md` as a §11.2 amendment after this project closes (not in scope here — separate concern).

### Phase 1 — Archive folder bootstrap

- [ ] `mkdir -p archive/projects archive/features`.
- [ ] `touch archive/projects/.gitkeep archive/features/.gitkeep`.
- [ ] Write `archive/README.md` (≤30 lines): explains the archive convention, structure, numbering, ad-hoc shape, how to invoke the MCP tool, why archive ≠ delete.
- [ ] Stage + commit: `feat(archive): bootstrap archive folder structure (projects/ + features/ + ad-hoc datetime-prefixed root entries) [archive-system Phase 1]`.

**Improvements:** _(captured live)_

### Phase 2 — Methodology amendments (KB + CLAUDE) ✅

- [x] Amend `KB § PATTERNS/project-execution.md § 0 execution workflow`: replaced "folder deletion" with "Folder ARCHIVE via `noctus.dev.archive`" + cross-reference to §11.2.
- [x] Amend `KB § PATTERNS/project-execution.md § 11 Clean-folder` rule 4: now says "auto-ARCHIVED, not deleted" + explicit-deletion override clause.
- [x] Add `KB § PATTERNS/project-execution.md § 11.2 Archive system` (NEW — full body covering folder structure, numbering, MCP tool spec, when-archive-applies table, anti-patterns).
- [x] Amend `KB § PATTERNS/project-execution.md § 11.1 Features` closure rule: file-archive default, file-deletion explicit-override.
- [x] Amend `CLAUDE/projects.md` commit-per-phase bullet: "after folder ARCHIVE via `noctus.dev.archive`".
- [x] Amend `CLAUDE/projects.md` features bullet with closure-archive language.
- [x] Add `CLAUDE/projects.md` new bullet "Archive-on-close — closed work moves to `archive/`, not deleted" pointing to §11.2.
- [x] `verify-kb-sync.sh` + `update-kb-counts.py --check` green.
- [x] Stage + commit: `docs(kb+claude): archive-on-close — close-gate replaces folder deletion with archive [archive-system Phase 2]`.

**Improvements:** none identified — Phase 2 was clean three-doc amendment + new §11.2 section. Section ordering choice (§11.2 between §11 and §11.1) is intentional — clean-folder principle is the parent concept, archive system is its modern implementation, features section is the lightweight variant; reads naturally in this order.

### Phase 3 — Memory updates ✅

- [x] Amend `feedback_no_auto_commit.md`: replaced "after folder deletion" with "after folder ARCHIVE via `noctus.dev.archive`" in the project-close gate (2 occurrences).
- [x] Amend `feedback_apply_inline_delete_proposals.md`: not amended — already correctly scoped to "filed proposals" (per-phase artifacts), not project-folder deletion. Two-lifecycle distinction is implicit; cross-reference added in `feedback_archive_system.md` companion rules instead.
- [x] Amend `feedback_features_methodology.md`: closure section now says archive (default) with delete (explicit override).
- [x] Add new `feedback_archive_system.md`: full system rule + Why + How to apply + when-archive-vs-delete table + anti-patterns + companion rules.
- [x] Update `MEMORY.md` index — new entry added under "Project execution" cluster after the exploratory-branching line.
- [x] Stage + commit: `docs(memory): archive-on-close 3-way sync — feedback amendments + new feedback_archive_system [archive-system Phase 3]`.

**Improvements:** apply-inline-then-delete entry didn't actually need amendment — re-read confirmed it's scoped to "filed proposals" (per-phase artifacts in `proposals/` folders), not the project-folder lifecycle. The two are distinct: proposals delete (apply-inline-then-delete); project folders archive (close-gate). Added cross-reference in `feedback_archive_system.md` to clarify the boundary. **applied — saved an unnecessary edit and clarified the lifecycle distinction by documenting it in the new memory entry rather than amending the old one.**

### Phase 4 — MCP tool `noctus.dev.archive` ✅

- [x] Create `mcp/noctusai/tools/noctus/dev/archive.py` per §5.4 spec.
- [x] Register in `mcp/noctusai/tools/noctus/dev/__init__.py` (alphabetical lazy-import + register call; module count 25 → 26).
- [x] Direct-args function signature: `target_path`, optional `mode`, optional `name` (ad-hoc only). Plus optional `repo_root` for tests.
- [x] Auto-detect mode: PROJECT.md folder → project; .md under features/ → feature; else → ad_hoc.
- [x] Idempotency guard: refuses if target already under `archive/`.
- [x] `subprocess.run(["git", "mv", src, dst])` for the move (preserves history).
- [x] Compute NN by listing date folder + max+1; works on empty / .gitkeep-only folders.
- [x] Local timezone (`America/Sao_Paulo`) for date computation; matches seed scheduler convention.
- [x] Smoke test: server builds with all 26 tools registered (64 total tool names; `noctus.dev.archive` + `noctus.dev.phase_learning_*` all present).
- [x] Stage + commit: `feat(mcp): noctus.dev.archive tool — auto-numbered archive on close (project / feature / ad-hoc) [archive-system Phase 4]`.

**Improvements:** added `repo_root` parameter for test override (mirrors `phase_learnings.get_db_path`'s env-override pattern, but as a function arg since the archive tool doesn't have a singleton storage path). **applied inline.** Local timezone import via `zoneinfo` instead of `pytz` (Python 3.9+ stdlib, no extra dependency). **applied inline.**

### Phase 5 — Tests ✅

- [x] Create `mcp/noctusai/tests/test_archive.py`.
- [x] 27 test cases covering: mode auto-detect (5 cases), NN numbering (6 cases including gaps + skip-non-numbered), project archive (4 cases including same-day NN+1), feature archive (3 cases), ad-hoc archive (2 cases including require-name), idempotency guard (2 cases including archive-root-itself), error cases (2 — non-existent, invalid mode), git history preservation (1 — `--follow` works), MCP registration (2 — register exists, tool in server registry).
- [x] `tmp_repo` fixture creates real git repo via `subprocess` (not mocking — real `git mv` calls).
- [x] All 27 archive tests pass.
- [x] Full MCP suite: 616 passed (was 589 pre-Phase-5 after merging-methodology shipped; +27 archive tests).
- [x] Stage + commit: `test(mcp): noctus.dev.archive — test coverage for all 3 modes + numbering + idempotency [archive-system Phase 5]`.

**Improvements:** test fixture creates a real git repo via `subprocess` (not mocking) — gives more realistic coverage of `git mv` behavior including history-preservation. **applied inline.** History-preservation test specifically commits a `PROJECT.md` update before archiving so `git log --follow` has multi-commit history to walk; without that step, `--follow` returns just 1 commit and the test passes vacuously. **applied inline.**

### Phase 6 — Project close (dogfood: archive itself!)

- [ ] Verify all phases shipped: `verify-kb-sync.sh` green, KB counts green, MCP tests green.
- [ ] **Dogfood the archive system on this project's own close.** Instead of `git rm -r projects/archive-system/`, invoke `noctus.dev.archive --target-path=projects/archive-system --mode=project`. The project lands at `archive/projects/<today>/<NN>-archive-system/`.
- [ ] Stage + commit: `chore(projects): archive-system close — archived to archive/projects/<today>/<NN>-archive-system/ (canonical first dogfood) [archive-system close]`.
- [ ] Push branch: `git push -u origin archive-system` (already tracking).
- [ ] **Orchestrator** fresh-eyes pass per `KB § PATTERNS/branching-and-merging.md § 12`.
- [ ] Orchestrator fast-forward push: `git push origin archive-system:main`.

**Improvements:** _(captured live)_

---

## 7. Open questions

- **§11 inline vs new `KB § PATTERNS/archive-system.md`?** Current decision: extend §11 inline. The archive system IS the clean-folder principle's close-gate amendment; same conceptual home. If §11 grows beyond ~150 lines after Phase 2, split into sibling. **Default: inline; revisit at Phase 2 close.**
- **Should the MCP tool support batch archive** (archive N projects in one call)? Recommendation: **no for v1.** YAGNI. Add later if a use case surfaces.
- **Should the tool auto-commit the `git mv`** or leave it staged for the agent to commit? Recommendation: **leave staged.** Commit message belongs in the close commit, not the archive tool. The tool stages; the agent commits as part of the close.

---

## 8. Dependencies & blockers

- **Branching + merging methodology in place** — ✅ shipped earlier today.
- **Phase enrichment loop in place** — ✅ shipped (lets each phase log its learnings durably).
- **No external blockers.** This is internal methodology + tooling, no code dependencies.

---

## 9. Success criteria

- [ ] `archive/` folder exists at repo root, structured per §5.1.
- [ ] `noctus.dev.archive` tool ships, tested, registered in dev umbrella.
- [ ] All methodology references to "folder deletion" on close updated to "folder archive."
- [ ] Memory entries amended; new `feedback_archive_system.md` indexed.
- [ ] **This project's own close uses the archive system** — `archive/projects/<today>/<NN>-archive-system/` exists on origin/main after merge.
- [ ] `verify-kb-sync.sh` + `update-kb-counts.py --check` both green throughout and at close.
- [ ] All MCP tests green; full suite stays green (no regressions).

---

## 10. How to use this plan

```bash
# Phase 1 — bootstrap
mkdir -p archive/projects archive/features
touch archive/projects/.gitkeep archive/features/.gitkeep
# (write archive/README.md)
git add archive/
git commit -m "feat(archive): bootstrap archive folder structure ... [archive-system Phase 1]"

# Phase 2 — methodology amendments (manual edits)
# Edit KB § PATTERNS/project-execution.md (§0, §11, §11.1)
# Edit CLAUDE/projects.md (commit-per-phase bullet, features bullet)
bash scripts/verify-kb-sync.sh
git add KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md CLAUDE/projects.md
git commit -m "docs(kb+claude): archive-on-close ... [archive-system Phase 2]"

# Phase 3 — memory amendments + new entry
# Edit/create memory files
git add ...   # (memory files live outside repo; only their references in KB get committed if any)
git commit -m "docs(memory): archive-on-close 3-way sync ... [archive-system Phase 3]"

# Phase 4 — MCP tool
# Create mcp/noctusai/tools/noctus/dev/archive.py
# Edit mcp/noctusai/tools/noctus/dev/__init__.py to register
git add mcp/noctusai/tools/noctus/dev/archive.py mcp/noctusai/tools/noctus/dev/__init__.py
git commit -m "feat(mcp): noctus.dev.archive tool ... [archive-system Phase 4]"

# Phase 5 — tests
# Create mcp/noctusai/tests/test_archive.py
PYTHONPATH=seed/lib/backend mcp/noctusai/.venv/bin/python -m pytest mcp/noctusai/tests/test_archive.py -q
PYTHONPATH=seed/lib/backend mcp/noctusai/.venv/bin/python -m pytest mcp/noctusai/tests/ -q   # full
git add mcp/noctusai/tests/test_archive.py
git commit -m "test(mcp): noctus.dev.archive ... [archive-system Phase 5]"

# Phase 6 — close (dogfood)
PYTHONPATH=seed/lib/backend mcp/noctusai/.venv/bin/python -c "import sys; sys.path.insert(0, 'mcp/noctusai'); from tools.noctus.dev.archive import archive; print(archive('projects/archive-system', mode='project'))"
git add archive/ projects/archive-system   # staged: archive/<today>/<NN>-archive-system/* (added) + projects/archive-system/* (deleted)
git commit -m "chore(projects): archive-system close — archived to archive/projects/<today>/<NN>-archive-system/ ... [archive-system close]"
git push -u origin archive-system
# Orchestrator pass:
git diff origin/main..origin/archive-system --stat
# If clean:
git push origin archive-system:main
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | Project filed by claude-opus-4-7 after user directive: "branch this request and handle 100%". Two-thread directive: (a) auto-archive replaces auto-delete on project/feature close; (b) explicit-archive command for ad-hoc artifacts. Carve-out: explicit deletion still deletes. Branched first per the new "branch this" trigger order. Single-session execution intended; project-scale (multi-phase, multi-file, MCP tool work). | claude-opus-4-7 |

---

## 12. No-leftovers constraint

- **Folder `projects/archive-system/` ARCHIVED on close** (not deleted — the project itself dogfoods the new system). Lands at `archive/projects/<today>/<NN>-archive-system/`.
- **Final orchestrator push to main** must include only this project's commits (`[archive-system ...]` bracketed). Verify authorship via `git log origin/main..origin/archive-system --pretty="%h %an %s"` before fast-forward push.
- **No new untracked files** introduced by this project, except the gitignored test artifacts (none expected for archive testing).
