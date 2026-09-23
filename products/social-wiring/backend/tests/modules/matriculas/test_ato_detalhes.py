"""Migration 115 — act details, the título phrase, the ônus creditor, the
previous owners, and permuta quotes. Through HTTP where a route exists.

Every read here that hands back party names / CPFs without the act text is
asserted on its `detalhes_view` log row, and every write on what it wrote —
a 200 alone proves nothing. All texts, names, CPFs and banks are invented.
"""
from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID, uuid4

from app.modules.matriculas import estrutura_service as svc
from app.modules.matriculas import titulo_service
from tests.modules.matriculas.conftest import (
    CODIGO,
    ORG_ID,
    TEXTO,
    RecordingDB,
    contrato_row,
    extracao_row,
    registry_row,
    seed,
)

ORG = UUID(ORG_ID)

TEXTO_TITULO = (
    "MATRÍCULA Nº 12.345 — FICHA 01\n"
    "IMÓVEL: Casa ficticia nº 7 da Rua dos Exemplos, Cotia.\n"
    "PROPRIETÁRIO: JOÃO EXEMPLO DA SILVA, CPF 123.456.789-09.\n"
    "R-1/12.345 - Em 12/03/2020. VENDA E COMPRA. TÍTULO: Escritura Pública de Venda "
    "e Compra lavrada em 12/03/2020 no 2º Tabelionato de Notas de Cotia, Livro 100, "
    "fls. 20. TRANSMITENTE: JOÃO EXEMPLO DA SILVA, CPF 123.456.789-09; ADQUIRENTE: "
    "PEDRO AMOSTRA SOUZA, CPF 987.654.321-00. VALOR: R$ 450.000,00.\n"
    "R-2/12.345 - Em 12/03/2020. ALIENAÇÃO FIDUCIÁRIA. CREDORA FIDUCIÁRIA: CAIXA "
    "ECONÔMICA EXEMPLO - CEE, CNPJ 11.222.333/0001-81. DEVEDOR FIDUCIANTE: PEDRO "
    "AMOSTRA SOUZA.\n"
)

FRASE_ESPERADA = (
    "por Escritura Pública de Venda e Compra lavrada em 12/03/2020 no 2º "
    "Tabelionato de Notas de Cotia, Livro 100, fls. 20, registrada sob o R-1"
)


def texto_com_venda(data_venda: date) -> str:
    return (
        "MATRÍCULA Nº 777\nTerreno ficticio.\n"
        "R-1/777 - Em 01/02/1990. COMPRA E VENDA. Transmitente: ANTIGO DONO FICTICIO, "
        "CPF 246.813.579-28; adquirente: SEGUNDO DONO FICTICIO, CPF 135.792.468-28.\n"
        f"R-2/777 - Em {data_venda:%d/%m/%Y}. VENDA E COMPRA. Transmitente: SEGUNDO "
        "DONO FICTICIO, CPF 135.792.468-28; adquirente: ATUAL DONA FICTICIA, CPF "
        "314.159.265-90.\n"
        "AV-3/777 - Em 05/05/2021. Averba-se a CONSTRUÇÃO de uma casa.\n"
    )


def _data(resp):
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _por_chave(atos):
    return {(a["kind"], a["numero"]): a for a in atos}


def _logs(scoped, acao):
    return [r for r in scoped.table("imovel_documento_acessos").inserted_payloads if r["acao"] == acao]


def _atos(client, ext_id):
    return _data(client.get(f"/api/matriculas/extracoes/{ext_id}/atos"))["atos"]


# ─── details on the act listing ───────────────────────────────────────────


