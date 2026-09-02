"""Card positions inside a pipeline column — FRACTIONAL, so a drag is ONE write.

WHY NOT DENSE INTEGERS
----------------------
The obvious model is "position 0, 1, 2, …, renumber the column on every move".
It is correct and it does not scale here: social-wiring's intake column held
1.850 open cards in a single stage, so one drag would be 1.850 UPDATEs — a
table-rewrite per gesture, and a race between two people dragging at once that
silently interleaves two renumberings.

Instead a card's position is any real number, and the ORDER is what the numbers
imply. Dropping between two cards stores the MIDPOINT of its neighbours, which
touches exactly one row and cannot disturb anybody else's position:

    [1.0]  [2.0]  [3.0]        drop between 1.0 and 2.0  →  1.5
    [1.0]  [1.5]  [2.0]  [3.0]

Smaller number = higher in the column (ascending sort), so "move to the top" is
`first - 1` and needs no knowledge of the rest of the column.

🔴 THE COLUMN TYPE MUST BE `numeric`, NOT `integer`. On an integer column the
midpoint of 1 and 2 rounds to 1 or 2 and the card lands on the wrong side of
its neighbour — silently, and only sometimes. `numeric` (arbitrary precision,
not float) also avoids the binary-fraction drift that makes two midpoints
compare equal after ~50 subdivisions. Consumers still on an integer column must
keep passing integer indices; this module is opt-in per caller for exactly that
reason (erp-imobiliario is one — see `move_card`'s `novo_indice`).

PRECISION IS NOT INFINITE, AND THAT IS FINE
-------------------------------------------
Repeatedly dropping into the SAME gap halves it each time, so the decimal
expansion grows ~1 digit per 3 drops. `numeric` has no practical ceiling for
this (thousands of digits), and a human dragging cards will not reach it. There
is deliberately NO automatic renumber-on-threshold: it would be a rare,
hard-to-test code path that rewrites the column — the thing this design exists
to avoid. If a pathological column ever appears, renumbering it is a one-off
maintenance query, not a hot path.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

__all__ = ["POSITION_FIELD", "position_for_index", "position_of", "position_on_top"]

POSITION_FIELD = "kanban_pos"

# Gap used when pushing past an end of the column. Any positive number works —
# the ORDER is what matters, never the magnitude.
_STEP = Decimal(1)


def position_of(card: Any) -> Decimal:
    """A card's position as `Decimal`, tolerating dict or object rows.

    Missing / unparseable ⇒ 0, matching the column default. A row that predates
    the numeric migration reads as 0 rather than exploding the whole board.
    """
    raw = card.get(POSITION_FIELD) if isinstance(card, dict) else getattr(card, POSITION_FIELD, None)
    if raw is None:
        return Decimal(0)
    try:
        return Decimal(str(raw))
    except Exception:
        return Decimal(0)


def position_on_top(cards: Sequence[Any]) -> Decimal:
    """A position strictly above every card in `cards`.

    This is where a NEWLY ARRIVED card goes: the intake column must show the
    newest lead first, and giving it a position above everything achieves that
    without forcing a date sort on the column — which is what would take
    hand-arranged order away from the operator. New arrivals stack on top, and
    anything a human dragged stays exactly where they put it.
    """
    if not cards:
        return Decimal(0)
    return min(position_of(c) for c in cards) - _STEP


def position_for_index(cards: Sequence[Any], index: int) -> Decimal:
    """The position that lands a card at `index` within `cards`.

    `cards` must be the destination column IN ITS DISPLAYED ORDER and must NOT
    contain the card being moved — the caller removes it first, because "drop
    at index 3" means three cards above it once it is gone, not counting
    itself. Getting that wrong is the classic off-by-one where dragging a card
    one slot down does nothing.

    `index` is clamped, so an out-of-range index from a racy client lands at an
    end instead of raising: a drag that arrives late should misplace a card at
    worst, never 500.
    """
    if not cards:
        return Decimal(0)

    index = max(0, min(index, len(cards)))

    if index == 0:
        return position_of(cards[0]) - _STEP
    if index >= len(cards):
        return position_of(cards[-1]) + _STEP

    anterior = position_of(cards[index - 1])
    seguinte = position_of(cards[index])
    if anterior == seguinte:
        # Neighbours share a position — possible on data that predates the
        # migration (everything defaulted to 0). There is no midpoint to take,
        # so go just below the pair and let the next drag subdivide normally.
        return anterior + _STEP / 2
    return (anterior + seguinte) / 2
