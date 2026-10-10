"""Property-level legal data follows the manual<->Vista link (CONTRACT §8.7,
owner rule noc-2 2026-10-09; `app.modules.imovel_hub.vinculo_legal`).

WHAT THESE PIN
--------------
- unlinked imóvel: every reader answers exactly what it did before;
- Vista side empty -> the manual record's value, labelled with its source;
- both sides equal (modulo formatting) -> no conflict; both different -> a
  conflict on the EXISTING mechanism (`fonte_tabela='vinculo'`), Vista's own
  value shown plus the flag, never the other one silently;
- the manual side is never overlaid (Vista -> manual only);
- documents / proprietários: union through the link, labelled, never copied;
- the contract loader's imóvel carries the manual matrícula for a deal on the
  Vista código;
- `limpar` removes exactly the link conflicts (restores the pre-link state);
  `reconciliar` / `limpar` are idempotent; the automatic resolver leaves a link
  conflict to a human; a human "no" is not re-asked.
"""
from __future__ import annotations

from uuid import UUID, uuid4

from app.modules.imovel_hub import campos_extraidos_service as campos
from app.modules.imovel_hub import (
    dados_service,
    documentos_service,
    proprietarios_service,
    vinculo_legal,
)
from app.modules.imovel_hub.vinculo_service import Vinculo, resolver_vinculo
from tests.modules.imovel_hub.conftest import (
    ORG_ID,
    dados_row,
    documento_row,
    imovel_row,
    registry_row,
    seed,
)

ORG = UUID(ORG_ID)
VISTA = "AP1234"
MANUAL = "SW-0001"
VINCULO = Vinculo(manual_codigo=MANUAL, vista_codigo=VISTA)


def par(scoped, *, vista=None, manual=None, vinculado=True, documentos=None, conflitos=None):
    """A registered Vista código + a manual one (linked unless told otherwise)."""
    reg_vista = registry_row(VISTA)
    reg_manual = registry_row(
        MANUAL, ativo_no_vista=False, origem_descoberta="manual",
        vinculado_a=reg_vista["id"] if vinculado else None,
    )
    seed(
        scoped,
        registry=[reg_vista, reg_manual],
        imoveis=[imovel_row()],
        dados=[
            *([dados_row(VISTA, **vista)] if vista is not None else []),
            *([dados_row(MANUAL, **manual)] if manual is not None else []),
        ],
        documentos=documentos,
        conflitos=conflitos,
    )
    scoped.set_table_data("imovel_proprietarios", [])


def matricula(valor, origem="manual"):
    return {
        "numero_matricula": valor,
        "numero_matricula_origem": origem,
        "numero_matricula_confirmado_em": "2026-02-01T00:00:00+00:00",
    }


def conflitos_do(scoped, **filtro):
    rows = scoped.table("imovel_campo_conflitos").select("*").execute().data
    return [r for r in rows if all(r.get(k) == v for k, v in filtro.items())]


class TestResolver:
    def test_either_side_resolves_the_pair_and_unlinked_is_none(self, client, scoped):
        par(scoped, vista={}, manual={})
        assert resolver_vinculo(scoped, ORG, VISTA) == VINCULO
        assert resolver_vinculo(scoped, ORG, MANUAL) == VINCULO
        par(scoped, vista={}, manual={}, vinculado=False)
        assert resolver_vinculo(scoped, ORG, VISTA) is None
        assert resolver_vinculo(scoped, ORG, MANUAL) is None


