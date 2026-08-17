"""Bounded, self-terminating pager for offset-paged PostgREST reads.

Two independent hazards live in every ``while True: ... range(offset,
offset + n - 1)`` loop in this fleet, and each of them has bitten us:

1. **Silent truncation.** PostgREST caps any single response at
   ``db-max-rows`` (1000 on Supabase by default) with NO error and NO
   truncation signal. A bare ``.select().execute()`` therefore returns a
   plausible, wrong answer — observed 2026-07-22 (a summary reporting
   ``total=1000`` against 12,177 real rows) and again in commit
   ``98377d26`` (365 of 1,365 negociações silently skipped). Paging is
   the fix, which creates hazard 2.
2. **A loop whose termination depends on the backend.** An offset-only
   loop terminates only if the backend HONOURS ``range()``. One that
   ignores it returns the same page forever and the loop never ends.
   That is not hypothetical: ``MockSupabaseClient.range()`` was a no-op
   until 2026-08-17, and the Grupo OLX backfill hung on its first test
   run because of it. The mock is honest now, which removes how we FOUND
   this — not the hazard itself: a client or proxy that dropped the
   ``Range`` header would hang production identically, on the code path
   that touches the MOST rows, and no test would be watching.

This module owns the loop so no call site has to solve either again.
Termination rests on **making progress over rows not already seen**,
never on the pager cooperating, so the loop always ends. What happens
when it detects a non-advancing pager depends on whether stopping would
lose rows, which the page size tells us:

* a page LARGER than ``page_size`` means the range was disregarded
  outright and the backend handed back its entire set — the first page
  already carried everything, so the pager warns and stops;
* a full-but-repeated page is ambiguous ("everything" vs "a capped
  prefix") and raises, because a caller that asked for every row and
  silently got a prefix computes wrong totals that look right.

A hard page ceiling backstops both, and it raises rather than truncating
for the same reason.

The caller keeps query construction (filters differ at every call site)
and MUST order by ``id_key``: without a deterministic sort PostgREST may
return overlapping or missing rows across ranges.

Usage::

    rows = list(iter_paged_rows(
        lambda start, end: (
            client.table("leads").select("*").eq("org_id", org)
            .order("id").range(start, end).execute().data
        ),
        label=f"leads scan for org_id={org}",
    ))

Consumers: ``products/social-wiring/backend`` (``leads`` query pager,
Meta + Grupo OLX backfills). Any new offset-paged read should compose
this rather than hand-rolling the loop — see
``KB § PATTERNS/backend/postgrest-row-cap.md § Layer 2``.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Iterator

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_PAGE_SIZE",
    "DEFAULT_MAX_PAGES",
    "PagerOverflowError",
    "iter_paged_rows",
]

#: Matches PostgREST's own default response cap, so one of our pages is
#: one of its pages. A smaller value costs round-trips; a larger one is
#: silently clipped back to this by the server.
DEFAULT_PAGE_SIZE = 1000

#: Hard ceiling on pages walked. At the default page size that is 500,000
#: rows — far past any legitimate single-org result set, so hitting it
#: means a runaway, not a big tenant.
DEFAULT_MAX_PAGES = 500


class PagerOverflowError(RuntimeError):
    """The result set exceeded ``page_size * max_pages`` rows.

    Deliberately an exception and not a silent truncation: a caller that
    asked for "every row" and got "the first half, no warning" produces
    wrong totals, wrong charts and wrong backfills, all of which look
    right. Callers may pass a domain-specific subclass via
    ``overflow_error`` so their public exception name is preserved.
    """


def iter_paged_rows(
    fetch_page: Callable[[int, int], Any],
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int = DEFAULT_MAX_PAGES,
    id_key: str = "id",
    label: str = "result set",
    overflow_error: type[PagerOverflowError] = PagerOverflowError,
) -> Iterator[dict]:
    """Yield every row of an offset-paged read, exactly once.

    ``fetch_page(start, end)`` receives an INCLUSIVE range (PostgREST's
    own convention, i.e. what you hand ``.range()``) and returns that
    page's rows, or a falsy value for none. It must apply
    ``.order(id_key)`` — see the module docstring.

    ``id_key`` names the column the progress guard dedupes on; every row
    must carry it, so a ``select`` that projects a column subset has to
    include it. A missing key raises rather than degrading the guard to a
    no-op, because a silently inert guard reintroduces the hang.

    Raises ``overflow_error`` (default :class:`PagerOverflowError`) when
    ``max_pages`` pages were walked without the read running out.
    """
    if page_size < 1:
        raise ValueError(f"iter_paged_rows: page_size must be >= 1, got {page_size}")
    if max_pages < 1:
        raise ValueError(f"iter_paged_rows: max_pages must be >= 1, got {max_pages}")

    seen: set[str] = set()

    for page_index in range(max_pages):
        start = page_index * page_size
        rows = list(fetch_page(start, start + page_size - 1) or [])
        if not rows:
            return

        fresh: list[dict] = []
        for row in rows:
            if id_key not in row:
                raise ValueError(
                    f"iter_paged_rows: row in {label} has no {id_key!r} column — "
                    "the progress guard cannot dedupe without it; add it to the "
                    "select, or pass id_key=<the column you did select>"
                )
            key = str(row[id_key])
            if key in seen:
                continue
            seen.add(key)
            fresh.append(row)

        if not fresh:
            # Every row on this page was already yielded ⇒ the backend is
            # not advancing, and an offset-only loop would spin here
            # forever. Whether stopping is SAFE depends on something we
            # can actually measure: the page's own size.
            if len(rows) > page_size:
                # It returned MORE than we asked for, which real PostgREST
                # never does — so the range was disregarded outright and
                # what came back is the backend's whole set, already
                # yielded in full on the first page. Stopping loses
                # nothing.
                logger.warning(
                    "iter_paged_rows: %s — page at offset %s returned %s row(s) "
                    "for a page size of %s and none of them new. The backend "
                    "ignores range(); the first page already carried the whole "
                    "set, so stopping at %s row(s).",
                    label, start, len(rows), page_size, len(seen),
                )
                return
            # A full-but-repeated page is ambiguous: it is equally
            # consistent with "this is everything" and with "this is a
            # capped prefix of something larger". We cannot tell, so we
            # refuse to answer — a caller that asked for every row and
            # silently got a prefix computes wrong totals that look right.
            raise overflow_error(
                f"iter_paged_rows: {label} — the pager is not advancing (page at "
                f"offset {start} returned {len(rows)} row(s), none of them new). "
                "The backend appears to ignore range(), so a complete result set "
                "and a silently capped one are indistinguishable here; refusing "
                "to return either"
            )

        yield from fresh

        if len(rows) < page_size:
            return

    raise overflow_error(
        f"iter_paged_rows: {label} exceeded {max_pages * page_size} rows "
        f"({max_pages} pages of {page_size}) — refusing to return a silently "
        "truncated set"
    )
