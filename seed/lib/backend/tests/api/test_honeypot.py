"""Honeypot helper: the server-side test and the pinned embed markup."""
from __future__ import annotations

import re

import pytest

from noctusai_lib.api.honeypot import HONEYPOT_FIELD, honeypot_input_html, honeypot_tripped


@pytest.mark.parametrize("value", ["http://spam.example", "x", 1, True, " a "])
def test_a_filled_honeypot_trips(value):
    assert honeypot_tripped({HONEYPOT_FIELD: value}) is True


@pytest.mark.parametrize("body", [None, {}, {HONEYPOT_FIELD: ""}, {HONEYPOT_FIELD: "   "}, {HONEYPOT_FIELD: None}, {HONEYPOT_FIELD: False}, {"name": "x"}])
def test_an_empty_or_absent_honeypot_does_not_trip(body):
    assert honeypot_tripped(body) is False


def test_the_markup_is_invisible_to_humans_but_not_type_hidden():
    html = honeypot_input_html()
    assert 'type="hidden"' not in html and "display:none" not in html  # bots skip both
    assert "left:-10000px" in html  # off-screen
    assert 'autocomplete="off"' in html and 'tabindex="-1"' in html
    assert html.count('aria-hidden="true"') == 2  # wrapper and input
    assert re.search(r'name="hp_website"', html) and 'value=""' in html
