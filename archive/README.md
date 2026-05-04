# archive/ — closed work, preserved

Browseable + git-tracked archive of closed projects, features, and ad-hoc artifacts. Replaces the previous "delete on close" rule per `KB § PATTERNS/project-execution.md § 11` (clean-folder + archive-on-close).

## Why archive instead of delete

- Closed work's content lives in git history either way, but archives are filesystem-browseable without `git log` archaeology.
- Chronological ordering (`<YYYY-MM-DD>/<NN>-<slug>`) preserves within-day sequence + day-by-day shape.
- Aligns with `KB § 01-PHILOSOPHY.md § Safety nets capture failures; failures become learnings; methodology evolves` — closing isn't erasure; it's preservation.

## Structure

```
archive/
├── projects/                   ← category: closed projects (folders).
│   └── <YYYY-MM-DD>/
│       ├── 01-<project-slug>/
│       │   ├── PROJECT.md
│       │   └── proposals/      ← preserved as-is from the project folder.
│       ├── 02-<project-slug>/
│       │   └── ...
│       └── ...
├── features/                   ← category: closed features (single .md files).
│   └── <YYYY-MM-DD>/
│       ├── 01-<feature-slug>.md
│       ├── 02-<feature-slug>.md
│       └── ...
└── <YYYY-MM-DD>_<HH-MM-SS>_<name>/   ← ad-hoc archive (no established category).
    └── <whatever was archived>
```

## Numbering

- Per-day, per-category. `<NN>-<slug>` zero-padded 2-digit, incrementing from `01`.
- Resets daily.
- The MCP tool `noctus.dev.archive` computes `NN = max(existing) + 1` automatically.

## How to archive

**Default (auto-archive on close):** Project/feature close gates invoke `noctus.dev.archive` instead of `git rm -r`:

```bash
# At project close (after final commit on the branch):
python -c "import sys; sys.path.insert(0, 'mcp/noctusai'); from tools.noctus.dev.archive import archive; print(archive('projects/<slug>', mode='project'))"
# Result: project moved to archive/projects/<today>/<NN>-<slug>/
```

**Explicit-archive (user says "archive X"):** Same tool; `mode` parameter selects the category. For ad-hoc items (no established category), pass `mode="ad_hoc"` + descriptive `name`:

```bash
python -c "from tools.noctus.dev.archive import archive; archive('some/path', mode='ad_hoc', name='descriptive-name')"
# Result: moved to archive/2026-05-03_15-42-30_descriptive-name/
```

**Explicit-DELETE override:** When the user explicitly says "delete X" / "remove X" (NOT "archive X" / "close X"), `git rm -r` is correct. Archive is the auto-default; delete is the explicit override.

## Idempotency guard

`noctus.dev.archive` refuses if the target is already under `archive/`. Don't archive an archive.

## What's NOT archived

- Working-tree garbage (uncommitted scratch files).
- Stash entries (`git stash drop` is correct).
- Temporary memory entries explicitly retired by user (memory deletes are direct).
- Things the user explicitly says to "delete."

## Archive lifecycle

Archives stay forever (or until a future archive-cleanup project decides otherwise). Date-based ordering means old archives don't clutter recent ones; consumers walk by date.
