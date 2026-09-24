"""`GET/POST /api/clientes/{cliente_id}/empresas` (P0c contract §D1/§D2) —
the card's company-graph panel, and `card_hub.empresas_service.listar`'s own
assembly (item 5 of the P0c integration dispatch).

WHAT THESE PIN
--------------
- HTTP: empty (never a 409) with no open/an ambiguous atendimento; a manual
  link 201s, 422s an invalid CNPJ, 404s a non-participant;
- `listar`'s assembly: owners MERGED across participações (E4 — one
  `Empresa` row even when two people share it, both spouses' `owners[]`
  entries present); `exige_certidoes`/`motivo` for every E1 bucket (`ativa`,
  `baixada` inside/outside the 5-year window, no Cartão yet, a permuta
  comprador counted as certificando, and NO certificando owner at all —
  `sem_socio_certificando` overrides even an `ativa` situação);
- the certidões summary (`total`/`por_resultado`/`consulta_ids`).

Auth is NOT re-tested here — `card_hub/test_auth_boundary.py` covers every
mounted card_hub route, `/api/clientes/{cliente_id}/empresas` included.
"""
from __future__ import annotations

from datetime import date
from uuid import uuid4

from noctusai_lib.testing import TEST_USER_ID

from app.modules.card_hub import empresas_service as svc
from tests.modules.card_hub.conftest import ORG_ID, cliente_row


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _atendimento(aid: str, cliente_id: str, **over) -> dict:
    row = {
        "id": aid, "org_id": ORG_ID, "cliente_id": cliente_id,
        "lead_id": None, "meta_ads_lead_id": None, "status": "aberta",
        "substituida_por": None, "arquivado": False, "titulo": "Compra do apto",
        "created_at": "2026-01-01T00:00:00+00:00", "closed_at": None,
    }
    row.update(over)
    return row


def _empresa(id_=None, **over) -> dict:
    row = {
        "id": id_ or str(uuid4()), "org_id": ORG_ID, "cnpj": "11222333000181",
        "razao_social": "Empresa Um LTDA", "nome_fantasia": None,
        "natureza_juridica": None, "data_abertura": None,
        "situacao_cadastral": None, "data_situacao_cadastral": None,
        "motivo_situacao": None, "dados_origem": None, "dados_documento_id": None,
        "dados_em": None, "dados_confirmado_por": None, "dados_confirmado_em": None,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": None,
    }
    row.update(over)
    return row


