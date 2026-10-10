"""É o mesmo imóvel — link / unlink (migration 228, CONTRACT §8.7).

WHAT THIS PINS
--------------
- `resolver_vinculo` from EITHER side (the interface `vinculo_legal` codes against);
- `vincular`: pair must be `pendente` (409 `duplicata_ja_resolvida`), sets
  `vinculado_a` + `confirmado` + an audit event, THEN calls `reconciliar`;
- `desvincular`: calls `limpar` FIRST, then restores the registry row and the
  pair EXACTLY;
- the legal module is a DI port (a fake is injected — never patched) and its
  absence / failure is REPORTED in `legal`, never silent, never undoing the link;
- both routes are admin-only on the TRUSTED `noctus_users` row;
- display through the link (`enriquecer`, `GET /{codigo}`, `/busca`).
"""
from __future__ import annotations

import copy
from uuid import UUID

import pytest

from noctusai_lib.primitives.exceptions import AppException

from app.modules.imovel_hub import busca_service
from app.modules.imovel_hub import vinculo_service as vinc
from app.modules.imovel_hub.deps import get_vinculo_legal
from tests.modules.imovel_hub.conftest import ORG_ID, auth
from tests.modules.imovel_hub.dup_rows import MANUAL, VISTA, cenario, par_row

ORG = UUID(ORG_ID)
V = vinc.Vinculo(MANUAL, VISTA)


class FakeVinculoLegal:
    """The `vinculo_legal` port: records calls and the registry state at call
    time (so ORDER is observable)."""

    def __init__(self, scoped=None, *, falha_em=None, retorno=None):
        self.chamadas: list[tuple] = []
        self._scoped, self._falha_em, self._retorno = scoped, falha_em, retorno

    def _estado(self):
        if self._scoped is None:
            return None
        return {r["codigo_canonical"]: r.get("vinculado_a") for r in self._scoped.table("imovel_registry")._data}

    def reconciliar(self, client, org_id, vinculo):
        self.chamadas.append(("reconciliar", org_id, vinculo, self._estado()))
        if self._falha_em == "reconciliar":
            raise RuntimeError("legal boom")
        return self._retorno

    def limpar(self, client, org_id, vinculo):
        self.chamadas.append(("limpar", org_id, vinculo, self._estado()))
        if self._falha_em == "limpar":
            raise RuntimeError("limpar boom")
        return self._retorno


def registro(scoped, codigo):
    return next(r for r in scoped.table("imovel_registry")._data if r["codigo_canonical"] == codigo)


def par(scoped):
    return scoped.table("imovel_duplicata_candidatos")._data[0]


def eventos(scoped):
    return scoped.table("imovel_vinculo_eventos")._data


# ─── resolver_vinculo ─────────────────────────────────────────────────────


class TestResolver:
    def test_dos_dois_lados(self, client, scoped):
        reg = cenario(scoped)
        registro(scoped, MANUAL)["vinculado_a"] = reg["vista"]["id"]
        assert vinc.resolver_vinculo(scoped, ORG, MANUAL) == V
        assert vinc.resolver_vinculo(scoped, ORG, "sw-0001") == V
        assert vinc.resolver_vinculo(scoped, ORG, VISTA) == V
        assert vinc.resolver_vinculo(scoped, ORG, " one1234 ") == V

    def test_sem_vinculo_ou_desconhecido_e_none(self, client, scoped):
        cenario(scoped)
        assert vinc.resolver_vinculo(scoped, ORG, MANUAL) is None
        assert vinc.resolver_vinculo(scoped, ORG, VISTA) is None
        assert vinc.resolver_vinculo(scoped, ORG, "NOPE") is None

    def test_outra_org_nao_resolve(self, client, scoped):
        reg = cenario(scoped)
        registro(scoped, MANUAL)["vinculado_a"] = reg["vista"]["id"]
        assert vinc.resolver_vinculo(scoped, UUID("00000000-0000-4000-8000-000000000099"), MANUAL) is None

    def test_linhas_sem_id_nao_quebram(self, client, scoped):
        """Legacy fixtures seed registry rows with no `id`: None, never a KeyError."""
        cenario(scoped)
        for r in scoped.table("imovel_registry")._data:
            r.pop("id", None)
        assert vinc.resolver_vinculo(scoped, ORG, VISTA) is None
        assert vinc.resolver_vinculo(scoped, ORG, MANUAL) is None

    def test_vinculo_e_imutavel_e_serializavel(self):
        assert V.as_dict() == {"manual_codigo": MANUAL, "vista_codigo": VISTA}
        with pytest.raises(Exception):
            V.manual_codigo = "x"  # frozen dataclass


