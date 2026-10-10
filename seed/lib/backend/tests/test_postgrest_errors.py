"""`is_unique_violation` — the single PostgREST 23505 predicate."""
from __future__ import annotations

from noctusai_lib.primitives.postgrest_errors import is_unique_violation


class _Coded(Exception):
    def __init__(self, code, msg=""):
        super().__init__(msg)
        self.code = code


def test_matches_code_message_and_duplicate_key_text():
    assert is_unique_violation(_Coded("23505"))
    assert is_unique_violation(Exception("{'code': '23505', 'message': 'x'}"))
    assert is_unique_violation(Exception('Duplicate Key value violates unique constraint "k"'))


def test_does_not_match_bare_unique_or_other_codes():
    assert not is_unique_violation(Exception("column is not unique-ish"))
    assert not is_unique_violation(_Coded("23503", "foreign key"))
    assert not is_unique_violation(ValueError("boom"))
