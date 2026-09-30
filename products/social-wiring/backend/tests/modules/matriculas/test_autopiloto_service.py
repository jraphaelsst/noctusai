"""The matrícula autopilot (owner directive 2026-09-30) — confirms a
contract-feeding field WITHOUT a human click exactly when the derivation is
unambiguous, and never touches anything a human already decided.

🔴 EVERY NAME, NUMBER AND BANK BELOW IS INVENTED (same convention as
`conftest.py`).
"""
from __future__ import annotations

from uuid import UUID, uuid4

from app.modules.imovel_hub import dados_service
from app.modules.matriculas import autopiloto_service as autopiloto
from app.modules.matriculas import estrutura_service as estrutura_svc
from app.modules.matriculas import preenchimento_service as preench
from tests.modules.matriculas.conftest import (
    CODIGO,
    ORG_ID,
    contrato_row,
    extracao_row,
    negociacao_row,
    registry_row,
    seed,
)

ORG = UUID(ORG_ID)

CABECALHO = (
    "1º OFICIAL DE REGISTRO DE IMÓVEIS DE COTIA - SP\n"
    "MATRÍCULA Nº 45.678 — FICHA 01\n"
    "IMÓVEL: Apartamento nº 12 do Edifício Exemplar, situado à Rua das "
    "Amostras, 99.\n"
    "PROPRIETÁRIA: Fulana de Teste Exemplar, brasileira, CPF 000.000.000-00.\n"
    "\n"
)

#: A título act WITH a full instrumento — `frase_titulo_aquisitivo` resolves.
ATO_R1_COM_INSTRUMENTO = (
    "R-1/45.678 - Em 10 de março de 2001. COMPRA E VENDA por Escritura "
    "Pública lavrada em 05 de março de 2001 no 2º Tabelionato de Notas de "
    "Cotia, Livro 100, fls. 20. Transmitente: Fulana de Teste Exemplar; "
    "adquirente: Beltrano Modelo. Valor R$ 100.000,00.\n"
)

#: The same act, WITHOUT an instrument — `frase_titulo_aquisitivo` returns
#: `None` (no `tipo` to name), the [MOTIVO_SEM_INSTRUMENTO] ambiguous case.
ATO_R1_SEM_INSTRUMENTO = (
    "R-1/45.678 - Em 10 de março de 2001. COMPRA E VENDA. Transmitente: "
    "Fulana de Teste Exemplar; adquirente: Beltrano Modelo. Valor R$ "
    "100.000,00.\n"
)

ATO_R2_ALIENACAO = (
    "R-2/45.678 - Em 11 de março de 2001. ALIENAÇÃO FIDUCIÁRIA em garantia "
    "ao Banco Ficticio.\n"
)

ATO_AV3_CANCELAMENTO = (
    "AV-3/45.678 - Em 5 de maio de 2010. CANCELAMENTO da alienação "
    "fiduciária objeto do R-2, por quitação.\n"
)

#: Neither the `natureza` regex NOR the text heuristic recognises this act —
#: `derivar_situacao_onus`'s own "blind spot" guard refuses to answer.
ATO_R6_INDETERMINADO = (
    "R-6/45.678 - Em 1 de julho de 2020. Registra-se ato conforme "
    "requerimento protocolado sob o número 999.\n"
)


def _texto(*atos: str) -> str:
    return CABECALHO + "".join(atos)


def _dados(scoped) -> dict:
    return dados_service.linha(scoped, ORG, CODIGO) or {}


def _atos_por_chave(scoped, extracao_id: str) -> dict:
    atos = estrutura_svc.listar_atos(scoped, ORG, UUID(extracao_id))["atos"]
    return {(a["kind"], a["numero"]): a for a in atos}


def _rodar(scoped, texto: str, *, contratos=None, negociacoes=None) -> tuple[str, dict]:
    """Seed a concluded, linked extraction, run the D1 fill + the autopilot,
    and return `(extracao_id, resultado)`."""
    eid = str(uuid4())
    seed(
        scoped,
        registry=[registry_row()],
        extracoes=[extracao_row(eid, texto=texto)],
        contratos=contratos,
        negociacoes=negociacoes,
    )
    resumo, _conflitos = preench.preencher_sincrono(scoped, ORG, eid)
    assert resumo["status"] == "ok"
    resultado = autopiloto.aplicar_autopiloto(scoped, ORG, eid)
    return eid, resultado


