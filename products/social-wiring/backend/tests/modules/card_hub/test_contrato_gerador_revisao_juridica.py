"""One final legal review per contract (owner decision 2026-09-30, migration
177) — the default `Politica.revisao_final_unica=True` mode.

WHAT THESE PIN
--------------
- `gerar` SUCCEEDS with machine-extracted values nobody validated, and the
  version records them (`revisao_juridica_campos`: labels + provenance + a
  value fingerprint, never the value itself) — status "aguardando";
- EVERY generated version awaits the review — a fully human card's too
  (owner decision 2026-09-30: ONE final legal review PER CONTRACT; it used
  to read "nao_exigida" and go to signature unreviewed);
- an open extraction CONFLICT still refuses (the system cannot pick a
  reading), and the per-field mode (flag False) still refuses on pending;
- "Aprovar revisão jurídica" is admin/owner only (trusted DB row — a JWT
  claim does not count), stamps `revisado_por/_em`, confirms every recorded
  value on its own row and logs one ledger row tagged with the version;
- it refuses — writing nothing — when a recorded value changed after the
  rendering, when already approved, and for a version the generator did not
  write (an upload / signed copy — nothing generated to vouch for);
- sending for signature, "Baixar para impressão", marking a física contract
  signed and a manual PATCH to a final status are refused while the version
  awaits the review; a plain (rascunho) download is not.

Auth (strict 401) is covered by the card_hub route-enumerating boundary
test. All data is synthetic.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest

from noctusai_lib.testing import TEST_USER_ID

from app.modules.card_hub import contratos_service as contratos_svc
from app.modules.card_hub.contrato_gerador import validacao_extracao as vx
from app.modules.card_hub.contrato_gerador.deps import get_politica_contrato
from app.modules.card_hub.contrato_gerador.politica import POLITICA_PADRAO
from app.modules.card_hub.contrato_gerador.service import hoje
from app.modules.card_hub.deps import BUCKET
from tests.modules.card_hub.conftest import ORG_ID
from tests.modules.card_hub.test_contrato_gerador_endpoints import (
    _T0,
    _auth,
    _rows,
    _seed_completo,
    _url,
)
from tests.modules.card_hub.test_contrato_gerador_validacao_extracao import (
    _cpf_extraido,
    _vendedor,
)
from tests.modules.card_hub.test_contratos_assinatura import (
    _enviar,
    _seed,
    _seed_versao_gerada,
)

_CAMPO_REGISTRADO = {
    "chave": "cliente:x:cpf", "entidade": "cliente", "entidade_id": "x", "campo": "cpf",
    "rotulo": "CPF", "grupo": "Fulano (proprietario)", "origem": "rg",
    "fonte_documento_id": None, "fonte_nome": "rg.pdf", "confianca": "alta",
    "valor_sha256": "0" * 64,
}


def _make_admin(client, org_role: str = "owner") -> None:
    """The review is LEGAL_REVIEW_ROLES only (owner/admin/jurídico) — seed the
    TRUSTED row `is_org_admin` reads (the shared `client` carries no role)."""
    client.mock_supabase.set_table_data(
        "noctus_users", [{"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": org_role}]
    )


def _gerar(client, ids):
    return client.post(_url(ids, "gerar"), json={"assinatura_data": hoje().isoformat()}, headers=_auth())


def _aprovar(client, ids, versao_id):
    return client.post(_url(ids, f"versoes/{versao_id}/revisao-juridica"), headers=_auth())


def _versao_row(scoped, versao_id) -> dict:
    return next(r for r in _rows(scoped, "atendimento_contrato_versoes") if r["id"] == versao_id)


def _gerado_com_cpf_extraido(client, scoped) -> tuple[dict, dict]:
    ids = _seed_completo(scoped)
    doc_id = _cpf_extraido(scoped, ids)
    r = _gerar(client, ids)
    assert r.status_code == 201, r.text
    return ids, {**r.json()["versao"], "_doc_id": doc_id}


@pytest.fixture
def modo_por_campo(client):
    from app.main import app

    app.dependency_overrides[get_politica_contrato] = lambda: replace(
        POLITICA_PADRAO, revisao_final_unica=False
    )
    yield
    app.dependency_overrides.pop(get_politica_contrato, None)


class TestPolitica:
    def test_one_final_review_is_the_production_default(self):
        assert POLITICA_PADRAO.revisao_final_unica is True

    def test_the_autopilot_placeholder_is_an_alias_not_a_copy(self):
        from app.modules.matriculas import autopiloto_service

        assert autopiloto_service.REVISAO_FINAL_UNICA_POR_CONTRATO is POLITICA_PADRAO.revisao_final_unica

    def test_geracao_tells_the_ui_which_mode_is_on(self, client, scoped):
        ids = _seed_completo(scoped)
        assert client.get(_url(ids, "geracao"), headers=_auth()).json()["revisao_final_unica"] is True


class TestGerarComRevisaoFinal:
    def test_a_pending_machine_value_no_longer_blocks_and_is_recorded(self, client, scoped, fake_storage):
        ids, versao = _gerado_com_cpf_extraido(client, scoped)
        vendedor = _vendedor(scoped, ids)

        revisao = versao["revisao_juridica"]
        assert revisao["status"] == "aguardando"
        assert revisao["revisado_por"] is None and revisao["revisado_em"] is None
        assert revisao["campos"] == [{
            "chave": f"cliente:{ids['vendedor']}:cpf",
            "entidade": "cliente",
            "entidade_id": ids["vendedor"],
            "campo": "cpf",
            "rotulo": "CPF",
            "grupo": "Fulano de Tal (proprietario)",
            "origem": "rg",
            "fonte_documento_id": versao["_doc_id"],
            "fonte_nome": "rg-fulano.pdf",
            "confianca": "alta",
        }]
        # The row keeps a fingerprint of the printed value — never the value.
        [registrado] = _versao_row(scoped, versao["id"])["revisao_juridica_campos"]
        assert "valor" not in registrado
        campo_cpf = next(c for c in vx.CAMPOS_CLIENTE if c.campo == "cpf")
        assert registrado["valor_sha256"] == vx.valor_sha256(campo_cpf, vendedor)
        # Generating confirms nothing — the review does.
        assert vendedor["cpf_confirmado_em"] is None
        assert _rows(scoped, vx.LEDGER) == []

    def test_a_fully_human_card_still_awaits_the_final_review(self, client, scoped, fake_storage):
        """Zero machine-pending values used to read 'nao_exigida' — a
        generated contract went to signature with NO legal review. The
        review is of the finished instrument, so it is always due."""
        ids = _seed_completo(scoped)
        r = _gerar(client, ids)
        assert r.status_code == 201, r.text
        versao = r.json()["versao"]
        assert versao["revisao_juridica"] == {
            "status": "aguardando", "campos": [], "itens": [], "revisado_por": None, "revisado_em": None,
        }
        assert not _versao_row(scoped, versao["id"]).get("revisao_juridica_campos")

    def test_an_open_conflict_still_refuses(self, client, scoped, fake_storage):
        ids = _seed_completo(scoped)
        _cpf_extraido(scoped, ids)
        scoped.set_table_data("cliente_campo_conflitos", [{
            "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": ids["vendedor"], "campo": "cpf",
            "valor_anterior": "111", "origem_anterior": "manual", "valor_proposto": "222",
            "origem_proposto": "rg", "confianca_proposta": "alta", "fonte_tabela": "cliente_documentos",
            "fonte_id": str(uuid4()), "status": "pendente", "notificado_em": None,
            "decidido_por": None, "decidido_em": None,
        }])
        r = _gerar(client, ids)
        assert r.status_code == 409, r.text
        erro = r.json()["error"]
        assert erro["code"] == "EXTRACAO_PENDENTE_VALIDACAO"
        # Only the conflict refuses — the pending value is the review's.
        assert erro["details"]["pendentes"] == []
        assert len(erro["details"]["conflitos"]) == 1
        assert _rows(scoped, "atendimento_contrato_versoes") == []

    def test_the_per_field_mode_still_refuses_on_pending(self, client, scoped, fake_storage, modo_por_campo):
        ids = _seed_completo(scoped)
        _cpf_extraido(scoped, ids)
        r = _gerar(client, ids)
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "EXTRACAO_PENDENTE_VALIDACAO"
        assert r.json()["error"]["details"]["pendentes"]
        assert client.get(_url(ids, "geracao"), headers=_auth()).json()["revisao_final_unica"] is False


class TestAprovarRevisaoJuridica:
    def test_a_member_is_refused_and_nothing_is_written(self, client, scoped, fake_storage):
        ids, versao = _gerado_com_cpf_extraido(client, scoped)
        r = _aprovar(client, ids, versao["id"])
        assert r.status_code == 403, r.text
        assert _versao_row(scoped, versao["id"]).get("revisado_em") is None
        assert _vendedor(scoped, ids)["cpf_confirmado_em"] is None

    def test_a_corretor_is_refused(self, client, scoped, fake_storage):
        _make_admin(client, "corretor")
        ids, versao = _gerado_com_cpf_extraido(client, scoped)
        assert _aprovar(client, ids, versao["id"]).status_code == 403

    def test_the_juridico_role_may_approve(self, client, scoped, fake_storage):
        _make_admin(client, "juridico")
        ids, versao = _gerado_com_cpf_extraido(client, scoped)
        r = _aprovar(client, ids, versao["id"])
        assert r.status_code == 200, r.text
        assert _versao_row(scoped, versao["id"]).get("revisado_em") is not None

    def test_a_jwt_claiming_admin_does_not_count(self, client, scoped, fake_storage):
        client.mock_supabase.auth.get_user.return_value.user.user_metadata["org_role"] = "admin"
        ids, versao = _gerado_com_cpf_extraido(client, scoped)
        assert _aprovar(client, ids, versao["id"]).status_code == 403

    def test_approval_stamps_the_version_and_confirms_every_recorded_value(
        self, client, scoped, fake_storage
    ):
        _make_admin(client)
        ids, versao = _gerado_com_cpf_extraido(client, scoped)
        cpf = _vendedor(scoped, ids)["cpf"]

        r = _aprovar(client, ids, versao["id"])
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["confirmados"] == 1
        atual = corpo["contrato"]["versao_atual"]
        assert atual["id"] == versao["id"]
        assert atual["revisao_juridica"]["status"] == "aprovada"
        assert atual["revisao_juridica"]["revisado_em"] is not None
        assert atual["revisao_juridica"]["revisado_por"]["id"] == TEST_USER_ID

        linha = _versao_row(scoped, versao["id"])
        assert linha["revisado_por"] == TEST_USER_ID and linha["revisado_em"] is not None
        # Provenance stays truthful: the value is confirmed BY the reviewer,
        # on its own row, value untouched.
        vendedor = _vendedor(scoped, ids)
        assert vendedor["cpf"] == cpf and vendedor["cpf_origem"] == "rg"
        assert vendedor["cpf_confirmado_por"] == TEST_USER_ID
        assert vendedor["cpf_confirmado_em"] is not None
        [ledger] = _rows(scoped, vx.LEDGER)
        assert ledger["decisao"] == "aceito" and ledger["revisao_versao_id"] == versao["id"]
        assert (ledger["entidade"], ledger["campo"]) == ("cliente", "cpf")
        assert ledger["contrato_id"] == ids["contrato"] and ledger["decidido_por"] == TEST_USER_ID
        # Nothing is pending any more.
        assert client.get(_url(ids, "validacao-extracao"), headers=_auth()).json()["pendentes"] == []

    def test_a_second_approval_is_refused(self, client, scoped, fake_storage):
        _make_admin(client)
        ids, versao = _gerado_com_cpf_extraido(client, scoped)
        assert _aprovar(client, ids, versao["id"]).status_code == 200
        r = _aprovar(client, ids, versao["id"])
        assert r.status_code == 409 and r.json()["error"]["code"] == "REVISAO_JURIDICA_JA_APROVADA"
        assert len(_rows(scoped, vx.LEDGER)) == 1

    def test_a_generated_version_with_no_recorded_value_is_approved_and_confirms_nothing(
        self, client, scoped, fake_storage
    ):
        _make_admin(client)
        ids = _seed_completo(scoped)
        versao = _gerar(client, ids).json()["versao"]
        r = _aprovar(client, ids, versao["id"])
        assert r.status_code == 200, r.text
        assert r.json()["confirmados"] == 0
        assert r.json()["contrato"]["versao_atual"]["revisao_juridica"]["status"] == "aprovada"
        assert _versao_row(scoped, versao["id"])["revisado_em"] is not None
        assert _rows(scoped, vx.LEDGER) == []

    def test_a_version_the_generator_did_not_write_is_refused(self, client, scoped, fake_storage):
        """An upload / signed copy — no generated instrument to vouch for."""
        _make_admin(client)
        ids = _seed_completo(scoped)
        versao = _gerar(client, ids).json()["versao"]
        scoped.set_table_data("atendimento_contrato_versoes", [
            {**v, "origem": "upload"} for v in _rows(scoped, "atendimento_contrato_versoes")
        ])
        r = _aprovar(client, ids, versao["id"])
        assert r.status_code == 409 and r.json()["error"]["code"] == "REVISAO_JURIDICA_NAO_EXIGIDA"
        assert _versao_row(scoped, versao["id"]).get("revisado_em") is None

    def test_a_value_changed_after_the_rendering_refuses_and_writes_nothing(
        self, client, scoped, fake_storage
    ):
        _make_admin(client)
        ids, versao = _gerado_com_cpf_extraido(client, scoped)
        linhas = [
            {**r, "cpf": "98765432100"} if r["id"] == ids["vendedor"] else r
            for r in _rows(scoped, "clientes")
        ]
        scoped.set_table_data("clientes", linhas)

        r = _aprovar(client, ids, versao["id"])
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "REVISAO_JURIDICA_VERSAO_DESATUALIZADA"
        assert r.json()["error"]["details"]["chaves"] == [f"cliente:{ids['vendedor']}:cpf"]
        assert _versao_row(scoped, versao["id"]).get("revisado_em") is None
        assert _vendedor(scoped, ids)["cpf_confirmado_em"] is None
        assert _rows(scoped, vx.LEDGER) == []

    def test_a_value_confirmed_meanwhile_is_skipped_not_refused(self, client, scoped, fake_storage):
        _make_admin(client)
        ids, versao = _gerado_com_cpf_extraido(client, scoped)
        linhas = [
            {**r, "cpf_confirmado_em": _T0, "cpf_confirmado_por": "outra-pessoa"}
            if r["id"] == ids["vendedor"] else r
            for r in _rows(scoped, "clientes")
        ]
        scoped.set_table_data("clientes", linhas)

        r = _aprovar(client, ids, versao["id"])
        assert r.status_code == 200, r.text
        assert r.json()["confirmados"] == 0
        assert _vendedor(scoped, ids)["cpf_confirmado_por"] == "outra-pessoa"
        assert _rows(scoped, vx.LEDGER) == []

    def test_an_unknown_version_is_404(self, client, scoped, fake_storage):
        _make_admin(client)
        ids, _ = _gerado_com_cpf_extraido(client, scoped)
        assert _aprovar(client, ids, str(uuid4())).status_code == 404


def _versao_aguardando(scoped, fake_storage, *, modalidade=None) -> tuple[str, dict]:
    """A contract whose ONE generated version awaits the review — seeded
    straight onto the version row so the gates are tested apart from the
    generator."""
    cid, aid = _seed(scoped)
    ids = _seed_versao_gerada(scoped, fake_storage, aid)
    versoes = [
        {**v, "revisao_juridica_campos": [_CAMPO_REGISTRADO], "revisado_por": None,
         "revisado_em": None, "modalidade_assinatura": modalidade}
        for v in _rows(scoped, "atendimento_contrato_versoes")
    ]
    scoped.set_table_data("atendimento_contrato_versoes", versoes)
    if modalidade:
        contratos = [{**c, "modalidade_assinatura": modalidade} for c in _rows(scoped, "atendimento_contratos")]
        scoped.set_table_data("atendimento_contratos", contratos)
    return cid, ids


def _aprovar_direto(scoped) -> None:
    versoes = [{**v, "revisado_por": TEST_USER_ID, "revisado_em": _T0}
               for v in _rows(scoped, "atendimento_contrato_versoes")]
    scoped.set_table_data("atendimento_contrato_versoes", versoes)


def _url_versao(cid, ids, **query) -> str:
    qs = "&".join(f"{k}={v}" for k, v in query.items())
    return f"/api/clientes/{cid}/contratos/{ids['contrato_id']}/versoes/{ids['versao_id']}/url?{qs}"


class TestPortoesFinais:
    def test_sending_for_signature_waits_for_the_review(
        self, client, scoped, fake_storage, fake_signature_adapter
    ):
        cid, ids = _versao_aguardando(scoped, fake_storage)
        r = _enviar(client, cid, ids["contrato_id"], versao_id=ids["versao_id"])
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "CONTRATO_AGUARDANDO_REVISAO_JURIDICA"
        assert _rows(scoped, "atendimento_contrato_assinaturas") == []
        assert fake_signature_adapter.calls == []

        _aprovar_direto(scoped)
        r = _enviar(client, cid, ids["contrato_id"], versao_id=ids["versao_id"])
        assert r.status_code == 201, r.text

    def test_print_download_waits_for_the_review_but_the_draft_does_not(
        self, client, scoped, fake_storage
    ):
        cid, ids = _versao_aguardando(scoped, fake_storage, modalidade="fisica")
        r = client.get(_url_versao(cid, ids, intent="download", impressao="true"), headers=_auth())
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "CONTRATO_AGUARDANDO_REVISAO_JURIDICA"
        # The rascunho stays readable — the reviewer reads this very PDF.
        assert client.get(_url_versao(cid, ids, intent="download"), headers=_auth()).status_code == 200

        _aprovar_direto(scoped)
        r = client.get(_url_versao(cid, ids, intent="download", impressao="true"), headers=_auth())
        assert r.status_code == 200, r.text

    def test_marking_a_physical_contract_signed_waits_for_the_review(self, client, scoped, fake_storage):
        cid, ids = _versao_aguardando(scoped, fake_storage, modalidade="fisica")
        url = f"/api/clientes/{cid}/contratos/{ids['contrato_id']}/assinatura-fisica"
        r = client.post(url, headers=_auth())
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "CONTRATO_AGUARDANDO_REVISAO_JURIDICA"
        assert _rows(scoped, "atendimento_contratos")[0]["status"] != "assinado"

        _aprovar_direto(scoped)
        assert client.post(url, headers=_auth()).status_code == 200

    @pytest.mark.parametrize("status", ["enviado_assinatura", "assinado"])
    def test_a_manual_final_status_waits_for_the_review(self, client, scoped, fake_storage, status):
        cid, ids = _versao_aguardando(scoped, fake_storage)
        url = f"/api/clientes/{cid}/contratos/{ids['contrato_id']}"
        r = client.patch(url, json={"status": status}, headers=_auth())
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "CONTRATO_AGUARDANDO_REVISAO_JURIDICA"
        # A non-final status is never gated.
        assert client.patch(url, json={"status": "em_revisao"}, headers=_auth()).status_code == 200

    def test_a_generated_version_without_recorded_values_is_still_gated(
        self, client, scoped, fake_storage, fake_signature_adapter
    ):
        """No `revisao_juridica_campos` at all (a pre-177 row, or a rendering
        that relied on no machine value) — still a GENERATED instrument, so
        it waits for the one final review like any other."""
        cid, aid = _seed(scoped)
        ids = _seed_versao_gerada(scoped, fake_storage, aid)
        scoped.set_table_data("atendimento_contrato_versoes", [
            {k: v for k, v in linha.items() if k not in ("revisado_em", "revisado_por")}
            for linha in _rows(scoped, "atendimento_contrato_versoes")
        ])
        assert "revisao_juridica_campos" not in _rows(scoped, "atendimento_contrato_versoes")[0]
        r = _enviar(client, cid, ids["contrato_id"], versao_id=ids["versao_id"])
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "CONTRATO_AGUARDANDO_REVISAO_JURIDICA"

        _aprovar_direto(scoped)
        r = _enviar(client, cid, ids["contrato_id"], versao_id=ids["versao_id"])
        assert r.status_code == 201, r.text


def test_the_fake_pdf_exists_for_the_gate_tests(scoped, fake_storage):
    """Guard: the gate tests above read real bytes off the fake storage."""
    _cid, aid = _seed(scoped)
    ids = _seed_versao_gerada(scoped, fake_storage, aid)
    linha = _rows(scoped, "atendimento_contrato_versoes")[0]
    assert linha["id"] == ids["versao_id"]
    assert asyncio.run(fake_storage.get(bucket=BUCKET, key=linha["storage_path"])) is not None


def test_status_vocabulary_is_derived_from_the_row():
    # Keyed on the ORIGEM: every generated version awaits the review, with or
    # without recorded machine values; uploads / signed copies never do.
    assert contratos_svc.revisao_juridica_status({"origem": "gerado"}) == "aguardando"
    assert contratos_svc.revisao_juridica_status(
        {"origem": "gerado", "revisao_juridica_campos": []}
    ) == "aguardando"
    assert contratos_svc.revisao_juridica_status(
        {"origem": "gerado", "revisao_juridica_campos": [_CAMPO_REGISTRADO]}
    ) == "aguardando"
    assert contratos_svc.revisao_juridica_status(
        {"origem": "gerado", "revisao_juridica_campos": [_CAMPO_REGISTRADO], "revisado_em": _T0}
    ) == "aprovada"
    assert contratos_svc.revisao_juridica_status({"origem": "gerado", "revisado_em": _T0}) == "aprovada"
    assert contratos_svc.revisao_juridica_status({"origem": "upload"}) == "nao_exigida"
    assert contratos_svc.revisao_juridica_status({"origem": "assinado"}) == "nao_exigida"
    assert contratos_svc.revisao_juridica_status({}) == "nao_exigida"
