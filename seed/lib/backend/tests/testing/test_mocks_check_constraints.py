"""Unit tests for `MockSupabaseClient(validate_schema_constraints=True, manifest=...)`.

Covers the opt-in CHECK-constraint validator that raises `MockCheckViolation`
when an INSERT/UPDATE writes a literal outside the allowed-values tuple.

The validator closes the silent-success class where a test would happily pass
a write that PostgreSQL would reject at runtime (the ADCO-REWARDS-STATUS-CHECK
shape: a service inserts `status='success'` against a table whose CHECK is
`status IN ('acumulado', 'resgatado', 'expirado')`).

Coverage:
  1. INSERT with valid `tipo` literal → no raise (green path).
  2. INSERT with invalid `tipo` literal → MockCheckViolation (red path).
  3. INSERT with invalid `status` literal → MockCheckViolation (matches the
     ADCO-REWARDS-STATUS-CHECK regression shape — would have caught the bug).
  4. UPDATE with invalid status → MockCheckViolation (write paths symmetric).
  5. Default mode (validate_schema_constraints=False) → no raise on invalid
     literal, preserving existing test behavior.

Notes:
  - The mock client's `validate_schema` flag defaults to True, so we pass
    `validate_schema=False` to focus tests on the CHECK pathway alone (the
    test rows reference real columns regardless).
  - The CHECK manifest mirrors the live `001_adconnect.sql` constraints on
    `recompensas_acumuladas` + `resgates_recompensa`.
"""
from __future__ import annotations

import pytest

from noctusai_lib.testing import (
    MockCheckViolation,
    MockSupabaseClient,
)


# Manifest mirroring the live AdConnect CHECK constraints on rewards tables.
# Bare table keys (no `adconnect.` prefix) match the schema-bound client.
ADCONNECT_REWARDS_MANIFEST = {
    "recompensas_acumuladas": {
        "tipo": ("cashback", "pontos"),
        "status": ("acumulado", "resgatado", "expirado"),
    },
    "resgates_recompensa": {
        "metodo": (
            "credito_em_pedido",
            "credito_em_fatura",
            "reembolso_pix",
            "outro",
        ),
        "status": ("pendente", "aprovado", "recusado", "pago"),
    },
}


# ---------------------------------------------------------------------------
# Test 1 — green path: INSERT with valid literal succeeds
# ---------------------------------------------------------------------------


def test_insert_with_valid_tipo_passes():
    """A literal explicitly listed in the manifest's allowed tuple must NOT
    raise. The validator is opt-in but must not be a blanket-block."""
    client = MockSupabaseClient(
        validate_schema=False,
        validate_schema_constraints=True,
        manifest=ADCONNECT_REWARDS_MANIFEST,
    )
    # `cashback` is one of the allowed `tipo` literals.
    result = (
        client.table("recompensas_acumuladas")
        .insert({
            "id": "row-1",
            "tipo": "cashback",
            "status": "acumulado",
            "valor": 100.0,
        })
        .execute()
    )
    assert result.data, "insert should return the inserted row"
    assert result.data[0]["tipo"] == "cashback"


# ---------------------------------------------------------------------------
# Test 2 — red path: INSERT with invalid `tipo`
# ---------------------------------------------------------------------------


def test_insert_with_invalid_tipo_raises():
    """A literal outside the allowed-values tuple must raise loudly. This is
    the archetypal silent-fail the validator closes."""
    client = MockSupabaseClient(
        validate_schema=False,
        validate_schema_constraints=True,
        manifest=ADCONNECT_REWARDS_MANIFEST,
    )
    with pytest.raises(MockCheckViolation) as excinfo:
        (
            client.table("recompensas_acumuladas")
            .insert({
                "id": "row-bad",
                "tipo": "verba_mkt",  # not in ('cashback', 'pontos')
                "status": "acumulado",
            })
            .execute()
        )
    # Error must name the offending table, column, value, AND the allowed set
    # — silent-error rule requires the message be diagnosable.
    msg = str(excinfo.value)
    assert "recompensas_acumuladas" in msg
    assert "tipo" in msg
    assert "verba_mkt" in msg
    assert "cashback" in msg and "pontos" in msg
    # Structured fields preserved for programmatic inspection.
    assert excinfo.value.column == "tipo"
    assert excinfo.value.invalid_value == "verba_mkt"
    assert "cashback" in excinfo.value.allowed_values


# ---------------------------------------------------------------------------
# Test 3 — red path: INSERT with invalid `status` (ADCO-REWARDS-STATUS-CHECK shape)
# ---------------------------------------------------------------------------


