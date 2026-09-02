"""Fractional card positions — the arithmetic a drag depends on.

These are pure-function tests on purpose: `position_for_index` is the piece
that decides where a dragged card lands, and every board bug in this area is
an off-by-one or a rounding error, not an integration problem.
"""
from decimal import Decimal

import pytest

from noctusai_lib.domain.pipeline import (
    position_for_index,
    position_of,
    position_on_top,
)


def card(pos):
    return {"id": f"c{pos}", "kanban_pos": pos}


class TestPositionOf:
    def test_reads_int_and_str_and_decimal_alike(self):
        """PostgREST returns `numeric` as a STRING to keep precision, while an
        integer column comes back as int. Sorting a mixed list raises, so both
        must normalise to the same type."""
        assert position_of({"kanban_pos": 2}) == Decimal(2)
        assert position_of({"kanban_pos": "2.5"}) == Decimal("2.5")
        assert position_of({"kanban_pos": Decimal("2.5")}) == Decimal("2.5")

    def test_missing_or_garbage_reads_as_zero_not_crash(self):
        """A row predating the migration must not take the whole board down."""
        assert position_of({}) == Decimal(0)
        assert position_of({"kanban_pos": None}) == Decimal(0)
        assert position_of({"kanban_pos": "não é número"}) == Decimal(0)


class TestPositionForIndex:
    def test_empty_column(self):
        assert position_for_index([], 0) == Decimal(0)

    def test_drop_on_top_goes_above_the_first(self):
        cards = [card(1), card(2), card(3)]
        assert position_for_index(cards, 0) < position_of(cards[0])

    def test_drop_at_the_end_goes_below_the_last(self):
        cards = [card(1), card(2), card(3)]
        assert position_for_index(cards, 3) > position_of(cards[-1])

    def test_drop_in_the_middle_is_the_midpoint(self):
        cards = [card(1), card(2), card(3)]
        assert position_for_index(cards, 1) == Decimal("1.5")

    def test_repeated_subdivision_stays_strictly_ordered(self):
        """The property the whole design rests on: halving the same gap over
        and over must keep producing DISTINCT, correctly-ordered positions.
        On a float column these collapse to equality after ~50 rounds; on
        `Decimal` they do not."""
        cards = [card(Decimal(1)), card(Decimal(2))]
        anterior = None
        for _ in range(60):
            nova = position_for_index(cards, 1)
            assert Decimal(1) < nova < Decimal(2)
            if anterior is not None:
                assert nova != anterior
            cards = [card(Decimal(1)), card(nova), card(Decimal(2))]
            anterior = nova

    def test_index_is_clamped_not_an_error(self):
        """A racy client can send an index past the end of a column that
        shrank under it. Misplacing the card beats a 500."""
        cards = [card(1), card(2)]
        assert position_for_index(cards, 99) > position_of(cards[-1])
        assert position_for_index(cards, -5) < position_of(cards[0])

    def test_tied_neighbours_still_produce_a_position(self):
        """Every row sat at 0 before the migration. Two neighbours can
        therefore share a position, and there is no midpoint to take."""
        cards = [card(0), card(0), card(0)]
        nova = position_for_index(cards, 1)
        assert Decimal(0) < nova < Decimal(1)

    def test_moving_a_card_down_one_slot_actually_moves_it(self):
        """🔴 The off-by-one that makes drag-down feel broken.

        The caller must pass the column WITHOUT the moved card. Given
        [A,B,C] and moving A to index 1, the neighbour list is [B,C] and the
        new position must sit between B and C — NOT between A and B, which is
        where it lands if the caller forgets to exclude the card.
        """
        b, c = card(2), card(3)
        nova = position_for_index([b, c], 1)
        assert position_of(b) < nova < position_of(c)


class TestPositionOnTop:
    def test_above_everything(self):
        cards = [card(1), card(2), card(-4)]
        assert position_on_top(cards) < Decimal(-4)

    def test_empty_column_is_zero(self):
        assert position_on_top([]) == Decimal(0)

    def test_successive_arrivals_stack_newest_first(self):
        """What replaces the force-sort-by-date: each new card takes a spot
        above the previous one, so the intake column reads newest-first
        without the sort ever overriding a human's arrangement."""
        cards = []
        for _ in range(3):
            cards.insert(0, card(position_on_top(cards)))
        posicoes = [position_of(c) for c in cards]
        assert posicoes == sorted(posicoes), "newest must sort to the top"
        assert len(set(posicoes)) == 3