class TestTheListingCarriesDetails:
    def test_every_act_but_the_abertura_has_a_suggestion(self, client, scoped):
        ext = extracao_row()
        seed(scoped, extracoes=[ext])

        atos = _por_chave(_atos(client, ext["id"]))

        assert atos[("abertura", None)]["detalhes"] is None
        r1 = atos[("R", 1)]["detalhes"]
        assert r1["natureza"] == "compra_e_venda"
        assert r1["data_registro"] == "2001-03-10"
        assert r1["valor"] == "100000.00"
        assert [p["nome"] for p in r1["transmitentes"]] == ["Fulana de Teste Exemplar"]
        assert [p["nome"] for p in r1["adquirentes"]] == ["Beltrano Modelo"]
        assert r1["origem"] == "sugestao" and r1["confirmado_por"] is None
        assert atos[("R", 2)]["detalhes"]["credor"] == "Banco Imaginario S/A"
        assert atos[("AV", 3)]["detalhes"]["natureza"] == "cancelamento"
        assert atos[("AV", 3)]["detalhes"]["atos_referidos"] == [{"kind": "R", "numero": 2}]

    def test_one_text_view_covers_the_details(self, client, scoped):
        ext = extracao_row()
        seed(scoped, extracoes=[ext])

        _atos(client, ext["id"])

        assert len(_logs(scoped, "text_view")) == 1
        assert _logs(scoped, "detalhes_view") == []

    def test_details_are_minted_at_segmentation(self):
        db = RecordingDB()

        svc.persistir_atos(db, str(uuid4()), ORG_ID, TEXTO)

        linhas = db.inserts["matricula_ato_detalhes"]
        assert len(linhas) == len(db.inserts["matricula_atos"]) - 1  # no abertura
        assert {r["origem"] for r in linhas} == {"sugestao"}
        ato_ids = {a["id"] for a in db.inserts["matricula_atos"] if a["kind"] != "abertura"}
        assert {r["ato_id"] for r in linhas} == ato_ids

    def test_acts_without_details_are_backfilled_on_read(self, client, scoped):
        ext = extracao_row()
        seed(scoped, extracoes=[ext])
        _atos(client, ext["id"])
        atos_existentes = scoped.table("matricula_atos").select("*").execute().data
        # Acts segmented before migration 115: rows exist, details do not.
        seed(scoped, extracoes=[ext], atos=atos_existentes, detalhes=[])

        atos = _atos(client, ext["id"])

        assert all(a["detalhes"] for a in atos if a["kind"] != "abertura")
        assert scoped.table("matricula_atos").inserted_payloads == []
        assert len(scoped.table("matricula_ato_detalhes").inserted_payloads) == 6

    def test_a_confirmed_row_is_never_re_suggested(self, client, scoped):
        ext = extracao_row()
        seed(scoped, extracoes=[ext])
        r2 = _por_chave(_atos(client, ext["id"]))[("R", 2)]
        _data(client.put(f"/api/matriculas/atos/{r2['id']}/detalhes", json={"credor": "Outro Banco"}))

        de_novo = _por_chave(_atos(client, ext["id"]))[("R", 2)]["detalhes"]

        assert de_novo["credor"] == "Outro Banco"
        assert de_novo["origem"] == "confirmado"


# ─── PUT /atos/{id}/detalhes ──────────────────────────────────────────────


