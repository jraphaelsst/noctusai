"""`clip_ranges` / `runs_from_ranges` — the flat (non-paragraph-split)
primitives `paragraphs_from_text` composes internally, made PUBLIC for a
caller building a single docxtpl `RichText` from `(text, ranges)` directly
(contract `projects/abnt-formatting-CONTRACT.md` §5's matrícula quote).
`paragraphs_from_text`'s own tests already cover the paragraph-splitting
behaviour that calls these; this file pins the primitives' OWN contract.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.abnt import clip_ranges, runs_from_ranges
from noctusai_lib.integrations.documents.formatting import FormatRange


class TestClipRanges:
    def test_a_range_fully_inside_the_window_is_rebased_to_zero(self):
        out = clip_ranges((FormatRange(10, 15, bold=True),), 10, 20)
        assert out == [FormatRange(0, 5, bold=True)]

    def test_a_range_fully_outside_the_window_is_dropped(self):
        assert clip_ranges((FormatRange(0, 5, bold=True),), 10, 20) == []

    def test_a_range_crossing_the_window_start_is_clipped(self):
        out = clip_ranges((FormatRange(5, 15, underline=True),), 10, 20)
        assert out == [FormatRange(0, 5, underline=True)]

    def test_a_range_crossing_the_window_end_is_clipped(self):
        out = clip_ranges((FormatRange(15, 25, bold=True),), 10, 20)
        assert out == [FormatRange(5, 10, bold=True)]

    def test_a_range_exactly_touching_the_window_edges_is_dropped_not_zero_length(self):
        # [start, end) is exclusive at `end` — a range ending exactly at
        # `start` or starting exactly at `end` has zero overlap.
        assert clip_ranges((FormatRange(0, 10, bold=True),), 10, 20) == []
        assert clip_ranges((FormatRange(20, 30, bold=True),), 10, 20) == []

    def test_multiple_ranges_are_each_clipped_independently(self):
        ranges = (FormatRange(0, 5, bold=True), FormatRange(12, 18, underline=True))
        out = clip_ranges(ranges, 10, 20)
        assert out == [FormatRange(2, 8, underline=True)]


class TestRunsFromRanges:
    def test_no_ranges_is_one_plain_run(self):
        runs = runs_from_ranges("texto simples", ())
        assert len(runs) == 1
        assert runs[0].text == "texto simples" and not runs[0].bold and not runs[0].underline

    def test_empty_text_is_no_runs(self):
        assert runs_from_ranges("", ()) == ()

    def test_ranges_must_already_be_local_to_the_text(self):
        # A LOCAL (0-origin) range over "ABCDEF" bolds "CD".
        runs = runs_from_ranges("ABCDEF", (FormatRange(2, 4, bold=True),))
        assert [(r.text, r.bold, r.underline) for r in runs] == [
            ("AB", False, False),
            ("CD", True, False),
            ("EF", False, False),
        ]

    def test_composes_with_clip_ranges_for_a_sub_slice_rebase(self):
        # The exact recipe a caller re-basing document-level ranges onto a
        # SUB-slice's own text uses: clip_ranges then runs_from_ranges.
        # "ABCDEFGHIJ"[2:9] == "CDEFGHI"; the document range [3,7) == "DEFG".
        document_ranges = (FormatRange(3, 7, bold=True),)
        slice_start, slice_end = 2, 9
        text = "ABCDEFGHIJ"[slice_start:slice_end]
        local = clip_ranges(document_ranges, slice_start, slice_end)
        runs = runs_from_ranges(text, local)
        assert "".join(r.text for r in runs) == text
        assert [(r.text, r.bold) for r in runs] == [
            ("C", False),
            ("DEFG", True),
            ("HI", False),
        ]
