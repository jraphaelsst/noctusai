"""The deal-paperwork retention clock (079) — anchored at `closed_at`.

WHAT THESE PIN
--------------
- 🔴 an OPEN deal's documents never expire. Lei 9.613/98 art. 10 III counts
  from "a conclusão da transação", so anchoring at upload would expire a
  month-1 document a full deal-length before the legal minimum. This is the
  assertion that keeps the anchor where it belongs;
- the sweep RE-derives `retencao_ate` every run rather than stamping once, so
  changing the policy or reopening a deal actually moves the date — a
  stamp-once sweep would leave the screen claiming a period nothing honours;
- a policy of `None` (keep indefinitely) clears the date rather than expiring
  the document;
- expired documents are soft-deleted with a system-attributed access-log
  entry, never attributed to a person who did not do it.
"""
from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest

from app.dependencies import coerce_org_uuid
from app.modules.card_hub import financiamento_service as svc
from tests.modules.card_hub.conftest import ORG_ID

ORG = coerce_org_uuid("test-org-123")
POLITICAS = "documento_retencao_politicas"


def _politica(tipo, dias, *, org_id=None) -> dict:
    return {
        "id": str(uuid4()),
        "org_id": str(org_id) if org_id else None,
        "superficie": "atendimento",
        "tipo_documento": tipo,
        "retencao_dias": dias,
        "motivo": None,
        "atualizado_em": None,
        "atualizado_por": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }


def _atendimento(aid, *, closed_at=None, cliente_id=None) -> dict:
    # Mirrors `test_financiamento.py::_atendimento` field-for-field — the
    # atendimento resolver filters on `substituida_por`/`arquivado`, so a
    # thinner row resolves to "no open atendimento" and every upload 409s.
    return {
        "id": aid,
        "org_id": ORG_ID,
        "cliente_id": cliente_id or str(uuid4()),
        "lead_id": None,
        "meta_ads_lead_id": None,
        "status": "aberta" if closed_at is None else "ganha",
        "substituida_por": None,
        "arquivado": False,
        "titulo": "Compra do apto",
        "created_at": "2026-01-01T00:00:00+00:00",
        "closed_at": closed_at,
    }


def _documento(did, aid, *, tipo="extratos_fgts", retencao_ate=None, deleted_at=None) -> dict:
    return {
        "id": did,
        "org_id": ORG_ID,
        "atendimento_id": aid,
        "storage_path": f"{ORG_ID}/atendimentos/{aid}/{did}",
        "nome_original": "extrato.pdf",
        "mime_type": "application/pdf",
        "tamanho_bytes": 10,
        "tipo_documento": tipo,
        "categoria_lgpd": "financeiro",
        "retencao_ate": retencao_ate,
        "enviado_por": None,
        "deleted_at": deleted_at,
        "delete_motivo": None,
        "delete_solicitado_por": None,
        "created_at": "2026-02-01T00:00:00+00:00",
    }


@pytest.fixture
def seeded(client, scoped):
    """One open deal, one closed deal, one document each, 730-day policy."""
    aberto, fechado = str(uuid4()), str(uuid4())
    doc_aberto, doc_fechado = str(uuid4()), str(uuid4())
    scoped.set_table_data(
        "atendimentos",
        [_atendimento(aberto), _atendimento(fechado, closed_at="2026-03-10T12:00:00+00:00")],
    )
    scoped.set_table_data(
        "atendimento_documentos",
        [_documento(doc_aberto, aberto), _documento(doc_fechado, fechado)],
    )
    scoped.set_table_data("atendimento_documento_acessos", [])
    scoped.set_table_data(POLITICAS, [_politica("extratos_fgts", 730)])
    return {
        "scoped": scoped,
        "aberto": aberto,
        "fechado": fechado,
        "doc_aberto": doc_aberto,
        "doc_fechado": doc_fechado,
    }


def _linha(scoped, doc_id) -> dict:
    rows = scoped.table("atendimento_documentos").select("*").eq("id", doc_id).execute().data
    assert rows, f"documento {doc_id} sumiu"
    return rows[0]


class TestAncoraNoFechamento:
    def test_open_deal_documents_never_expire(self, seeded):
        """🔴 The legal point. An open deal has no `closed_at`, so there is
        nothing for the clock to count from — and its paperwork is in active
        use besides."""
        svc.varrer_retencao(seeded["scoped"], ORG)

        assert _linha(seeded["scoped"], seeded["doc_aberto"])["retencao_ate"] is None
        assert _linha(seeded["scoped"], seeded["doc_aberto"])["deleted_at"] is None

    def test_closed_deal_gets_closed_at_plus_the_policy(self, seeded):
        resultado = svc.varrer_retencao(seeded["scoped"], ORG)

        esperado = (date(2026, 3, 10) + timedelta(days=730)).isoformat()
        assert _linha(seeded["scoped"], seeded["doc_fechado"])["retencao_ate"] == esperado
        assert resultado["reavaliados"] == 1
        assert resultado["removidos"] == 0


