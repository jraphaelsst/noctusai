"""Tests for ``scripts/render-project-history.py``.

Coverage (Phase 3 spec):
- Empty ledger → header-only output.
- Single record → table with one row.
- Multiple records, mixed dates → DESC ordering by ``dates.closed``.
- Dedupe-by-slug → only the latest-closed survives.
- Idempotent re-render → byte-identical output.
- Invalid NDJSON line → ``ValueError`` with line-number context.
- Pipe character + newline escaped in summary cells.
- Missing ledger file → empty rendering, no crash.

Test conventions follow ``test_history.py`` (sibling MCP-tool test).
The renderer is a plain script, so we import it via spec_from_file_location
(it lives outside the ``tools/`` tree which the test harness adds to
``sys.path``).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

# Repo root: this test file lives at mcp/noctusai/tests/.
_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO / "scripts" / "render-project-history.py"


def _load_renderer():
    """Load the renderer module via importlib (dashes in filename)."""
    spec = importlib.util.spec_from_file_location("render_project_history", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def renderer():
    return _load_renderer()


def _record(
    slug: str,
    closed: str,
    summary: str = "Short summary text.",
    *,
    scope: str = "cross-product",
    status: str = "shipped",
    total: int = 1000,
    created: str | None = "2026-05-01",
) -> dict[str, Any]:
    """Build a well-formed ledger record dict (matches HistoryRecord shape)."""
    return {
        "slug": slug,
        "scope": scope,
        "status_at_close": status,
        "dates": {"created": created, "closed": closed},
        "phases": [],
        "short_summary": summary,
        "short_review": "Review body.",
        "token_count": {
            "project_doc_tokens": 100,
            "improvements_tokens": 50,
            "proposals_tokens": 25,
            "code_delta_tokens": total - 175,
            "total": total,
            "tokenizer_used": "tiktoken-cl100k_base",
        },
        "outcome_signals": [],
    }


def _write_ndjson(path: Path, records: list[dict]) -> None:
    """Write records to a NDJSON file, one per line."""
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")


# ---------------------------------------------------------------------------
# Header-only / empty-ledger
# ---------------------------------------------------------------------------


def test_empty_ledger_renders_header_only(renderer, tmp_path: Path) -> None:
    """Zero records → placeholder banner + empty-footer, no table."""
    ledger = tmp_path / "ledger.ndjson"
    ledger.touch()
    out = tmp_path / "PROJECT-HISTORY.md"

    renderer.write_history(ledger, out)

    body = out.read_text(encoding="utf-8")
    assert body.startswith("# Project History\n")
    assert "do not edit by hand" in body
    assert "The ledger is empty" in body or "ledger is empty" in body.lower()
    assert "| Date |" not in body  # no table


def test_missing_ledger_file_renders_empty(renderer, tmp_path: Path) -> None:
    """Ledger file absent → renderer treats as empty, no crash."""
    ledger = tmp_path / "does-not-exist.ndjson"
    out = tmp_path / "PROJECT-HISTORY.md"

    renderer.write_history(ledger, out)

    body = out.read_text(encoding="utf-8")
    assert body.startswith("# Project History\n")
    assert "| Date |" not in body


# ---------------------------------------------------------------------------
# Single-record path
# ---------------------------------------------------------------------------


def test_single_record_renders_one_row(renderer, tmp_path: Path) -> None:
    """One record → header + one table row, the column count matches."""
    ledger = tmp_path / "ledger.ndjson"
    rec = _record("only-project", closed="2026-05-10", summary="Only row.")
    _write_ndjson(ledger, [rec])
    out = tmp_path / "PROJECT-HISTORY.md"

    renderer.write_history(ledger, out)

    body = out.read_text(encoding="utf-8")
    assert "| Date |" in body
    assert "| :--- |" in body  # separator row
    assert "| 2026-05-10 | only-project | cross-product | shipped | 1000 | Only row. |" in body
    # exactly one data row (header + separator + data = 3 pipe-starting lines).
    data_rows = [ln for ln in body.splitlines() if ln.startswith("| ") and "Date" not in ln and ":---" not in ln]
    assert len(data_rows) == 1


# ---------------------------------------------------------------------------
# Mixed-date ordering
# ---------------------------------------------------------------------------


def test_multiple_records_sort_closed_desc(renderer, tmp_path: Path) -> None:
    """Mixed dates → most-recent first; oldest last."""
    ledger = tmp_path / "ledger.ndjson"
    records = [
        _record("slug-mid", closed="2026-05-05"),
        _record("slug-old", closed="2026-04-30"),
        _record("slug-new", closed="2026-05-10"),
    ]
    _write_ndjson(ledger, records)
    out = tmp_path / "PROJECT-HISTORY.md"

    renderer.write_history(ledger, out)

    body = out.read_text(encoding="utf-8")
    pos_new = body.index("slug-new")
    pos_mid = body.index("slug-mid")
    pos_old = body.index("slug-old")
    assert pos_new < pos_mid < pos_old


def test_same_date_ties_break_by_slug_asc(renderer, tmp_path: Path) -> None:
    """Two records on same close-date → alphabetical by slug ASC.

    Lets the renderer stay deterministic for idempotency.
    """
    ledger = tmp_path / "ledger.ndjson"
    records = [
        _record("zebra", closed="2026-05-10"),
        _record("alpha", closed="2026-05-10"),
        _record("mango", closed="2026-05-10"),
    ]
    _write_ndjson(ledger, records)
    out = tmp_path / "PROJECT-HISTORY.md"

    renderer.write_history(ledger, out)

    body = out.read_text(encoding="utf-8")
    pos_alpha = body.index("alpha")
    pos_mango = body.index("mango")
    pos_zebra = body.index("zebra")
    assert pos_alpha < pos_mango < pos_zebra


# ---------------------------------------------------------------------------
# Dedupe-by-slug-keep-latest
# ---------------------------------------------------------------------------


def test_dedupe_by_slug_keeps_latest_closed(renderer, tmp_path: Path) -> None:
    """Multiple records for one slug → only the latest-closed appears."""
    ledger = tmp_path / "ledger.ndjson"
    records = [
        _record("the-project", closed="2026-05-08", summary="EARLIER stamp."),
        _record("the-project", closed="2026-05-10", summary="LATER stamp wins."),
        _record("the-project", closed="2026-05-09", summary="MIDDLE stamp."),
    ]
    _write_ndjson(ledger, records)
    out = tmp_path / "PROJECT-HISTORY.md"

    renderer.write_history(ledger, out)

    body = out.read_text(encoding="utf-8")
    assert "LATER stamp wins." in body
    assert "EARLIER stamp." not in body
    assert "MIDDLE stamp." not in body
    # Exactly one data row.
    data_rows = [ln for ln in body.splitlines() if ln.startswith("| ") and "Date" not in ln and ":---" not in ln]
    assert len(data_rows) == 1


def test_dedupe_preserves_unique_slugs(renderer, tmp_path: Path) -> None:
    """Records with distinct slugs all survive dedupe."""
    ledger = tmp_path / "ledger.ndjson"
    records = [
        _record("alpha", closed="2026-05-08"),
        _record("beta", closed="2026-05-09"),
        _record("gamma", closed="2026-05-10"),
    ]
    _write_ndjson(ledger, records)
    out = tmp_path / "PROJECT-HISTORY.md"

    renderer.write_history(ledger, out)

    body = out.read_text(encoding="utf-8")
    assert "alpha" in body
    assert "beta" in body
    assert "gamma" in body


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_idempotent_re_render(renderer, tmp_path: Path) -> None:
    """Re-running on unchanged ledger produces byte-identical output.

    Also confirms ``write_history`` returns ``False`` on no-op (so the
    pre-commit hook can skip ``git add`` when nothing changed).
    """
    ledger = tmp_path / "ledger.ndjson"
    records = [
        _record("a", closed="2026-05-08"),
        _record("b", closed="2026-05-10"),
    ]
    _write_ndjson(ledger, records)
    out = tmp_path / "PROJECT-HISTORY.md"

    changed_first = renderer.write_history(ledger, out)
    first_bytes = out.read_bytes()

    changed_second = renderer.write_history(ledger, out)
    second_bytes = out.read_bytes()

    assert changed_first is True
    assert changed_second is False
    assert first_bytes == second_bytes


def test_check_mode_detects_drift(renderer, tmp_path: Path) -> None:
    """--check should report drift when output is stale."""
    ledger = tmp_path / "ledger.ndjson"
    _write_ndjson(ledger, [_record("a", closed="2026-05-10")])
    out = tmp_path / "PROJECT-HISTORY.md"
    out.write_text("stale content\n", encoding="utf-8")

    rc = renderer.main(["--ledger", str(ledger), "--output", str(out), "--check"])
    assert rc == 1


def test_check_mode_passes_when_in_sync(renderer, tmp_path: Path) -> None:
    """--check should pass when output matches the ledger."""
    ledger = tmp_path / "ledger.ndjson"
    _write_ndjson(ledger, [_record("a", closed="2026-05-10")])
    out = tmp_path / "PROJECT-HISTORY.md"

    renderer.write_history(ledger, out)
    rc = renderer.main(["--ledger", str(ledger), "--output", str(out), "--check"])
    assert rc == 0


# ---------------------------------------------------------------------------
# Error surfacing
# ---------------------------------------------------------------------------


def test_invalid_ndjson_raises_with_line_number(renderer, tmp_path: Path) -> None:
    """Malformed JSON line → ValueError citing the line number."""
    ledger = tmp_path / "ledger.ndjson"
    good = _record("good", closed="2026-05-10")
    ledger.write_text(
        json.dumps(good) + "\n" + "this-is-not-json\n" + json.dumps(good) + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "PROJECT-HISTORY.md"

    with pytest.raises(ValueError) as exc:
        renderer.write_history(ledger, out)

    msg = str(exc.value)
    assert "ledger.ndjson:2" in msg
    assert "this-is-not-json" in msg


def test_non_object_ndjson_raises(renderer, tmp_path: Path) -> None:
    """A JSON line that's not an object → ValueError citing line type."""
    ledger = tmp_path / "ledger.ndjson"
    ledger.write_text("[1, 2, 3]\n", encoding="utf-8")
    out = tmp_path / "PROJECT-HISTORY.md"

    with pytest.raises(ValueError) as exc:
        renderer.write_history(ledger, out)

    msg = str(exc.value)
    assert "not a JSON object" in msg
    assert ":1" in msg