class TestConfirmingDetails:
    def _r2(self, client, scoped):
        ext = extracao_row()
        seed(scoped, extracoes=[ext])
        return ext, _por_chave(_atos(client, ext["id"]))

    def test_an_edit_confirms_and_stamps(self, client, scoped):
        ext, atos = self._r2(client, scoped)
        scoped.set_table_data("imovel_documento_acessos", [])

        data = _data(
            client.put(
                f"/api/matriculas/atos/{atos[('R', 2)]['id']}/detalhes",
                json={
                    "credor": " Banco Imaginario S/A ",
                    "valor": 80000,
                    "transmitentes": [{"nome": "Beltrano Modelo", "cpf_cnpj": "12345678909"}],
                },
            )
        )

        det = data["detalhes"]
        assert data["ato_ref"] == "R-2"
        assert det["origem"] == "confirmado"
        assert det["confirmado_por"] and det["confirmado_em"]
        assert det["credor"] == "Banco Imaginario S/A"
        assert det["credor_confianca"] == "alta"
        assert det["valor"] == "80000.00"
        assert det["transmitentes"] == [{"nome": "Beltrano Modelo", "cpf_cnpj": "123.456.789-09"}]
        assert det["natureza"] == "hipoteca", "an untouched field keeps its suggestion"
        log = _logs(scoped, "detalhes_view")
        assert len(log) == 1 and log[0]["extracao_id"] == ext["id"]

    def test_an_empty_body_confirms_the_suggestion_as_is(self, client, scoped):
        _ext, atos = self._r2(client, scoped)

        det = _data(client.put(f"/api/matriculas/atos/{atos[('R', 1)]['id']}/detalhes", json={}))["detalhes"]

        assert det["origem"] == "confirmado"
        assert det["natureza"] == "compra_e_venda"
        atualizados = scoped.table("matricula_ato_detalhes").updated_payloads
        assert atualizados and atualizados[-1]["origem"] == "confirmado"

    def test_null_clears_a_field(self, client, scoped):
        _ext, atos = self._r2(client, scoped)

        det = _data(
            client.put(f"/api/matriculas/atos/{atos[('R', 2)]['id']}/detalhes", json={"credor": None})
        )["detalhes"]

        assert (det["credor"], det["credor_confianca"]) == (None, "nenhuma")

    def test_the_abertura_has_no_details_to_confirm(self, client, scoped):
        _ext, atos = self._r2(client, scoped)
        resp = client.put(
            f"/api/matriculas/atos/{atos[('abertura', None)]['id']}/detalhes", json={}
        )
        assert resp.status_code == 400

    def test_an_unknown_act_is_a_404(self, client, scoped):
        seed(scoped)
        resp = client.put(f"/api/matriculas/atos/{uuid4()}/detalhes", json={})
        assert resp.status_code == 404

    def test_an_unknown_field_or_nature_is_a_422(self, client, scoped):
        _ext, atos = self._r2(client, scoped)
        url = f"/api/matriculas/atos/{atos[('R', 2)]['id']}/detalhes"
        assert client.put(url, json={"origem": "confirmado"}).status_code == 422
        assert client.put(url, json={"natureza": "venda"}).status_code == 422


# ─── título aquisitivo phrase ─────────────────────────────────────────────


class TestTituloAquisitivo:
    def _preparar(self, client, scoped):
        ext = extracao_row(texto=TEXTO_TITULO)
        seed(scoped, registry=[registry_row()], extracoes=[ext])
        atos = _por_chave(_atos(client, ext["id"]))
        return ext, atos

    def test_without_a_confirmed_title_act_there_is_no_suggestion(self, client, scoped):
        self._preparar(client, scoped)

        data = _data(client.get(f"/api/matriculas/imoveis/{CODIGO}/titulo-aquisitivo"))

        assert data["sugestao"] is None
        assert data["motivo_sem_sugestao"] == "sem_titulo_confirmado"
        assert data["ato"] is None and data["confirmado"] is None

    def test_the_phrase_is_built_from_the_confirmed_acts_instrument(self, client, scoped):
        ext, atos = self._preparar(client, scoped)
        r1 = atos[("R", 1)]
        _data(
            client.put(
                f"/api/matriculas/extracoes/{ext['id']}/fontes",
                json={"titulo_aquisitivo_ato_id": r1["id"]},
            )
        )
        scoped.set_table_data("imovel_documento_acessos", [])

        data = _data(client.get(f"/api/matriculas/imoveis/{CODIGO.lower()}/titulo-aquisitivo"))

        assert data["sugestao"] == FRASE_ESPERADA
        assert data["ato"]["ato_ref"] == "R-1"
        assert data["ato"]["detalhes_origem"] == "sugestao"
        assert len(_logs(scoped, "detalhes_view")) == 1

    def test_confirming_lands_on_imovel_dados_and_null_clears(self, client, scoped):
        ext, atos = self._preparar(client, scoped)
        client.put(
            f"/api/matriculas/extracoes/{ext['id']}/fontes",
            json={"titulo_aquisitivo_ato_id": atos[("R", 1)]["id"]},
        )
        url = f"/api/matriculas/imoveis/{CODIGO}/titulo-aquisitivo"

        data = _data(client.put(url, json={"texto": FRASE_ESPERADA + " (ajustado)"}))
        assert data["confirmado"]["texto"] == FRASE_ESPERADA + " (ajustado)"
        assert data["confirmado"]["confirmado_por"]
        dados = client.get(f"/api/imoveis/{CODIGO}/dados").json()
        assert dados["titulo_aquisitivo_texto"] == FRASE_ESPERADA + " (ajustado)"

        limpo = _data(client.put(url, json={"texto": None}))
        assert limpo["confirmado"] is None

    def test_the_body_key_is_required(self, client, scoped):
        self._preparar(client, scoped)
        resp = client.put(f"/api/matriculas/imoveis/{CODIGO}/titulo-aquisitivo", json={})
        assert resp.status_code == 422

    def test_an_unknown_imovel_is_a_404(self, client, scoped):
        seed(scoped)
        resp = client.get("/api/matriculas/imoveis/NOPE9/titulo-aquisitivo")
        assert resp.status_code == 404


