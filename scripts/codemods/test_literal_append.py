"""Colocated regression tests for ``scripts/codemods/literal_append.py``.

Per `KB § PATTERNS/testing.md § Regression-test-the-detector`: every
codemod ships with a regression test. Covers single-line / multi-line
``__all__``, named set-literal, idempotency, and round-trip
formatting-preservation (no spurious blank lines / quote drift).

Run (from main tree, mcp venv has libcst+pytest)::

    mcp/noctusai/.venv/bin/python -m pytest scripts/codemods/test_literal_append.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from literal_append import (  # noqa: E402
    append_symbols_to_literal,
    append_to_all,
    append_to_named_literal,
)


# ---------------------------------------------------------------------------
# (a) single-line __all__
# ---------------------------------------------------------------------------


def test_append_single_line_all():
    src = '__all__ = ["foo", "bar"]\n'
    out, added = append_symbols_to_literal(src, target="__all__", symbols=["baz"])
    assert added == ["baz"]
    assert out == '__all__ = ["foo", "bar", "baz"]\n'


def test_append_single_line_all_no_trailing_comma_single_elem():
    src = '__all__ = ["foo"]\n'
    out, added = append_symbols_to_literal(src, target="__all__", symbols=["bar"])
    assert added == ["bar"]
    assert out == '__all__ = ["foo", "bar"]\n'


# ---------------------------------------------------------------------------
# (b) multi-line __all__ — indentation + trailing-comma convention preserved
# ---------------------------------------------------------------------------


def test_append_multi_line_all_trailing_comma():
    src = (
        "__all__ = [\n"
        '    "foo",\n'
        '    "bar",\n'
        "]\n"
    )
    out, added = append_symbols_to_literal(
        src, target="__all__", symbols=["baz"]
    )
    assert added == ["baz"]
    assert out == (
        "__all__ = [\n"
        '    "foo",\n'
        '    "bar",\n'
        '    "baz",\n'
        "]\n"
    )
    # no spurious blank-line element
    assert "\n\n" not in out


def test_append_multi_line_all_no_trailing_comma_on_last():
    src = (
        "__all__ = [\n"
        '    "foo",\n'
        '    "bar"\n'
        "]\n"
    )
    out, added = append_symbols_to_literal(
        src, target="__all__", symbols=["baz"]
    )
    assert added == ["baz"]
    # prior last element gains a separator; new tail element appended cleanly
    assert '"bar"' in out and '"baz"' in out
    assert "\n\n" not in out
    # still parses + round-trips
    import libcst as cst

    assert cst.parse_module(out).code == out


# ---------------------------------------------------------------------------
# (c) named set-literal (the test-fixture set case)
# ---------------------------------------------------------------------------


def test_append_named_set_literal_single_line():
    src = 'EXPECTED = {"a", "b"}\n'
    out, added = append_symbols_to_literal(
        src, target="EXPECTED", symbols=["c"]
    )
    assert added == ["c"]
    assert out == 'EXPECTED = {"a", "b", "c"}\n'


def test_append_named_set_literal_multi_line_single_quote():
    src = (
        "EXPECTED = {\n"
        "    'a',\n"
        "    'b',\n"
        "}\n"
    )
    out, added = append_symbols_to_literal(
        src, target="EXPECTED", symbols=["c"]
    )
    assert added == ["c"]
    # quote-style preserved (single quotes, not double)
    assert "'c'," in out
    assert '"c"' not in out
    assert out == (
        "EXPECTED = {\n"
        "    'a',\n"
        "    'b',\n"
        "    'c',\n"
        "}\n"
    )


# ---------------------------------------------------------------------------
# (d) idempotency
# ---------------------------------------------------------------------------


def test_append_single_element_multiline_set():
    # the lone-element multi-line case: per-line indent lives on the
    # opening brace, not on the single element's comma
    src = (
        "EXPECTED = {\n"
        '    "a",\n'
        "}\n"
    )
    out, added = append_symbols_to_literal(
        src, target="EXPECTED", symbols=["b"]
    )
    assert added == ["b"]
    assert out == (
        "EXPECTED = {\n"
        '    "a",\n'
        '    "b",\n'
        "}\n"
    )
    assert "\n\n" not in out


def test_idempotent_single_line():
    src = '__all__ = ["foo", "bar"]\n'
    out, added = append_symbols_to_literal(
        src, target="__all__", symbols=["bar"]
    )
    assert added == []
    assert out == src  # byte-identical no-op


def test_idempotent_partial():
    src = (
        "__all__ = [\n"
        '    "foo",\n'
        '    "bar",\n'
        "]\n"
    )
    out, added = append_symbols_to_literal(
        src, target="__all__", symbols=["bar", "baz"]
    )
    assert added == ["baz"]  # only the missing one
    assert out == (
        "__all__ = [\n"
        '    "foo",\n'
        '    "bar",\n'
        '    "baz",\n'
        "]\n"
    )


# ---------------------------------------------------------------------------
# (e) formatting-preserved round-trip — surrounding code untouched
# ---------------------------------------------------------------------------


FIXTURE = '''\
"""Module docstring."""

from __future__ import annotations

import os  # a comment


def helper():
    # body
    return os.getcwd()


__all__ = [
    "helper",
]
'''


def test_round_trip_preserves_surrounding_code():
    out, added = append_symbols_to_literal(
        FIXTURE, target="__all__", symbols=["helper", "extra"]
    )
    assert added == ["extra"]  # helper already present → skipped
    # everything before __all__ is byte-identical (PEP8 blank lines in the
    # surrounding code are preserved exactly — proves no global reformat)
    head_in = FIXTURE.split("__all__")[0]
    head_out = out.split("__all__")[0]
    assert head_in == head_out
    # no NEW blank lines introduced beyond what the fixture already had
    assert out.count("\n\n\n") == FIXTURE.count("\n\n\n")
    # the __all__ block itself carries no spurious blank-line element
    all_block = "__all__" + out.split("__all__")[1]
    assert "\n\n" not in all_block
    assert out.endswith(
        '__all__ = [\n    "helper",\n    "extra",\n]\n'
    )
    import libcst as cst

    assert cst.parse_module(out).code == out


def test_untouched_file_round_trips_byte_identical():
    # symbol already present ⇒ whole file must be byte-for-byte unchanged
    out, added = append_symbols_to_literal(
        FIXTURE, target="__all__", symbols=["helper"]
    )
    assert added == []
    assert out == FIXTURE


# ---------------------------------------------------------------------------
# file-level API + error path
# ---------------------------------------------------------------------------


def test_append_to_all_file_api(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text('__all__ = ["a"]\n', encoding="utf-8")
    added = append_to_all(f, ["b", "a"])
    assert added == ["b"]
    assert f.read_text() == '__all__ = ["a", "b"]\n'


def test_append_to_named_literal_file_api(tmp_path):
    f = tmp_path / "t.py"
    f.write_text("CASES = [\n    'x',\n]\n", encoding="utf-8")
    added = append_to_named_literal(f, "CASES", ["y"])
    assert added == ["y"]
    assert f.read_text() == "CASES = [\n    'x',\n    'y',\n]\n"


def test_missing_target_raises():
    with pytest.raises(LookupError):
        append_symbols_to_literal(
            "x = 1\n", target="__all__", symbols=["a"]
        )


def test_tuple_literal_supported():
    src = '__all__ = ("a", "b")\n'
    out, added = append_symbols_to_literal(
        src, target="__all__", symbols=["c"]
    )
    assert added == ["c"]
    assert out == '__all__ = ("a", "b", "c")\n'
