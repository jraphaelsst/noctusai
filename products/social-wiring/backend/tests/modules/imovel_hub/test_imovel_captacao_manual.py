"""Manual captação — `POST/PATCH /api/imoveis/manuais`, `PATCH /{codigo}/referencias`,
`GET /{codigo}` for a manual código (sw-lead-to-contract CONTRACT §8, migration 226).

WHAT THIS PINS
--------------
- a manual imóvel is a registry row (`origem_descoberta='manual'`,
  `ativo_no_vista=false`) + an `imovel_captacao` row + `imovel_dados`; the Vista
  mirror `imoveis` is NEVER written;
- código `SW-NNNN`, generated: numeric max (not lexicographic), race retry on
  the registry's unique, bounded, loud failure;
- the Drive folder id is DERIVED from the link, a non-folder link is a 400
  `drive_url_invalida` and writes nothing;
- `PATCH /manuais/{codigo}`: 409 `imovel_vista_somente_leitura` for a non-manual
  código, 404 unknown / other org, route order vs `/{codigo}/dados`;
- `GET /{codigo}` for a manual código returns the SAME shape as a mirror row
  (every `imoveis` column, nulls where a manual imóvel cannot have it);
- drift guards: the Python serializer's column set, the view's two arms and the
  `imoveis` table cannot diverge silently.

Auth is not re-tested per route here — `test_imovel_auth_boundary.py`
enumerates every mounted route; the explicit `== 401` rows for the new routes
are at the bottom of this file.
"""
from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError

from noctusai_lib.primitives.exceptions import AppException
from noctusai_lib.testing import migration_parser

from app.modules.imovel_hub import captacao_service as cap
from app.modules.imovel_hub import dados_service as dados_svc
from app.modules.imovel_hub.deps import get_imovel_hub_client
from tests.modules.imovel_hub.conftest import (
    ORG_ID,
    auth,
    dados_row,
    imovel_row,
    manual,
    registry_row,
    seed,
)

OUTRA_ORG = "00000000-0000-4000-8000-000000000099"
MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"
# Located by name, never by number: SW migration numbers are taken at
# integrate time and this one was renumbered once already (225 → 226).
(MIGRATION_CAPTACAO,) = sorted(MIGRATIONS.glob("*_imovel_captacao_manual.sql"))
DRIVE = "https://drive.google.com/drive/folders/1vfD3HHF7jN8EiMwhcHkKYrvuxz5GDlEK"

ENDERECO = {
    "cep": "05422-000",
    "logradouro": "Alameda Liverpool",
    "numero": "81",
    "bairro": "Reserva do Vianna",
    "cidade": "Cotia",
    "uf": "SP",
}


def corpo(**over) -> dict:
    body = {"titulo": "Casa Reserva do Vianna", "endereco": dict(ENDERECO)}
    body.update(over)
    return body


def seed_vazio(scoped) -> None:
    seed(scoped, registry=[], imoveis=[])
    scoped.set_table_data("imovel_captacao", [])


class _InsertFalha:
    """DI test double over a scoped client: `insert` on ONE table raises."""

    def __init__(self, inner, tabela: str, erro: Exception, vezes: int | None = None):
        self._inner, self._tabela, self._erro, self._restam = inner, tabela, erro, vezes

    def table(self, nome):
        real = self._inner.table(nome)
        if nome != self._tabela:
            return real
        outer = self

        class _Proxy:
            def __getattr__(self, attr):
                return getattr(real, attr)

            def insert(self, *a, **k):
                if outer._restam is None or outer._restam > 0:
                    if outer._restam is not None:
                        outer._restam -= 1
                    raise outer._erro
                return real.insert(*a, **k)

        return _Proxy()

    def __getattr__(self, attr):
        return getattr(self._inner, attr)


def _unico() -> APIError:
    return APIError(
        {
            "message": 'duplicate key value violates unique constraint "uq_imovel_registry_org_codigo"',
            "code": "23505",
            "details": "",
            "hint": "",
        }
    )