# ─── vincular ─────────────────────────────────────────────────────────────

ATOR = UUID("00000000-0000-4000-8000-0000000000a1")


class TestVincular:
    def test_liga_confirma_audita_e_reconcilia_nessa_ordem(self, client, scoped):
        reg = cenario(scoped, pares=[par_row()])
        legal = FakeVinculoLegal(scoped, retorno={"matricula": "copiada"})
        out = vinc.vincular(scoped, ORG, par(scoped)["id"], ATOR, legal=legal)

        assert registro(scoped, MANUAL)["vinculado_a"] == reg["vista"]["id"]
        assert registro(scoped, VISTA).get("vinculado_a") is None
        p = par(scoped)
        assert p["status"] == "confirmado" and p["resolvido_por"] == str(ATOR) and p["resolvido_em"]
        (ev,) = eventos(scoped)
        assert (ev["acao"], ev["codigo_manual"], ev["codigo_vista"], ev["ator"]) == (
            "vincular", MANUAL, VISTA, str(ATOR)
        )
        assert ev["duplicata_id"] == p["id"]
        # reconciliar ran AFTER the link existed
        (chamada,) = legal.chamadas
        assert chamada[0] == "reconciliar" and chamada[1] == ORG and chamada[2] == V
        assert chamada[3][MANUAL] == reg["vista"]["id"]
        # wire shape
        assert set(out) == {"duplicata", "vinculo", "legal", "novos_conflitos"}
        assert out["vinculo"] == {"manual_codigo": MANUAL, "vista_codigo": VISTA}
        assert out["legal"] == {"status": "ok", "matricula": "copiada"}
        assert out["duplicata"]["status"] == "confirmado" and out["duplicata"]["id"] == p["id"]
        # and the outcome is recorded on the audit event
        assert ev["legal"] == out["legal"]

    def test_legal_devolve_novos_e_ja_em_conflito_sem_as_linhas(self, client, scoped):
        cenario(scoped, pares=[par_row()])
        legal = FakeVinculoLegal(retorno={
            "novos": ["numero_matricula"], "fechados": [], "ja_em_conflito": ["x"],
            "novos_conflitos": [{"campo": "numero_matricula"}],
        })
        out = vinc.vincular(scoped, ORG, par(scoped)["id"], ATOR, legal=legal)
        assert out["legal"] == {"status": "ok", "novos": ["numero_matricula"], "fechados": [],
                                "ja_em_conflito": ["x"]}
        assert out["novos_conflitos"] == [{"campo": "numero_matricula"}]
        assert "novos_conflitos" not in eventos(scoped)[0]["legal"]

    def test_retorno_nao_dict_do_legal_vira_status_ok(self, client, scoped):
        cenario(scoped, pares=[par_row()])
        out = vinc.vincular(scoped, ORG, par(scoped)["id"], ATOR, legal=FakeVinculoLegal(retorno=None))
        assert out["legal"] == {"status": "ok"}

    @pytest.mark.parametrize("status", ["confirmado", "descartado"])
    def test_par_resolvido_e_409_e_nada_muda(self, client, scoped, status):
        cenario(scoped, pares=[par_row(status)])
        legal = FakeVinculoLegal()
        with pytest.raises(AppException) as exc:
            vinc.vincular(scoped, ORG, par(scoped)["id"], ATOR, legal=legal)
        assert exc.value.code == "duplicata_ja_resolvida" and exc.value.status_code == 409
        assert registro(scoped, MANUAL).get("vinculado_a") is None
        assert eventos(scoped) == [] and legal.chamadas == []

    def test_manual_ja_vinculado_a_outro_e_409(self, client, scoped):
        reg = cenario(scoped, pares=[par_row()])
        registro(scoped, MANUAL)["vinculado_a"] = reg["manual"]["id"]  # any non-null
        with pytest.raises(AppException) as exc:
            vinc.vincular(scoped, ORG, par(scoped)["id"], ATOR, legal=FakeVinculoLegal())
        assert exc.value.code == "imovel_ja_vinculado"

    def test_vista_que_ja_tem_manual_e_409(self, client, scoped):
        from tests.modules.imovel_hub.conftest import registry_row

        reg = cenario(scoped, pares=[par_row(manual="SW-0002")],
                      extra_registry=[registry_row("SW-0002", ativo_no_vista=False, origem_descoberta="manual")])
        registro(scoped, MANUAL)["vinculado_a"] = reg["vista"]["id"]
        with pytest.raises(AppException) as exc:
            vinc.vincular(scoped, ORG, par(scoped)["id"], ATOR, legal=FakeVinculoLegal())
        assert exc.value.code == "vista_ja_vinculada"

    def test_lado_manual_que_nao_e_manual_e_409(self, client, scoped):
        cenario(scoped, pares=[par_row()], manual_reg={"origem_descoberta": "vista_sync"})
        with pytest.raises(AppException) as exc:
            vinc.vincular(scoped, ORG, par(scoped)["id"], ATOR, legal=FakeVinculoLegal())
        assert exc.value.code == "imovel_nao_manual"

    def test_par_de_outra_org_e_404(self, client, scoped):
        cenario(scoped, pares=[par_row(org_id="00000000-0000-4000-8000-000000000099")])
        with pytest.raises(Exception) as exc:
            vinc.vincular(scoped, ORG, par(scoped)["id"], ATOR, legal=FakeVinculoLegal())
        assert getattr(exc.value, "status_code", None) == 404


