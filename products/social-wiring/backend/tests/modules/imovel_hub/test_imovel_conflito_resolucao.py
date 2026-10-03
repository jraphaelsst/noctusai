"""The imóvel automatic conflict resolver (`imovel_hub.conflito_resolucao`,
2026-10-03) — live (inside `campos_extraidos_service.aplicar`) and backfill
(`backfill_resolver_conflitos_pendentes`, resolve-on-read in `listar`).

Measured motivation (P3/P4 owner test loop): contracts stayed blocked because
values written by since-FIXED readers conflicted with the fixed reader's
correct fresh read of the same matrícula — a cartório missing its city, a
pointer into a superseded extraction, an inscrição transcribed by the
matrícula against the prefeitura's own document.

Every test here fails on the pre-resolver code: there, each of these opened
(or kept) a `pendente` conflict for a human.
"""
from __future__ import annotations

from uuid import UUID, uuid4

from app.modules.imovel_hub import campos_extraidos_service as campos_svc
from tests.modules.imovel_hub.conftest import CODIGO, ORG_ID, auth, dados_row, seed

ORG = UUID(ORG_ID)
SERVENTIA = "SERVENTIA DO REGISTRO DE IMÓVEIS"
SERVENTIA_COTIA = "SERVENTIA DO REGISTRO DE IMÓVEIS de Cotia"


def _dados(scoped) -> dict:
    return [r for r in scoped.table("imovel_dados").select("*").execute().data
            if r["codigo"] == CODIGO][0]


def _conflitos(scoped) -> list[dict]:
    return scoped.table("imovel_campo_conflitos").select("*").execute().data


def _extracao(id_: str, *, substituida_por: str | None = None, codigo: str = CODIGO) -> dict:
    return {
        "id": id_, "org_id": ORG_ID, "codigo": codigo, "status": "concluida",
        "substituida_por": substituida_por, "nome_arquivo": "matricula.pdf",
        "created_at": "2026-10-01T00:00:00+00:00",
    }


def _pendente(campo: str, anterior, proposto, *, origem_anterior, origem_proposto,
              fonte_id=None, fonte_tabela="matricula_extracoes", documento_id=None) -> dict:
    return {
        "id": str(uuid4()), "org_id": ORG_ID, "codigo": CODIGO, "campo": campo,
        "valor_anterior": anterior, "origem_anterior": origem_anterior,
        "valor_proposto": proposto, "origem_proposto": origem_proposto,
        "fonte_tabela": fonte_tabela, "fonte_id": fonte_id,
        "documento_id_proposto": documento_id, "status": "pendente",
        "decidido_por": None, "created_at": "2026-10-01T00:00:00+00:00",
    }


class TestCartorio:
    def test_the_reading_naming_the_city_replaces_an_autopilot_value(self, scoped):
        """On file: an older reader's cartório WITHOUT its city, confirmed
        by the autopilot (`origem='ia'`, `confirmado_em` set, nobody's id) —
        a machine vouch, not a person's. The fixed reader's `... de Cotia`
        is the same serventia plus its locality: applied, audited."""
        old_eid, new_eid = str(uuid4()), str(uuid4())
        seed(scoped, dados=[dados_row(
            numero_registro_imoveis=SERVENTIA, numero_registro_imoveis_origem="ia",
            numero_registro_imoveis_documento_id=old_eid,
            numero_registro_imoveis_confirmado_em="2026-09-30T00:00:00+00:00",
        )])
        scoped.set_table_data("matricula_extracoes", [])
        r = campos_svc.aplicar(
            scoped, ORG, CODIGO, "numero_registro_imoveis", SERVENTIA_COTIA,
            origem="matricula", documento_id=new_eid,
            fonte_tabela="matricula_extracoes", fonte_id=new_eid,
        )
        assert r.status == campos_svc.RESOLVIDO_APLICADO
        row = _dados(scoped)
        assert row["numero_registro_imoveis"] == SERVENTIA_COTIA
        assert row["numero_registro_imoveis_origem"] == "matricula"
        assert row["numero_registro_imoveis_confirmado_em"] is None  # machine-pending again
        [c] = _conflitos(scoped)
        assert c["status"] == "resolvido_automatico"
        assert c["decidido_por"] is None
        assert c["motivo_resolucao"].startswith("[cartorio_localidade]")

    def test_a_human_typed_cartorio_is_never_replaced(self, scoped):
        seed(scoped, dados=[dados_row(
            numero_registro_imoveis=SERVENTIA, numero_registro_imoveis_origem="manual",
        )])
        scoped.set_table_data("matricula_extracoes", [])
        r = campos_svc.aplicar(
            scoped, ORG, CODIGO, "numero_registro_imoveis", SERVENTIA_COTIA,
            origem="matricula",
        )
        assert r.status == campos_svc.CONFLITO
        assert _dados(scoped)["numero_registro_imoveis"] == SERVENTIA
        [c] = _conflitos(scoped)
        assert c["status"] == "pendente"

    def test_a_human_confirmed_cartorio_is_never_replaced(self, scoped):
        seed(scoped, dados=[dados_row(
            numero_registro_imoveis=SERVENTIA, numero_registro_imoveis_origem="matricula",
            numero_registro_imoveis_confirmado_por=str(uuid4()),
            numero_registro_imoveis_confirmado_em="2026-09-30T00:00:00+00:00",
        )])
        scoped.set_table_data("matricula_extracoes", [])
        r = campos_svc.aplicar(
            scoped, ORG, CODIGO, "numero_registro_imoveis", SERVENTIA_COTIA,
            origem="matricula",
        )
        assert r.status == campos_svc.CONFLITO
        assert _dados(scoped)["numero_registro_imoveis"] == SERVENTIA

    def test_the_book_header_is_not_part_of_the_cartorio(self, scoped):
        """`LIVRO Nº 2 - REGISTRO GERAL` glued on by an older reader is page
        furniture — the same serventia, no conflict."""
        seed(scoped, dados=[dados_row(
            numero_registro_imoveis=SERVENTIA, numero_registro_imoveis_origem="matricula",
        )])
        r = campos_svc.aplicar(
            scoped, ORG, CODIGO, "numero_registro_imoveis",
            f"LIVRO Nº 2 - REGISTRO GERAL {SERVENTIA}", origem="matricula",
        )
        assert r.status == campos_svc.IGUAL
        assert _conflitos(scoped) == []

    def test_a_different_cartorio_still_needs_a_human(self, scoped):
        seed(scoped, dados=[dados_row(
            numero_registro_imoveis="1º RI de Barueri", numero_registro_imoveis_origem="matricula",
        )])
        scoped.set_table_data("matricula_extracoes", [])
        r = campos_svc.aplicar(
            scoped, ORG, CODIGO, "numero_registro_imoveis", "2º RI de Barueri",
            origem="matricula",
        )
        assert r.status == campos_svc.CONFLITO


