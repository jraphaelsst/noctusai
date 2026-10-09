"""`pos_aceite_service` — CONTRACT sw-lead-to-contract §7 (certidões of every
vendedor + the matrícula, right after the aceite).

Only the EXTERNAL boundary is faked (the `Agendador` records what would have
hit InfoSimples / the vision provider); every guard under test — the vendedor
resolution, the staleness predicate, the credentials pre-flight, the
consulta writes — is the real code.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.modules.card_hub import pos_aceite_service as svc
from app.modules.card_hub.contrato_gerador.politica import POLITICA_PADRAO
from app.modules.certidoes.registry import CERTIDOES_CONFIG
from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.test_certidoes_matriz import (
    _atendimento,
    _consulta,
    _empresa,
    _parte,
    _participacao,
    _resultado,
    _seed_tables,
)

HOJE = date(2026, 10, 9)
CODIGO = "AP0001"
AUTOMATICOS = sorted(c["tipo"] for c in CERTIDOES_CONFIG if c["tipo"] != "tjsp")


class Gravador:
    """The external boundary: records what would have been scheduled."""

    def __init__(self) -> None:
        self.consultas: list[str] = []
        self.extracoes: list[tuple[str, str]] = []

    @property
    def agendador(self) -> svc.Agendador:
        return svc.Agendador(
            consulta=self.consultas.append,
            extracao=lambda eid, path: self.extracoes.append((eid, path)),
        )


def _sem_falta(_org):
    return []


def _falta_token(_org):
    return ["Token InfoSimples não configurado."]


def _tabelas_extras(scoped) -> None:
    for t in ("atendimento_negociacao", "imovel_proprietarios", "imovel_documentos",
              "matricula_extracoes", "atendimento_propostas"):
        scoped.set_table_data(t, [])
    scoped.set_table_data("imovel_registry", [{"org_id": ORG_ID, "codigo_canonical": CODIGO}])


def _cliente(scoped, row: dict) -> None:
    scoped.set_table_data("clientes", [*scoped.table("clientes").select("*").execute().data, row])


def _deal(scoped):
    """Titular + vendedor A (spouse SA, NO party row) + vendedor B (spouse SB,
    anuente WITH a party row) + a co-owner C only registered on the imóvel."""
    _seed_tables(scoped)
    _tabelas_extras(scoped)
    ids = {k: str(uuid4()) for k in ("cid", "aid", "a", "sa", "b", "sb", "c")}
    scoped.set_table_data("clientes", [
        cliente_row(ids["cid"], nome="Titular", cpf="41295423898"),
        cliente_row(ids["a"], nome="Vend A", cpf="11111111111", conjuge_cliente_id=ids["sa"]),
        cliente_row(ids["sa"], nome="Conjuge A", cpf="22222222222", conjuge_cliente_id=ids["a"]),
        cliente_row(ids["b"], nome="Vend B", cpf="33333333333", conjuge_cliente_id=ids["sb"]),
        cliente_row(ids["sb"], nome="Conjuge B", cpf="44444444444", conjuge_cliente_id=ids["b"]),
        cliente_row(ids["c"], nome="Dono C", cpf="55555555555"),
    ])
    scoped.set_table_data("atendimentos", [_atendimento(ids["aid"], ids["cid"])])
    scoped.set_table_data("atendimento_partes", [
        _parte(ids["aid"], ids["a"]),
        _parte(ids["aid"], ids["b"]),
        _parte(ids["aid"], ids["sb"], papel="conjuge"),
    ])
    scoped.set_table_data("atendimento_negociacao", [
        {"org_id": ORG_ID, "atendimento_id": ids["aid"], "imovel_codigo": CODIGO},
    ])
    scoped.set_table_data("imovel_proprietarios", [
        {"id": str(uuid4()), "org_id": ORG_ID, "codigo": CODIGO, "cliente_id": ids["c"],
         "empresa_id": None, "origem": "manual", "deleted_at": None,
         "created_at": "2026-01-01T00:00:00+00:00"},
    ])
    return ids


def _rodar(scoped, ids, grav=None, check=_sem_falta):
    grav = grav or Gravador()
    out = svc.disparar(
        scoped, ORG_ID, ids["aid"], str(uuid4()),
        agendador=grav.agendador, check_credentials=check, hoje=HOJE,
    )
    return out, grav


def _por_alvo(out: svc.PosAceite) -> dict[str, svc.CertidaoPosAceite]:
    return {c.alvo_id: c for c in out.certidoes}


def _consultas(scoped) -> list[dict]:
    return scoped.table("certidao_consultas").select("*").execute().data


class TestVendedores:
    def test_dono_conjuges_anuente_e_coproprietario_sao_todos_certificados(self, scoped):
        ids = _deal(scoped)
        out, grav = _rodar(scoped, ids)

        por = _por_alvo(out)
        assert set(por) == {ids["a"], ids["sa"], ids["b"], ids["sb"], ids["c"]}
        assert ids["cid"] not in por  # the comprador is not a vendedor
        assert all(c.status == "emitindo" and c.kind == "pessoa" for c in por.values())
        assert all(sorted(c.tipos) == AUTOMATICOS for c in por.values())
        assert len(grav.consultas) == 5 == len(_consultas(scoped))
        assert {c["cliente_id"] for c in _consultas(scoped)} == set(por)
        assert set(grav.consultas) == {c.consulta_id for c in por.values()}

    def test_empresa_derivada_do_vendedor_tambem(self, scoped):
        ids = _deal(scoped)
        emp = str(uuid4())
        scoped.set_table_data("empresas", [_empresa(emp)])
        scoped.set_table_data("cliente_empresa_participacoes", [_participacao(ids["a"], emp)])

        out, _ = _rodar(scoped, ids)

        item = _por_alvo(out)[emp]
        assert item.kind == "empresa" and item.status == "emitindo"
        assert {c.get("empresa_id") for c in _consultas(scoped)} >= {emp}

    def test_conjuge_sem_cpf_e_erro_so_dele(self, scoped):
        ids = _deal(scoped)
        scoped.set_table_data("clientes", [
            r | {"cpf": None} if r["id"] == ids["sa"] else r
            for r in scoped.table("clientes").select("*").execute().data
        ])
        out, _ = _rodar(scoped, ids)
        por = _por_alvo(out)
        assert por[ids["sa"]].status == "erro"
        assert por[ids["a"]].status == "emitindo"


class TestIdempotenciaEValidade:
    def test_segunda_rodada_nao_emite_nada(self, scoped):
        ids = _deal(scoped)
        _rodar(scoped, ids)
        antes = len(_consultas(scoped))

        out, grav = _rodar(scoped, ids)

        assert len(_consultas(scoped)) == antes and grav.consultas == []
        assert all(c.status == "pulada" and c.motivo == "consulta_em_andamento" for c in out.certidoes)

    def test_certidoes_validas_viram_ja_valida(self, scoped):
        ids = _deal(scoped)
        _rodar(scoped, ids)
        consultas = _consultas(scoped)
        scoped.set_table_data("certidao_resultados", [
            r | {"status": "sucesso", "resultado": "negativa",
                 "emitida_em": (HOJE - timedelta(days=1)).isoformat()}
            for r in scoped.table("certidao_resultados").select("*").execute().data
        ])
        assert consultas
        out, grav = _rodar(scoped, ids)
        assert grav.consultas == []
        assert all(c.status == "ja_valida" for c in out.certidoes)

    def test_certidao_vencida_e_reemitida_so_nos_tipos_vencidos(self, scoped):
        ids = _deal(scoped)
        _rodar(scoped, ids)
        limite = POLITICA_PADRAO.certidao_max_dias
        vencida = (HOJE - timedelta(days=limite)).isoformat()   # exactly at the gate's limit
        fresca = (HOJE - timedelta(days=limite - 1)).isoformat()
        resultados = scoped.table("certidao_resultados").select("*").execute().data
        consulta_a = next(c["id"] for c in _consultas(scoped) if c["cliente_id"] == ids["a"])
        scoped.set_table_data("certidao_resultados", [
            r | {
                "status": "sucesso", "resultado": "negativa",
                "emitida_em": vencida if (r["consulta_id"] == consulta_a and r["tipo"] == "cnd_federal") else fresca,
            }
            for r in resultados
        ])

        out, grav = _rodar(scoped, ids)

        reemitidas = [c for c in out.certidoes if c.status == "emitindo"]
        assert len(reemitidas) == 1 and reemitidas[0].alvo_id == ids["a"]
        assert reemitidas[0].tipos == ["cnd_federal"]
        assert len(grav.consultas) == 1

    def test_consulta_orfa_antiga_nao_bloqueia_a_reemissao(self, scoped):
        ids = _deal(scoped)
        _rodar(scoped, ids)
        velho = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        scoped.set_table_data("certidao_resultados", [
            r | {"created_at": velho} for r in scoped.table("certidao_resultados").select("*").execute().data
        ])
        out, grav = _rodar(scoped, ids)
        assert len(grav.consultas) == 5
        assert all(c.status == "emitindo" for c in out.certidoes)


class TestCredenciais:
    def test_sem_token_bloqueia_tudo_antes_de_qualquer_escrita(self, scoped):
        ids = _deal(scoped)
        out, grav = _rodar(scoped, ids, check=_falta_token)

        assert len(out.certidoes) == 5
        assert all(c.status == "bloqueado" and c.motivo == "credenciais" for c in out.certidoes)
        assert _consultas(scoped) == [] and grav.consultas == []
        assert scoped.table("certidao_resultados").select("*").execute().data == []


class TestMatricula:
    def _doc(self, scoped, created="2026-10-01T00:00:00+00:00", **over):
        doc = {
            "id": str(uuid4()), "org_id": ORG_ID, "codigo": CODIGO,
            "tipo_documento": "matricula", "mime_type": "application/pdf",
            "nome_original": "mat.pdf", "storage_path": f"imoveis/{CODIGO}/mat.pdf",
            "tamanho_bytes": 10, "created_at": created, "deleted_at": None,
        } | over
        scoped.set_table_data("imovel_documentos", [*scoped.table("imovel_documentos").select("*").execute().data, doc])
        return doc

    def test_sem_matricula_e_faltando(self, scoped, monkeypatch):
        ids = _deal(scoped)
        out, grav = _rodar(scoped, ids)
        assert (out.matricula.status, out.matricula.motivo) == ("faltando", "matricula_ausente")
        assert grav.extracoes == []

    def test_documento_sem_extracao_agenda_a_leitura_uma_vez(self, scoped, monkeypatch):
        monkeypatch.setattr("app.modules.matriculas.service.check_required_credentials", lambda org: [])
        ids = _deal(scoped)
        doc = self._doc(scoped)

        out, grav = _rodar(scoped, ids)
        assert (out.matricula.status, out.matricula.documento_id) == ("extraindo", doc["id"])
        assert len(grav.extracoes) == 1 and grav.extracoes[0][1] == doc["storage_path"]
        [extracao] = scoped.table("matricula_extracoes").select("*").execute().data
        assert extracao["imovel_documento_id"] == doc["id"] and extracao["status"] == "pendente"

        # second run: the extraction is in flight — nothing new
        out2, grav2 = _rodar(scoped, ids)
        assert out2.matricula.status == "extraindo" and grav2.extracoes == []
        assert len(scoped.table("matricula_extracoes").select("*").execute().data) == 1

    def test_sem_credencial_de_leitura_e_erro_sem_escrever(self, scoped, monkeypatch):
        monkeypatch.setattr(
            "app.modules.matriculas.service.check_required_credentials", lambda org: ["sem chave"]
        )
        ids = _deal(scoped)
        self._doc(scoped)
        out, grav = _rodar(scoped, ids)
        assert (out.matricula.status, out.matricula.motivo) == ("erro", "credenciais")
        assert scoped.table("matricula_extracoes").select("*").execute().data == []

    def test_documento_mais_novo_ganha_nova_leitura(self, scoped, monkeypatch):
        monkeypatch.setattr("app.modules.matriculas.service.check_required_credentials", lambda org: [])
        ids = _deal(scoped)
        velho = self._doc(scoped, created="2026-09-01T00:00:00+00:00")
        scoped.set_table_data("matricula_extracoes", [{
            "id": str(uuid4()), "org_id": ORG_ID, "codigo": CODIGO, "status": "concluida",
            "imovel_documento_id": velho["id"], "nome_arquivo": "mat.pdf",
            "created_at": "2026-09-01T01:00:00+00:00", "substituida_por": None,
        }])
        novo = self._doc(scoped, created="2026-10-05T00:00:00+00:00")

        out, grav = _rodar(scoped, ids)

        assert (out.matricula.status, out.matricula.documento_id) == ("extraindo", novo["id"])
        assert len(grav.extracoes) == 1

    def test_extracao_concluida_roda_o_autopiloto(self, scoped):
        ids = _deal(scoped)
        doc = self._doc(scoped)
        scoped.set_table_data("matricula_extracoes", [{
            "id": str(uuid4()), "org_id": ORG_ID, "codigo": CODIGO, "status": "concluida",
            "imovel_documento_id": doc["id"], "nome_arquivo": "mat.pdf", "texto_extraido": "",
            "created_at": "2026-10-01T01:00:00+00:00", "substituida_por": None,
        }])
        out, grav = _rodar(scoped, ids)
        assert out.matricula.documento_id == doc["id"]
        assert out.matricula.status == "ok"
        assert grav.extracoes == []


class TestConjugeTardio:
    def _aceitar(self, scoped, ids):
        scoped.set_table_data("atendimento_propostas", [{
            "id": str(uuid4()), "org_id": ORG_ID, "atendimento_id": ids["aid"],
            "status": "aceita", "aceita_por": str(uuid4()), "imovel_codigo": CODIGO,
        }])

    def test_conjuge_vinculado_depois_do_aceite_e_certificado(self, scoped):
        ids = _deal(scoped)
        novo = str(uuid4())
        _cliente(scoped, cliente_row(novo, nome="Conjuge C", cpf="66666666666"))
        self._aceitar(scoped, ids)
        grav = Gravador()

        afetados = svc.ao_vincular_conjuge(
            scoped, ORG_ID, ids["c"], novo, agendador=grav.agendador, check_credentials=_sem_falta,
        )

        [a] = afetados
        assert a["atendimento_id"] == ids["aid"]
        # C is an owner of the imóvel; the link is written by the caller, so the
        # new spouse shows up once `conjuge_cliente_id` is set:
        assert ids["c"] in _por_alvo(a["pos_aceite"])

    def test_sem_proposta_aceita_nao_dispara(self, scoped):
        ids = _deal(scoped)
        grav = Gravador()
        assert svc.ao_vincular_conjuge(
            scoped, ORG_ID, ids["a"], ids["sa"], agendador=grav.agendador, check_credentials=_sem_falta,
        ) == []
        assert grav.consultas == [] and _consultas(scoped) == []

    def test_casar_real_grava_o_vinculo_e_o_hook_nunca_derruba_a_escrita(self, scoped):
        """The real write path (`compradores_service._casar`) fires the hook; with
        no InfoSimples token in the test env the hook reports `bloqueado` and
        writes nothing billable, and the marriage itself is intact."""
        from app.modules.card_hub import compradores_service as comp

        ids = _deal(scoped)
        novo = str(uuid4())
        _cliente(scoped, cliente_row(novo, nome="Conjuge C", cpf="66666666666"))
        self._aceitar(scoped, ids)

        comp._casar(scoped, ORG_ID, ids["c"], novo)

        rows = {r["id"]: r for r in scoped.table("clientes").select("*").execute().data}
        assert rows[ids["c"]]["conjuge_cliente_id"] == novo
        assert rows[novo]["conjuge_cliente_id"] == ids["c"]
        assert _consultas(scoped) == []