def _participacao(cliente_id: str, empresa_id: str, **over) -> dict:
    row = {
        "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": cliente_id,
        "empresa_id": empresa_id, "participacao_pct": "50.00", "desde": None,
        "fonte_documento_id": None, "origem": "manual",
        "confirmado_por": None, "confirmado_em": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    row.update(over)
    return row


def _seed_tables(scoped) -> None:
    for t in (
        "clientes", "atendimentos", "atendimento_partes",
        "atendimento_negociacao_parcelas", "empresas",
        "cliente_empresa_participacoes", "certidao_consultas",
        "certidao_resultados", "empresa_documentos",
    ):
        scoped.set_table_data(t, [])


class TestHttpEmptyCases:
    def test_no_open_atendimento_is_an_empty_list_never_a_409(self, client, scoped):
        cid = str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Solo")])
        r = client.get(f"/api/clientes/{cid}/empresas", headers=_auth())
        assert r.status_code == 200
        assert r.json() == {"atendimento_id": None, "referencia": r.json()["referencia"], "items": []}

    def test_an_ambiguous_atendimento_is_also_an_empty_list(self, client, scoped):
        cid = str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Dois Negocios")])
        scoped.set_table_data("atendimentos", [
            _atendimento(str(uuid4()), cid), _atendimento(str(uuid4()), cid),
        ])
        r = client.get(f"/api/clientes/{cid}/empresas", headers=_auth())
        assert r.status_code == 200
        assert r.json()["items"] == []


class TestHttpManualLink:
    def test_creates_a_manual_link(self, client, scoped):
        cid, aid = str(uuid4()), str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Titular")])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
        r = client.post(
            f"/api/clientes/{cid}/empresas", headers=_auth(),
            json={"cnpj": "11222333000181", "participante_cliente_id": cid,
                  "razao_social": "Nova Empresa LTDA"},
        )
        assert r.status_code == 201, r.text
        assert r.json()["cnpj"] == "11222333000181"

    def test_an_invalid_cnpj_is_400(self, client, scoped):
        cid, aid = str(uuid4()), str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Titular")])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
        r = client.post(
            f"/api/clientes/{cid}/empresas", headers=_auth(),
            json={"cnpj": "11222333000199", "participante_cliente_id": cid},
        )
        assert r.status_code == 400, r.text

    def test_a_non_participant_is_404(self, client, scoped):
        cid, aid = str(uuid4()), str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Titular")])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
        r = client.post(
            f"/api/clientes/{cid}/empresas", headers=_auth(),
            json={"cnpj": "11222333000181", "participante_cliente_id": str(uuid4())},
        )
        assert r.status_code == 404


class TestListarAssembly:
    """`empresas_service.listar`, called directly — the panel's own
    assembly, independent of the HTTP transport already pinned above."""

    def test_owners_merge_across_a_shared_empresa(self, scoped):
        """E4: a vendedor and their spouse both hold a participação in the
        SAME empresa -> ONE `items[]` row, `owners[]` carrying both."""
        cid, aid = str(uuid4()), str(uuid4())
        vendedor_id, conjuge_id = str(uuid4()), str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [
            cliente_row(cid, nome="Titular"),
            cliente_row(vendedor_id, nome="Vendedor Um", conjuge_cliente_id=conjuge_id),
            cliente_row(conjuge_id, nome="Conjuge Do Vendedor"),
        ])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
        scoped.set_table_data("atendimento_partes", [{
            "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": aid,
            "cliente_id": vendedor_id, "lado": "vendedor", "papel": "proprietario",
            "ordem": 0, "observacao": None, "created_at": "2026-01-01T00:00:00+00:00",
            "created_by": None, "updated_at": None,
        }])
        empresa = _empresa(situacao_cadastral="ativa")
        scoped.set_table_data("empresas", [empresa])
        scoped.set_table_data("cliente_empresa_participacoes", [
            _participacao(vendedor_id, empresa["id"], origem="serasa_crednet"),
            _participacao(conjuge_id, empresa["id"], origem="serasa_crednet"),
        ])

        resultado = svc.listar(scoped, ORG_ID, cid)

        assert len(resultado["items"]) == 1
        owners = resultado["items"][0]["owners"]
        assert {o["cliente_id"] for o in owners} == {vendedor_id, conjuge_id}
        assert all(o["certificando"] for o in owners)

    def test_exige_certidoes_ativa(self, scoped):
        cid, dono_id = str(uuid4()), str(uuid4())
        exige, motivo = self._um_dono_vendedor(scoped, cid, dono_id, situacao_cadastral="ativa")
        assert (exige, motivo) == (True, "ativa")

    def test_exige_certidoes_baixada_menos_de_5_anos(self, scoped):
        cid, dono_id = str(uuid4()), str(uuid4())
        recente = date.today().replace(year=date.today().year - 2).isoformat()
        exige, motivo = self._um_dono_vendedor(
            scoped, cid, dono_id, situacao_cadastral="baixada",
            data_situacao_cadastral=recente,
        )
        assert (exige, motivo) == (True, "baixada_menos_5_anos")

    def test_exige_certidoes_baixada_5_anos_ou_mais(self, scoped):
        cid, dono_id = str(uuid4()), str(uuid4())
        antiga = date.today().replace(year=date.today().year - 6).isoformat()
        exige, motivo = self._um_dono_vendedor(
            scoped, cid, dono_id, situacao_cadastral="baixada",
            data_situacao_cadastral=antiga,
        )
        assert (exige, motivo) == (False, "baixada_5_anos_ou_mais")

    def test_exige_certidoes_sem_cartao_cnpj(self, scoped):
        cid, dono_id = str(uuid4()), str(uuid4())
        exige, motivo = self._um_dono_vendedor(scoped, cid, dono_id, situacao_cadastral=None)
        assert (exige, motivo) == (False, "sem_cartao_cnpj")

    def test_permuta_comprador_is_certificando(self, scoped):
        """[E6/H11] The titular (a comprador) counts too, only when the
        deal `tem_permuta`."""
        cid, aid = str(uuid4()), str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Comprador Permuta")])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
        scoped.set_table_data("atendimento_negociacao_parcelas", [{
            "id": "p-permuta", "org_id": ORG_ID, "atendimento_id": aid, "tipo": "permuta",
        }])
        empresa = _empresa(situacao_cadastral="ativa")
        scoped.set_table_data("empresas", [empresa])
        scoped.set_table_data("cliente_empresa_participacoes", [
            _participacao(cid, empresa["id"]),
        ])

        resultado = svc.listar(scoped, ORG_ID, cid)

        [item] = resultado["items"]
        assert item["owners"][0]["certificando"] is True
        assert item["exige_certidoes"] is True

    def test_a_comprador_without_permuta_is_not_certificando_so_the_empresa_is_not_exigida(
        self, scoped
    ):
        """The mirror of the permuta case: no permuta parcela -> the
        titular's own empresa is never required, EVEN `ativa`
        (`sem_socio_certificando` overrides the situação)."""
        cid, aid = str(uuid4()), str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Comprador Simples")])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
        empresa = _empresa(situacao_cadastral="ativa")
        scoped.set_table_data("empresas", [empresa])
        scoped.set_table_data("cliente_empresa_participacoes", [
            _participacao(cid, empresa["id"]),
        ])

        resultado = svc.listar(scoped, ORG_ID, cid)

        [item] = resultado["items"]
        assert item["owners"][0]["certificando"] is False
        assert item["exige_certidoes"] is False
        assert item["motivo"] == "sem_socio_certificando"

    def test_certidoes_summary_counts(self, scoped):
        cid, aid = str(uuid4()), str(uuid4())
        vendedor_id = str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [
            cliente_row(cid, nome="Titular"), cliente_row(vendedor_id, nome="Vendedor"),
        ])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
        scoped.set_table_data("atendimento_partes", [{
            "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": aid,
            "cliente_id": vendedor_id, "lado": "vendedor", "papel": "proprietario",
            "ordem": 0, "observacao": None, "created_at": "2026-01-01T00:00:00+00:00",
            "created_by": None, "updated_at": None,
        }])
        empresa = _empresa(situacao_cadastral="ativa")
        scoped.set_table_data("empresas", [empresa])
        scoped.set_table_data("cliente_empresa_participacoes", [
            _participacao(vendedor_id, empresa["id"]),
        ])
        consultas = [
            {"id": f"c{i}", "org_id": ORG_ID, "empresa_id": empresa["id"],
             "cliente_id": None, "atendimento_parte_id": None,
             "tipo_documento": "cnpj", "documento": empresa["cnpj"], "nome": empresa["razao_social"],
             "excluida_em": None, "situacao_cadastral": None, "data_situacao": None,
             "situacao_origem": None}
            for i in (1, 2)
        ]
        scoped.set_table_data("certidao_consultas", consultas)
        scoped.set_table_data("certidao_resultados", [
            {"id": "r1", "org_id": ORG_ID, "consulta_id": "c1", "tipo": "cnd_federal",
             "resultado": "negativa", "numero": "1", "emitida_em": None, "validade_ate": None,
             "ordem": 0},
            {"id": "r2", "org_id": ORG_ID, "consulta_id": "c2", "tipo": "serasa",
             "resultado": None, "numero": None, "emitida_em": None, "validade_ate": None,
             "ordem": 0},
        ])

        resultado = svc.listar(scoped, ORG_ID, cid)

        [item] = resultado["items"]
        assert item["certidoes"]["total"] == 2
        assert item["certidoes"]["por_resultado"]["negativa"] == 1
        assert item["certidoes"]["por_resultado"]["pendente"] == 1
        assert set(item["certidoes"]["consulta_ids"]) == {"c1", "c2"}

    @staticmethod
    def _um_dono_vendedor(scoped, cid, dono_id, **empresa_over):
        aid = str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [
            cliente_row(cid, nome="Titular"), cliente_row(dono_id, nome="Vendedor"),
        ])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
        scoped.set_table_data("atendimento_partes", [{
            "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": aid,
            "cliente_id": dono_id, "lado": "vendedor", "papel": "proprietario",
            "ordem": 0, "observacao": None, "created_at": "2026-01-01T00:00:00+00:00",
            "created_by": None, "updated_at": None,
        }])
        empresa = _empresa(**empresa_over)
        scoped.set_table_data("empresas", [empresa])
        scoped.set_table_data("cliente_empresa_participacoes", [
            _participacao(dono_id, empresa["id"]),
        ])
        resultado = svc.listar(scoped, ORG_ID, cid)
        [item] = resultado["items"]
        return item["exige_certidoes"], item["motivo"]