class TestFallback:
    def test_unlinked_reads_are_unchanged(self, client, scoped):
        par(scoped, vista={}, manual=matricula("777"), vinculado=False)
        out = dados_service.obter(scoped, ORG, VISTA)
        assert out["numero_matricula"] is None
        assert out["vinculo_legal"] is None
        assert vinculo_legal.linha_efetiva(scoped, ORG, VISTA) == dados_service.linha(
            scoped, ORG, VISTA
        )

    def test_vista_side_empty_takes_the_manual_value_with_its_provenance(self, client, scoped):
        par(scoped, vista={}, manual={
            **matricula("12.345"),
            "numero_registro_imoveis": "1º CRI",
            "situacao_onus": "livre",
            "situacao_onus_origem": "manual",
            "onus_certidao_em": "2026-03-01",
        })
        out = dados_service.obter(scoped, ORG, VISTA)
        assert out["numero_matricula"] == "12.345"
        assert out["numero_matricula_confirmado_em"] == "2026-02-01T00:00:00+00:00"
        assert out["numero_registro_imoveis"] == "1º CRI"
        # the group travels whole: the ônus date comes with the situação
        assert out["situacao_onus"] == "livre"
        assert out["onus_certidao_em"] == "2026-03-01"
        assert out["proveniencia"]["numero_matricula"]["origem"] == "manual"
        assert out["vinculo_legal"]["manual_codigo"] == MANUAL
        assert out["vinculo_legal"]["fontes"]["numero_matricula"] == MANUAL
        assert out["vinculo_legal"]["conflitos"] == []
        valor = vinculo_legal.valor_efetivo(scoped, ORG, VISTA, "numero_matricula")
        assert valor == {"valor": "12.345", "fonte_codigo": MANUAL, "conflito": False}

    def test_per_group_fallback_keeps_the_vista_value_it_has(self, client, scoped):
        par(scoped, vista=matricula("999", "matricula"), manual={
            **matricula("777"), "numero_registro_imoveis": "2º CRI",
        })
        out = dados_service.obter(scoped, ORG, VISTA)
        assert out["numero_matricula"] == "999"
        assert out["numero_registro_imoveis"] == "2º CRI"
        assert set(out["vinculo_legal"]["fontes"]) == {"numero_registro_imoveis"}

    def test_the_manual_side_is_never_overlaid(self, client, scoped):
        par(scoped, vista=matricula("999"), manual={})
        out = dados_service.obter(scoped, ORG, MANUAL)
        assert out["numero_matricula"] is None
        assert out["vinculo_legal"] is None

    def test_vista_without_a_dados_row_still_reads_the_manual_one(self, client, scoped):
        par(scoped, manual=matricula("777"))
        assert dados_service.obter(scoped, ORG, VISTA)["numero_matricula"] == "777"

    def test_the_title_pointer_group_travels_whole(self, client, scoped):
        ext = str(uuid4())
        par(scoped, vista={}, manual={
            "titulo_aquisitivo_extracao_id": ext,
            "titulo_aquisitivo_ato_id": "ato-1",
            "titulo_aquisitivo_char_inicio": 3,
            "titulo_aquisitivo_char_fim": 9,
            "titulo_aquisitivo_origem": "manual",
        })
        ef = vinculo_legal.linha_efetiva(scoped, ORG, VISTA)
        assert ef["titulo_aquisitivo_extracao_id"] == ext
        assert ef["titulo_aquisitivo_char_fim"] == 9
        assert ef["titulo_aquisitivo_origem"] == "manual"