class TestUnambiguousMatriculaConfirmsEveryField:
    def test_an_active_encumbrance_autoconfirms_cartorio_titulo_and_onus(self, scoped):
        eid, resultado = _rodar(scoped, _texto(ATO_R1_COM_INSTRUMENTO, ATO_R2_ALIENACAO))

        assert resultado["status"] == "ok"
        campos = resultado["campos"]
        assert campos == {
            "numero_registro_imoveis": autopiloto.CONFIRMADO_AUTOMATICO,
            "titulo_aquisitivo": autopiloto.CONFIRMADO_AUTOMATICO,
            "titulo_aquisitivo_texto": autopiloto.CONFIRMADO_AUTOMATICO,
            "onus_fonte": autopiloto.CONFIRMADO_AUTOMATICO,
            "situacao_onus": autopiloto.CONFIRMADO_AUTOMATICO,
            "onus_credor": autopiloto.CONFIRMADO_AUTOMATICO,
        }

        row = _dados(scoped)
        # Cartório — header matched, "ia" provenance, nobody clicked.
        assert row["numero_registro_imoveis"] == (
            "1º OFICIAL DE REGISTRO DE IMÓVEIS DE COTIA - SP"
        )
        assert row["numero_registro_imoveis_origem"] == "ia"
        assert row["numero_registro_imoveis_confirmado_por"] is None
        assert row["numero_registro_imoveis_confirmado_em"]

        # Título aquisitivo — the pointer group stays `sugerido` (109's CHECK
        # forbids "ia" there) but IS confirmed, with no human behind it.
        assert row["titulo_aquisitivo_origem"] == "sugerido"
        assert row["titulo_aquisitivo_confirmado_por"] is None
        assert row["titulo_aquisitivo_confirmado_em"]
        assert row["titulo_aquisitivo_texto"].startswith("por Escritura Pública")
        assert "R-1" in row["titulo_aquisitivo_texto"]
        assert row["titulo_aquisitivo_texto_origem"] == "ia"
        assert row["titulo_aquisitivo_texto_confirmado_por"] is None
        assert row["titulo_aquisitivo_texto_confirmado_em"]

        # Ônus — unreleased alienação fiduciária.
        assert row["onus_fonte_origem"] == "sugerido"
        assert row["onus_fonte_confirmado_em"]
        assert row["situacao_onus"] == "alienacao_fiduciaria"
        assert row["situacao_onus_origem"] == "ia"
        assert row["situacao_onus_confirmado_em"]
        assert row["onus_credor"] == "Banco Ficticio"
        assert row["onus_credor_origem"] == "ia"
        assert row["onus_credor_confirmado_em"]

    def test_a_cancelled_encumbrance_autoconfirms_livre(self, scoped):
        _eid, resultado = _rodar(
            scoped,
            _texto(ATO_R1_COM_INSTRUMENTO, ATO_R2_ALIENACAO, ATO_AV3_CANCELAMENTO),
        )

        row = _dados(scoped)
        assert row["situacao_onus"] == "livre"
        assert row["situacao_onus_origem"] == "ia"
        assert row["situacao_onus_confirmado_em"]
        assert resultado["campos"]["situacao_onus"] == autopiloto.CONFIRMADO_AUTOMATICO
        # The alienação is released — no ônus source acts to point at, and
        # no creditor to confirm.
        assert row.get("onus_fonte_atos") in (None, [])
        assert resultado["campos"]["onus_fonte"] == autopiloto.SEM_VALOR
        assert resultado["campos"]["onus_credor"] == autopiloto.SEM_VALOR

    def test_a_second_run_is_idempotent(self, scoped):
        eid, primeiro = _rodar(scoped, _texto(ATO_R1_COM_INSTRUMENTO, ATO_R2_ALIENACAO))
        antes = dict(_dados(scoped))

        segundo = autopiloto.aplicar_autopiloto(scoped, ORG, eid)

        assert set(segundo["campos"].values()) == {autopiloto.JA_CONFIRMADO_HUMANO}
        assert _dados(scoped) == antes