@pytest.fixture
def usar_cliente(client):
    """Install a client double through the module's DI seam."""
    from app.main import app

    def _usar(duble):
        app.dependency_overrides[get_imovel_hub_client] = lambda: duble

    yield _usar
    app.dependency_overrides.pop(get_imovel_hub_client, None)


# ─── código ───────────────────────────────────────────────────────────────


class TestCodigo:
    def test_formato_e_primeiro_da_sequencia(self, scoped):
        seed_vazio(scoped)
        assert cap.formatar_codigo(7) == "SW-0007"
        assert cap.formatar_codigo(12345) == "SW-12345"
        assert cap.proximo_numero(scoped, ORG_ID) == 1

    def test_o_maximo_e_numerico_nao_lexicografico(self, scoped):
        """`SW-10000` sorts BEFORE `SW-9999` as text — a text max would hand
        out a duplicate. Other shapes and other orgs never count."""
        seed(
            scoped,
            registry=[
                registry_row("SW-9999", origem_descoberta="manual"),
                registry_row("SW-10000", origem_descoberta="manual"),
                registry_row("ONE99999"),
                registry_row("SW-ABC", origem_descoberta="manual"),
                {**registry_row("SW-50000", origem_descoberta="manual"), "org_id": OUTRA_ORG},
            ],
            imoveis=[],
        )
        assert cap.proximo_numero(scoped, ORG_ID) == 10001

    def test_corrida_na_unique_tenta_o_proximo(self, scoped):
        """Two requests computed `SW-0001`; the loser's INSERT hits the
        registry unique and it retries with the next number."""
        seed_vazio(scoped)
        vencedor = registry_row("SW-0001", ativo_no_vista=False, origem_descoberta="manual")
        duble = _InsertFalha(scoped, "imovel_registry", _unico(), vezes=1)
        # the winner's row is committed by the time the loser retries
        scoped.table("imovel_registry")._data.append(vencedor)
        out = cap.registrar_manual(
            duble, ORG_ID, {"titulo": "X", "endereco": dict(ENDERECO)}, usuario_id=None
        )
        assert out["codigo"] == "SW-0002"
        assert out["fonte"] == "manual"

    def test_esgotadas_as_tentativas_falha_alto(self, scoped):
        seed_vazio(scoped)
        duble = _InsertFalha(scoped, "imovel_registry", _unico())
        with pytest.raises(AppException) as exc:
            cap.registrar_manual(
                duble, ORG_ID, {"titulo": "X", "endereco": dict(ENDERECO)}, usuario_id=None
            )
        assert exc.value.code == "imovel_codigo_indisponivel"
        assert exc.value.status_code == 503
        assert scoped.table("imovel_captacao").inserted_payloads == []

    def test_um_erro_que_nao_e_unique_nao_e_engolido(self, scoped):
        seed_vazio(scoped)
        duble = _InsertFalha(scoped, "imovel_registry", RuntimeError("conexão caiu"))
        with pytest.raises(RuntimeError, match="conexão caiu"):
            cap.registrar_manual(
                duble, ORG_ID, {"titulo": "X", "endereco": dict(ENDERECO)}, usuario_id=None
            )


# ─── POST /manuais ────────────────────────────────────────────────────────