class TestLegalIndisponivelOuComFalha:
    def test_modulo_ausente_e_reportado_e_o_vinculo_fica(self, client, scoped, caplog):
        reg = cenario(scoped, pares=[par_row()])
        with caplog.at_level("ERROR"):
            out = vinc.vincular(scoped, ORG, par(scoped)["id"], ATOR, legal=None)
        assert out["legal"] == {"status": "erro", "mensagem": "módulo indisponível"}
        assert registro(scoped, MANUAL)["vinculado_a"] == reg["vista"]["id"]
        assert par(scoped)["status"] == "confirmado"
        assert "vinculo_legal module unavailable" in caplog.text
        assert eventos(scoped)[0]["legal"] == out["legal"]

    def test_excecao_em_reconciliar_e_reportada_e_nao_desfaz(self, client, scoped, caplog):
        reg = cenario(scoped, pares=[par_row()])
        with caplog.at_level("ERROR"):
            out = vinc.vincular(scoped, ORG, par(scoped)["id"], ATOR, legal=FakeVinculoLegal(falha_em="reconciliar"))
        assert out["legal"]["status"] == "erro" and "legal boom" in out["legal"]["mensagem"]
        assert registro(scoped, MANUAL)["vinculado_a"] == reg["vista"]["id"]
        assert any(r.exc_info for r in caplog.records)

    def test_excecao_em_limpar_e_reportada_e_o_desvinculo_segue(self, client, scoped):
        reg = cenario(scoped, pares=[par_row("confirmado")])
        registro(scoped, MANUAL)["vinculado_a"] = reg["vista"]["id"]
        out = vinc.desvincular(scoped, ORG, MANUAL, ATOR, legal=FakeVinculoLegal(falha_em="limpar"))
        assert out["legal"]["status"] == "erro" and "limpar boom" in out["legal"]["mensagem"]
        assert registro(scoped, MANUAL).get("vinculado_a") is None

    def test_carregador_devolve_none_quando_o_modulo_nao_existe(self):
        assert vinc.carregar_vinculo_legal("app.modules.imovel_hub.este_modulo_nao_existe") is None
        assert vinc.carregar_vinculo_legal("app.modulos_inexistentes.vinculo_legal") is None

    def test_carregador_carrega_um_modulo_existente(self):
        modulo = vinc.carregar_vinculo_legal("app.modules.imovel_hub.dados_service")
        assert modulo is not None and hasattr(modulo, "linha")

    def test_default_carrega_preguicosamente_e_sem_modulo_reporta(self, client, scoped):
        """With NO `legal` argument the service loads `vinculo_legal` lazily; in
        a tree where it does not exist yet the outcome is the reported 'erro',
        in a tree where it does the call is made — either way never silent."""
        cenario(scoped, pares=[par_row()])
        out = vinc.vincular(scoped, ORG, par(scoped)["id"], ATOR)
        assert out["legal"]["status"] in ("ok", "erro")
        if out["legal"]["status"] == "erro":
            assert out["legal"]["mensagem"]