class TestExtracaoSubstituida:
    def _seed_ponteiro(self, scoped, *, confirmado_por=None):
        old_eid, new_eid = str(uuid4()), str(uuid4())
        old_ato, new_ato = str(uuid4()), str(uuid4())
        proposto = {
            "titulo_aquisitivo_extracao_id": new_eid,
            "titulo_aquisitivo_ato_id": new_ato,
            "titulo_aquisitivo_char_inicio": 10,
            "titulo_aquisitivo_char_fim": 90,
        }
        anterior = {
            "titulo_aquisitivo_extracao_id": old_eid,
            "titulo_aquisitivo_ato_id": old_ato,
            "titulo_aquisitivo_char_inicio": 12,
            "titulo_aquisitivo_char_fim": 95,
        }
        conflito = _pendente(
            "titulo_aquisitivo", anterior, proposto,
            origem_anterior="sugerido", origem_proposto="sugerido", fonte_id=new_eid,
        )
        seed(scoped, dados=[dados_row(
            **anterior, titulo_aquisitivo_origem="sugerido",
            titulo_aquisitivo_confirmado_por=confirmado_por,
            titulo_aquisitivo_confirmado_em="2026-09-30T00:00:00+00:00" if confirmado_por else None,
        )], conflitos=[conflito])
        scoped.set_table_data("matricula_extracoes", [
            _extracao(old_eid, substituida_por=new_eid), _extracao(new_eid),
        ])
        return old_eid, new_eid, new_ato, conflito

    def test_a_pending_pointer_into_a_superseded_extraction_is_resolved(self, scoped):
        old_eid, new_eid, new_ato, conflito = self._seed_ponteiro(scoped)
        out = campos_svc.backfill_resolver_conflitos_pendentes(scoped, ORG)
        assert [r["id"] for r in out["resolvidos"]] == [conflito["id"]]
        row = _dados(scoped)
        assert row["titulo_aquisitivo_extracao_id"] == new_eid
        assert row["titulo_aquisitivo_ato_id"] == new_ato
        [c] = _conflitos(scoped)
        assert c["status"] == "resolvido_automatico"
        assert c["decidido_por"] is None
        assert c["motivo_resolucao"].startswith("[extracao_substituida]")
        # The audit trail names the evidence: both extraction ids.
        assert old_eid in c["motivo_resolucao"] and new_eid in c["motivo_resolucao"]

    def test_a_human_confirmed_pointer_stays_for_a_human(self, scoped):
        old_eid, _new, _ato, conflito = self._seed_ponteiro(scoped, confirmado_por=str(uuid4()))
        out = campos_svc.backfill_resolver_conflitos_pendentes(scoped, ORG)
        assert [r["id"] for r in out["ainda_pendentes"]] == [conflito["id"]]
        assert _dados(scoped)["titulo_aquisitivo_extracao_id"] == old_eid
        [c] = _conflitos(scoped)
        assert c["status"] == "pendente"

    def test_resolve_on_read_settles_it_before_listing(self, client, scoped):
        self._seed_ponteiro(scoped)
        body = client.get(f"/api/imoveis/{CODIGO}/conflitos", headers=auth()).json()
        assert body["items"] == []

    def test_a_proposal_from_a_superseded_extraction_is_retracted(self, scoped):
        cur_eid, prop_eid, tip_eid = str(uuid4()), str(uuid4()), str(uuid4())
        conflito = _pendente(
            "situacao_onus", "livre", "hipoteca",
            origem_anterior="matricula", origem_proposto="matricula", fonte_id=prop_eid,
            documento_id=prop_eid,
        )
        seed(scoped, dados=[dados_row(
            situacao_onus="livre", situacao_onus_origem="matricula",
            situacao_onus_documento_id=cur_eid,
        )], conflitos=[conflito])
        scoped.set_table_data("matricula_extracoes", [
            _extracao(cur_eid), _extracao(prop_eid, substituida_por=tip_eid), _extracao(tip_eid),
        ])
        out = campos_svc.backfill_resolver_conflitos_pendentes(scoped, ORG)
        assert len(out["resolvidos"]) == 1
        assert _dados(scoped)["situacao_onus"] == "livre"
        [c] = _conflitos(scoped)
        assert c["status"] == "resolvido_automatico"
        assert c["motivo_resolucao"].startswith("[proposta_substituida]")

    def test_two_live_extractions_that_disagree_stay_for_a_human(self, scoped):
        cur_eid, prop_eid = str(uuid4()), str(uuid4())
        conflito = _pendente(
            "situacao_onus", "livre", "alienacao_fiduciaria",
            origem_anterior="ia", origem_proposto="matricula", fonte_id=prop_eid,
            documento_id=prop_eid,
        )
        seed(scoped, dados=[dados_row(
            situacao_onus="livre", situacao_onus_origem="ia",
            situacao_onus_documento_id=cur_eid,
            situacao_onus_confirmado_em="2026-09-30T00:00:00+00:00",
        )], conflitos=[conflito])
        scoped.set_table_data("matricula_extracoes", [_extracao(cur_eid), _extracao(prop_eid)])
        out = campos_svc.backfill_resolver_conflitos_pendentes(scoped, ORG)
        assert len(out["ainda_pendentes"]) == 1
        [c] = _conflitos(scoped)
        assert c["status"] == "pendente"