# ---------------------------------------------------------------------------
# Markdown-cell safety
# ---------------------------------------------------------------------------


def test_pipe_character_escaped_in_summary(renderer, tmp_path: Path) -> None:
    """Pipe in short_summary must be escaped so the table column survives."""
    ledger = tmp_path / "ledger.ndjson"
    rec = _record("project", closed="2026-05-10", summary="Has | pipe inside.")
    _write_ndjson(ledger, [rec])
    out = tmp_path / "PROJECT-HISTORY.md"

    renderer.write_history(ledger, out)

    body = out.read_text(encoding="utf-8")
    # Data row contains escaped pipe.
    assert "Has \\| pipe inside." in body
    # No bare un-escaped pipe inside the cell (after the leading `| `).
    data_row = [ln for ln in body.splitlines() if ln.startswith("| 2026-05-10")][0]
    # Count of `|` should equal the number of column separators (7 for 6 columns).
    # The bare pipe was escaped, so it no longer counts.
    bare_pipes = data_row.count("|") - data_row.count("\\|")
    assert bare_pipes == 7  # 6 columns + bookends = 7 separators


def test_newline_in_summary_collapsed_to_space(renderer, tmp_path: Path) -> None:
    """Newlines in short_summary would break the row — must be collapsed."""
    ledger = tmp_path / "ledger.ndjson"
    rec = _record(
        "project",
        closed="2026-05-10",
        summary="Line one.\nLine two.\nLine three.",
    )
    _write_ndjson(ledger, [rec])
    out = tmp_path / "PROJECT-HISTORY.md"

    renderer.write_history(ledger, out)

    body = out.read_text(encoding="utf-8")
    assert "Line one. Line two. Line three." in body
    # The data row stays single-line (no broken table).
    data_row = [ln for ln in body.splitlines() if ln.startswith("| 2026-05-10")][0]
    assert "Line one." in data_row
    assert "Line two." in data_row
    assert "Line three." in data_row


# ---------------------------------------------------------------------------
# Blank-line tolerance
# ---------------------------------------------------------------------------


def test_blank_lines_in_ledger_are_skipped(renderer, tmp_path: Path) -> None:
    """Blank lines in NDJSON (e.g. trailing newline at EOF) don't error."""
    ledger = tmp_path / "ledger.ndjson"
    good = _record("a", closed="2026-05-10")
    ledger.write_text("\n" + json.dumps(good) + "\n\n", encoding="utf-8")
    out = tmp_path / "PROJECT-HISTORY.md"

    renderer.write_history(ledger, out)

    body = out.read_text(encoding="utf-8")
    assert "| 2026-05-10 | a |" in body