class TestAmbiguousDerivationsStaySuggestions:
    def test_a_titulo_act_with_no_instrumento_is_never_autoconfirmed(self, scoped):
        eid, resultado = _rodar(scoped, _texto(ATO_R1_SEM_INSTRUMENTO, ATO_R2_ALIENACAO))

        campos = resultado["campos"]
        assert campos["titulo_aquisitivo"] == autopiloto.SUGESTAO_PENDENTE
        assert campos["titulo_aquisitivo_texto"] == autopiloto.SEM_VALOR
        # Independent fields still resolve — ambiguity on one field never
        # blocks another.
        assert campos["numero_registro_imoveis"] == autopiloto.CONFIRMADO_AUTOMATICO
        assert campos["situacao_onus"] == autopiloto.CONFIRMADO_AUTOMATICO

        row = _dados(scoped)
        assert row["titulo_aquisitivo_ato_id"]  # the heuristic's own pointer landed
        assert row["titulo_aquisitivo_confirmado_em"] is None
        assert not (row.get("titulo_aquisitivo_texto") or "")

    def test_an_unclassified_act_leaves_onus_a_suggestion(self, scoped):
        eid, resultado = _rodar(
            scoped,
            _texto(ATO_R1_COM_INSTRUMENTO, ATO_R2_ALIENACAO, ATO_R6_INDETERMINADO),
        )

        campos = resultado["campos"]
        # `situacao_onus` is indeterminate (`derivar_situacao_onus` refuses
        # to answer), so `preenchimento_service` never even wrote it — there
        # is no value to be pending, only nothing proposed at all.
        assert campos["situacao_onus"] == autopiloto.SEM_VALOR
        # The ônus ACT POINTER (and, from it, the credor) is independent of
        # `situacao_onus` — the text heuristic still finds R-2's live
        # alienação, so both DID get a value; the autopilot just may not
        # confirm either while the situação itself stays unresolved.
        assert campos["onus_fonte"] == autopiloto.SUGESTAO_PENDENTE
        assert campos["onus_credor"] == autopiloto.SUGESTAO_PENDENTE
        # The título is unrelated to this ambiguity and still autoconfirms.
        assert campos["titulo_aquisitivo"] == autopiloto.CONFIRMADO_AUTOMATICO

        row = _dados(scoped)
        assert row.get("situacao_onus") is None
        assert row["onus_fonte_confirmado_em"] is None


#: [Drift-fix-on-contact, 2026-09-30] Live prod, 5 freshly re-transcribed
#: historical matrículas: a bare `CADASTRO` averbação — no pre-existing
#: `_NATUREZAS` pattern covered it — read `natureza=None`, the SAME blind
#: spot `ATO_R6_INDETERMINADO` above pins, and for the same reason blocked
#: `situacao_onus` from ever confirming `livre`. `matricula_ato_detalhes.
#: _NATUREZAS["outro"]` now recognises it.
ATO_AV7_CADASTRO = (
    "AV-7/45.678 - Em 10/10/2015. CADASTRO - Pelo instrumento particular "
    "adiante mencionado, e espelho do IPTU/2015, procede-se ao "
    "cadastramento do imóvel junto a esta serventia.\n"
)


class TestThePreviouslyUnclassifiedCorpusWordingNoLongerBlocksOnus:
    def test_a_bare_cadastro_averbacao_no_longer_blocks_situacao_onus(self, scoped):
        eid, resultado = _rodar(
            scoped,
            _texto(
                ATO_R1_COM_INSTRUMENTO, ATO_R2_ALIENACAO, ATO_AV3_CANCELAMENTO,
                ATO_AV7_CADASTRO,
            ),
        )

        campos = resultado["campos"]
        assert campos["situacao_onus"] == autopiloto.CONFIRMADO_AUTOMATICO

        row = _dados(scoped)
        assert row["situacao_onus"] == "livre"
        assert row["situacao_onus_origem"] == "ia"
        assert row["situacao_onus_confirmado_em"]


class TestNeverOverridesAHuman:
    def test_a_manually_confirmed_cartorio_is_never_touched(self, scoped):
        eid = str(uuid4())
        humano = str(uuid4())
        seed(
            scoped,
            registry=[registry_row()],
            extracoes=[extracao_row(eid, texto=_texto(ATO_R1_COM_INSTRUMENTO))],
            dados=[{
                "org_id": ORG_ID, "codigo": CODIGO,
                "numero_registro_imoveis": "2º Registro de Imóveis de Barueri",
                "numero_registro_imoveis_origem": "manual",
                "numero_registro_imoveis_confirmado_por": humano,
                "numero_registro_imoveis_confirmado_em": "2026-01-01T00:00:00+00:00",
                "created_at": "2026-01-01T00:00:00+00:00",
            }],
        )
        preench.preencher_sincrono(scoped, ORG, eid)  # opens a conflict, never applies

        resultado = autopiloto.aplicar_autopiloto(scoped, ORG, eid)

        assert resultado["campos"]["numero_registro_imoveis"] == autopiloto.JA_CONFIRMADO_HUMANO
        row = _dados(scoped)
        assert row["numero_registro_imoveis"] == "2º Registro de Imóveis de Barueri"
        assert row["numero_registro_imoveis_confirmado_por"] == humano

    def test_a_human_choosing_a_different_titulo_act_is_never_overridden(self, scoped):
        eid = str(uuid4())
        humano = str(uuid4())
        seed(
            scoped,
            registry=[registry_row()],
            extracoes=[extracao_row(
                eid, texto=_texto(ATO_R1_COM_INSTRUMENTO, ATO_R2_ALIENACAO)
            )],
        )
        atos = _atos_por_chave(scoped, eid)
        # A human re-classifies the R-2 act (not a transfer at all) as the
        # título — an explicit override of the heuristic's own R-1 pick.
        estrutura_svc.definir_fontes(
            scoped, ORG, UUID(eid),
            valores={"titulo_aquisitivo_ato_id": atos[("R", 2)]["id"]},
            usuario_id=humano,
        )

        resultado = autopiloto.aplicar_autopiloto(scoped, ORG, eid)

        assert resultado["campos"]["titulo_aquisitivo"] == autopiloto.JA_CONFIRMADO_HUMANO
        row = _dados(scoped)
        assert row["titulo_aquisitivo_ato_id"] == atos[("R", 2)]["id"]
        assert row["titulo_aquisitivo_origem"] == "manual"
        assert row["titulo_aquisitivo_confirmado_por"] == humano