# ─── ônus creditor ────────────────────────────────────────────────────────


class TestOnusCredor:
    def test_suggested_from_the_confirmed_onus_acts_then_confirmed(self, client, scoped):
        ext = extracao_row(texto=TEXTO_TITULO)
        seed(scoped, registry=[registry_row()], extracoes=[ext])
        atos = _por_chave(_atos(client, ext["id"]))
        client.put(
            f"/api/matriculas/extracoes/{ext['id']}/fontes",
            json={"onus_ato_ids": [atos[("R", 2)]["id"]]},
        )
        scoped.set_table_data("imovel_documento_acessos", [])
        url = f"/api/matriculas/imoveis/{CODIGO}/onus-credor"

        data = _data(client.get(url))
        assert data["sugestao"] == "CAIXA ECONÔMICA EXEMPLO"
        assert data["atos"][0]["ato_ref"] == "R-2"
        assert data["atos"][0]["natureza"] == "alienacao_fiduciaria"
        assert data["atos"][0]["credor_confianca"] == "alta"
        assert len(_logs(scoped, "detalhes_view")) == 1

        confirmado = _data(client.put(url, json={"credor": "Caixa Econômica Exemplo"}))
        assert confirmado["confirmado"]["credor"] == "Caixa Econômica Exemplo"
        dados = client.get(f"/api/imoveis/{CODIGO}/dados").json()
        assert dados["onus_credor"] == "Caixa Econômica Exemplo"

    def test_without_onus_acts_there_is_no_suggestion(self, client, scoped):
        seed(scoped, registry=[registry_row()])
        data = _data(client.get(f"/api/matriculas/imoveis/{CODIGO}/onus-credor"))
        assert (data["sugestao"], data["motivo_sem_sugestao"]) == (None, "sem_onus_confirmado")


# ─── previous owners ──────────────────────────────────────────────────────


