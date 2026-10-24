"""`antigos_proprietarios_service` — the Certidões tab's previous-owner group
(owner decisions 2026-10-05). The matrícula reading is handed in through the
service's DI seam (`ler_antigos`); everything else runs against the mock DB.
Every name / CPF / CNPJ is synthetic."""
from __future__ import annotations

from uuid import uuid4

import pytest
from noctusai_lib.primitives.exceptions import ConflictError, ValidationError_

from app.modules.card_hub import antigos_proprietarios_service as svc
from app.modules.card_hub import certidoes_partes_service as certidoes_svc
from app.modules.card_hub import partes_service
from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.test_certidoes_matriz import _atendimento, _seed_tables

CPF_A = "52998224725"
CPF_B = "11144477735"
CNPJ_A = "11444777000161"
USER = uuid4()


def _creds_ok(_org_id):
    return []


def _creds_faltando(_org_id):
    return ["Chave InfoSimples ausente."]


def _info(*transmitentes, exige=True, origem="titulo_confirmado"):
    return lambda *_a, **_k: {
        "transmitentes": [{"nome": n, "cpf_cnpj": d} for n, d in transmitentes],
        "exige_certidoes": exige,
        "origem": origem,
        "sem_registro": False,
        "ultima_transferencia": {"data_registro": "2024-03-01", "natureza": "compra_e_venda"},
    }