# ─── desvincular ──────────────────────────────────────────────────────────


class TestDesvincular:
    def test_vincular_e_desvincular_restauram_exatamente(self, client, scoped):
        cenario(scoped, pares=[par_row()])
        registry_antes = copy.deepcopy(scoped.table("imovel_registry")._data)
        par_antes = copy.deepcopy(par(scoped))
        legal = FakeVinculoLegal(scoped)

        vinc.vincular(scoped, ORG, par(scoped)["id"], ATOR, legal=legal)
        out = vinc.desvincular(scoped, ORG, MANUAL, ATOR, legal=legal)

        # (`vinculado_a` is NULL = absent in the mock; compare as NULL)
        assert [{**r, "vinculado_a": r.get("vinculado_a")} for r in scoped.table("imovel_registry")._data] == [
            {**r, "vinculado_a": r.get("vinculado_a")} for r in registry_antes
        ]
        p = par(scoped)
        assert (p["status"], p["resolvido_por"], p["resolvido_em"]) == ("pendente", None, None)
        assert {k: v for k, v in p.items() if k != "atualizado_em"} == {
            k: v for k, v in par_antes.items() if k != "atualizado_em"
        }
        assert [c[0] for c in legal.chamadas] == ["reconciliar", "limpar"]
        assert [e["acao"] for e in eventos(scoped)] == ["vincular", "desvincular"]
        assert out["vinculo"] == {"manual_codigo": MANUAL, "vista_codigo": VISTA}
        assert out["duplicata"]["status"] == "pendente" and out["legal"] == {"status": "ok"}
        assert set(out) == {"vinculo", "duplicata", "legal"}

    def test_limpar_roda_antes_de_apagar_o_vinculo(self, client, scoped):
        reg = cenario(scoped, pares=[par_row("confirmado")])
        registro(scoped, MANUAL)["vinculado_a"] = reg["vista"]["id"]
        legal = FakeVinculoLegal(scoped)
        vinc.desvincular(scoped, ORG, MANUAL, ATOR, legal=legal)
        (chamada,) = legal.chamadas
        assert chamada[0] == "limpar" and chamada[2] == V
        assert chamada[3][MANUAL] == reg["vista"]["id"]  # link still there when `limpar` ran

    def test_aceita_o_codigo_vista(self, client, scoped):
        reg = cenario(scoped, pares=[par_row("confirmado")])
        registro(scoped, MANUAL)["vinculado_a"] = reg["vista"]["id"]
        out = vinc.desvincular(scoped, ORG, VISTA, ATOR, legal=FakeVinculoLegal())
        assert out["vinculo"] == {"manual_codigo": MANUAL, "vista_codigo": VISTA}
        assert registro(scoped, MANUAL).get("vinculado_a") is None

    def test_sem_vinculo_e_404(self, client, scoped):
        cenario(scoped)
        legal = FakeVinculoLegal()
        with pytest.raises(AppException) as exc:
            vinc.desvincular(scoped, ORG, MANUAL, ATOR, legal=legal)
        assert exc.value.code == "imovel_nao_vinculado" and exc.value.status_code == 404
        assert legal.chamadas == [] and eventos(scoped) == []

    def test_nao_toca_nenhuma_outra_tabela_de_negocio(self, client, scoped):
        """Nothing is re-pointed: captação, dados and the mirror are identical
        after a link + unlink."""
        cenario(scoped, pares=[par_row()])
        antes = {t: copy.deepcopy(scoped.table(t)._data) for t in ("imovel_captacao", "imovel_dados", "imoveis")}
        vinc.vincular(scoped, ORG, par(scoped)["id"], ATOR, legal=FakeVinculoLegal())
        vinc.desvincular(scoped, ORG, MANUAL, ATOR, legal=FakeVinculoLegal())
        for t, linhas in antes.items():
            assert scoped.table(t)._data == linhas, t