class TestCriar:
    def test_cria_registry_captacao_e_dados_sem_tocar_o_espelho(self, client, scoped):
        seed_vazio(scoped)
        r = client.post(
            "/api/imoveis/manuais",
            json=corpo(
                categoria="Casa", status="Venda", finalidades=["venda"],
                valor_venda=1500000, area_total=420.5, dormitorios=4, suites=2, vagas=3,
                descricao_web="Casa térrea", observacoes="chaves na portaria",
                empreendimento="Reserva do Vianna", em_condominio=True,
                processo_atual_numero="876", drive_folder_url=DRIVE,
            ),
            headers=auth(),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["codigo"] == "SW-0001"
        assert body["fonte"] == "manual"
        assert body["titulo"] == "Casa Reserva do Vianna"
        assert body["valor_venda"] == 1500000
        assert body["logradouro"] == "Alameda Liverpool" and body["uf"] == "SP"
        assert body["empreendimento"] == "Reserva do Vianna"
        assert body["em_condominio"] is True
        assert body["referencias"] == {
            "processo_atual_numero": "876",
            "drive_folder_url": DRIVE,
            "drive_folder_id": "1vfD3HHF7jN8EiMwhcHkKYrvuxz5GDlEK",
        }

        reg = scoped.table("imovel_registry").inserted_payloads
        assert len(reg) == 1
        assert reg[0]["codigo_canonical"] == "SW-0001"
        assert reg[0]["origem_descoberta"] == "manual"
        assert reg[0]["ativo_no_vista"] is False
        capt = scoped.table("imovel_captacao").inserted_payloads
        assert len(capt) == 1 and capt[0]["codigo_canonical"] == "SW-0001"
        assert capt[0]["org_id"] == ORG_ID
        # 🔴 the Vista mirror is NEVER written for a manual imóvel
        mirror = scoped.table("imoveis")
        assert mirror.inserted_payloads == [] and mirror.updated_payloads == []
        assert mirror.upserted_payloads == []

    def test_resposta_tem_a_forma_completa_do_espelho_com_nulos(self, client, scoped):
        """Every `imoveis` column is present; what a manual imóvel cannot
        have is null/empty — never a missing key the FE would crash on."""
        seed_vazio(scoped)
        r = client.post("/api/imoveis/manuais", json=corpo(), headers=auth())
        assert r.status_code == 201, r.text
        body = r.json()
        faltando = set(cap.MIRROR_COLUMNS) - set(body)
        assert not faltando, faltando
        assert body["fotos"] == [] and body["corretores"] == []
        assert body["caracteristicas"] == [] and body["orientacao_solar"] == []
        assert body["foto_destaque"] is None
        assert body["valor_venda"] is None and body["valor_locacao"] is None
        assert body["exibir_no_site"] is None and body["destaque_web"] is None
        assert body["sincronizado_em"] is None
        assert body["dias_desde_atualizacao"] is None
        assert body["referencias"] == {
            "processo_atual_numero": None, "drive_folder_url": None, "drive_folder_id": None,
        }

    def test_a_sequencia_avanca(self, client, scoped):
        seed_vazio(scoped)
        a = client.post("/api/imoveis/manuais", json=corpo(), headers=auth()).json()
        b = client.post("/api/imoveis/manuais", json=corpo(titulo="Outra"), headers=auth()).json()
        assert (a["codigo"], b["codigo"]) == ("SW-0001", "SW-0002")

    @pytest.mark.parametrize(
        "mut",
        [
            lambda b: b.pop("titulo"),
            lambda b: b.pop("endereco"),
            lambda b: b["endereco"].update(cep="123"),
            lambda b: b["endereco"].pop("logradouro"),
            lambda b: b.update(titulo=""),
            lambda b: b.update(valor_venda=0),
            lambda b: b.update(area_total=-1),
            lambda b: b.update(dormitorios=-1),
            lambda b: b.update(campo_inventado=1),
        ],
    )
    def test_corpo_invalido_e_422_e_nada_e_gravado(self, client, scoped, mut):
        seed_vazio(scoped)
        body = corpo()
        mut(body)
        r = client.post("/api/imoveis/manuais", json=body, headers=auth())
        assert r.status_code == 422, r.text
        assert scoped.table("imovel_registry").inserted_payloads == []

    def test_link_que_nao_e_pasta_do_drive_e_400_e_nada_e_gravado(self, client, scoped):
        seed_vazio(scoped)
        r = client.post(
            "/api/imoveis/manuais",
            json=corpo(drive_folder_url="https://example.com/folders/abc"),
            headers=auth(),
        )
        assert r.status_code == 400, r.text
        assert r.json()["error"]["code"] == "drive_url_invalida"
        assert scoped.table("imovel_registry").inserted_payloads == []
        assert scoped.table("imovel_captacao").inserted_payloads == []

    def test_falha_depois_do_registry_e_reportada_com_o_codigo_e_converge(
        self, client, scoped, usar_cliente
    ):
        seed_vazio(scoped)
        usar_cliente(_InsertFalha(scoped, "imovel_captacao", RuntimeError("timeout"), vezes=1))
        r = client.post("/api/imoveis/manuais", json=corpo(), headers=auth())
        assert r.status_code == 500, r.text
        erro = r.json()["error"]
        assert erro["code"] == "imovel_registro_incompleto"
        assert erro["details"] == {"codigo": "SW-0001", "etapa": "captacao"}
        # the registry row exists; PATCH with a título completes it
        r2 = client.patch(
            "/api/imoveis/manuais/SW-0001",
            json={"titulo": "Casa Reserva do Vianna", "endereco": dict(ENDERECO)},
            headers=auth(),
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["codigo"] == "SW-0001" and r2.json()["fonte"] == "manual"


class TestPinsDoTechLead:
    """finalidades vocabulary, optional CEP, registry-only manual imóvel."""

    @pytest.mark.parametrize("fin", [["venda"], ["aluguel"], ["venda", "aluguel"], []])
    def test_finalidades_validas(self, client, scoped, fin):
        seed_vazio(scoped)
        r = client.post("/api/imoveis/manuais", json=corpo(finalidades=fin), headers=auth())
        assert r.status_code == 201, r.text
        assert r.json()["finalidades"] == fin

    @pytest.mark.parametrize("fin", [["Venda"], ["venda", "permuta"], ["locacao"]])
    def test_finalidades_invalidas_sao_400_com_o_campo(self, client, scoped, fin):
        seed_vazio(scoped)
        r = client.post("/api/imoveis/manuais", json=corpo(finalidades=fin), headers=auth())
        assert r.status_code == 400, r.text
        assert r.json()["error"]["details"]["field"] == "finalidades"
        assert scoped.table("imovel_registry").inserted_payloads == []

    def test_finalidades_invalidas_no_patch(self, client, scoped):
        manual(scoped)
        r = client.patch("/api/imoveis/manuais/SW-0001", json={"finalidades": ["Aluguel"]}, headers=auth())
        assert r.status_code == 400, r.text
        assert r.json()["error"]["details"]["field"] == "finalidades"

    def test_cep_e_opcional_no_post(self, client, scoped):
        seed_vazio(scoped)
        body = corpo()
        body["endereco"].pop("cep")
        r = client.post("/api/imoveis/manuais", json=body, headers=auth())
        assert r.status_code == 201, r.text
        assert r.json()["cep"] is None and r.json()["logradouro"] == "Alameda Liverpool"

    @pytest.mark.parametrize("cep", ["05422000", "05422-000"])
    def test_cep_valido_aceito(self, client, scoped, cep):
        seed_vazio(scoped)
        body = corpo()
        body["endereco"]["cep"] = cep
        assert client.post("/api/imoveis/manuais", json=body, headers=auth()).status_code == 201

    def test_get_de_registry_only_manual_devolve_imovel_minimo(self, client, scoped, espelho_vista):
        seed(
            scoped,
            registry=[registry_row("TYPED-1", ativo_no_vista=False, origem_descoberta="manual")],
            imoveis=[],
            dados=[dados_row("TYPED-1", endereco_manual_logradouro="Rua A", endereco_manual_numero="1",
                             endereco_manual_bairro="Centro", endereco_manual_cidade="Cotia",
                             endereco_manual_uf="SP", empreendimento_manual="Cond X", em_condominio=False,
                             processo_atual_numero="9")],
        )
        scoped.set_table_data("imovel_captacao", [])
        r = client.get("/api/imoveis/typed-1", headers=auth())
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["fonte"] == "manual" and b["titulo"] is None
        assert not set(cap.MIRROR_COLUMNS) - set(b)
        assert b["logradouro"] == "Rua A" and b["empreendimento"] == "Cond X"
        assert b["em_condominio"] is False
        assert b["fotos"] == [] and b["finalidades"] == [] and b["valor_venda"] is None
        assert b["referencias"]["processo_atual_numero"] == "9"

    def test_get_de_imovel_vista_traz_empreendimento_e_em_condominio(self, client, scoped, espelho_vista):
        seed(
            scoped, registry=[registry_row("ONE1")],
            imoveis=[imovel_row("ONE1", empreendimento="Edifício Aurora")],
            dados=[dados_row("ONE1", em_condominio=True)],
        )
        scoped.set_table_data("imovel_captacao", [])
        b = client.get("/api/imoveis/ONE1", headers=auth()).json()
        assert b["empreendimento"] == "Edifício Aurora" and b["em_condominio"] is True

    def test_registry_de_origem_vista_sem_captacao_continua_404_no_get(self, client, scoped, espelho_vista):
        seed(scoped, registry=[registry_row("ONE7", ativo_no_vista=False)], imoveis=[])
        scoped.set_table_data("imovel_captacao", [])
        assert client.get("/api/imoveis/ONE7", headers=auth()).status_code == 404


# ─── PATCH /manuais/{codigo} ──────────────────────────────────────────────


class TestEditar:
    def test_atualizacao_parcial(self, client, scoped):
        manual(scoped)
        r = client.patch(
            "/api/imoveis/manuais/sw-0001",
            json={"titulo": "Novo título", "valor_venda": 1600000, "endereco": {"numero": "83"}},
            headers=auth(),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["titulo"] == "Novo título" and body["valor_venda"] == 1600000
        assert body["numero"] == "83"
        assert body["logradouro"] == "Alameda Liverpool"  # untouched
        assert body["categoria"] == "Casa"  # untouched
        assert scoped.table("imoveis").updated_payloads == []

    def test_null_limpa_um_campo(self, client, scoped):
        manual(scoped)
        r = client.patch("/api/imoveis/manuais/SW-0001", json={"valor_venda": None}, headers=auth())
        assert r.status_code == 200, r.text
        assert r.json()["valor_venda"] is None

    def test_titulo_nao_pode_ser_limpo(self, client, scoped):
        manual(scoped)
        r = client.patch("/api/imoveis/manuais/SW-0001", json={"titulo": None}, headers=auth())
        assert r.status_code == 422, r.text

    @pytest.mark.parametrize("origem", ["vista_sync", "lead", "venda", "intake", "desconhecida"])
    def test_imovel_nao_manual_e_409_somente_leitura(self, client, scoped, origem):
        seed(scoped, registry=[registry_row("ONE1", origem_descoberta=origem)], imoveis=[imovel_row("ONE1")])
        scoped.set_table_data("imovel_captacao", [])
        r = client.patch("/api/imoveis/manuais/ONE1", json={"titulo": "X"}, headers=auth())
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "imovel_vista_somente_leitura"
        assert scoped.table("imovel_captacao").inserted_payloads == []

    def test_codigo_desconhecido_e_404(self, client, scoped):
        seed_vazio(scoped)
        r = client.patch("/api/imoveis/manuais/SW-0404", json={"titulo": "X"}, headers=auth())
        assert r.status_code == 404, r.text

    def test_outra_org_e_404(self, client, scoped):
        manual(scoped)
        scoped.table("imovel_registry")._data[0]["org_id"] = OUTRA_ORG
        r = client.patch("/api/imoveis/manuais/SW-0001", json={"titulo": "X"}, headers=auth())
        assert r.status_code == 404, r.text

    def test_manual_sem_captacao_vira_manual_completo_sem_exigir_titulo(self, client, scoped):
        """A registry-only manual imóvel (the picker's typed-código
        registration) gets its captação row from PATCH (upsert); `titulo` is
        required on CREATE only."""
        seed(scoped, registry=[registry_row("TYPED-1", ativo_no_vista=False, origem_descoberta="manual")], imoveis=[])
        scoped.set_table_data("imovel_captacao", [])
        r = client.patch("/api/imoveis/manuais/TYPED-1", json={"categoria": "Casa"}, headers=auth())
        assert r.status_code == 200, r.text
        assert r.json()["categoria"] == "Casa" and r.json()["titulo"] is None
        capt = scoped.table("imovel_captacao").inserted_payloads
        assert len(capt) == 1 and capt[0]["codigo_canonical"] == "TYPED-1"

    def test_rota_manuais_nao_e_capturada_por_codigo_dados(self, client, scoped):
        """`PATCH /manuais/dados` must reach the manuais handler (unknown
        código "DADOS" -> 404), never `PATCH /{codigo}/dados` with
        codigo="manuais" (which would 404 on "MANUAIS" with another
        shape/validation)."""
        seed_vazio(scoped)
        r = client.patch("/api/imoveis/manuais/dados", json={"titulo": "X"}, headers=auth())
        assert r.status_code == 404, r.text
        assert "DADOS" in r.text

    def test_declarada_antes_das_rotas_com_codigo(self):
        from app.modules.imovel_hub import register

        router = next(
            r for r in register().routers
            if any(getattr(x, "path", "") == "/api/imoveis/manuais" for x in r.routes)
        )
        paths = [(x.path, tuple(sorted(x.methods))) for x in router.routes]
        manuais = paths.index(("/api/imoveis/manuais/{codigo}", ("PATCH",)))
        for depois in ("/api/imoveis/{codigo}/dados", "/api/imoveis/{codigo}/referencias"):
            assert manuais < min(i for i, (p, _m) in enumerate(paths) if p == depois)


# ─── PATCH /{codigo}/referencias ──────────────────────────────────────────


class TestReferencias:
    def _vista(self, scoped):
        seed(scoped, registry=[registry_row("ONE1")], imoveis=[imovel_row("ONE1")])

    def test_qualquer_imovel_inclusive_vista(self, client, scoped):
        self._vista(scoped)
        r = client.patch(
            "/api/imoveis/ONE1/referencias",
            json={"processo_atual_numero": " 876 ", "drive_folder_url": DRIVE + "?usp=sharing"},
            headers=auth(),
        )
        assert r.status_code == 200, r.text
        assert r.json() == {
            "processo_atual_numero": "876",
            "drive_folder_url": DRIVE + "?usp=sharing",
            "drive_folder_id": "1vfD3HHF7jN8EiMwhcHkKYrvuxz5GDlEK",
        }
        assert scoped.table("imoveis").updated_payloads == []

    def test_parcial_e_limpar(self, client, scoped):
        seed(
            scoped, registry=[registry_row("ONE1")], imoveis=[imovel_row("ONE1")],
            dados=[dados_row("ONE1", processo_atual_numero="1", drive_folder_url=DRIVE,
                             drive_folder_id="1vfD3HHF7jN8EiMwhcHkKYrvuxz5GDlEK")],
        )
        r = client.patch("/api/imoveis/ONE1/referencias", json={"processo_atual_numero": "2"}, headers=auth())
        assert r.json()["processo_atual_numero"] == "2"
        assert r.json()["drive_folder_url"] == DRIVE  # absent = left alone
        r = client.patch("/api/imoveis/ONE1/referencias", json={"drive_folder_url": None}, headers=auth())
        assert r.json()["drive_folder_url"] is None and r.json()["drive_folder_id"] is None
        assert r.json()["processo_atual_numero"] == "2"

    @pytest.mark.parametrize(
        "url",
        [
            "https://drive.google.com/file/d/abc123/view",
            "https://drive.google.com/open?id=abc123",
            "http://drive.google.com/drive/folders/abc123",
            "https://evil.example.com/drive/folders/abc123",
            "https://drive.google.com/drive/folders/",
            "nao-e-url",
        ],
    )
    def test_link_invalido_e_400(self, client, scoped, url):
        self._vista(scoped)
        r = client.patch("/api/imoveis/ONE1/referencias", json={"drive_folder_url": url}, headers=auth())
        assert r.status_code == 400, r.text
        assert r.json()["error"]["code"] == "drive_url_invalida"
        assert scoped.table("imovel_dados").inserted_payloads == []

    def test_desconhecido_e_404(self, client, scoped):
        seed_vazio(scoped)
        r = client.patch("/api/imoveis/NADA/referencias", json={"processo_atual_numero": "1"}, headers=auth())
        assert r.status_code == 404, r.text

    def test_corpo_estrito(self, client, scoped):
        self._vista(scoped)
        r = client.patch("/api/imoveis/ONE1/referencias", json={"drive_folder_id": "x"}, headers=auth())
        assert r.status_code == 422, r.text

    @pytest.mark.parametrize(
        "url,pasta",
        [
            ("https://drive.google.com/drive/folders/AbC_123-x", "AbC_123-x"),
            ("https://drive.google.com/drive/u/0/folders/AbC_123-x?usp=sharing", "AbC_123-x"),
            ("https://drive.google.com/folders/AbC_123-x", "AbC_123-x"),
            ("  https://drive.google.com/drive/folders/AbC_123-x  ", "AbC_123-x"),
        ],
    )
    def test_id_e_derivado_da_url(self, url, pasta):
        assert dados_svc.parse_drive_folder_url(url)[1] == pasta

    def test_vazio_limpa(self):
        assert dados_svc.parse_drive_folder_url("  ") == (None, None)
        assert dados_svc.parse_drive_folder_url(None) == (None, None)


# ─── GET /{codigo} ────────────────────────────────────────────────────────


class TestDetalhe:
    def test_codigo_manual_devolve_o_imovel_completo(self, client, scoped, espelho_vista):
        manual(scoped, processo_atual_numero="876", drive_folder_url=DRIVE,
               drive_folder_id="1vfD3HHF7jN8EiMwhcHkKYrvuxz5GDlEK", empreendimento_manual="Reserva do Vianna")
        r = client.get("/api/imoveis/sw-0001", headers=auth())
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["fonte"] == "manual" and body["codigo"] == "SW-0001"
        assert not set(cap.MIRROR_COLUMNS) - set(body)
        assert body["titulo"] == "Casa Reserva do Vianna" and body["empreendimento"] == "Reserva do Vianna"
        assert body["referencias"]["processo_atual_numero"] == "876"
        assert body["referencias"]["drive_folder_id"] == "1vfD3HHF7jN8EiMwhcHkKYrvuxz5GDlEK"

    def test_imovel_vista_carrega_fonte_e_referencias(self, client, scoped, espelho_vista):
        seed(
            scoped, registry=[registry_row("ONE1")],
            imoveis=[imovel_row("ONE1", titulo="Apto")],
            dados=[dados_row("ONE1", processo_atual_numero="55")],
        )
        scoped.set_table_data("imovel_captacao", [])
        r = client.get("/api/imoveis/one1", headers=auth())
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["fonte"] == "vista" and body["titulo"] == "Apto"
        assert body["referencias"] == {
            "processo_atual_numero": "55", "drive_folder_url": None, "drive_folder_id": None,
        }

    def test_desconhecido_e_404(self, client, scoped, espelho_vista):
        seed_vazio(scoped)
        assert client.get("/api/imoveis/SW-0404", headers=auth()).status_code == 404

    def test_imovel_manual_de_outra_org_e_404(self, client, scoped, espelho_vista):
        manual(scoped)
        scoped.table("imovel_registry")._data[0]["org_id"] = OUTRA_ORG
        scoped.table("imovel_captacao")._data[0]["org_id"] = OUTRA_ORG
        assert client.get("/api/imoveis/SW-0001", headers=auth()).status_code == 404

    def test_busca_e_manuais_nao_sao_capturadas_por_codigo(self):
        from app.routers.imoveis_router import router

        paths = [getattr(r, "path", "") for r in router.routes]
        catch_all = next(i for i, p in enumerate(paths) if p == "/api/imoveis/{codigo}")
        for estatica in ("/api/imoveis/busca", "/api/imoveis/busca/duplicatas"):
            assert paths.index(estatica) < catch_all


# ─── drift guards ─────────────────────────────────────────────────────────


def _sql_sem_comentarios(arquivo: Path = MIGRATION_CAPTACAO) -> str:
    return "\n".join(l for l in arquivo.read_text().splitlines() if not l.strip().startswith("--"))


def _bracos_da_view(arquivo: Path = MIGRATION_CAPTACAO) -> tuple[list[str], list[str]]:
    sql = _sql_sem_comentarios(arquivo)
    corpo_view = sql[sql.index("CREATE OR REPLACE VIEW social_wiring.imoveis_catalogo"):]
    corpo_view = corpo_view[: corpo_view.index("COMMENT ON VIEW")]
    arm_vista, arm_manual = corpo_view.split("UNION ALL")

    def itens(arm: str) -> list[str]:
        select = arm[arm.index("SELECT") + len("SELECT"): arm.index("\nFROM")]
        return [i.strip() for i in migration_parser._split_top_level_commas(select) if i.strip()]

    return itens(arm_vista), itens(arm_manual)


class TestDerivaConjunta:
    def test_serializador_python_cobre_exatamente_as_colunas_do_espelho(self):
        migracoes = sorted(p for p in MIGRATIONS.glob("*.sql") if re.match(r"^\d+_", p.name))
        esquema = migration_parser.parse_files(migracoes)
        colunas = esquema["social_wiring.imoveis"]
        assert set(cap.MIRROR_COLUMNS) == colunas, (
            f"só no serializador: {set(cap.MIRROR_COLUMNS) - colunas}; "
            f"só em imoveis: {colunas - set(cap.MIRROR_COLUMNS)}"
        )

    def test_os_dois_bracos_da_view_tem_as_mesmas_colunas_na_mesma_ordem(self):
        vista, manual_arm = _bracos_da_view()
        nomes_vista = [re.sub(r"^i\.", "", i) for i in vista[:-1]]
        assert nomes_vista == list(cap.MIRROR_COLUMNS)
        assert vista[-1].endswith("AS fonte") and manual_arm[-1].endswith("AS fonte")
        assert len(vista) == len(manual_arm) == len(cap.MIRROR_COLUMNS) + 1

    def test_view_e_security_invoker(self):
        assert "security_invoker = true" in _sql_sem_comentarios()


# ─── strict 401 on the new routes ─────────────────────────────────────────


@pytest.mark.parametrize(
    "metodo,caminho,json",
    [
        ("post", "/api/imoveis/manuais", {}),
        ("patch", "/api/imoveis/manuais/SW-0001", {}),
        ("patch", "/api/imoveis/SW-0001/referencias", {}),
        ("get", "/api/imoveis/SW-0001", None),
    ],
)
def test_novas_rotas_exigem_auth_com_401_estrito(anon_client, metodo, caminho, json):
    kwargs = {} if json is None else {"json": json}
    resp = getattr(anon_client, metodo)(caminho, **kwargs)
    assert resp.status_code == 401, f"{metodo.upper()} {caminho} -> {resp.status_code}: {resp.text}"
