"""`estrutura_service` — acts as offsets, literal quotes, suggestions that
never write, and pointers that never touch the manual ônus reading.

Uses the `client` fixture for its DB patches (actor resolution reads the
core client) and seeds through `scoped`. Every text is synthetic — see
`conftest.py`.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from noctusai_lib.integrations.documents import segment_matricula_atos
from noctusai_lib.primitives.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError_,
)

from app.modules.imovel_hub import dados_service
from app.modules.matriculas import estrutura_service as svc
from tests.modules.matriculas.conftest import (
    CODIGO,
    ESPERADOS,
    ORG_ID,
    TEXTO,
    contrato_row,
    extracao_row,
    negociacao_row,
    registry_row,
    seed,
)

ORG = UUID(ORG_ID)


def _atos(scoped, extracao_id: str) -> list[dict]:
    return svc.listar_atos(scoped, ORG, UUID(extracao_id))["atos"]


def _por_chave(atos: list[dict]) -> dict:
    return {(a["kind"], a["numero"]): a for a in atos}


# ─── offsets ──────────────────────────────────────────────────────────────


class TestTheActsAreLiteralOffsets:
    def test_every_act_is_a_slice_and_the_slices_rebuild_the_text(self, scoped):
        ext = extracao_row()
        seed(scoped, extracoes=[ext])

        atos = _atos(scoped, ext["id"])

        assert [(a["kind"], a["numero"]) for a in atos] == ESPERADOS
        for ato in atos:
            assert ato["texto"] == TEXTO[ato["char_inicio"] : ato["char_fim"]]
        assert "".join(a["texto"] for a in atos) == TEXTO

    def test_typos_and_double_spaces_are_quoted_untouched(self, scoped):
        ext = extracao_row()
        seed(scoped, extracoes=[ext])

        abertura = _atos(scoped, ext["id"])[0]["texto"]

        assert "Edificio Jacarandá Ficticio" in abertura
        assert "confrontando com  o apto 11." in abertura

    def test_no_copy_of_the_text_is_persisted(self, scoped):
        ext = extracao_row()
        seed(scoped, extracoes=[ext])
        _atos(scoped, ext["id"])

        linhas = scoped.table("matricula_atos").inserted_payloads
        assert len(linhas) == len(ESPERADOS)
        for linha in linhas:
            assert "texto" not in linha
            assert set(linha) >= {"char_inicio", "char_fim", "ordem", "kind"}

    def test_the_rotulo_is_the_acts_first_line(self, scoped):
        ext = extracao_row()
        seed(scoped, extracoes=[ext])

        r4 = _por_chave(_atos(scoped, ext["id"]))[("R", 4)]

        assert r4["rotulo"].startswith("R-4/45.678 - Em 1 de junho de 2015.")
        assert "\n" not in r4["rotulo"]
        assert r4["header_inicio"] == r4["char_inicio"]

    def test_acts_are_never_resegmented(self, scoped):
        """Re-segmenting would mint new ids and orphan every contract quote."""
        ext = extracao_row()
        seed(scoped, extracoes=[ext])
        primeiros = [a["id"] for a in _atos(scoped, ext["id"])]

        assert svc.persistir_atos(scoped, ext["id"], ORG_ID, TEXTO) == 0
        assert [a["id"] for a in _atos(scoped, ext["id"])] == primeiros

    def test_an_unfinished_extraction_has_no_acts(self, scoped):
        ext = extracao_row(status="processando")
        seed(scoped, extracoes=[ext])

        out = svc.listar_atos(scoped, ORG, UUID(ext["id"]))

        assert out["total"] == 0
        assert scoped.table("matricula_atos").inserted_payloads == []

    def test_offsets_outside_the_text_are_refused_not_clamped(self, scoped):
        """Python would silently return a SHORTER quote. For a legal quote
        that is the worst failure there is."""
        ext = extracao_row()
        corrompido = {
            "id": str(uuid4()),
            "org_id": ORG_ID,
            "extracao_id": ext["id"],
            "ordem": 0,
            "kind": "abertura",
            "numero": None,
            "char_inicio": 0,
            "char_fim": len(TEXTO) + 10,
            "header_inicio": None,
            "header_fim": None,
        }
        seed(scoped, extracoes=[ext], atos=[corrompido])

        with pytest.raises(ValueError, match="divergiram"):
            svc.listar_atos(scoped, ORG, UUID(ext["id"]))

    def test_a_service_role_write_without_an_org_is_refused(self):
        with pytest.raises(ValueError, match="org_id"):
            svc.persistir_atos(object(), "x", None, TEXTO)

    def test_an_extraction_of_another_org_is_a_404(self, scoped):
        ext = extracao_row()
        ext["org_id"] = str(uuid4())
        seed(scoped, extracoes=[ext])

        with pytest.raises(NotFoundError):
            svc.listar_atos(scoped, ORG, UUID(ext["id"]))


# ─── suggester ────────────────────────────────────────────────────────────


def _linhas(texto: str) -> list[dict]:
    return svc.linhas_de_atos("ext", ORG_ID, segment_matricula_atos(texto))


class TestTheSuggester:
    def test_the_latest_transfer_is_the_titulo_aquisitivo(self):
        titulo = svc.sugerir(TEXTO, _linhas(TEXTO))["titulo_aquisitivo"]

        assert (titulo["kind"], titulo["numero"]) == ("R", 4)
        assert titulo["termo"] == "compra e venda"

    def test_a_cancelled_hipoteca_is_shown_but_not_suggested(self):
        linhas = _linhas(TEXTO)
        av3 = next(l for l in linhas if (l["kind"], l["numero"]) == ("AV", 3))

        onus = svc.sugerir(TEXTO, linhas)["onus"]
        hipoteca = next(o for o in onus if o["tipo"] == "hipoteca")

        assert hipoteca["numero"] == 2
        assert hipoteca["sugerido"] is False
        assert hipoteca["cancelamento_citado_por"] == [av3["id"]]

    def test_live_encumbrances_are_suggested(self):
        onus = svc.sugerir(TEXTO, _linhas(TEXTO))["onus"]

        assert {(o["tipo"], o["numero"]) for o in onus if o["sugerido"]} == {
            ("alienacao_fiduciaria", 5),
            ("indisponibilidade", 6),
        }

    def test_the_cancellation_act_itself_is_not_an_onus(self):
        onus = svc.sugerir(TEXTO, _linhas(TEXTO))["onus"]
        assert all(o["numero"] != 3 for o in onus)

    def test_no_transfer_act_means_no_suggestion(self):
        texto = (
            "MATRÍCULA 1.111\nTerreno ficticio.\n"
            "R-1/1.111 - PENHORA em favor de Credor Inventado.\n"
        )
        assert svc.sugerir(texto, _linhas(texto))["titulo_aquisitivo"] is None

    def test_citing_R_12_does_not_cancel_R_1(self):
        texto = (
            "MATRÍCULA 2.222\nLote ficticio.\n"
            "R-1/2.222 - PENHORA em favor de Credor Inventado.\n"
            "AV-2/2.222 - CANCELAMENTO da penhora do R-12 de outra matricula.\n"
        )
        penhora = svc.sugerir(texto, _linhas(texto))["onus"][0]

        assert penhora["numero"] == 1
        assert penhora["sugerido"] is True


# ─── título / ônus pointers ───────────────────────────────────────────────


class TestTheFontes:
    def _seed(self, scoped, *, dados=None, **extra):
        ext = extracao_row(**extra)
        seed(scoped, registry=[registry_row()], extracoes=[ext], dados=dados)
        return ext, _por_chave(_atos(scoped, ext["id"]))

    def _definir(self, scoped, ext, **valores):
        return svc.definir_fontes(
            scoped, ORG, UUID(ext["id"]), valores=valores, usuario_id=None
        )

    def test_confirming_the_suggested_titulo_is_origem_sugerido(self, scoped):
        ext, atos = self._seed(scoped)

        titulo = self._definir(
            scoped, ext, titulo_aquisitivo_ato_id=atos[("R", 4)]["id"]
        )["titulo_aquisitivo"]

        assert titulo["origem"] == "sugerido"
        assert titulo["texto"] == atos[("R", 4)]["texto"]
        assert titulo["confirmado_em"]

    def test_choosing_another_act_is_origem_manual(self, scoped):
        ext, atos = self._seed(scoped)

        titulo = self._definir(
            scoped, ext, titulo_aquisitivo_ato_id=atos[("R", 1)]["id"]
        )["titulo_aquisitivo"]

        assert titulo["origem"] == "manual"
        assert (titulo["char_inicio"], titulo["char_fim"]) == (
            atos[("R", 1)]["char_inicio"],
            atos[("R", 1)]["char_fim"],
        )

    def test_the_suggested_onus_set_is_sugerido_and_keeps_operator_order(self, scoped):
        ext, atos = self._seed(scoped)
        escolha = [atos[("AV", 6)]["id"], atos[("R", 5)]["id"]]

        onus = self._definir(scoped, ext, onus_ato_ids=escolha)["onus"]

        assert onus["origem"] == "sugerido"
        assert [a["ato_id"] for a in onus["atos"]] == escolha
        assert onus["atos"][0]["texto"] == atos[("AV", 6)]["texto"]

    def test_a_different_onus_set_is_manual(self, scoped):
        ext, atos = self._seed(scoped)

        onus = self._definir(scoped, ext, onus_ato_ids=[atos[("R", 2)]["id"]])["onus"]

        assert onus["origem"] == "manual"

    def test_null_clears_a_pointer(self, scoped):
        ext, atos = self._seed(scoped)
        self._definir(scoped, ext, onus_ato_ids=[atos[("R", 5)]["id"]])

        assert self._definir(scoped, ext, onus_ato_ids=None)["onus"] is None

    def test_the_manual_situacao_onus_is_never_touched(self, scoped):
        ext, atos = self._seed(
            scoped,
            dados=[{"org_id": ORG_ID, "codigo": CODIGO, "situacao_onus": "livre"}],
        )

        self._definir(
            scoped, ext, onus_ato_ids=[atos[("R", 5)]["id"], atos[("AV", 6)]["id"]]
        )

        dados = dados_service.obter(scoped, ORG, CODIGO)
        assert dados["situacao_onus"] == "livre"
        assert dados["onus_fonte"]["origem"] == "sugerido"

    def test_suggestions_are_never_written(self, scoped):
        ext, _atos_ = self._seed(scoped)

        fontes = svc.obter_fontes(scoped, ORG, UUID(ext["id"]))

        assert fontes["sugestoes"]["titulo_aquisitivo"]["numero"] == 4
        assert fontes["titulo_aquisitivo"] is None
        assert dados_service.linha(scoped, ORG, CODIGO) is None

    def test_an_act_of_another_matricula_is_refused(self, scoped):
        ext, _atos_ = self._seed(scoped)
        with pytest.raises(ValidationError_):
            self._definir(scoped, ext, titulo_aquisitivo_ato_id=str(uuid4()))

    def test_repeated_onus_acts_are_refused(self, scoped):
        ext, atos = self._seed(scoped)
        rid = atos[("R", 5)]["id"]
        with pytest.raises(ValidationError_):
            self._definir(scoped, ext, onus_ato_ids=[rid, rid])

    def test_an_unlinked_extraction_cannot_source_an_imovel(self, scoped):
        ext, atos = self._seed(scoped, codigo=None)
        with pytest.raises(ValidationError_, match="imóvel"):
            self._definir(scoped, ext, titulo_aquisitivo_ato_id=atos[("R", 4)]["id"])

    def test_the_gravar_seam_refuses_authored_columns(self, scoped):
        seed(scoped, registry=[registry_row()])
        with pytest.raises(ValueError, match="situacao_onus"):
            dados_service.gravar_fontes_matricula(
                scoped, ORG, CODIGO, {"situacao_onus": "hipoteca"}
            )


# ─── contract selection ───────────────────────────────────────────────────


class TestTheContractSelection:
    def _seed(self, scoped, **contrato_extra):
        ext = extracao_row()
        contrato = contrato_row(**contrato_extra)
        seed(scoped, extracoes=[ext], contratos=[contrato])
        return ext, contrato, _atos(scoped, ext["id"])

    def _definir(self, scoped, contrato, ext, ids, **kw):
        return svc.definir_selecao(
            scoped,
            ORG,
            UUID(contrato["id"]),
            extracao_id=UUID(ext["id"]) if ext else None,
            ato_ids=[UUID(i) for i in ids],
            usuario_id=kw.get("usuario_id"),
        )

    def test_selecting_every_act_in_order_is_byte_identical(self, scoped):
        ext, contrato, atos = self._seed(scoped)

        out = self._definir(scoped, contrato, ext, [a["id"] for a in atos])

        assert out["texto"].encode("utf-8") == TEXTO.encode("utf-8")
        assert [a["ordem"] for a in out["atos"]] == list(range(1, len(atos) + 1))

    def test_the_operator_order_is_the_contract_order(self, scoped):
        ext, contrato, atos = self._seed(scoped)
        por = _por_chave(atos)

        out = self._definir(
            scoped, contrato, ext, [por[("R", 4)]["id"], por[("abertura", None)]["id"]]
        )

        assert out["texto"] == por[("R", 4)]["texto"] + por[("abertura", None)]["texto"]

    def test_a_new_selection_replaces_the_old(self, scoped):
        ext, contrato, atos = self._seed(scoped)
        self._definir(scoped, contrato, ext, [a["id"] for a in atos])

        out = self._definir(scoped, contrato, ext, [atos[1]["id"]])

        assert [a["ato_id"] for a in out["atos"]] == [atos[1]["id"]]

    def test_an_empty_selection_clears(self, scoped):
        ext, contrato, atos = self._seed(scoped)
        self._definir(scoped, contrato, ext, [atos[0]["id"]])

        out = self._definir(scoped, contrato, None, [])

        assert out["atos"] == [] and out["texto"] == "" and out["extracao_id"] is None

    def test_repeated_acts_are_refused(self, scoped):
        ext, contrato, atos = self._seed(scoped)
        with pytest.raises(ValidationError_):
            self._definir(scoped, contrato, ext, [atos[0]["id"], atos[0]["id"]])

    def test_an_act_of_another_matricula_is_refused(self, scoped):
        ext, contrato, _atos_ = self._seed(scoped)
        with pytest.raises(ValidationError_):
            self._definir(scoped, contrato, ext, [str(uuid4())])

    def test_acts_without_an_extraction_are_refused(self, scoped):
        _ext, contrato, atos = self._seed(scoped)
        with pytest.raises(ValidationError_, match="extracao_id"):
            self._definir(scoped, contrato, None, [atos[0]["id"]])

    def test_a_deleted_contract_is_a_404(self, scoped):
        ext, contrato, atos = self._seed(scoped, deleted_at="2026-04-01T00:00:00+00:00")
        with pytest.raises(NotFoundError):
            self._definir(scoped, contrato, ext, [atos[0]["id"]])

    def test_an_unlinked_extraction_cannot_be_selected(self, scoped):
        """`codigo=None` is the 092 unlinked-upload shape — it was never
        vinculated to ANY imóvel, so it cannot be trusted to be THIS deal's
        either (migration 111)."""
        ext = extracao_row(codigo=None)
        contrato = contrato_row()
        seed(scoped, extracoes=[ext], contratos=[contrato])
        atos = _atos(scoped, ext["id"])

        with pytest.raises(ValidationError_, match="não está vinculada"):
            self._definir(scoped, contrato, ext, [atos[0]["id"]])

    def test_a_matricula_of_a_different_imovel_cannot_be_selected(self, scoped):
        """The deal negotiates `imovel_codigo="AP1234"`; the extração belongs
        to a different property. Without this check F5's contract generation
        would read the wrong imóvel's matrícula as this deal's title source."""
        ext = extracao_row(codigo="OUTRO99")
        contrato = contrato_row()
        seed(
            scoped,
            extracoes=[ext],
            contratos=[contrato],
            negociacoes=[negociacao_row(contrato["atendimento_id"], imovel_codigo=CODIGO)],
        )
        atos = _atos(scoped, ext["id"])

        with pytest.raises(ValidationError_, match="imóvel diferente"):
            self._definir(scoped, contrato, ext, [atos[0]["id"]])

    def test_no_negociacao_row_at_all_is_also_refused(self, scoped):
        """No `atendimento_negociacao` row means no imóvel was ever
        negotiated for this deal — a NULL default must not read as a match."""
        ext, contrato, atos = self._seed(scoped)
        scoped.set_table_data("atendimento_negociacao", [])

        with pytest.raises(ValidationError_, match="imóvel diferente"):
            self._definir(scoped, contrato, ext, [atos[0]["id"]])


# ─── delete guard ─────────────────────────────────────────────────────────


class TestTheDeleteGuard:
    def test_a_quoted_extraction_cannot_be_removed(self, scoped):
        ext = extracao_row()
        contrato = contrato_row()
        seed(scoped, extracoes=[ext], contratos=[contrato])
        atos = _atos(scoped, ext["id"])
        svc.definir_selecao(
            scoped, ORG, UUID(contrato["id"]),
            extracao_id=UUID(ext["id"]), ato_ids=[UUID(atos[0]["id"])], usuario_id=None,
        )

        with pytest.raises(ConflictError, match="contrato"):
            svc.garantir_removivel(scoped, ORG, ext["id"])

    def test_an_imovel_pointer_blocks_removal(self, scoped):
        ext = extracao_row()
        seed(scoped, registry=[registry_row()], extracoes=[ext])
        atos = _por_chave(_atos(scoped, ext["id"]))
        svc.definir_fontes(
            scoped, ORG, UUID(ext["id"]),
            valores={"titulo_aquisitivo_ato_id": atos[("R", 4)]["id"]}, usuario_id=None,
        )

        with pytest.raises(ConflictError, match="título"):
            svc.garantir_removivel(scoped, ORG, ext["id"])

    def test_an_unquoted_extraction_can_be_removed(self, scoped):
        ext = extracao_row()
        seed(scoped, extracoes=[ext])
        svc.garantir_removivel(scoped, ORG, ext["id"])