class TestPrefeituraAutoridade:
    def test_a_pending_matricula_transcription_loses_to_the_guia(self, scoped):
        conflito = _pendente(
            "prefeitura_cadastro_imobiliario", "23144.54.72.0014.00.000", "2314/34/72.000",
            origem_anterior="guia_iptu", origem_proposto="matricula", fonte_id=str(uuid4()),
        )
        seed(scoped, dados=[dados_row(
            prefeitura_cadastro_imobiliario="23144.54.72.0014.00.000",
            prefeitura_cadastro_imobiliario_origem="guia_iptu",
        )], conflitos=[conflito])
        scoped.set_table_data("matricula_extracoes", [])
        out = campos_svc.backfill_resolver_conflitos_pendentes(scoped, ORG)
        assert len(out["resolvidos"]) == 1
        [c] = _conflitos(scoped)
        assert c["motivo_resolucao"].startswith("[autoridade_prefeitura]")
        assert _dados(scoped)["prefeitura_cadastro_imobiliario"] == "23144.54.72.0014.00.000"

    def test_two_prefeitura_documents_that_disagree_stay_for_a_human(self, scoped):
        conflito = _pendente(
            "prefeitura_cadastro_imobiliario", "32252.53.55.0304.00.000",
            "23252.53.55.0304.00.000", origem_anterior="guia_iptu", origem_proposto="cnd_iptu",
            fonte_tabela="imovel_documentos", fonte_id=str(uuid4()),
        )
        seed(scoped, dados=[dados_row(
            prefeitura_cadastro_imobiliario="32252.53.55.0304.00.000",
            prefeitura_cadastro_imobiliario_origem="guia_iptu",
        )], conflitos=[conflito])
        out = campos_svc.backfill_resolver_conflitos_pendentes(scoped, ORG)
        assert len(out["ainda_pendentes"]) == 1


class TestNeverOverridesAHumanNo:
    def test_a_rejected_reading_is_not_applied_by_the_resolver(self, scoped):
        """A person rejected exactly this reading: even though the resolver
        would prefer it (locality refinement), it is never applied."""
        seed(
            scoped,
            dados=[dados_row(
                numero_registro_imoveis=SERVENTIA, numero_registro_imoveis_origem="matricula",
            )],
            conflitos=[{
                **_pendente(
                    "numero_registro_imoveis", SERVENTIA, SERVENTIA_COTIA,
                    origem_anterior="matricula", origem_proposto="matricula",
                ),
                "status": "rejeitado", "decidido_por": str(uuid4()),
            }],
        )
        r = campos_svc.aplicar(
            scoped, ORG, CODIGO, "numero_registro_imoveis", SERVENTIA_COTIA,
            origem="matricula",
        )
        assert r.status == campos_svc.REJEITADO_ANTES
        assert _dados(scoped)["numero_registro_imoveis"] == SERVENTIA