def _card(scoped):
    cid, aid = str(uuid4()), str(uuid4())
    _seed_tables(scoped)
    for t in ("atendimento_negociacao", "atendimento_negociacao_termos", "organizacao_negociacao_defaults"):
        scoped.set_table_data(t, [])
    scoped.set_table_data("clientes", [cliente_row(cid, nome="Titular", cpf="39053344705")])
    scoped.set_table_data("atendimentos", [{**_atendimento(aid, cid), "exigir_certidoes_antigos": True}])
    scoped.set_table_data("atendimento_negociacao", [
        {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": aid, "imovel_codigo": "AP0001"},
    ])
    return cid, aid


def _sync(scoped, cid, info, creds=_creds_ok):
    return svc.sincronizar(
        scoped, ORG_ID, cid, user_id=USER, check_credentials=creds, ler_antigos=info,
    )


class TestSincronizar:
    def test_recent_transfer_creates_the_group_and_starts_emission(self, scoped):
        cid, aid = _card(scoped)
        out = _sync(scoped, cid, _info(("Antigo Dono Exemplo", CPF_A), ("Construtora Exemplo", CNPJ_A)))
        assert [c["tipo_pessoa"] for c in out["criados"]] == ["PF", "PJ"]
        assert [e["status"] for e in out["emissoes"]] == ["solicitada", "solicitada"]
        assert all(e["consulta_id"] for e in out["emissoes"])
        antigos = partes_service.listar_antigos(scoped, ORG_ID, cid)
        assert [a["rotulo"] for a in antigos] == ["ANT 1", "ANT 2"]
        assert {a["papel"] for a in antigos} == {"antigo_proprietario"}
        assert {a["origem"] for a in antigos} == {"matricula"}
        consultas = scoped.table("certidao_consultas").select("*").execute().data
        assert len(consultas) == 2

    def test_previous_owners_are_never_in_the_parties_list(self, scoped):
        cid, _aid = _card(scoped)
        _sync(scoped, cid, _info(("Antigo Dono Exemplo", CPF_A)))
        _alvo, itens = partes_service.listar_partes(scoped, ORG_ID, cid)
        assert [i["rotulo"] for i in itens] == ["COMP 1"]

    def test_certidoes_payload_carries_the_group_after_the_sellers(self, scoped):
        cid, _aid = _card(scoped)
        _sync(scoped, cid, _info(("Antigo Dono Exemplo", CPF_A)))
        partes = certidoes_svc.montar(scoped, ORG_ID, cid)["partes"]
        assert [(p["grupo"], p["rotulo"]) for p in partes] == [
            ("comprador", "COMP 1"), ("antigo_proprietario", "ANT 1"),
        ]
        assert partes[1]["papel"] == "antigo_proprietario"

    def test_is_idempotent(self, scoped):
        cid, _aid = _card(scoped)
        info = _info(("Antigo Dono Exemplo", CPF_A))
        assert len(_sync(scoped, cid, info)["criados"]) == 1
        again = _sync(scoped, cid, info)
        assert again["criados"] == [] and again["emissoes"] == []
        assert len(again["ja_no_card"]) == 1

    def test_optional_by_default_creates_nothing_and_bills_nothing(self, scoped):
        """Owner 2026-10-21 (migration 295): without the deal's opt-in no group
        is built and no automatic emission is requested."""
        cid, aid = _card(scoped)
        scoped.set_table_data("atendimentos", [_atendimento(aid, cid)])  # flag absent ⇒ false
        out = _sync(scoped, cid, _info(("Antigo Dono Exemplo", CPF_A)))
        assert out["ignorado"] == "nao_exigido"
        assert out["criados"] == [] and out["emissoes"] == []

    def test_dispensed_deal_creates_nothing(self, scoped):
        cid, _aid = _card(scoped)
        svc.dispensar(scoped, ORG_ID, cid, motivo="Acordo com o cliente", usuario_id=USER,
                      ler_antigos=_info())
        out = _sync(scoped, cid, _info(("Antigo Dono Exemplo", CPF_A)))
        assert out["ignorado"] == "dispensado" and out["criados"] == []

    def test_transfer_of_five_years_or_more_creates_nothing(self, scoped):
        cid, _aid = _card(scoped)
        out = _sync(scoped, cid, _info(("Antigo Dono Exemplo", CPF_A), exige=False))
        assert out["ignorado"] == "transferencia_5_anos_ou_mais"
        assert partes_service.listar_antigos(scoped, ORG_ID, cid) == []

    def test_a_manual_override_names_nobody_so_nothing_is_created(self, scoped):
        cid, _aid = _card(scoped)
        out = _sync(scoped, cid, _info(origem="manual"))
        assert out["ignorado"] == "matricula_nao_nomeia_antigos"

    def test_missing_credentials_are_reported_not_swallowed(self, scoped):
        cid, _aid = _card(scoped)
        out = _sync(scoped, cid, _info(("Antigo Dono Exemplo", CPF_A)), creds=_creds_faltando)
        assert len(out["criados"]) == 1
        assert out["emissoes"][0]["status"] == "nao_iniciada"
        assert out["emissoes"][0]["codigo"] == "CREDENCIAIS_AUSENTES"

    def test_a_transmitente_without_a_document_is_added_but_emission_is_named_missing(self, scoped):
        cid, _aid = _card(scoped)
        out = _sync(scoped, cid, _info(("Antigo Sem Documento", None)))
        assert out["emissoes"][0]["codigo"] == "DOCUMENTO_AUSENTE"

    def test_f97_a_ja_qualificado_seller_resolved_by_the_matricula_is_created_with_his_cpf(
        self, scoped
    ):
        """`titulo_service` now hands the back-referenced seller WITH the CPF
        the earlier act qualified him with — the party is created with it and
        emission starts, instead of DOCUMENTO_AUSENTE."""
        cid, _aid = _card(scoped)
        out = _sync(scoped, cid, _info(("Antigo Dono Exemplo", CPF_A)))
        (antigo,) = partes_service.listar_antigos(scoped, ORG_ID, cid)
        assert antigo["documento"] == CPF_A
        assert out["emissoes"][0]["status"] == "solicitada"

    def test_f97_an_antigo_synced_without_a_document_gets_the_cpf_filled_not_duplicated(
        self, scoped
    ):
        cid, _aid = _card(scoped)
        _sync(scoped, cid, _info(("Antigo Dono Exemplo", None)))  # before the fix
        out = _sync(scoped, cid, _info(("ANTIGO DONO EXEMPLO", CPF_A)))
        assert out["criados"] == []
        assert out["ja_no_card"][0]["documento_preenchido"] is True
        (antigo,) = partes_service.listar_antigos(scoped, ORG_ID, cid)
        assert antigo["documento"] == CPF_A
        cliente = scoped.table("clientes").select("*").eq("id", antigo["cliente_id"]).execute().data[0]
        assert cliente["cpf_origem"] == "matricula"
        assert cliente["cpf_confirmado_por"] is None


class TestDispensa:
    def test_requires_a_motivo(self, scoped):
        cid, _aid = _card(scoped)
        with pytest.raises(ValidationError_):
            svc.dispensar(scoped, ORG_ID, cid, motivo=" a ", usuario_id=USER)

    def test_stamps_who_when_why_and_can_be_undone(self, scoped):
        cid, aid = _card(scoped)
        out = svc.dispensar(scoped, ORG_ID, cid, motivo="Acordo com o cliente", usuario_id=USER,
                            ler_antigos=_info())
        assert out["dispensado"]["motivo"] == "Acordo com o cliente"
        assert svc.esta_dispensado(scoped, ORG_ID, aid)
        out = svc.reativar(scoped, ORG_ID, cid, usuario_id=USER, ler_antigos=_info())
        assert out["dispensado"] is None and not svc.esta_dispensado(scoped, ORG_ID, aid)


class TestManual:
    def test_add_and_remove_by_hand(self, scoped):
        cid, _aid = _card(scoped)
        out = svc.adicionar_manual(
            scoped, ORG_ID, cid, nome="Antigo Manual Exemplo", cpf=CPF_B,
            user_id=USER, check_credentials=_creds_ok,
        )
        assert out["parte"]["origem"] == "manual" and out["emissao"]["status"] == "solicitada"
        with pytest.raises(ConflictError):
            svc.adicionar_manual(
                scoped, ORG_ID, cid, nome="Antigo Manual Exemplo", cpf=CPF_B,
                user_id=USER, check_credentials=_creds_ok,
            )
        svc.remover(scoped, ORG_ID, cid, out["parte"]["parte_id"])
        assert partes_service.listar_antigos(scoped, ORG_ID, cid) == []

    def test_remove_refuses_a_party_that_is_not_a_previous_owner(self, scoped):
        cid, aid = _card(scoped)
        seller = str(uuid4())
        scoped.set_table_data("clientes", [
            *scoped.table("clientes").select("*").execute().data, cliente_row(seller, nome="Vend", cpf=CPF_B),
        ])
        from tests.modules.card_hub.test_certidoes_matriz import _parte
        parte = _parte(aid, seller)
        scoped.set_table_data("atendimento_partes", [parte])
        with pytest.raises(ValidationError_):
            svc.remover(scoped, ORG_ID, cid, parte["id"])

    def test_invalid_document_is_refused(self, scoped):
        cid, _aid = _card(scoped)
        with pytest.raises(ValidationError_):
            svc.adicionar_manual(scoped, ORG_ID, cid, nome="X Y", cpf="11111111111",
                                 user_id=USER, check_credentials=_creds_ok)


class TestEstado:
    def test_header_state_is_required_with_masked_transmitentes(self, scoped):
        cid, _aid = _card(scoped)
        out = svc.estado(scoped, ORG_ID, cid, ler_antigos=_info(("Antigo Dono Exemplo", CPF_A)))
        assert out["exigido"] is True and out["motivo"] == "transferencia_menos_de_5_anos"
        assert out["transmitentes"][0]["documento_mascarado"] == "***.982.247-**"
        assert out["sincronizacao_pendente"] == 1 and out["dispensado"] is None


class TestGatilhoDoPipelineDeMatricula:
    """Owner 2026-10-05: emission starts the moment the matrícula is on the
    card — the pipeline hook syncs every open deal of the imóvel."""

    def _agendador(self):
        chamadas: list[list[str]] = []

        def agendar(ids, _client):
            chamadas.append(list(ids))
            return []

        return agendar, chamadas

    def test_syncs_every_open_deal_of_the_imovel_and_schedules_the_emission(self, scoped):
        cid, aid = _card(scoped)
        agendar, chamadas = self._agendador()
        out = svc.sincronizar_por_imovel(
            scoped, ORG_ID, "AP0001", user_id=USER,
            ler_antigos=_info(("Antigo Dono Exemplo", CPF_A)), agendar=agendar,
            check_credentials=_creds_ok,
        )
        assert out["erros"] == [] and out["cards"][0]["criados"] == 1
        assert len(chamadas) == 1 and len(chamadas[0]) == 1
        # idempotent: a second pipeline pass creates and schedules nothing
        out = svc.sincronizar_por_imovel(
            scoped, ORG_ID, "AP0001", user_id=USER,
            ler_antigos=_info(("Antigo Dono Exemplo", CPF_A)), agendar=agendar,
            check_credentials=_creds_ok,
        )
        assert out["cards"][0]["criados"] == 0 and len(chamadas) == 1

    def test_other_imoveis_are_untouched(self, scoped):
        _card(scoped)
        agendar, chamadas = self._agendador()
        out = svc.sincronizar_por_imovel(
            scoped, ORG_ID, "OUTRO", user_id=USER,
            ler_antigos=_info(("Antigo Dono Exemplo", CPF_A)), agendar=agendar,
            check_credentials=_creds_ok,
        )
        assert out["cards"] == [] and chamadas == []

    def test_a_failing_deal_is_reported_not_raised(self, scoped):
        _card(scoped)

        def quebrado(*_a, **_k):
            raise RuntimeError("leitura indisponivel")

        out = svc.sincronizar_por_imovel(
            scoped, ORG_ID, "AP0001", user_id=USER, ler_antigos=quebrado,
        )
        assert out["erros"] and "leitura indisponivel" in out["erros"][0]["erro"]

    def test_without_a_user_nothing_is_created_and_it_is_said(self, scoped):
        cid, _aid = _card(scoped)
        out = svc.sincronizar_por_imovel(
            scoped, ORG_ID, "AP0001", user_id=None, ler_antigos=_info(("Antigo", CPF_A)),
        )
        assert out["ignorado"] == "sem_usuario"
        assert partes_service.listar_antigos(scoped, ORG_ID, cid) == []

    def test_without_an_event_loop_the_consultas_are_returned_not_dropped(self, scoped):
        _card(scoped)
        out = svc.sincronizar_por_imovel(
            scoped, ORG_ID, "AP0001", user_id=USER, ler_antigos=_info(("Antigo Dono Exemplo", CPF_A)),
            agendar=svc._agendar_processamento, check_credentials=_creds_ok,
        )
        assert len(out["nao_agendadas"]) == 1


def _info_por_codigo(por_codigo: dict, *, exige=True):
    """A `ler_antigos` that answers ONLY for the códigos it knows — proves
    WHICH imóvel the service read the matrícula of."""
    lidos: list[str] = []

    def ler(_client, _org_id, codigo, **_k):
        lidos.append(codigo)
        transmitentes = por_codigo.get(codigo)
        if transmitentes is None:
            return {"transmitentes": [], "exige_certidoes": False, "origem": "nenhuma",
                    "sem_registro": True, "ultima_transferencia": None}
        return {
            "transmitentes": [{"nome": n, "cpf_cnpj": d} for n, d in transmitentes],
            "exige_certidoes": exige, "origem": "extracao", "sem_registro": False,
            "ultima_transferencia": {"data_registro": "2023-05-10", "natureza": "compra_e_venda"},
        }

    ler.lidos = lidos
    return ler


def _junction(aid, codigo, *, principal=True, origem="lead"):
    return {
        "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": aid, "codigo": codigo,
        "origem": origem, "principal": principal, "deleted_at": None,
        "created_at": "2026-10-01T10:00:00+00:00",
    }


def _card_so_com_principal(scoped, codigo="LD0042"):
    """F85's shape: the imóvel came with the lead (junction principal), the
    Negociação tab was never filled."""
    cid, aid = _card(scoped)
    scoped.set_table_data("atendimento_negociacao", [])
    scoped.set_table_data("atendimento_imoveis", [_junction(aid, codigo)])
    return cid, aid


class TestImovelCanonico:
    """F85 — the antigos subtab reads the SAME imóvel the card shows."""

    def test_principal_only_imovel_drives_the_header(self, scoped):
        cid, aid = _card_so_com_principal(scoped)
        ler = _info_por_codigo({"LD0042": [("Antigo Dono Exemplo", CPF_A)]})
        out = svc.estado(scoped, ORG_ID, cid, atendimento_id=aid, ler_antigos=ler)
        assert ler.lidos == ["LD0042"]
        assert out["exigido"] is True and out["motivo"] == "transferencia_menos_de_5_anos"
        assert [t["nome"] for t in out["transmitentes"]] == ["Antigo Dono Exemplo"]

    def test_principal_only_imovel_sincronizar_creates_the_antigo(self, scoped):
        cid, aid = _card_so_com_principal(scoped)
        ler = _info_por_codigo({"LD0042": [("Antigo Dono Exemplo", CPF_A), ("Construtora Exemplo", CNPJ_A)]})
        out = svc.sincronizar(scoped, ORG_ID, cid, user_id=USER, check_credentials=_creds_ok, ler_antigos=ler)
        assert out["ignorado"] is None
        assert [c["nome"] for c in out["criados"]][0] == "Antigo Dono Exemplo"
        assert len(out["criados"]) == 2
        assert [a["rotulo"] for a in partes_service.listar_antigos(scoped, ORG_ID, cid, atendimento_id=aid)] == ["ANT 1", "ANT 2"]

    def test_negociacao_imovel_wins_when_present(self, scoped):
        cid, aid = _card_so_com_principal(scoped)
        scoped.set_table_data("atendimento_negociacao", [
            {"id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": aid, "imovel_codigo": "AP0001"},
        ])
        ler = _info_por_codigo({"AP0001": [("Antigo Negociado", CPF_B)], "LD0042": [("Errado", CPF_A)]})
        out = svc.estado(scoped, ORG_ID, cid, atendimento_id=aid, ler_antigos=ler)
        assert ler.lidos == ["AP0001"]
        assert [t["nome"] for t in out["transmitentes"]] == ["Antigo Negociado"]

    def test_no_imovel_at_all_is_still_sem_imovel(self, scoped):
        cid, aid = _card_so_com_principal(scoped)
        scoped.set_table_data("atendimento_imoveis", [])
        ler = _info_por_codigo({})
        out = svc.estado(scoped, ORG_ID, cid, atendimento_id=aid, ler_antigos=ler)
        assert out["exigido"] is None and out["motivo"] == "sem_imovel" and ler.lidos == []
        sync = svc.sincronizar(scoped, ORG_ID, cid, user_id=USER, check_credentials=_creds_ok, ler_antigos=ler)
        assert sync["ignorado"] == "sem_imovel"

    def test_a_removed_junction_row_is_not_the_imovel(self, scoped):
        cid, aid = _card_so_com_principal(scoped)
        scoped.set_table_data("atendimento_imoveis", [{**_junction(aid, "LD0042"), "deleted_at": "2026-10-02T00:00:00+00:00"}])
        out = svc.estado(scoped, ORG_ID, cid, atendimento_id=aid, ler_antigos=_info_por_codigo({}))
        assert out["motivo"] == "sem_imovel"

    def test_pipeline_hook_reaches_a_principal_only_deal(self, scoped):
        _cid, aid = _card_so_com_principal(scoped)
        out = svc.sincronizar_por_imovel(
            scoped, ORG_ID, "LD0042", user_id=USER,
            ler_antigos=_info_por_codigo({"LD0042": [("Antigo Dono Exemplo", CPF_A)]}),
            agendar=lambda ids, _c: [], check_credentials=_creds_ok,
        )
        assert [c["atendimento_id"] for c in out["cards"]] == [aid]
        assert out["cards"][0]["criados"] == 1


class TestProcessoLegadoNaoEmite:
    """A pre-platform deal: parties are created, NO automatic billed emission
    is requested (owner, InfoSimples spend) — but the operator's EXPLICIT
    emission on the row still works (owner 2026-10-24)."""

    def _legado(self, scoped, aid):
        scoped.set_table_data("atendimento_contratos", [{
            "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": aid,
            "processo_legado": True, "deleted_at": None, "created_at": "2026-10-01T00:00:00+00:00",
        }])

    def test_sincronizar_creates_parties_without_emission(self, scoped):
        cid, aid = _card_so_com_principal(scoped)
        self._legado(scoped, aid)
        ler = _info_por_codigo({"LD0042": [("Antigo Dono Exemplo", CPF_A)]})
        out = svc.sincronizar(scoped, ORG_ID, cid, user_id=USER, check_credentials=_creds_ok, ler_antigos=ler)
        assert len(out["criados"]) == 1
        assert out["emissoes"] == [{
            "parte_id": out["criados"][0]["parte_id"], "status": "nao_iniciada",
            "codigo": "PROCESSO_LEGADO", "consulta_id": None,
        }]
        assert out["emissao_ignorada"] == "processo_legado"
        assert scoped.table("certidao_consultas").select("*").execute().data == []

    def test_manual_add_on_a_legacy_deal_bills_nothing(self, scoped):
        cid, aid = _card(scoped)
        self._legado(scoped, aid)
        out = svc.adicionar_manual(
            scoped, ORG_ID, cid, nome="Antigo Manual Exemplo", cpf=CPF_B,
            user_id=USER, check_credentials=_creds_ok,
        )
        assert out["emissao"]["codigo"] == "PROCESSO_LEGADO"
        assert scoped.table("certidao_consultas").select("*").execute().data == []

    def test_a_removed_legacy_contract_no_longer_suppresses(self, scoped):
        cid, aid = _card(scoped)
        scoped.set_table_data("atendimento_contratos", [{
            "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": aid,
            "processo_legado": True, "deleted_at": "2026-10-02T00:00:00+00:00",
        }])
        out = _sync(scoped, cid, _info(("Antigo Dono Exemplo", CPF_A)))
        assert out["emissoes"][0]["status"] == "solicitada" and out["emissao_ignorada"] is None

    @pytest.mark.parametrize("tipos", [None, ["cnd_federal"]], ids=["todas", "linha"])
    def test_explicit_emission_on_a_legacy_deal_still_works(self, scoped, tipos):
        cid, aid = _card_so_com_principal(scoped)
        self._legado(scoped, aid)
        out = svc.sincronizar(
            scoped, ORG_ID, cid, user_id=USER, check_credentials=_creds_ok,
            ler_antigos=_info_por_codigo({"LD0042": [("Antigo Dono Exemplo", CPF_A)]}),
        )
        parte = next(
            p for p in certidoes_svc.todas_as_partes(scoped, ORG_ID, cid, aid)
            if p.get("parte_id") == out["criados"][0]["parte_id"]
        )
        kind = "empresa" if parte.get("empresa_id") else "pessoa"
        alvo_id = parte.get("empresa_id") or parte.get("cliente_id")
        emitida = certidoes_svc.solicitar_emissao(
            scoped, ORG_ID, cid, kind, alvo_id, tipos=tipos,
            atendimento_id=aid, user_id=USER, check_credentials=_creds_ok,
        )
        assert emitida["consulta_id"]
        assert len(scoped.table("certidao_consultas").select("*").execute().data) == 1
