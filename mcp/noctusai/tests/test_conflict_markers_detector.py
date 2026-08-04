"""Regression tests for check_conflict_markers.

The real incident, 2026-08-04: a merge-integrity audit run immediately before
a prod promotion found `products/social-wiring/backend/migrations/
042_whatsapp_inbox_realtime_schema.sql` on `origin/dev` carrying a five-line
conflict header, committed by the 040->042 renumber (`d4150aea`).

Two properties made it invisible to everything else:

  * git emits the EIGHT-character marker variant with a `path:` suffix when
    the conflict is in a RENAMED file. Nobody scanning for the familiar
    seven-char `<<<<<<< HEAD` sees it.
  * the markers landed in the file's header COMMENT block, so the SQL body was
    byte-identical to the intended version. `test_migrations.py` asserts on the
    body and stayed green; the shared database had already applied a clean blob
    so the live schema was correct too. The only place it would ever have
    surfaced is a fresh environment or a DR restore replaying the migrations,
    where line 1 is a bare syntax error.

The positive fixture below is therefore the EXACT eight-char rename-conflict
shape from that file, not a paraphrase of the textbook seven-char one — a
detector regression-tested against the shape it did NOT miss proves nothing.

Markers are built by character repetition rather than written literally so that
this test file cannot trip the detector it is testing (and so the detector's
own full-tree sweep stays clean).

KB § PATTERNS/common/methodology-execution-discipline.md § Prove the check can FAIL
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_conflict_markers

OPEN7 = "<" * 7
OPEN8 = "<" * 8
DIV7 = "=" * 7
DIV8 = "=" * 8
CLOSE7 = ">" * 7
CLOSE8 = ">" * 8

# The literal header found on origin/dev in migration 042 (eight-char variant,
# emitted because the conflict was in a renamed file).
_POSITIVE_RENAME_CONFLICT = f"""\
{OPEN8} HEAD:products/social-wiring/backend/migrations/044_whatsapp_inbox_realtime_schema.sql
-- 044_whatsapp_inbox_realtime_schema.sql — Postgres as the read source of
{DIV8}
-- 042_whatsapp_inbox_realtime_schema.sql — Postgres as the read source of
{CLOSE8} origin/dev:products/social-wiring/backend/migrations/042_whatsapp_inbox_realtime_schema.sql
-- truth for the WhatsApp chat inbox.
CREATE TABLE social_wiring.whatsapp_chats (id uuid PRIMARY KEY);
"""

# The textbook seven-char shape, for completeness.
_POSITIVE_CLASSIC = f"""\
def handler():
{OPEN7} HEAD
    return 1
{DIV7}
    return 2
{CLOSE7} origin/dev
"""

# 🔴 The false positive that a naive "grep for =======" implementation hits on
# its first real run: a Markdown setext heading underline.
_NEGATIVE_MD_HEADING = """\
Branching and merging
=======

Body text about merges.
"""

# 🔴 The false positive that actually fired while building this detector:
# `KB § PATTERNS/architect/branching-and-merging.md` TEACHES conflict
# resolution, so it necessarily prints all three markers — inside a fence.
_NEGATIVE_MD_FENCED_EXAMPLE = f"""\
A conflict means both sides changed the same lines. The marker shape:

```
{OPEN7} HEAD
ours version
{DIV7}
theirs version
{CLOSE7} origin/main
```

Resolution: keep the side you meant.
"""

# A Python file using an equals-rule as a section divider — extremely common,
# and must never be flagged on its own.
_NEGATIVE_PY_DIVIDER = f"""\
# {DIV7}{DIV7}
# Section: helpers
# {DIV7}{DIV7}
VALUE = 1
"""


def _repo(tmp: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        target = tmp / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return tmp


def test_flags_the_eight_char_rename_conflict_that_shipped(tmp_path: Path) -> None:
    """The exact shape that reached origin/dev. If this stops failing, the
    detector no longer catches the incident it was built for."""
    repo = _repo(tmp_path, {"migrations/042_x.sql": _POSITIVE_RENAME_CONFLICT})
    found = check_conflict_markers(repo_root=repo, paths=["migrations/042_x.sql"])
    assert len(found) == 1, found
    assert found[0]["severity"] == "high"
    assert found[0]["file"] == "migrations/042_x.sql"
    # Line numbers must be actionable, not just "somewhere in this file".
    assert "1" in found[0]["issue"]


def test_flags_the_classic_seven_char_conflict(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"app/handler.py": _POSITIVE_CLASSIC})
    found = check_conflict_markers(repo_root=repo, paths=["app/handler.py"])
    assert len(found) == 1, found


def test_markdown_setext_heading_is_not_a_conflict(tmp_path: Path) -> None:
    """A lone divider line is a heading underline far more often than it is a
    conflict — which is why the rule requires an opener AND a closer."""
    repo = _repo(tmp_path, {"README.md": _NEGATIVE_MD_HEADING})
    assert check_conflict_markers(repo_root=repo, paths=["README.md"]) == []


def test_doc_teaching_conflict_markers_in_a_fence_is_not_flagged(tmp_path: Path) -> None:
    """KB § PATTERNS/architect/branching-and-merging.md must stay publishable."""
    repo = _repo(tmp_path, {"KB/branching.md": _NEGATIVE_MD_FENCED_EXAMPLE})
    assert check_conflict_markers(repo_root=repo, paths=["KB/branching.md"]) == []


def test_python_equals_section_divider_is_not_flagged(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"app/util.py": _NEGATIVE_PY_DIVIDER})
    assert check_conflict_markers(repo_root=repo, paths=["app/util.py"]) == []


def test_markdown_conflict_OUTSIDE_a_fence_is_still_flagged(tmp_path: Path) -> None:
    """The fence exemption is scoped to fenced blocks only. A doc that got
    genuinely mangled by a merge must still fail."""
    repo = _repo(tmp_path, {"notes.md": f"# Notes\n{_POSITIVE_CLASSIC}"})
    found = check_conflict_markers(repo_root=repo, paths=["notes.md"])
    assert len(found) == 1, found


def test_a_non_markdown_file_gets_no_fence_exemption(tmp_path: Path) -> None:
    """Triple-backticks carry no meaning in SQL/Python — a conflict wrapped in
    them there is still a conflict, and must not inherit the .md exemption."""
    fenced_sql = f"```\n{_POSITIVE_CLASSIC}```\n"
    repo = _repo(tmp_path, {"migrations/001_x.sql": fenced_sql})
    found = check_conflict_markers(repo_root=repo, paths=["migrations/001_x.sql"])
    assert len(found) == 1, found


def test_clean_file_passes(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"app/clean.py": "def f():\n    return 1\n"})
    assert check_conflict_markers(repo_root=repo, paths=["app/clean.py"]) == []


def test_binary_and_missing_paths_are_skipped_not_raised(tmp_path: Path) -> None:
    """A scanner that dies on the first unreadable file protects nothing."""
    (tmp_path / "bin").mkdir(parents=True, exist_ok=True)
    (tmp_path / "bin" / "blob.bin").write_bytes(b"\x00\xff\xfe" + OPEN7.encode())
    found = check_conflict_markers(
        repo_root=tmp_path, paths=["bin/blob.bin", "does/not/exist.py"]
    )
    assert found == []