# ─── routes: admin-only ───────────────────────────────────────────────────

BASE = "/api/imoveis"


def _scoped_do_cliente():
    from app.modules.imovel_hub.deps import get_imovel_hub_client

    return get_imovel_hub_client()


@pytest.fixture
def legal_injetado():
    from app.main import app

    fake = FakeVinculoLegal()
    app.dependency_overrides[get_vinculo_legal] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_vinculo_legal, None)


class TestRotasAdmin:
    def test_membro_comum_leva_403_estrito_em_vincular_e_nada_muda(self, member_client, legal_injetado):
        scoped = _scoped_do_cliente()
        cenario(scoped, pares=[par_row()])
        r = member_client.post(f"{BASE}/duplicatas/{par(scoped)['id']}/vincular", headers=auth())
        assert r.status_code == 403, r.text
        assert registro(scoped, MANUAL).get("vinculado_a") is None
        assert par(scoped)["status"] == "pendente" and eventos(scoped) == []
        assert legal_injetado.chamadas == []

    def test_membro_comum_leva_403_estrito_em_desvincular_e_nada_muda(self, member_client, legal_injetado):
        scoped = _scoped_do_cliente()
        reg = cenario(scoped, pares=[par_row("confirmado")])
        registro(scoped, MANUAL)["vinculado_a"] = reg["vista"]["id"]
        r = member_client.post(f"{BASE}/{MANUAL}/desvincular", headers=auth())
        assert r.status_code == 403, r.text
        assert registro(scoped, MANUAL)["vinculado_a"] == reg["vista"]["id"]
        assert par(scoped)["status"] == "confirmado" and legal_injetado.chamadas == []

    def test_jwt_dizendo_admin_nao_burla_o_gate(self):
        """The TRUSTED row says member; a caller-rewritten `user_metadata`
        claiming admin must still 403."""
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from tests.conftest import bind_consent_module_to_mock  # type: ignore[attr-defined]
        from tests.modules.imovel_hub.conftest import _role_mock
        from noctusai_lib.testing import MockUser, MockUserResponse
        from unittest.mock import MagicMock
        from noctusai_lib.testing import TEST_USER_ID
        from tests.modules.imovel_hub.conftest import ORG_RAW

        mock_sb = _role_mock("member")
        mock_sb.auth.get_user = MagicMock(
            return_value=MockUserResponse(MockUser(id=TEST_USER_ID, org_id=ORG_RAW, org_role="admin"))
        )
        with (
            patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
            patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
            patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
        ):
            from app.main import app

            bind_consent_module_to_mock(mock_sb)
            scoped = _scoped_do_cliente()
            cenario(scoped, pares=[par_row()])
            r = TestClient(app).post(f"{BASE}/duplicatas/{par(scoped)['id']}/vincular", headers=auth())
            assert r.status_code == 403, r.text
            app.dependency_overrides.clear()

    def test_admin_vincula_e_desvincula_pela_rota(self, admin_client, legal_injetado):
        scoped = _scoped_do_cliente()
        reg = cenario(scoped, pares=[par_row()])
        pid = par(scoped)["id"]

        r = admin_client.post(f"{BASE}/duplicatas/{pid}/vincular", headers=auth())
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body) == {"duplicata", "vinculo", "legal"}
        assert body["vinculo"] == {"manual_codigo": MANUAL, "vista_codigo": VISTA}
        assert body["legal"] == {"status": "ok"} and body["duplicata"]["status"] == "confirmado"
        assert registro(scoped, MANUAL)["vinculado_a"] == reg["vista"]["id"]
        assert eventos(scoped)[0]["ator"] is not None  # the audit row names the admin

        r = admin_client.post(f"{BASE}/duplicatas/{pid}/vincular", headers=auth())
        assert r.status_code == 409 and r.json()["error"]["code"] == "duplicata_ja_resolvida"

        r = admin_client.post(f"{BASE}/{MANUAL.lower()}/desvincular", headers=auth())
        assert r.status_code == 200, r.text
        assert set(r.json()) == {"vinculo", "duplicata", "legal"}
        assert registro(scoped, MANUAL).get("vinculado_a") is None and par(scoped)["status"] == "pendente"
        assert [c[0] for c in legal_injetado.chamadas] == ["reconciliar", "limpar"]

    def test_rota_anuncia_os_novos_conflitos_e_nao_os_expoe(self, admin_client):
        from app.main import app
        from app.modules.imovel_hub.deps import get_imovel_notification_service
        from tests.modules.imovel_hub.conftest import FakeImovelNotifier

        notif = FakeImovelNotifier()
        legal = FakeVinculoLegal(retorno={
            "novos": ["numero_matricula"], "fechados": [], "ja_em_conflito": [],
            "novos_conflitos": [{"campo": "numero_matricula", "id": "c1"}],
        })
        app.dependency_overrides[get_vinculo_legal] = lambda: legal
        app.dependency_overrides[get_imovel_notification_service] = lambda: notif
        try:
            scoped = _scoped_do_cliente()
            cenario(scoped, pares=[par_row()])
            r = admin_client.post(f"{BASE}/duplicatas/{par(scoped)['id']}/vincular", headers=auth())
        finally:
            app.dependency_overrides.pop(get_vinculo_legal, None)
            app.dependency_overrides.pop(get_imovel_notification_service, None)
        assert r.status_code == 200, r.text
        assert set(r.json()) == {"duplicata", "vinculo", "legal"}
        assert r.json()["legal"]["novos"] == ["numero_matricula"]
        assert [(n["codigo"], n["conflito"]["campo"]) for n in notif.conflitos] == [(VISTA, "numero_matricula")]

    def test_rota_sem_modulo_legal_reporta_erro_no_corpo(self, admin_client):
        from app.main import app

        app.dependency_overrides[get_vinculo_legal] = lambda: None
        try:
            scoped = _scoped_do_cliente()
            cenario(scoped, pares=[par_row()])
            r = admin_client.post(f"{BASE}/duplicatas/{par(scoped)['id']}/vincular", headers=auth())
        finally:
            app.dependency_overrides.pop(get_vinculo_legal, None)
        assert r.status_code == 200, r.text
        assert r.json()["legal"] == {"status": "erro", "mensagem": "módulo indisponível"}

    def test_desvincular_sem_vinculo_e_404_pela_rota(self, admin_client, legal_injetado):
        scoped = _scoped_do_cliente()
        cenario(scoped)
        r = admin_client.post(f"{BASE}/{MANUAL}/desvincular", headers=auth())
        assert r.status_code == 404 and r.json()["error"]["code"] == "imovel_nao_vinculado"

    def test_ordem_das_rotas_post_nao_colide(self):
        from app.main import app

        posts = [(r.path, r.methods) for r in app.routes if hasattr(r, "methods") and "POST" in r.methods]
        paths = [p for p, _ in posts]
        assert f"{BASE}/duplicatas/{{duplicata_id}}/descartar" in paths
        assert f"{BASE}/duplicatas/{{duplicata_id}}/vincular" in paths
        assert f"{BASE}/{{codigo}}/desvincular" in paths