class TestOrdering:
    """Slice D (owner decision, 2026-09-24): a dispensada empresa stays on
    the tab (never unlinked) but sorts LAST."""

    def test_dispensada_empresas_sort_last(self, scoped):
        cid, aid = str(uuid4()), str(uuid4())
        vendedor_a, vendedor_b = str(uuid4()), str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [
            cliente_row(cid, nome="Titular"),
            cliente_row(vendedor_a, nome="Vendedor A"),
            cliente_row(vendedor_b, nome="Vendedor B"),
        ])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
        scoped.set_table_data("atendimento_partes", [
            {
                "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": aid,
                "cliente_id": vendedor_a, "lado": "vendedor", "papel": "proprietario",
                "ordem": 0, "observacao": None, "created_at": "2026-01-01T00:00:00+00:00",
                "created_by": None, "updated_at": None,
            },
            {
                "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": aid,
                "cliente_id": vendedor_b, "lado": "vendedor", "papel": "proprietario",
                "ordem": 1, "observacao": None, "created_at": "2026-01-01T00:00:00+00:00",
                "created_by": None, "updated_at": None,
            },
        ])
        # `empresa_dispensada` sorts alphabetically/insertion-order BEFORE
        # `empresa_exigida` — proving the reorder is what put it last, not
        # incidental insertion order.
        empresa_dispensada = _empresa(
            id_="a" + str(uuid4())[1:], cnpj="11222333000181", situacao_cadastral=None,
        )
        empresa_exigida = _empresa(
            id_="z" + str(uuid4())[1:], cnpj="12345678000195", situacao_cadastral="ativa",
        )
        scoped.set_table_data("empresas", [empresa_dispensada, empresa_exigida])
        scoped.set_table_data("cliente_empresa_participacoes", [
            _participacao(vendedor_a, empresa_dispensada["id"]),
            _participacao(vendedor_b, empresa_exigida["id"]),
        ])

        resultado = svc.listar(scoped, ORG_ID, cid)

        assert [i["exige_certidoes"] for i in resultado["items"]] == [True, False]
        assert resultado["items"][-1]["empresa"]["id"] == empresa_dispensada["id"]