class TestAntigosProprietarios:
    def _url(self):
        return f"/api/matriculas/imoveis/{CODIGO}/antigos-proprietarios"

    def test_a_recent_sale_requires_the_sellers_certidoes(self, client, scoped):
        venda = date.today() - timedelta(days=2 * 365)
        ext = extracao_row(texto=texto_com_venda(venda))
        seed(scoped, registry=[registry_row()], extracoes=[ext])

        data = _data(client.get(self._url()))

        assert data["ultima_transferencia"] == {
            "ato_id": data["ultima_transferencia"]["ato_id"],
            "ato_ref": "R-2",
            "natureza": "compra_e_venda",
            "data_registro": venda.isoformat(),
            "detalhes_origem": "sugestao",
        }
        assert data["transmitentes"] == [
            {"nome": "SEGUNDO DONO FICTICIO", "cpf_cnpj": "135.792.468-28"}
        ]
        assert data["exige_certidoes"] is True
        assert data["data_desconhecida"] is False
        log = _logs(scoped, "detalhes_view")
        assert len(log) == 1 and log[0]["extracao_id"] == ext["id"]

    def test_an_old_sale_does_not(self, client, scoped):
        ext = extracao_row(texto=texto_com_venda(date.today() - timedelta(days=10 * 365)))
        seed(scoped, registry=[registry_row()], extracoes=[ext])

        data = _data(client.get(self._url()))

        assert data["exige_certidoes"] is False

    def test_no_transcription_means_no_transfer(self, client, scoped):
        seed(scoped, registry=[registry_row()])

        data = _data(client.get(self._url()))

        assert data["ultima_transferencia"] is None
        assert data["transmitentes"] == [] and data["exige_certidoes"] is False
        assert _logs(scoped, "detalhes_view") == []

    def test_the_five_year_boundary_and_an_unknown_date(self, client, scoped):
        hoje = date(2026, 9, 15)
        ext = extracao_row(texto=texto_com_venda(date(2021, 9, 15)))
        seed(scoped, registry=[registry_row()], extracoes=[ext])

        exatos = titulo_service.antigos_proprietarios(scoped, ORG, CODIGO, hoje=hoje)
        um_dia_antes = titulo_service.antigos_proprietarios(
            scoped, ORG, CODIGO, hoje=hoje - timedelta(days=1)
        )
        assert exatos["exige_certidoes"] is False  # exactly 5 years is not "< 5"
        assert um_dia_antes["exige_certidoes"] is True

        ato_id = exatos["ultima_transferencia"]["ato_id"]
        client.put(f"/api/matriculas/atos/{ato_id}/detalhes", json={"data_registro": None})
        desconhecida = titulo_service.antigos_proprietarios(scoped, ORG, CODIGO, hoje=hoje)
        assert desconhecida["data_desconhecida"] is True
        assert desconhecida["exige_certidoes"] is True, "an unreadable date never waives them"

    def test_the_confirmed_nature_decides_what_a_sale_is(self, client, scoped):
        ext = extracao_row(texto=texto_com_venda(date.today() - timedelta(days=365)))
        seed(scoped, registry=[registry_row()], extracoes=[ext])
        atos = _por_chave(_atos(client, ext["id"]))
        client.put(f"/api/matriculas/atos/{atos[('R', 2)]['id']}/detalhes", json={"natureza": "doacao"})

        data = _data(client.get(self._url()))

        assert data["ultima_transferencia"]["ato_ref"] == "R-1"
        assert data["exige_certidoes"] is False

    def test_a_confirmed_titulo_act_that_is_a_permuta_derives_it(self, client, scoped):
        """The live dead end: R-4 confirmed as título aquisitivo, natureza
        `permuta` — invisible to the old compra-e-venda-only search."""
        recente = date.today() - timedelta(days=365)
        ext = extracao_row(texto=texto_com_venda(recente))
        seed(scoped, registry=[registry_row()], extracoes=[ext])
        atos = _por_chave(_atos(client, ext["id"]))
        r2 = atos[("R", 2)]["id"]
        client.put(f"/api/matriculas/atos/{r2}/detalhes", json={"natureza": "permuta"})
        client.put(
            f"/api/matriculas/extracoes/{ext['id']}/fontes",
            json={"titulo_aquisitivo_ato_id": r2},
        )

        data = _data(client.get(self._url()))

        assert data["origem"] == "titulo_confirmado"
        assert data["ultima_transferencia"]["ato_ref"] == "R-2"
        assert data["ultima_transferencia"]["natureza"] == "permuta"
        assert data["ultima_transferencia"]["data_registro"] == recente.isoformat()
        assert data["exige_certidoes"] is True

    def test_manual_override_answers_it_when_no_extraction_transfer_exists(self, client, scoped):
        seed(scoped, registry=[registry_row()])
        recente = (date.today() - timedelta(days=365)).isoformat()

        put = _data(
            client.put(
                f"/api/matriculas/imoveis/{CODIGO}/ultima-transferencia",
                json={"data": recente, "natureza": "permuta", "sem_registro": False},
            )
        )
        assert put["origem"] == "manual"
        assert put["ultima_transferencia"] == {
            "ato_id": None,
            "ato_ref": None,
            "natureza": "permuta",
            "data_registro": recente,
            "detalhes_origem": "manual",
        }
        assert put["exige_certidoes"] is True
        assert put["manual"]["data_registro"] == recente
        assert put["manual"]["confirmado_por"] is not None

        # A found act in the extraction always wins over the manual override.
        # `seed()` resets EVERY table it's given, `imovel_dados` included —
        # carry the override just written forward explicitly, or this
        # `seed()` call would silently wipe it before the assertion below.
        dados_atual = scoped.table("imovel_dados").select("*").execute().data
        antigo = (date.today() - timedelta(days=10 * 365)).isoformat()
        ext = extracao_row(texto=texto_com_venda(date.today() - timedelta(days=10 * 365)))
        seed(scoped, registry=[registry_row()], extracoes=[ext], dados=dados_atual)
        derivado = _data(client.get(self._url()))
        assert derivado["origem"] == "extracao"
        assert derivado["ultima_transferencia"]["data_registro"] == antigo
        # The raw override state is still reported for the FE form.
        assert derivado["manual"]["data_registro"] == recente

        limpo = _data(
            client.put(
                f"/api/matriculas/imoveis/{CODIGO}/ultima-transferencia",
                json={"data": None, "natureza": None, "sem_registro": False},
            )
        )
        assert limpo["manual"] is None

    def test_sem_registro_is_recorded_as_an_answer_not_a_fallback(self, client, scoped):
        seed(scoped, registry=[registry_row()])

        put = _data(
            client.put(
                f"/api/matriculas/imoveis/{CODIGO}/ultima-transferencia",
                json={"data": None, "sem_registro": True},
            )
        )
        assert put["ultima_transferencia"] is None
        assert put["sem_registro"] is True
        assert put["origem"] == "manual"
        assert put["manual"]["sem_registro"] is True
        assert put["exige_certidoes"] is False

    def test_a_date_and_sem_registro_together_is_refused(self, client, scoped):
        seed(scoped, registry=[registry_row()])
        resp = client.put(
            f"/api/matriculas/imoveis/{CODIGO}/ultima-transferencia",
            json={"data": "2023-01-01", "sem_registro": True},
        )
        assert resp.status_code == 400

    def test_a_nature_without_a_date_is_refused(self, client, scoped):
        seed(scoped, registry=[registry_row()])
        resp = client.put(
            f"/api/matriculas/imoveis/{CODIGO}/ultima-transferencia",
            json={"data": None, "natureza": "permuta", "sem_registro": False},
        )
        assert resp.status_code == 400

    def test_the_write_always_stamps_the_authenticated_org(self, client, scoped):
        """org scoping: `imovel_dados` rows carry the CALLER's org_id, never
        one taken from the request body — there is none to take it from."""
        seed(scoped, registry=[registry_row()])
        _data(
            client.put(
                f"/api/matriculas/imoveis/{CODIGO}/ultima-transferencia",
                json={"data": "2023-07-11", "natureza": "permuta", "sem_registro": False},
            )
        )
        rows = scoped.table("imovel_dados").select("*").execute().data
        assert rows and all(r["org_id"] == ORG_ID for r in rows)