def test_insert_with_invalid_status_would_have_caught_adco_rewards_bug():
    """The ADCO-REWARDS-STATUS-CHECK bug: production code inserted
    `status='success'` into `recompensas_acumuladas` whose CHECK allows only
    ('acumulado', 'resgatado', 'expirado'). The mock previously accepted this
    write silently → tests green, real DB rejected at deploy time.

    With the constraint validator wired, the same write fails loudly at test
    time — the validator IS the test-time analog of the DB's CHECK.
    """
    client = MockSupabaseClient(
        validate_schema=False,
        validate_schema_constraints=True,
        manifest=ADCONNECT_REWARDS_MANIFEST,
    )
    with pytest.raises(MockCheckViolation) as excinfo:
        (
            client.table("recompensas_acumuladas")
            .insert({
                "id": "row-1",
                "tipo": "cashback",
                "status": "success",  # the regression: not a valid status
                "valor": 50.0,
            })
            .execute()
        )
    assert excinfo.value.column == "status"
    assert excinfo.value.invalid_value == "success"
    assert excinfo.value.operation == "insert"
    # All three valid statuses must appear in the error so the engineer can
    # see what to change to.
    msg = str(excinfo.value)
    for valid in ("acumulado", "resgatado", "expirado"):
        assert valid in msg


# ---------------------------------------------------------------------------
# Test 4 — red path: UPDATE with invalid `status`
# ---------------------------------------------------------------------------


def test_update_with_invalid_status_raises():
    """UPDATE writes are validated symmetrically with INSERT. A test that
    `UPDATE resgates_recompensa SET status='shipped'` against the CHECK
    `status IN ('pendente', 'aprovado', 'recusado', 'pago')` must fail."""
    client = MockSupabaseClient(
        validate_schema=False,
        validate_schema_constraints=True,
        manifest=ADCONNECT_REWARDS_MANIFEST,
    )
    # Seed a row so UPDATE has something to match.
    client.set_table_data("resgates_recompensa", [
        {"id": "res-1", "status": "pendente", "metodo": "outro"},
    ])
    with pytest.raises(MockCheckViolation) as excinfo:
        (
            client.table("resgates_recompensa")
            .update({"status": "shipped"})  # invalid
            .eq("id", "res-1")
            .execute()
        )
    assert excinfo.value.operation == "update"
    assert excinfo.value.column == "status"
    assert excinfo.value.invalid_value == "shipped"
    assert excinfo.value.table == "resgates_recompensa"


# ---------------------------------------------------------------------------
# Test 5 — default mode (validator OFF): existing behavior unchanged
# ---------------------------------------------------------------------------


def test_default_mode_does_not_validate_constraints():
    """`validate_schema_constraints` defaults to False. Existing tests across
    every product must continue to pass without modification — that's the
    rollout contract for opt-in features."""
    client = MockSupabaseClient(validate_schema=False)  # default: constraints OFF
    # Same row that test 3 rejects under the validator — must succeed here.
    result = (
        client.table("recompensas_acumuladas")
        .insert({
            "id": "row-1",
            "tipo": "cashback",
            "status": "success",  # would violate CHECK; allowed here
            "valor": 50.0,
        })
        .execute()
    )
    assert result.data[0]["status"] == "success"


# ---------------------------------------------------------------------------
# Test 6 — invalid `metodo` on resgates_recompensa (multi-column manifest)
# ---------------------------------------------------------------------------


def test_insert_with_invalid_metodo_raises():
    """Sanity-check that multi-column manifest entries fire on whichever
    column the test violates. `metodo='paypal'` is outside the allowed
    `('credito_em_pedido', 'credito_em_fatura', 'reembolso_pix', 'outro')`."""
    client = MockSupabaseClient(
        validate_schema=False,
        validate_schema_constraints=True,
        manifest=ADCONNECT_REWARDS_MANIFEST,
    )
    with pytest.raises(MockCheckViolation) as excinfo:
        (
            client.table("resgates_recompensa")
            .insert({
                "id": "res-2",
                "status": "pendente",
                "metodo": "paypal",  # invalid
            })
            .execute()
        )
    assert excinfo.value.column == "metodo"


# ---------------------------------------------------------------------------
# Test 7 — schema-qualified manifest keys take precedence
# ---------------------------------------------------------------------------


def test_schema_qualified_manifest_key_resolves():
    """When the manifest uses `adconnect.<table>` keys, the validator must
    match the qualified form before falling back to bare lookups. Confirms
    products with multiple schemas can scope their manifests."""
    client = MockSupabaseClient(
        validate_schema=False,
        schema="adconnect",
        validate_schema_constraints=True,
        manifest={
            "adconnect.recompensas_acumuladas": {
                "status": ("acumulado", "resgatado", "expirado"),
            },
        },
    )
    with pytest.raises(MockCheckViolation) as excinfo:
        (
            client.table("recompensas_acumuladas")
            .insert({"id": "x", "status": "bogus"})
            .execute()
        )
    assert excinfo.value.schema == "adconnect"
    assert excinfo.value.invalid_value == "bogus"
