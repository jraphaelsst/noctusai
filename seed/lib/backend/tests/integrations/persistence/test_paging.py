"""Tests for the offset-paged read helper.

The interesting cases are not "does it page" — they are the two ways the
hand-rolled loops it replaces went wrong: a backend that ignores
``range()`` (hangs forever), and a result set bigger than the pager will
walk (silently truncates). Both are asserted here, because neither is
reachable through a well-behaved fake.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.persistence import (
    PagerOverflowError,
    iter_paged_rows,
)


def rows(count: int, *, offset: int = 0) -> list[dict]:
    return [{"id": f"row-{index + offset}"} for index in range(count)]


def honest_backend(all_rows: list[dict]):
    """A backend that honours `range()` — real PostgREST."""

    def fetch(start: int, end: int) -> list[dict]:
        return all_rows[start : end + 1]

    return fetch


def ignoring_backend(all_rows: list[dict]):
    """A backend that ignores `range()` and returns everything, every
    time — a proxy that drops the Range header (and `MockSupabaseClient`
    before it learned the cap, 2026-08-17)."""

    def fetch(start: int, end: int) -> list[dict]:
        return list(all_rows)

    return fetch


class TestHonestBackend:
    def test_yields_every_row_once_in_order(self):
        source = rows(7)

        assert list(iter_paged_rows(honest_backend(source), page_size=2)) == source

    def test_empty_result_yields_nothing(self):
        assert list(iter_paged_rows(honest_backend([]), page_size=2)) == []

    def test_exact_multiple_of_page_size_terminates(self):
        # The off-by-one trap: the last full page looks like "there may be
        # more", so the pager must ask once more and get nothing.
        source = rows(4)

        assert list(iter_paged_rows(honest_backend(source), page_size=2)) == source

    def test_tolerates_a_backend_returning_none_for_no_rows(self):
        # `resp.data` is None, not [], on several of our clients.
        assert list(iter_paged_rows(lambda start, end: None)) == []

    def test_passes_an_inclusive_range_matching_postgrest(self):
        seen: list[tuple[int, int]] = []

        def fetch(start: int, end: int):
            seen.append((start, end))
            return rows(2, offset=start) if start == 0 else []

        list(iter_paged_rows(fetch, page_size=2))

        assert seen[0] == (0, 1)
        assert seen[1] == (2, 3)


class TestBackendThatIgnoresRange:
    """The pager always terminates here — an offset-only loop does not.
    What it does on termination splits on whether stopping loses rows."""

    def test_terminates_instead_of_looping_forever(self):
        # The exact shape that hung the Grupo OLX backfill on its first
        # run: an over-long page proves the whole set already arrived.
        source = rows(7)

        result = list(iter_paged_rows(ignoring_backend(source), page_size=2))

        assert result == source

    def test_covers_every_row_exactly_once(self):
        source = rows(50)

        result = list(iter_paged_rows(ignoring_backend(source), page_size=10))

        assert [row["id"] for row in result] == [row["id"] for row in source]

    def test_warns_so_the_broken_pager_is_visible(self, caplog):
        with caplog.at_level("WARNING"):
            list(iter_paged_rows(ignoring_backend(rows(4)), page_size=2, label="leads"))

        assert "ignores range()" in caplog.text
        assert "leads" in caplog.text

    def test_raises_when_the_repeated_page_could_be_a_capped_prefix(self):
        # Exactly `page_size` rows, returned again and again. This is
        # equally consistent with "the set is 2 rows" and "the set is
        # 20,000 rows and the server capped us at 2" — indistinguishable,
        # so answering either way would be a guess.
        with pytest.raises(PagerOverflowError, match="not advancing"):
            list(iter_paged_rows(ignoring_backend(rows(2)), page_size=2))

    def test_a_short_repeated_page_is_just_the_end_of_the_data(self):
        # One row for a page size of two: the ordinary short-page exit
        # fires first, so the guard never has to judge it.
        source = rows(1)

        assert list(iter_paged_rows(ignoring_backend(source), page_size=2)) == source


class TestOverflow:
    def test_raises_rather_than_truncating(self):
        # A backend that always returns a full page of NEW rows: the
        # progress guard cannot fire, so only the ceiling stops it.
        counter = {"n": 0}

        def fetch(start: int, end: int):
            page = rows(2, offset=counter["n"])
            counter["n"] += 2
            return page

        with pytest.raises(PagerOverflowError) as excinfo:
            list(iter_paged_rows(fetch, page_size=2, max_pages=3, label="leads scan"))

        assert "leads scan" in str(excinfo.value)
        assert "truncated" in str(excinfo.value)

    def test_honours_a_domain_specific_exception_type(self):
        # Call sites keep their own public exception name; `except
        # PagerOverflowError` still catches it.
        class TooBig(PagerOverflowError):
            pass

        def fetch(start: int, end: int):
            return rows(2, offset=start)

        with pytest.raises(TooBig):
            list(
                iter_paged_rows(
                    fetch, page_size=2, max_pages=2, overflow_error=TooBig
                )
            )


class TestGuardIntegrity:
    def test_missing_id_column_raises_instead_of_disabling_the_guard(self):
        # A guard that silently no-ops when the key is absent brings the
        # hang straight back, so this must be loud.
        with pytest.raises(ValueError, match="progress guard"):
            list(iter_paged_rows(lambda start, end: [{"nome": "x"}], page_size=2))

    def test_dedupes_on_the_requested_key(self):
        source = [{"origin_lead_id": "a"}, {"origin_lead_id": "b"}, {"origin_lead_id": "c"}]

        result = list(
            iter_paged_rows(
                ignoring_backend(source), page_size=2, id_key="origin_lead_id"
            )
        )

        assert result == source

    @pytest.mark.parametrize("kwargs", [{"page_size": 0}, {"max_pages": 0}])
    def test_rejects_a_degenerate_configuration(self, kwargs):
        with pytest.raises(ValueError):
            list(iter_paged_rows(honest_backend(rows(2)), **kwargs))