class TestConflicts:
    def test_equal_values_modulo_formatting_open_no_conflict(self, client, scoped):
        par(scoped, vista=matricula("12345", "matricula"), manual=matricula("12.345"))
        assert vinculo_legal.reconciliar(scoped, ORG, VINCULO)["novos"] == []
        assert conflitos_do(scoped) == []

    def test_different_values_open_one_link_conflict_and_the_reader_flags_it(
        self, client, scoped
    ):
        par(scoped, vista=matricula("999", "matricula"), manual=matricula("777"))
        r = vinculo_legal.reconciliar(scoped, ORG, VINCULO)
        assert r["novos"] == ["numero_matricula"]
        (c,) = conflitos_do(scoped)
        assert c["codigo"] == VISTA and c["campo"] == "numero_matricula"
        assert c["fonte_tabela"] == campos.FONTE_VINCULO
        assert c["status"] == "pendente"
        assert (c["valor_anterior"], c["valor_proposto"]) == ("999", "777")
        # reader: Vista's OWN value, never the other, plus the flag
        out = dados_service.obter(scoped, ORG, VISTA)
        assert out["numero_matricula"] == "999"
        assert out["vinculo_legal"]["conflitos"] == ["numero_matricula"]
        assert vinculo_legal.valor_efetivo(scoped, ORG, VISTA, "numero_matricula")["conflito"]

    def test_reconciliar_is_idempotent(self, client, scoped):
        par(scoped, vista=matricula("999", "matricula"), manual=matricula("777"))
        vinculo_legal.reconciliar(scoped, ORG, VINCULO)
        again = vinculo_legal.reconciliar(scoped, ORG, VINCULO)
        assert again["novos"] == [] and len(conflitos_do(scoped)) == 1

    def test_an_open_conflict_from_another_source_is_not_superseded(self, client, scoped):
        outro = {
            "id": str(uuid4()), "org_id": ORG_ID, "codigo": VISTA,
            "campo": "numero_matricula", "valor_anterior": "999", "origem_anterior": "matricula",
            "valor_proposto": "555", "origem_proposto": "matricula",
            "fonte_tabela": "matricula_extracoes", "status": "pendente",
            "created_at": "2026-01-05T00:00:00+00:00",
        }
        par(scoped, vista=matricula("999", "matricula"), manual=matricula("777"), conflitos=[outro])
        r = vinculo_legal.reconciliar(scoped, ORG, VINCULO)
        assert r["ja_em_conflito"] == ["numero_matricula"] and r["novos"] == []
        (c,) = conflitos_do(scoped)
        assert c["id"] == outro["id"] and c["status"] == "pendente"

    def test_a_human_no_is_not_asked_again(self, client, scoped):
        par(scoped, vista=matricula("999", "matricula"), manual=matricula("777"))
        vinculo_legal.reconciliar(scoped, ORG, VINCULO)
        (c,) = conflitos_do(scoped)
        campos.resolver(scoped, ORG, VISTA, UUID(c["id"]), aceitar=False, decidido_por=uuid4())
        assert vinculo_legal.reconciliar(scoped, ORG, VINCULO)["novos"] == []
        assert dados_service.obter(scoped, ORG, VISTA)["vinculo_legal"]["conflitos"] == []

    def test_accepting_lands_the_manual_value_on_the_vista_row(self, client, scoped):
        par(scoped, vista=matricula("999", "matricula"), manual=matricula("777"))
        vinculo_legal.reconciliar(scoped, ORG, VINCULO)
        (c,) = conflitos_do(scoped)
        campos.resolver(scoped, ORG, VISTA, UUID(c["id"]), aceitar=True, decidido_por=uuid4())
        assert dados_service.obter(scoped, ORG, VISTA)["numero_matricula"] == "777"
        assert vinculo_legal.reconciliar(scoped, ORG, VINCULO)["novos"] == []

    def test_a_link_conflict_is_never_auto_resolved(self, client, scoped):
        par(scoped, vista=matricula("999", "matricula"), manual=matricula("777"))
        vinculo_legal.reconciliar(scoped, ORG, VINCULO)
        r = campos.backfill_resolver_conflitos_pendentes(scoped, ORG, codigo=VISTA)
        assert r["resolvidos"] == [] and len(r["ignorados"]) == 1
        assert conflitos_do(scoped)[0]["status"] == "pendente"

    def test_a_conflict_that_stopped_conflicting_is_closed(self, client, scoped):
        par(scoped, vista=matricula("999", "matricula"), manual=matricula("777"))
        vinculo_legal.reconciliar(scoped, ORG, VINCULO)
        scoped.set_table_data("imovel_dados", [
            dados_row(VISTA, **matricula("999", "matricula")), dados_row(MANUAL, **matricula("999")),
        ])
        assert vinculo_legal.reconciliar(scoped, ORG, VINCULO)["fechados"] == ["numero_matricula"]
        assert dados_service.obter(scoped, ORG, VISTA)["vinculo_legal"]["conflitos"] == []

    def test_limpar_removes_exactly_the_link_conflicts_and_restores_the_reads(
        self, client, scoped
    ):
        humano = {
            "id": str(uuid4()), "org_id": ORG_ID, "codigo": VISTA,
            "campo": "numero_registro_imoveis", "valor_anterior": None, "origem_anterior": None,
            "valor_proposto": "X", "origem_proposto": "matricula",
            "fonte_tabela": "matricula_extracoes", "status": "pendente",
            "created_at": "2026-01-05T00:00:00+00:00",
        }
        par(scoped, vista=matricula("999", "matricula"), manual=matricula("777"), conflitos=[humano])
        vinculo_legal.reconciliar(scoped, ORG, VINCULO)
        assert len(conflitos_do(scoped)) == 2
        assert vinculo_legal.limpar(scoped, ORG, VINCULO) == 1
        assert [c["id"] for c in conflitos_do(scoped)] == [humano["id"]]
        assert vinculo_legal.limpar(scoped, ORG, VINCULO) == 0
        # unlink (dup-A's write) + clean: reads are the pre-link ones
        par(scoped, vista=matricula("999", "matricula"), manual=matricula("777"),
            vinculado=False, conflitos=[humano])
        assert dados_service.obter(scoped, ORG, VISTA)["vinculo_legal"] is None


