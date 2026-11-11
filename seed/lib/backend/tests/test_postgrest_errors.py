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


def test_rls_refusal_is_a_403_not_a_500():
    """42501 (RLS WITH CHECK / missing GRANT) is the caller's refusal: 403, pt-BR, no raw PG text."""
    import asyncio
    import json

    from noctusai_lib.primitives.exceptions import postgrest_exception_handler

    exc = _Coded("42501", 'new row violates row-level security policy for table "matricula_extracoes"')
    exc.message = str(exc)
    resp = asyncio.run(postgrest_exception_handler(None, exc))
    assert resp.status_code == 403
    body = resp.body.decode()
    assert "matricula_extracoes" not in body
    assert "permissão" in json.loads(body)["error"]["message"]


def test_unmapped_postgrest_error_is_a_500_that_does_not_echo_driver_text(caplog):
    """CWE-209: an unmapped pg_code returns a FIXED message; the raw text is logged only."""
    import asyncio
    import json
    import logging

    from noctusai_lib.primitives.exceptions import postgrest_exception_handler

    sentinel = 'relation "spn_secret_table" constraint spn_secret_ck value=SPN-SENTINEL-42'
    exc = _Coded("XX000", sentinel)
    exc.message = sentinel
    with caplog.at_level(logging.ERROR):
        resp = asyncio.run(postgrest_exception_handler(None, exc))
    assert resp.status_code == 500
    body = resp.body.decode()
    assert "SPN-SENTINEL-42" not in body and "spn_secret_table" not in body
    err = json.loads(body)["error"]
    assert err["code"] == "INTERNAL_ERROR"
    assert err["message"] == "Erro interno do servidor"
    assert "SPN-SENTINEL-42" in caplog.text