class TestReavaliacao:
    def test_changing_the_policy_moves_an_already_stamped_date(self, seeded):
        """A stamp-once sweep would leave the old date in place, so the
        Settings screen would claim a period nothing actually honours."""
        svc.varrer_retencao(seeded["scoped"], ORG)
        seeded["scoped"].set_table_data(POLITICAS, [_politica("extratos_fgts", 365)])

        svc.varrer_retencao(seeded["scoped"], ORG)

        esperado = (date(2026, 3, 10) + timedelta(days=365)).isoformat()
        assert _linha(seeded["scoped"], seeded["doc_fechado"])["retencao_ate"] == esperado

    def test_reopening_a_deal_clears_its_documents_expiry(self, seeded):
        svc.varrer_retencao(seeded["scoped"], ORG)
        seeded["scoped"].set_table_data(
            "atendimentos",
            [_atendimento(seeded["aberto"]), _atendimento(seeded["fechado"])],
        )

        svc.varrer_retencao(seeded["scoped"], ORG)

        assert _linha(seeded["scoped"], seeded["doc_fechado"])["retencao_ate"] is None

    def test_keep_indefinitely_clears_the_date_rather_than_expiring(self, seeded):
        svc.varrer_retencao(seeded["scoped"], ORG)
        seeded["scoped"].set_table_data(POLITICAS, [_politica("extratos_fgts", None)])

        resultado = svc.varrer_retencao(seeded["scoped"], ORG)

        assert _linha(seeded["scoped"], seeded["doc_fechado"])["retencao_ate"] is None
        assert resultado["removidos"] == 0

    def test_an_org_override_wins_over_the_platform_default(self, seeded):
        seeded["scoped"].set_table_data(
            POLITICAS,
            [_politica("extratos_fgts", 730), _politica("extratos_fgts", 30, org_id=ORG)],
        )

        svc.varrer_retencao(seeded["scoped"], ORG)

        esperado = (date(2026, 3, 10) + timedelta(days=30)).isoformat()
        assert _linha(seeded["scoped"], seeded["doc_fechado"])["retencao_ate"] == esperado

    def test_a_second_run_changes_nothing(self, seeded):
        """Idempotent — the column is a materialized view of (closed_at,
        policy), so a no-change run must report zero re-evaluations."""
        svc.varrer_retencao(seeded["scoped"], ORG)

        assert svc.varrer_retencao(seeded["scoped"], ORG)["reavaliados"] == 0


class TestVarredura:
    def test_expired_documents_are_soft_deleted_and_logged_as_system(self, seeded):
        scoped = seeded["scoped"]
        ontem = (date.today() - timedelta(days=1)).isoformat()
        # A deal closed long enough ago that even a 1-day policy has run out.
        scoped.set_table_data(
            "atendimentos",
            [
                _atendimento(seeded["aberto"]),
                _atendimento(seeded["fechado"], closed_at=f"{ontem}T00:00:00+00:00"),
            ],
        )
        scoped.set_table_data(POLITICAS, [_politica("extratos_fgts", 1)])

        resultado = svc.varrer_retencao(scoped, ORG)

        assert resultado["removidos"] == 1
        linha = _linha(scoped, seeded["doc_fechado"])
        assert linha["deleted_at"] is not None
        assert "retenção expirada" in linha["delete_motivo"]

        acessos = scoped.table("atendimento_documento_acessos").select("*").execute().data
        delete_rows = [a for a in acessos if a["acao"] == "delete"]
        assert len(delete_rows) == 1
        # 🔴 A scheduled sweep is a system action. Attributing it to a person
        # would put a deletion in someone's audit trail that they never made.
        assert delete_rows[0]["usuario_id"] is None

    def test_an_already_deleted_document_is_not_swept_twice(self, seeded):
        scoped = seeded["scoped"]
        scoped.set_table_data(
            "atendimento_documentos",
            [
                _documento(
                    seeded["doc_fechado"],
                    seeded["fechado"],
                    retencao_ate="2020-01-01",
                    deleted_at="2026-01-01T00:00:00+00:00",
                )
            ],
        )

        assert svc.varrer_retencao(scoped, ORG)["removidos"] == 0

    def test_no_documents_is_not_an_error(self, client, scoped):
        scoped.set_table_data("atendimento_documentos", [])
        assert svc.varrer_retencao(scoped, ORG) == {"reavaliados": 0, "removidos": 0}


class TestUploadNaoCarimba:
    def test_upload_leaves_retencao_ate_null(self, client, scoped, fake_storage):
        """The clock starts at the deal's close, not at the upload — so a
        freshly uploaded document must carry no expiry at all."""
        from tests.modules.card_hub.conftest import cliente_row

        cid, aid = str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Luciano")])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cliente_id=cid)])
        scoped.set_table_data("atendimento_documentos", [])
        scoped.set_table_data("atendimento_documento_acessos", [])
        scoped.set_table_data("atendimento_financiamento", [])

        resp = client.post(
            f"/api/clientes/{cid}/financiamento/documentos",
            files={"file": ("ir.pdf", b"%PDF-1.7 fake", "application/pdf")},
            data={"tipo_documento": "certidao_casamento"},
            headers={"Authorization": "Bearer test-token"},
        )

        assert resp.status_code == 200, resp.text
        linhas = scoped.table("atendimento_documentos").select("*").execute().data
        assert len(linhas) == 1
        assert linhas[0]["retencao_ate"] is None


class TestScheduler:
    def test_configure_registers_a_daily_job(self):
        class FakeScheduler:
            def __init__(self):
                self.registered = []

            def register(self, job_id, fn, **kwargs):
                self.registered.append((job_id, fn, kwargs))

        fake = FakeScheduler()
        svc.configure(scheduler=fake)

        (job_id, fn, kwargs) = fake.registered[0]
        assert job_id == "card_hub_financiamento_retention_sweep"
        assert kwargs == {"hours": 24}
        assert callable(fn)

    def test_the_job_never_raises(self):
        """A bug in one run must not de-register the scheduled job."""

        def explode():
            raise RuntimeError("boom")

        svc._job_varrer_retencao(run_fn=explode)  # must not raise
