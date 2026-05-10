"""Unit tests for `noctusai_lib.api.crud_safety`.

Covers:

- Happy path: row exists → deletes; row absent → raises caller-provided exc.
- Variadic predicates: 1, 2, 3 predicates.
- Both raise shapes: `HTTPException(404)` (PF convention) AND `LookupError`
  (ERP convention).
- `delete_or_404` convenience wrapper raises HTTPException with correct
  status code AND detail (status-code-assertion-rule honored).
- Predicate alignment: the SELECT pre-check uses the same predicates as the
  DELETE — important for RLS/scoping safety.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from noctusai_lib.api.crud_safety import delete_or_404, delete_with_existence_check
from noctusai_lib.testing import MockSupabaseClient


# ── Happy path ───────────────────────────────────────────────────────


def test_delete_with_existence_check_deletes_when_row_present():
    """Row exists → SELECT pre-check passes → DELETE runs → row absent after."""
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data("widgets", [{"id": "w1", "name": "alpha"}])

    delete_with_existence_check(
        db,
        "widgets",
        ("id", "w1"),
        not_found_exc=lambda: LookupError("widget missing"),
    )

    remaining = db.table("widgets").select("*").execute().data
    assert remaining == [], "DELETE should have removed the row"


def test_delete_with_existence_check_raises_when_row_absent():
    """Row absent → SELECT pre-check returns [] → not_found_exc fires."""
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data("widgets", [])  # empty table

    with pytest.raises(LookupError, match="widget missing"):
        delete_with_existence_check(
            db,
            "widgets",
            ("id", "ghost"),
            not_found_exc=lambda: LookupError("widget missing"),
        )


# ── Variadic predicates ──────────────────────────────────────────────


def test_delete_with_existence_check_single_predicate():
    """One predicate: `(id,)` only — covers RLS-via-parent tables."""
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data("items", [{"id": "i1"}, {"id": "i2"}])

    delete_with_existence_check(
        db,
        "items",
        ("id", "i1"),
        not_found_exc=lambda: LookupError("item missing"),
    )

    remaining = db.table("items").select("*").execute().data
    assert [r["id"] for r in remaining] == ["i2"]


def test_delete_with_existence_check_two_predicates():
    """Two predicates: `(id, org_id)` — canonical PF/ERP scoping."""
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "metas",
        [
            {"id": "m1", "org_id": "org-A", "nome": "alpha"},
            {"id": "m2", "org_id": "org-B", "nome": "beta"},
        ],
    )

    delete_with_existence_check(
        db,
        "metas",
        ("id", "m1"),
        ("org_id", "org-A"),
        not_found_exc=lambda: LookupError("meta missing"),
    )

    remaining = db.table("metas").select("*").execute().data
    assert [r["id"] for r in remaining] == ["m2"]


def test_delete_with_existence_check_three_predicates():
    """Three predicates: `(id, org_id, tipo)` — multi-axis scoping."""
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data(
        "regras",
        [
            {"id": "r1", "org_id": "org-A", "tipo": "padrao"},
            {"id": "r1", "org_id": "org-A", "tipo": "outro"},
        ],
    )

    delete_with_existence_check(
        db,
        "regras",
        ("id", "r1"),
        ("org_id", "org-A"),
        ("tipo", "padrao"),
        not_found_exc=lambda: LookupError("regra missing"),
    )

    remaining = db.table("regras").select("*").execute().data
    assert remaining == [{"id": "r1", "org_id": "org-A", "tipo": "outro"}]


# ── Both raise shapes ────────────────────────────────────────────────


def test_delete_with_existence_check_raises_lookup_error_shape():
    """ERP convention: caller passes LookupError."""
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data("widgets", [])

    with pytest.raises(LookupError) as exc_info:
        delete_with_existence_check(
            db,
            "widgets",
            ("id", "ghost"),
            not_found_exc=lambda: LookupError("Período não encontrado"),
        )

    assert "Período não encontrado" in str(exc_info.value)


def test_delete_with_existence_check_raises_http_exception_shape():
    """PF convention: caller passes HTTPException(404).

    Status-code-assertion-rule: this test asserts on body (`.detail`) AND on
    `.status_code` in the same method.
    """
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data("widgets", [])

    with pytest.raises(HTTPException) as exc_info:
        delete_with_existence_check(
            db,
            "widgets",
            ("id", "ghost"),
            not_found_exc=lambda: HTTPException(
                status_code=404, detail="Widget não encontrado"
            ),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Widget não encontrado"


# ── delete_or_404 convenience wrapper ────────────────────────────────


def test_delete_or_404_happy_path():
    """Row exists → wrapper deletes silently."""
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data("widgets", [{"id": "w1"}])

    delete_or_404(db, "widgets", ("id", "w1"), message="Widget missing")

    remaining = db.table("widgets").select("*").execute().data
    assert remaining == []


def test_delete_or_404_raises_http_404():
    """Row absent → HTTPException with status 404 + caller message.

    Status-code-assertion-rule: body (`.detail`) AND `.status_code` both
    asserted in the same method.
    """
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data("widgets", [])

    with pytest.raises(HTTPException) as exc_info:
        delete_or_404(db, "widgets", ("id", "ghost"), message="Widget missing")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Widget missing"


def test_delete_or_404_default_message():
    """Default `message` is `"Not found"`."""
    db = MockSupabaseClient(validate_schema=False)
    db.set_table_data("widgets", [])

    with pytest.raises(HTTPException) as exc_info:
        delete_or_404(db, "widgets", ("id", "ghost"))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Not found"


# ── Predicate alignment / scoping safety ─────────────────────────────


class _RecordingFake:
    """Minimal fake DB recording every filter chain call for assertion.

    Used to prove the helper passes the SAME predicates to BOTH the SELECT
    pre-check and the DELETE — important for RLS scoping safety. We don't
    rely on MockSupabaseClient for this because its SELECT side doesn't
    apply filters (write→read propagation is the documented contract; SELECT
    filter evaluation is mock-out-of-scope).
    """

    def __init__(self, present: bool):
        self.present = present
        self.select_predicates: list[tuple[str, object]] = []
        self.delete_predicates: list[tuple[str, object]] = []
        self._mode: str | None = None

    def table(self, _name):
        self._mode = None
        return self

    def select(self, _cols):
        self._mode = "select"
        return self

    def delete(self):
        self._mode = "delete"
        return self

    def eq(self, col, val):
        if self._mode == "select":
            self.select_predicates.append((col, val))
        elif self._mode == "delete":
            self.delete_predicates.append((col, val))
        return self

    def execute(self):
        if self._mode == "select":
            data = [{"id": "x"}] if self.present else []
            return _ExecResult(data=data)
        return _ExecResult(data=None)


class _ExecResult:
    def __init__(self, data):
        self.data = data


def test_predicate_alignment_select_and_delete_match():
    """Both SELECT pre-check AND DELETE receive the SAME predicates in order.

    Cross-tenant scoping safety depends on the DELETE chain getting every
    predicate the SELECT got — otherwise the DELETE could match a broader
    row set than the pre-check approved.
    """
    fake = _RecordingFake(present=True)

    delete_with_existence_check(
        fake,
        "metas",
        ("id", "m1"),
        ("org_id", "org-A"),
        not_found_exc=lambda: LookupError("meta missing"),
    )

    assert fake.select_predicates == [("id", "m1"), ("org_id", "org-A")]
    assert fake.delete_predicates == [("id", "m1"), ("org_id", "org-A")]


def test_predicate_alignment_skips_delete_when_absent():
    """When pre-check fails, DELETE chain MUST NOT execute.

    Critical: the whole point of the helper is to avoid issuing a DELETE on a
    row that may be RLS-hidden. The fake records DELETE calls; we assert none
    happened.
    """
    fake = _RecordingFake(present=False)

    with pytest.raises(LookupError):
        delete_with_existence_check(
            fake,
            "metas",
            ("id", "m1"),
            ("org_id", "org-A"),
            not_found_exc=lambda: LookupError("meta missing"),
        )

    assert fake.delete_predicates == [], (
        "DELETE chain must not run when SELECT pre-check fails"
    )
