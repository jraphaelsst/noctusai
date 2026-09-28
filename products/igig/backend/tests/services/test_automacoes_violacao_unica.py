"""`automacoes.violacao_unica` — now delegated to the seam's dialect-neutral
classifier instead of its own string-sniffing.

This call site talks to the raw service-role/RLS client
(`portas.db.table(...)`), never the `RecordStore` seam, so it never raises
`UniqueViolation`; it still needs a `bool` from whatever the raw client threw.
`classify_constraint_violation` is the ONE place that mapping now lives —
these tests pin `violacao_unica` against both dialects' real error shapes so
a future change to the classifier's signature is caught here, not silently
in production the next time an automation race fires.
"""
from postgrest.exceptions import APIError

from app.services.automacoes import violacao_unica


def test_recognises_a_postgres_unique_violation_by_code():
    exc = APIError({"code": "23505", "message": "duplicate key value violates unique constraint"})
    assert violacao_unica(exc) is True


def test_recognises_a_sqlite_unique_violation_by_message():
    assert violacao_unica(Exception("UNIQUE constraint failed: automacao_execucao.id")) is True


def test_does_not_misclassify_a_foreign_key_violation_as_a_duplicate():
    exc = APIError({"code": "23503", "message": "violates foreign key constraint"})
    assert violacao_unica(exc) is False


def test_does_not_misclassify_an_unrelated_error():
    assert violacao_unica(RuntimeError("connection reset")) is False