class TestContractActsDefaultSelection:
    def test_no_selection_yet_defaults_to_abertura_titulo_and_onus(self, scoped):
        eid = str(uuid4())
        contrato = contrato_row()
        seed(
            scoped,
            registry=[registry_row()],
            extracoes=[extracao_row(
                eid, texto=_texto(ATO_R1_COM_INSTRUMENTO, ATO_R2_ALIENACAO)
            )],
            contratos=[contrato],
            negociacoes=[negociacao_row(contrato["atendimento_id"])],
        )
        atos = _atos_por_chave(scoped, eid)

        preench.preencher_sincrono(scoped, ORG, eid)
        resultado = autopiloto.aplicar_autopiloto(scoped, ORG, eid)

        assert resultado["atos_contrato"]["aplicavel"] is True
        assert resultado["atos_contrato"]["contratos_criados"] == [contrato["id"]]
        selecao = estrutura_svc.obter_selecao(scoped, ORG, UUID(contrato["id"]))
        assert [a["ato_id"] for a in selecao["atos"]] == [
            atos[("abertura", None)]["id"],
            atos[("R", 1)]["id"],
            atos[("R", 2)]["id"],
        ]

    def test_an_existing_selection_is_never_overridden(self, scoped):
        eid = str(uuid4())
        contrato = contrato_row()
        seed(
            scoped,
            registry=[registry_row()],
            extracoes=[extracao_row(
                eid, texto=_texto(ATO_R1_COM_INSTRUMENTO, ATO_R2_ALIENACAO)
            )],
            contratos=[contrato],
            negociacoes=[negociacao_row(contrato["atendimento_id"])],
        )
        atos = _atos_por_chave(scoped, eid)
        # A human already saved a (deliberately different, minimal) selection.
        estrutura_svc.definir_selecao(
            scoped, ORG, UUID(contrato["id"]),
            extracao_id=UUID(eid), ato_ids=[UUID(atos[("R", 1)]["id"])],
            usuario_id=str(uuid4()),
        )

        preench.preencher_sincrono(scoped, ORG, eid)
        resultado = autopiloto.aplicar_autopiloto(scoped, ORG, eid)

        assert resultado["atos_contrato"]["contratos_existentes"] == [contrato["id"]]
        assert resultado["atos_contrato"]["contratos_criados"] == []
        selecao = estrutura_svc.obter_selecao(scoped, ORG, UUID(contrato["id"]))
        assert [a["ato_id"] for a in selecao["atos"]] == [atos[("R", 1)]["id"]]

    def test_a_second_autopilot_run_does_not_duplicate_the_selection(self, scoped):
        eid = str(uuid4())
        contrato = contrato_row()
        seed(
            scoped,
            registry=[registry_row()],
            extracoes=[extracao_row(
                eid, texto=_texto(ATO_R1_COM_INSTRUMENTO, ATO_R2_ALIENACAO)
            )],
            contratos=[contrato],
            negociacoes=[negociacao_row(contrato["atendimento_id"])],
        )
        preench.preencher_sincrono(scoped, ORG, eid)
        autopiloto.aplicar_autopiloto(scoped, ORG, eid)

        segundo = autopiloto.aplicar_autopiloto(scoped, ORG, eid)

        assert segundo["atos_contrato"]["contratos_existentes"] == [contrato["id"]]
        assert segundo["atos_contrato"]["contratos_criados"] == []
