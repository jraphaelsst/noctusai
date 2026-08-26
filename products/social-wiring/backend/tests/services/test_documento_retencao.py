"""Document retention policy — the two-tier resolver and its clock (079).

WHAT THESE PIN
--------------
- an org row beats the platform row, and its ABSENCE is what "not customised"
  means (so `restaurar` deletes rather than nulls);
- `retencao_dias = None` means keep indefinitely and is never confused with
  "expired" — the direction that would delete files;
- 🔴 a neighbouring org's override is invisible. The mock records `.or_()` as
  match-all, so a single-query resolver would pass this file while leaking
  across tenants in production; the service reads the two tiers separately
  and this test is what holds it there;
- the platform tier is the allow-list: a typo'd tipo is refused, not written.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from noctusai_lib.primitives.exceptions import ValidationError_
from noctusai_lib.testing.mocks import MockSupabaseClient

from app.dependencies import coerce_org_uuid
from app.services import documento_retencao as svc

ORG = coerce_org_uuid("test-org-123")
OUTRA_ORG = coerce_org_uuid("outra-org-999")

TABLE = "documento_retencao_politicas"


def _politica(
    *, org_id=None, superficie="atendimento", tipo="extratos_fgts", dias=730, motivo=None
) -> dict:
    return {
        "id": str(uuid4()),
        "org_id": str(org_id) if org_id else None,
        "superficie": superficie,
        "tipo_documento": tipo,
        "retencao_dias": dias,
        "motivo": motivo,
        "atualizado_em": None,
        "atualizado_por": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }


@pytest.fixture
def client():
    mock = MockSupabaseClient()
    scoped = mock.schema("social_wiring")
    scoped.set_table_data(TABLE, [])
    return scoped


# ─── resolution ───────────────────────────────────────────────────────


class TestResolucao:
    def test_platform_default_applies_when_org_has_no_row(self, client):
        client.set_table_data(TABLE, [_politica(dias=730)])

        assert svc.dias_para(client, ORG, "atendimento", "extratos_fgts") == 730

        (item,) = svc.politicas(client, ORG)
        assert item["retencao_dias"] == 730
        assert item["padrao_dias"] == 730
        assert item["personalizado"] is False

    def test_org_row_overrides_the_platform_default(self, client):
        client.set_table_data(
            TABLE,
            [
                _politica(dias=730),
                _politica(org_id=ORG, dias=1095),
            ],
        )

        assert svc.dias_para(client, ORG, "atendimento", "extratos_fgts") == 1095

        (item,) = svc.politicas(client, ORG)
        assert item["retencao_dias"] == 1095
        assert item["padrao_dias"] == 730, "the default must survive being overridden"
        assert item["personalizado"] is True

    def test_another_orgs_override_is_invisible(self, client):
        """🔴 The regression this file exists for.

        `MockSupabaseClient.or_` is a synthetic match-all — it does not parse
        the PostgREST expression. A resolver written as one `.or_()` query
        would return OUTRA_ORG's row here and report 99 for ORG, and the test
        would still be green because the mock never filtered. Reading the two
        tiers with exactly-expressible filters is what makes this assertion
        mean anything.
        """
        client.set_table_data(
            TABLE,
            [
                _politica(dias=730),
                _politica(org_id=OUTRA_ORG, dias=99),
            ],
        )

        assert svc.dias_para(client, ORG, "atendimento", "extratos_fgts") == 730
        assert svc.politicas(client, ORG)[0]["personalizado"] is False

    def test_none_means_keep_indefinitely_not_expired(self, client):
        client.set_table_data(TABLE, [_politica(dias=None)])

        assert svc.dias_para(client, ORG, "atendimento", "extratos_fgts") is None
        assert svc.politicas(client, ORG)[0]["retencao_dias"] is None

    def test_unknown_type_resolves_to_none_rather_than_zero(self, client):
        """Missing policy → keep, never delete. The safe direction."""
        client.set_table_data(TABLE, [])
        assert svc.dias_para(client, ORG, "atendimento", "inexistente") is None


# ─── the anchor ───────────────────────────────────────────────────────


class TestAncora:
    def test_each_surface_reports_what_its_clock_counts_from(self, client):
        client.set_table_data(
            TABLE,
            [
                _politica(superficie="atendimento", tipo="extratos_fgts", dias=730),
                _politica(superficie="cliente", tipo="contrato", dias=1825),
            ],
        )
        por_superficie = {p["superficie"]: p for p in svc.politicas(client, ORG)}

        assert por_superficie["atendimento"]["ancora"] == "encerramento"
        assert por_superficie["cliente"]["ancora"] == "envio"
        # The screen renders the label verbatim; an empty one would leave a
        # bare duration on screen, which is the ambiguity this exists to kill.
        assert por_superficie["atendimento"]["ancora_rotulo"]
        assert por_superficie["cliente"]["ancora_rotulo"]

    def test_imovel_is_not_a_configurable_surface(self):
        """075 gave `imovel_documentos` no `retencao_ate` column. A control
        for it would be a lying UI, so it is absent from the enum AND from
        migration 079's CHECK — the two must not drift apart."""
        assert "imovel" not in svc.SUPERFICIES
        assert set(svc.ANCORAS) == set(svc.SUPERFICIES)