# ─── permuta quotes ───────────────────────────────────────────────────────


class TestPermutaQuote:
    def _preparar(self, client, scoped, *, codigo_ativo="PM0001"):
        ext = extracao_row()
        ext_permuta = extracao_row(codigo="PM0001")
        contrato = contrato_row()
        ativo = {"id": str(uuid4()), "org_id": ORG_ID, "imovel_codigo": codigo_ativo}
        seed(
            scoped,
            extracoes=[ext, ext_permuta],
            contratos=[contrato],
            permutas=[ativo],
        )
        atos = _atos(client, ext["id"])
        atos_permuta = _atos(client, ext_permuta["id"])
        return ext, ext_permuta, contrato, ativo, atos, atos_permuta

    def test_the_object_and_the_permuta_are_quoted_separately(self, client, scoped):
        ext, ext_p, contrato, ativo, atos, atos_p = self._preparar(client, scoped)
        url = f"/api/matriculas/contratos/{contrato['id']}/atos"

        _data(
            client.put(
                url,
                json={
                    "extracao_id": ext["id"],
                    "ato_ids": [atos[1]["id"]],
                    "permutas": [
                        {
                            "permuta_ativo_id": ativo["id"],
                            "extracao_id": ext_p["id"],
                            "ato_ids": [atos_p[4]["id"], atos_p[0]["id"]],
                        }
                    ],
                },
            )
        )
        data = _data(client.get(url))

        assert data["texto"] == atos[1]["texto"]
        assert len(data["permutas"]) == 1
        permuta = data["permutas"][0]
        assert permuta["permuta_ativo_id"] == ativo["id"]
        assert permuta["codigo"] == "PM0001"
        assert permuta["texto"] == atos_p[4]["texto"] + atos_p[0]["texto"]
        linhas = scoped.table("atendimento_contrato_matricula_atos").inserted_payloads
        assert {(r["papel"], r["ordem"]) for r in linhas} == {
            ("objeto", 1), ("permuta", 1), ("permuta", 2)
        }

    def test_a_permuta_matricula_of_another_property_is_a_400(self, client, scoped):
        _ext, ext_p, contrato, ativo, _atos_o, atos_p = self._preparar(
            client, scoped, codigo_ativo="OUTRO9"
        )
        resp = client.put(
            f"/api/matriculas/contratos/{contrato['id']}/atos",
            json={
                "permutas": [
                    {"permuta_ativo_id": ativo["id"], "extracao_id": ext_p["id"], "ato_ids": [atos_p[1]["id"]]}
                ]
            },
        )
        assert resp.status_code == 400
        assert "ativo de permuta" in resp.json()["error"]["message"]

    def test_an_unknown_permuta_ativo_is_a_404(self, client, scoped):
        _ext, ext_p, contrato, _ativo, _atos_o, atos_p = self._preparar(client, scoped)
        resp = client.put(
            f"/api/matriculas/contratos/{contrato['id']}/atos",
            json={
                "permutas": [
                    {"permuta_ativo_id": str(uuid4()), "extracao_id": ext_p["id"], "ato_ids": [atos_p[1]["id"]]}
                ]
            },
        )
        assert resp.status_code == 404

    def test_the_same_act_twice_across_groups_is_a_400(self, client, scoped):
        ext, _ext_p, contrato, ativo, atos, _atos_p = self._preparar(client, scoped)
        resp = client.put(
            f"/api/matriculas/contratos/{contrato['id']}/atos",
            json={
                "extracao_id": ext["id"],
                "ato_ids": [atos[1]["id"]],
                "permutas": [
                    {"permuta_ativo_id": ativo["id"], "extracao_id": ext["id"], "ato_ids": [atos[1]["id"]]}
                ],
            },
        )
        assert resp.status_code == 400


# ─── retention ────────────────────────────────────────────────────────────


def test_purging_the_text_purges_the_details_read_from_it(client, scoped):
    ext = {**extracao_row(), "retencao_ate": "2000-01-01"}
    seed(scoped, extracoes=[ext])
    svc.listar_atos(scoped, ORG, UUID(ext["id"]))
    assert scoped.table("matricula_ato_detalhes").select("*").execute().data

    assert svc.purgar_texto_expirado(scoped, ORG) == 1

    assert scoped.table("matricula_ato_detalhes").select("*").execute().data == []
