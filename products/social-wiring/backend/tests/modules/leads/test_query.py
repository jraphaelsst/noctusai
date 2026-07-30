"""Free-text filtering over the leads fact table."""
from __future__ import annotations

from app.modules.leads.services.query import matches_free_text



class TestFreeTextFindsTheNumberTheUiShows:
    """Regression guard for the format gap migration 037 opened.

    The Leads table, the Funil card and the detail modal all render the
    CANONICAL number; the row stores what arrived. Searching for what you can
    see must find it, or canonicalization made the product worse.
    """

    STORED = {"cliente_nome": "Maria", "contato": "11 98191.2534"}

    def test_pasting_the_displayed_canonical_number_finds_the_row(self):
        assert matches_free_text(self.STORED, "+5511981912534") is True

    def test_pasting_it_without_the_plus_also_finds_it(self):
        assert matches_free_text(self.STORED, "5511981912534") is True

    def test_a_partial_digit_fragment_finds_it(self):
        assert matches_free_text(self.STORED, "981912534") is True

    def test_the_raw_stored_spelling_still_finds_it(self):
        # Strictly additive: the pre-existing substring behaviour is intact.
        assert matches_free_text(self.STORED, "98191.2534") is True

    def test_name_search_is_untouched(self):
        assert matches_free_text(self.STORED, "maria") is True
        assert matches_free_text(self.STORED, "joão") is False

    def test_a_different_number_does_not_match(self):
        assert matches_free_text(self.STORED, "+5511999999999") is False

    def test_a_short_digit_run_does_not_reach_the_phone_pass(self):
        # "551" is not a substring of the stored "11 98191.2534", so the only
        # way it could match is the canonical-digit pass ("5511981912534"
        # contains it). Below the 4-digit floor that pass must not run, or a
        # 2-3 digit query would return every São Paulo lead.
        assert matches_free_text(self.STORED, "551") is False
        # ...and at the floor it does run, which is the intended prefix search.
        assert matches_free_text(self.STORED, "5511") is True

    def test_an_email_contact_is_not_phone_matched(self):
        row = {"cliente_nome": "Ana", "contato": "ana2534@example.com"}
        assert matches_free_text(row, "+5511982534000") is False