# ─── display through the link ─────────────────────────────────────────────


def ligar(scoped, **cen_kw):
    reg = cenario(scoped, pares=[par_row("confirmado")], **cen_kw)
    registro(scoped, MANUAL)["vinculado_a"] = reg["vista"]["id"]
    return reg


class TestExibicaoPeloVinculo:
    def test_enriquecer_do_manual_ligado_mostra_o_catalogo_da_vista(self, client, scoped):
        ligar(
            scoped,
            manual_dados={"endereco_manual_logradouro": "Alameda Liverpool", "endereco_manual_numero": "81",
                          "endereco_manual_cidade": "Cotia", "endereco_manual_uf": "SP"},
            espelho={"titulo": "Casa Vista ONE", "valor_venda": "1480000.00", "dormitorios": 4,
                     "area_total": "300.00"},
            manual_cap={"valor_venda": 1_500_000, "dormitorios": 2},
        )
        item = busca_service.enriquecer(scoped, ORG, [MANUAL])[MANUAL]
        # catalog data from the listing
        assert item["titulo"] == "Casa Vista ONE" and item["valor_venda"] == 1_480_000.0
        assert item["dormitorios"] == 4 and item["foto_destaque"] == "https://img/vista.jpg"
        assert item["valor"] == 1_480_000.0 and item["valor_tipo"] == "venda"
        # the manual record's own identity + address
        assert item["codigo"] == MANUAL and item["fonte"] == "manual" and item["origem"] == "manual"
        assert item["logradouro"] == "Alameda Liverpool" and item["numero"] == "81"
        assert item["vinculo"] == {"manual_codigo": MANUAL, "vista_codigo": VISTA}

    def test_endereco_em_branco_do_manual_cai_para_o_da_listagem(self, client, scoped):
        ligar(scoped, manual_dados={})
        item = busca_service.enriquecer(scoped, ORG, [MANUAL])[MANUAL]
        assert item["bairro"] == "Reserva do Vianna" and item["endereco"].startswith("Al. Liverpool")

    def test_seguir_vinculo_false_devolve_o_proprio(self, client, scoped):
        ligar(scoped, espelho={"titulo": "Casa Vista ONE"})
        item = busca_service.enriquecer(scoped, ORG, [MANUAL], seguir_vinculo=False)[MANUAL]
        assert item["titulo"] == "Casa Reserva do Vianna" and item["vinculo"] is not None

    def test_a_vista_carrega_vinculado_a_manual(self, client, scoped):
        ligar(scoped)
        item = busca_service.enriquecer(scoped, ORG, [VISTA])[VISTA]
        assert item["vinculado_a_manual"] == MANUAL
        assert item["vinculo"] == {"manual_codigo": MANUAL, "vista_codigo": VISTA}
        assert item["titulo"] == "Casa em condomínio"  # its own data, untouched

    def test_imovel_sem_vinculo_nao_ganha_chaves_novas(self, client, scoped):
        cenario(scoped)
        item = busca_service.enriquecer(scoped, ORG, [VISTA, MANUAL])
        assert "vinculo" not in item[VISTA] and "vinculado_a_manual" not in item[MANUAL]

    def test_listagem_sumida_do_espelho_mantem_os_dados_do_manual(self, client, scoped):
        ligar(scoped)
        scoped.set_table_data("imoveis", [])
        item = busca_service.enriquecer(scoped, ORG, [MANUAL])[MANUAL]
        assert item["titulo"] == "Casa Reserva do Vianna" and item["vinculo"]["vista_codigo"] == VISTA

    def test_busca_esconde_o_manual_ligado_e_devolve_a_vista(self, client, scoped):
        ligar(scoped, manual_dados={"endereco_manual_logradouro": "Alameda Liverpool"})
        r = client.get("/api/imoveis/busca?q=Liverpool", headers=auth())
        assert r.status_code == 200, r.text
        codigos = [i["codigo"] for i in r.json()["items"]]
        assert MANUAL not in codigos and VISTA in codigos
        vista = next(i for i in r.json()["items"] if i["codigo"] == VISTA)
        assert vista["vinculado_a_manual"] == MANUAL

    def test_busca_pelo_codigo_do_manual_devolve_a_vista(self, client, scoped):
        ligar(scoped)
        items = client.get("/api/imoveis/busca?q=SW-0001", headers=auth()).json()["items"]
        assert [i["codigo"] for i in items] == [VISTA]

    def test_busca_sem_vinculo_continua_achando_o_manual(self, client, scoped):
        cenario(scoped, manual_dados={"endereco_manual_logradouro": "Alameda Liverpool"})
        items = client.get("/api/imoveis/busca?q=Liverpool", headers=auth()).json()["items"]
        assert MANUAL in [i["codigo"] for i in items]

    def test_get_codigo_manual_ligado_rende_o_catalogo_da_vista_com_vinculo(self, client, scoped, espelho_vista):
        ligar(
            scoped,
            manual_dados={"endereco_manual_logradouro": "Alameda Liverpool", "endereco_manual_numero": "81",
                          "processo_atual_numero": "876", "em_condominio": True},
            espelho={"titulo": "Casa Vista ONE", "fotos": ["a.jpg", "b.jpg"], "valor_venda": "1480000.00"},
        )
        b = client.get(f"/api/imoveis/{MANUAL}", headers=auth()).json()
        assert b["titulo"] == "Casa Vista ONE" and b["fotos"] == ["a.jpg", "b.jpg"]
        assert b["valor_venda"] == "1480000.00" or float(b["valor_venda"]) == 1_480_000.0
        assert b["codigo"] == MANUAL and b["codigo_norm"] == MANUAL and b["fonte"] == "manual"
        assert b["referencias"]["processo_atual_numero"] == "876" and b["em_condominio"] is True
        assert b["logradouro"] == "Alameda Liverpool"  # the manual record's own address
        assert b["vinculo"] == {"manual_codigo": MANUAL, "vista_codigo": VISTA}

    def test_get_codigo_vista_ligada_traz_o_vinculo(self, client, scoped, espelho_vista):
        ligar(scoped)
        b = client.get(f"/api/imoveis/{VISTA}", headers=auth()).json()
        assert b["fonte"] == "vista" and b["vinculo"] == {"manual_codigo": MANUAL, "vista_codigo": VISTA}
        assert b["titulo"] == "Casa em condomínio"

    def test_get_codigo_manual_ligado_mas_listagem_ausente_devolve_o_manual(self, client, scoped, espelho_vista):
        ligar(scoped)
        scoped.set_table_data("imoveis", [])
        b = client.get(f"/api/imoveis/{MANUAL}", headers=auth()).json()
        assert b["fonte"] == "manual" and b["titulo"] == "Casa Reserva do Vianna"
        assert b["vinculo"] == {"manual_codigo": MANUAL, "vista_codigo": VISTA}