class TestChildren:
    def test_documents_union_is_labelled_and_never_copied(self, client, scoped):
        d_vista = documento_row(codigo=VISTA, tipo_documento="iptu", created_at="2026-01-01T00:00:00+00:00")
        d_manual = documento_row(codigo=MANUAL, created_at="2026-01-03T00:00:00+00:00")
        par(scoped, vista={}, manual={}, documentos=[d_vista, d_manual])
        itens = documentos_service.listar(scoped, ORG, VISTA)["items"]
        assert [(i["codigo"], i["fonte_codigo"]) for i in itens] == [(MANUAL, MANUAL), (VISTA, VISTA)]
        assert len(scoped.table("imovel_documentos").select("*").execute().data) == 2
        # the manual side lists only its own
        assert {i["codigo"] for i in documentos_service.listar(scoped, ORG, MANUAL)["items"]} == {MANUAL}

    def test_certidoes_of_the_vista_codigo_see_the_manual_matricula(self, client, scoped):
        d_manual = documento_row(codigo=MANUAL, numero="123")
        par(scoped, vista={}, manual={}, documentos=[d_manual])
        itens = documentos_service.certidoes(scoped, ORG, VISTA)["items"]
        assert [(i["tipo"], i["fonte_codigo"]) for i in itens] == [("matricula", MANUAL)]

    def test_proprietarios_union_dedupes_and_labels(self, client, scoped):
        pessoa = str(uuid4())
        outra = str(uuid4())
        par(scoped, vista={}, manual={})
        scoped.set_table_data("imovel_proprietarios", [
            {"id": str(uuid4()), "org_id": ORG_ID, "codigo": VISTA, "cliente_id": pessoa,
             "empresa_id": None, "origem": "manual", "deleted_at": None, "created_at": "2026-01-01"},
            {"id": str(uuid4()), "org_id": ORG_ID, "codigo": MANUAL, "cliente_id": pessoa,
             "empresa_id": None, "origem": "manual", "deleted_at": None, "created_at": "2026-01-02"},
            {"id": str(uuid4()), "org_id": ORG_ID, "codigo": MANUAL, "cliente_id": outra,
             "empresa_id": None, "origem": "manual", "deleted_at": None, "created_at": "2026-01-03"},
        ])
        scoped.set_table_data("clientes", [
            {"id": pessoa, "org_id": ORG_ID, "nome": "Ana", "cpf": "1"},
            {"id": outra, "org_id": ORG_ID, "nome": "Bia", "cpf": "2"},
        ])
        itens = proprietarios_service.do_imovel(scoped, ORG, VISTA)["items"]
        assert [(i["cliente_id"], i["fonte_codigo"]) for i in itens] == [
            (pessoa, VISTA), (outra, MANUAL),
        ]
        assert len(proprietarios_service.do_imovel(scoped, ORG, MANUAL)["items"]) == 2
        lote = proprietarios_service.por_codigos(scoped, ORG, [VISTA, MANUAL])
        assert [o["nome"] for o in lote[VISTA]] == ["Ana", "Bia"]
        assert [o["nome"] for o in lote[MANUAL]] == ["Ana", "Bia"]


class TestContractLoader:
    def test_a_deal_on_the_vista_codigo_loads_the_manual_matricula(self, client, scoped):
        from app.modules.card_hub.contrato_gerador import carregador

        par(scoped, vista={}, manual={
            **matricula("12345"),
            "numero_registro_imoveis": "1º CRI",
            "prefeitura_cadastro_imobiliario": "00.11",
        })
        imovel = carregador._imovel(scoped, ORG, VISTA, None)
        assert imovel.numero_matricula == "12345"
        assert imovel.numero_registro_imoveis == "1º CRI"
        assert imovel.inscricao_municipal == "00.11"