def _make_admin(client) -> None:
    """`DELETE .../empresas/{empresa_id}` is owner/admin only (the
    TRUSTED `noctus_users` row — mirrors `test_conflitos.py::_make_admin`'s
    identical seed)."""
    client.mock_supabase.set_table_data(
        "noctus_users",
        [{"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": "owner"}],
    )


class TestHttpDelete:
    def test_non_admin_is_403(self, client, scoped):
        cid, aid = str(uuid4()), str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Titular")])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
        empresa = _empresa()
        scoped.set_table_data("empresas", [empresa])
        scoped.set_table_data("cliente_empresa_participacoes", [
            _participacao(cid, empresa["id"]),
        ])

        r = client.delete(f"/api/clientes/{cid}/empresas/{empresa['id']}", headers=_auth())

        assert r.status_code == 403

    def test_admin_unlink_keeps_empresa_when_another_participacao_remains(
        self, client, scoped
    ):
        cid, aid = str(uuid4()), str(uuid4())
        outro_cliente = str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Titular")])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
        empresa = _empresa()
        scoped.set_table_data("empresas", [empresa])
        scoped.set_table_data("cliente_empresa_participacoes", [
            _participacao(cid, empresa["id"]),
            _participacao(outro_cliente, empresa["id"]),
        ])
        _make_admin(client)

        r = client.delete(f"/api/clientes/{cid}/empresas/{empresa['id']}", headers=_auth())

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["participacao_removida"] is True
        assert body["empresa_removida"] is False
        assert body["storage_falhas"] == []
        restantes = (
            scoped.table("cliente_empresa_participacoes").select("*")
            .eq("empresa_id", empresa["id"]).execute().data
        )
        assert [p["cliente_id"] for p in restantes] == [outro_cliente]

    def test_admin_unlink_last_participacao_deletes_empresa_and_storage(
        self, client, scoped
    ):
        from app.modules.empresas.deps import get_storage_backend as get_empresas_storage
        from app.main import app
        from noctusai_lib.integrations.storage import FakeStorageBackend

        cid, aid = str(uuid4()), str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Titular")])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
        empresa = _empresa()
        scoped.set_table_data("empresas", [empresa])
        scoped.set_table_data("cliente_empresa_participacoes", [
            _participacao(cid, empresa["id"]),
        ])
        doc = {
            "id": str(uuid4()), "org_id": ORG_ID, "empresa_id": empresa["id"],
            "storage_path": f"{ORG_ID}/empresas/{empresa['id']}/cartao.pdf",
        }
        scoped.set_table_data("empresa_documentos", [doc])
        _make_admin(client)

        fake_storage = FakeStorageBackend()
        app.dependency_overrides[get_empresas_storage] = lambda: fake_storage
        try:
            r = client.delete(
                f"/api/clientes/{cid}/empresas/{empresa['id']}", headers=_auth()
            )
        finally:
            app.dependency_overrides.pop(get_empresas_storage, None)

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["empresa_removida"] is True
        assert body["documentos_removidos"] == 1
        assert body["storage_falhas"] == []
        assert scoped.table("empresas").select("*").eq(
            "id", empresa["id"]
        ).execute().data == []

    def test_unknown_participacao_is_404(self, client, scoped):
        cid, aid = str(uuid4()), str(uuid4())
        _seed_tables(scoped)
        scoped.set_table_data("clientes", [cliente_row(cid, nome="Titular")])
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])
        empresa = _empresa()
        scoped.set_table_data("empresas", [empresa])
        _make_admin(client)

        r = client.delete(f"/api/clientes/{cid}/empresas/{empresa['id']}", headers=_auth())

        assert r.status_code == 404