class TestVinculoComOLegalReal:
    """End to end through the REAL `vinculo_legal` (no FakeVinculoLegal): the
    seam between dup-A (link) and dup-B (legal data follows it) — each half's
    own tests stub the other side."""

    def _dados_vista(self, scoped):
        from app.modules.imovel_hub import dados_service

        return dados_service.obter(scoped, ORG, VISTA)

    def test_vista_vazio_herda_a_matricula_do_cadastro_manual_e_desvincular_restaura(
        self, client, scoped
    ):
        cenario(
            scoped,
            pares=[par_row()],
            manual_dados={"numero_matricula": "12345", "numero_registro_imoveis": "1º CRI de Cotia"},
        )
        scoped.set_table_data("imovel_campo_conflitos", [])
        antes = self._dados_vista(scoped)
        assert not antes.get("numero_matricula")

        out = vinc.vincular(scoped, ORG, par(scoped)["id"], ATOR)
        assert out["legal"]["status"] == "ok", out["legal"]
        depois = self._dados_vista(scoped)
        assert depois["numero_matricula"] == "12345"
        assert depois["vinculo_legal"]["fontes"]["numero_matricula"] == MANUAL
        assert depois["vinculo_legal"]["conflitos"] == []

        vinc.desvincular(scoped, ORG, MANUAL, ATOR)
        restaurado = self._dados_vista(scoped)
        assert not restaurado.get("numero_matricula")
        assert restaurado.get("vinculo_legal") is None

    def test_valores_diferentes_viram_conflito_e_desvincular_o_remove(self, client, scoped):
        cenario(
            scoped,
            pares=[par_row()],
            manual_dados={"numero_matricula": "12345"},
            vista_dados={"numero_matricula": "99999"},
        )
        scoped.set_table_data("imovel_campo_conflitos", [])

        out = vinc.vincular(scoped, ORG, par(scoped)["id"], ATOR)
        assert out["legal"]["status"] == "ok", out["legal"]
        conflitos = scoped.table("imovel_campo_conflitos").select("*").execute().data
        assert [c.get("fonte_tabela") for c in conflitos] == ["vinculo"]
        dados = self._dados_vista(scoped)
        # never silently picks the manual value while the conflict is open
        assert dados["numero_matricula"] == "99999"
        assert "numero_matricula" in dados["vinculo_legal"]["conflitos"]

        vinc.desvincular(scoped, ORG, VISTA, ATOR)  # either side's código
        restantes = scoped.table("imovel_campo_conflitos").select("*").execute().data
        assert [c for c in restantes if c.get("fonte_tabela") == "vinculo" and not c.get("resolvido_em")] == []