# ─── writes ───────────────────────────────────────────────────────────


class TestEscrita:
    def test_definir_writes_an_org_row_and_leaves_the_default_alone(self, client):
        client.set_table_data(TABLE, [_politica(dias=730)])

        svc.definir(client, ORG, "atendimento", "extratos_fgts", 1095, motivo="pedido do cliente")

        linhas = client.table(TABLE).select("*").execute().data
        assert len(linhas) == 2
        padrao = [r for r in linhas if r["org_id"] is None][0]
        assert padrao["retencao_dias"] == 730
        override = [r for r in linhas if r["org_id"] == str(ORG)][0]
        assert override["retencao_dias"] == 1095
        assert override["motivo"] == "pedido do cliente"
        assert override["atualizado_em"] is not None

    def test_definir_twice_updates_rather_than_duplicating(self, client):
        client.set_table_data(TABLE, [_politica(dias=730)])

        svc.definir(client, ORG, "atendimento", "extratos_fgts", 1095)
        svc.definir(client, ORG, "atendimento", "extratos_fgts", 365)

        overrides = [
            r
            for r in client.table(TABLE).select("*").execute().data
            if r["org_id"] == str(ORG)
        ]
        assert len(overrides) == 1
        assert overrides[0]["retencao_dias"] == 365

    def test_definir_none_is_a_recorded_decision_not_an_absence(self, client):
        """"Keep forever, deliberately" and "nobody touched this" are
        different facts; an audit asks which one it is."""
        client.set_table_data(TABLE, [_politica(dias=730)])

        svc.definir(client, ORG, "atendimento", "extratos_fgts", None)

        assert svc.dias_para(client, ORG, "atendimento", "extratos_fgts") is None
        assert svc.politicas(client, ORG)[0]["personalizado"] is True

    def test_restaurar_deletes_the_override(self, client):
        client.set_table_data(
            TABLE, [_politica(dias=730), _politica(org_id=ORG, dias=1095)]
        )

        svc.restaurar(client, ORG, "atendimento", "extratos_fgts")

        assert svc.dias_para(client, ORG, "atendimento", "extratos_fgts") == 730
        assert svc.politicas(client, ORG)[0]["personalizado"] is False

    def test_unknown_tipo_is_refused_not_written(self, client):
        client.set_table_data(TABLE, [_politica(dias=730)])

        with pytest.raises(ValidationError_) as exc:
            svc.definir(client, ORG, "atendimento", "nao_existe", 365)

        assert "nao_existe" in str(exc.value)
        assert len(client.table(TABLE).select("*").execute().data) == 1

    def test_unknown_superficie_is_refused(self, client):
        client.set_table_data(TABLE, [_politica(dias=730)])

        with pytest.raises(ValidationError_):
            svc.definir(client, ORG, "imovel", "matricula", 365)

    def test_zero_days_is_refused(self, client):
        """Zero is falsy, and the upload path reads `if retencao_dias` — a 0
        would show as a policy on screen while behaving as no clock at all.
        `None` is already the way to say keep-forever."""
        client.set_table_data(TABLE, [_politica(dias=730)])

        with pytest.raises(ValidationError_):
            svc.definir(client, ORG, "atendimento", "extratos_fgts", 0)
