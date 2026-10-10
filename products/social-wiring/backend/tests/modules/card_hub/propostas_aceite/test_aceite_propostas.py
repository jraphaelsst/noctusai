"""`propostas.aceite.aceitar` — the one acceptance path (CONTRACT §4.4).

THE CLAIMS WORTH DEFENDING
--------------------------
1. Every refusal happens BEFORE the first write (card_hub has no transactions):
   the whole fake store is byte-identical after a refused accept.
2. The happy path REPLACES the live negotiation set from the snapshot, remaps the
   `fav:<i>` / `parcela:<i>` refs to the new ids, stamps the visita, starts the
   contract with the proposta's company + witnesses, and only then sets `aceita`.
3. Idempotent: a retry after a failure at step 1 or step 3 converges — never
   duplicates the set, never a second contract. Failures are injected through a
   fake CLIENT (a DI seam), never by patching our own code.
4. Steps 5-6 live in other sessions' modules: missing => passo `erro`, the accept
   stands; a failure there never undoes it.

All personal data is synthetic.
"""
from __future__ import annotations

import copy
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from noctusai_lib.primitives.exceptions import AppException, NotFoundError

from app.modules.card_hub.propostas import aceite
from app.modules.card_hub.propostas.aceite import AceitePorts, aceitar, reexecutar_pos_aceite
from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.test_contrato_gerador_endpoints import _TABELAS, _qualificado
from tests.modules.card_hub.test_roteiros import registry_row

ORG = UUID(ORG_ID)
ACTOR = uuid4()
CODIGO = "ONE9001"
CPF_FAV = "111.444.777-35"
CPF_TESTEMUNHA = "529.982.247-25"
T0 = "2026-01-01T00:00:00+00:00"

TABELAS_ESCRITAS = (
    *_TABELAS, "atendimento_propostas", "visitas", "atendimento_contratos",
    "atendimento_parcela_favorecidos", "atendimento_imoveis",
)


def _rows(scoped, tabela: str) -> list[dict]:
    return scoped.table(tabela).select("*").execute().data or []


def _estado(scoped) -> dict:
    return {t: copy.deepcopy(_rows(scoped, t)) for t in TABELAS_ESCRITAS}


def _snapshot_json() -> dict:
    return {
        "favorecidos": [
            {"nome": "Vendedor A", "cpf_cnpj": CPF_FAV, "pix": "a@pix"},
            {"nome": "Vendedor B"},
        ],
        "intermediarios": [
            {"nome": "Corretor X", "tipo": "percentual", "valor": "3", "favorecido_ref": "fav:1"},
        ],
        "parcelas": [
            {"tipo": "sinal", "valor": "50000", "vencimento": "2026-11-01", "favorecido_ref": "fav:0"},
            {"tipo": "saldo", "valor": "450000", "favorecido_ref": "fav:1"},
        ],
        "termos": {
            "posse_marco": "parcela", "posse_marco_parcela_ref": "parcela:0",
            "posse_prazo_dias": 30, "ad_corpus": True,
        },
    }


def _seed(scoped, *, status="enviada", visita=True, snapshot=None, imovel_negociacao=None,
          outra_aceita=False, com_vivo=True) -> dict:
    ids = {k: str(uuid4()) for k in (
        "cliente", "atendimento", "proposta", "visita", "imobiliaria", "t1", "t2", "outra",
    )}
    scoped.set_table_data("clientes", [
        _qualificado(ids["cliente"], "Beltrana Exemplo", "Feminino", "987654321", "22.222.222-2")
    ])
    scoped.set_table_data("atendimentos", [{
        "id": ids["atendimento"], "org_id": ORG_ID, "cliente_id": ids["cliente"], "lead_id": None,
        "meta_ads_lead_id": None, "status": "aberta", "substituida_por": None, "arquivado": False,
        "titulo": "Compra do apto", "created_at": T0, "closed_at": None,
    }])
    for tabela in TABELAS_ESCRITAS:
        scoped.set_table_data(tabela, [])
    scoped.set_table_data("imovel_registry", [registry_row(CODIGO), registry_row("ONE9002")])
    scoped.set_table_data("org_imobiliarias", [{
        "id": ids["imobiliaria"], "org_id": ORG_ID, "razao_social": "Imob Modelo Ltda",
        "excluida_em": None, "created_at": T0,
    }])
    scoped.set_table_data("org_testemunhas", [
        {"id": ids["t1"], "org_id": ORG_ID, "nome": "Test 1", "cpf": CPF_TESTEMUNHA,
         "rg": None, "email": None, "celular": None, "created_at": T0, "updated_at": None},
        {"id": ids["t2"], "org_id": ORG_ID, "nome": "Test 2", "cpf": "111.444.777-35",
         "rg": None, "email": None, "celular": None, "created_at": T0, "updated_at": None},
    ])
    if imovel_negociacao is not None:
        scoped.set_table_data("atendimento_negociacao", [{
            "atendimento_id": ids["atendimento"], "org_id": ORG_ID, "imovel_codigo": imovel_negociacao,
            "valor_negociado": "999.00", "pct_comissao": "6", "tem_parceria": False,
            "pct_parceria": "50", "pct_agencia": "50", "pct_agentes": "45", "pct_captador": "5",
            "financiamento": False, "fgts": False, "created_at": T0, "updated_at": None,
        }])
    if visita:
        scoped.set_table_data("visitas", [{
            "id": ids["visita"], "org_id": ORG_ID, "roteiro_id": str(uuid4()), "codigo": CODIGO,
            "proposta_em": None, "proposta_por": None, "proposta_aceita_em": None,
            "proposta_aceita_por": None, "deleted_at": None,
        }])
    if com_vivo:
        # A previous live set the accept must REPLACE (and whose parcela a termos
        # marco cites — the case `remover_parcela` would 409 on).
        velho_fav, velha_parcela = str(uuid4()), str(uuid4())
        scoped.set_table_data("atendimento_favorecidos", [{
            "id": velho_fav, "org_id": ORG_ID, "atendimento_id": ids["atendimento"],
            "nome": "Antigo", "created_at": T0,
        }])
        scoped.set_table_data("atendimento_negociacao_parcelas", [{
            "id": velha_parcela, "org_id": ORG_ID, "atendimento_id": ids["atendimento"],
            "tipo": "sinal", "valor": "1.00", "ordem": 0, "origem": "manual", "created_at": T0,
        }])
        scoped.set_table_data("atendimento_negociacao_termos", [{
            "atendimento_id": ids["atendimento"], "org_id": ORG_ID, "posse_marco": "parcela",
            "posse_marco_parcela_id": velha_parcela, "created_at": T0,
        }])
    propostas = [{
        "id": ids["proposta"], "org_id": ORG_ID, "atendimento_id": ids["atendimento"],
        "cliente_id": ids["cliente"], "visita_id": ids["visita"] if visita else None,
        "imovel_codigo": CODIGO, "status": status, "valor_proposto": "500000.00",
        "pct_comissao": "5", "financiamento": False, "fgts": True,
        "imobiliaria_id": ids["imobiliaria"], "testemunha_ids": [ids["t1"], ids["t2"]],
        "contrato_id": None, "created_at": T0,
        **(snapshot or _snapshot_json()),
    }]
    if outra_aceita:
        propostas.append({
            **propostas[0], "id": ids["outra"], "status": "aceita", "imovel_codigo": "ONE9002",
        })
    scoped.set_table_data("atendimento_propostas", propostas)
    return ids


def _proposta(scoped, ids) -> dict:
    return next(r for r in _rows(scoped, "atendimento_propostas") if r["id"] == ids["proposta"])


def _por_passo(resultado) -> dict:
    return {p["passo"]: p for p in resultado["passos"]}


# ── fake modules of the other sessions (injected through the importer) ──


class Modulos:
    def __init__(self, *, moveu=True, motivo=None, pos_levanta=None, funil_levanta=None):
        self.chamadas: list[tuple] = []
        self.agendadores: list = []
        outer = self

        def mover_por_evento(client, org_id, atendimento_id, evento, actor):
            outer.chamadas.append(("funil", str(atendimento_id), evento))
            if funil_levanta:
                raise funil_levanta
            return {"moveu": moveu, "de": "a", "para": "b", "motivo": motivo}

        def disparar(client, org_id, atendimento_id, actor, *, agendador):
            outer.chamadas.append(("pos_aceite", str(atendimento_id)))
            outer.agendadores.append(agendador)
            if pos_levanta:
                raise pos_levanta
            return {"certidoes": [], "matricula": {"status": "faltando", "documento_id": None,
                                                    "motivo": "matricula_ausente"}}

        self._mods = {
            aceite.MODULO_FUNIL: SimpleNamespace(mover_por_evento=mover_por_evento),
            aceite.MODULO_POS_ACEITE: SimpleNamespace(disparar=disparar),
        }

    def ports(self) -> AceitePorts:
        return AceitePorts(importar=self._mods.__getitem__)


def _sem_modulos() -> AceitePorts:
    def importar(nome):
        raise ModuleNotFoundError(f"No module named {nome!r}", name=nome)
    return AceitePorts(importar=importar)


# ── failure injection: a fake CLIENT, not a patch of our code ──


class _Tabela:
    """Raises when a WRITE is attempted (the mock applies a write eagerly, at the
    `insert()/update()/delete()` call, so failing at `.execute()` would leave the
    row written)."""

    def __init__(self, inner, falha, nome):
        self._inner, self._falha, self._nome = inner, falha, nome

    def __getattr__(self, op):
        attr = getattr(self._inner, op)
        if op in ("insert", "update", "delete", "upsert"):
            def escrever(*a, **k):
                if self._falha.dispara(self._nome, op):
                    raise RuntimeError("falha injetada")
                return attr(*a, **k)
            return escrever
        return attr


class ClienteQueFalha:
    """Fails the `pular`+1-th write of `operacao` on `tabela`, once."""

    def __init__(self, real, tabela, operacao, pular=0):
        self._real, self._alvo, self._pular, self.disparou = real, (tabela, operacao), pular, False

    def dispara(self, tabela, op):
        if self.disparou or (tabela, op) != self._alvo:
            return False
        if self._pular > 0:
            self._pular -= 1
            return False
        self.disparou = True
        return True

    def table(self, nome):
        return _Tabela(self._real.table(nome), self, nome)

    def __getattr__(self, nome):
        return getattr(self._real, nome)


def _vivo(scoped, ids):
    at = ids["atendimento"]
    f = [r for r in _rows(scoped, "atendimento_favorecidos") if r["atendimento_id"] == at]
    p = [r for r in _rows(scoped, "atendimento_negociacao_parcelas") if r["atendimento_id"] == at]
    i = [r for r in _rows(scoped, "atendimento_intermediarios") if r["atendimento_id"] == at]
    t = [r for r in _rows(scoped, "atendimento_negociacao_termos") if r["atendimento_id"] == at]
    return f, p, i, t


def _run(scoped, ids, *, client=None, ports=None, agendador=None):
    return aceitar(
        client or scoped, ORG, UUID(ids["atendimento"]), UUID(ids["proposta"]), ACTOR,
        ports=ports or Modulos().ports(), agendador=agendador,
    )


@pytest.fixture
def scoped_db(client, scoped):
    return scoped


# ── refusals ──


class TestRefusalsWriteNothing:
    def _recusa(self, scoped, ids, codigo, status, **kw):
        antes = _estado(scoped)
        with pytest.raises(AppException) as exc:
            _run(scoped, ids, **kw)
        assert exc.value.code == codigo and exc.value.status_code == status
        assert _estado(scoped) == antes, "a refused accept performed a write"
        return exc.value

    def test_unknown_proposta_is_404(self, scoped_db):
        ids = _seed(scoped_db)
        ids["proposta"] = str(uuid4())
        antes = _estado(scoped_db)
        with pytest.raises(NotFoundError):
            _run(scoped_db, ids)
        assert _estado(scoped_db) == antes

    def test_other_org_proposta_is_404(self, scoped_db):
        ids = _seed(scoped_db)
        rows = _rows(scoped_db, "atendimento_propostas")
        rows[0]["org_id"] = str(uuid4())
        scoped_db.set_table_data("atendimento_propostas", rows)
        antes = _estado(scoped_db)
        with pytest.raises(NotFoundError):
            _run(scoped_db, ids)
        assert _estado(scoped_db) == antes

    def test_proposta_of_another_atendimento_is_404(self, scoped_db):
        ids = _seed(scoped_db)
        ids["atendimento"] = str(uuid4())
        with pytest.raises(NotFoundError):
            _run(scoped_db, ids)

    @pytest.mark.parametrize("status", ["aceita", "recusada", "cancelada"])
    def test_closed_proposta_is_409(self, scoped_db, status):
        ids = _seed(scoped_db, status=status)
        e = self._recusa(scoped_db, ids, "proposta_fechada", 409)
        assert e.details["motivo"] == "proposta_fechada"

    def test_another_accepted_proposta_is_409(self, scoped_db):
        ids = _seed(scoped_db, outra_aceita=True)
        e = self._recusa(scoped_db, ids, "proposta_ja_aceita", 409)
        assert e.details["motivo"] == "proposta_ja_aceita"

    def test_a_different_deal_imovel_is_409(self, scoped_db):
        ids = _seed(scoped_db, imovel_negociacao="ONE9002")
        e = self._recusa(scoped_db, ids, "imovel_divergente", 409)
        assert e.details["motivo"] == "imovel_divergente"

    def test_the_same_deal_imovel_is_accepted(self, scoped_db):
        ids = _seed(scoped_db, imovel_negociacao=CODIGO.lower())
        assert _run(scoped_db, ids)["proposta_row"]["status"] == "aceita"

    def test_invalid_snapshot_is_400_with_dotted_field_paths_exact_body(self, scoped_db):
        snap = _snapshot_json()
        snap["parcelas"][1]["valor"] = "-5"
        snap["favorecidos"][0]["nome"] = ""
        snap["intermediarios"][0]["favorecido_ref"] = "fav:9"
        snap["termos"]["posse_marco_parcela_ref"] = "parcela:7"
        ids = _seed(scoped_db, snapshot=snap)
        e = self._recusa(scoped_db, ids, "snapshot_invalido", 400)
        campos = e.details["campos"]
        assert all(set(c) == {"path", "mensagem"} and c["mensagem"] for c in campos)
        assert [c["path"] for c in campos] == [
            "favorecidos.0.nome", "intermediarios.0.favorecido_ref",
            "parcelas.1.valor", "termos.posse_marco_parcela_ref",
        ]
        assert set(e.details) == {"campos"}
        assert e.message.startswith("Os termos desta proposta não são válidos")

    def test_refusal_bodies_are_exact(self, scoped_db):
        ids = _seed(scoped_db, status="recusada")
        with pytest.raises(AppException) as exc:
            _run(scoped_db, ids)
        assert (exc.value.code, exc.value.status_code, exc.value.details) == (
            "proposta_fechada", 409, {"motivo": "proposta_fechada", "status": "recusada"},
        )
        assert exc.value.message == (
            "Só é possível aceitar uma proposta em rascunho ou enviada (status atual: recusada)."
        )

    def test_a_literal_favorecido_id_is_refused_it_would_dangle(self, scoped_db):
        snap = _snapshot_json()
        snap["parcelas"][0]["favorecido_id"] = str(uuid4())
        snap["parcelas"][0].pop("favorecido_ref")
        ids = _seed(scoped_db, snapshot=snap)
        e = self._recusa(scoped_db, ids, "snapshot_invalido", 400)
        assert "parcelas.0.favorecido_id" in {x["path"] for x in e.details["campos"]}


# ── happy path ──


class TestHappyPath:
    def test_replaces_the_live_set_remaps_refs_and_runs_every_step(self, scoped_db):
        ids = _seed(scoped_db, imovel_negociacao=CODIGO)
        modulos = Modulos()
        r = _run(scoped_db, ids, ports=modulos.ports())

        assert [p["passo"] for p in r["passos"]] == list(aceite.PASSOS)
        assert all(p["status"] == "ok" for p in r["passos"]), r["passos"]

        fav, parcelas, inter, termos = _vivo(scoped_db, ids)
        assert sorted(f["nome"] for f in fav) == ["Vendedor A", "Vendedor B"]  # "Antigo" gone
        by_nome = {f["nome"]: f["id"] for f in fav}
        assert sorted(float(p["valor"]) for p in parcelas) == [50000.0, 450000.0]
        sinal = next(p for p in parcelas if p["tipo"] == "sinal")
        saldo = next(p for p in parcelas if p["tipo"] == "saldo")
        assert sinal["favorecido_id"] == by_nome["Vendedor A"]
        assert saldo["favorecido_id"] == by_nome["Vendedor B"]
        assert [i["favorecido_id"] for i in inter] == [by_nome["Vendedor B"]]
        assert len(termos) == 1 and termos[0]["posse_marco_parcela_id"] == sinal["id"]
        assert termos[0]["posse_prazo_dias"] == 30

        neg = next(n for n in _rows(scoped_db, "atendimento_negociacao")
                   if n["atendimento_id"] == ids["atendimento"])
        assert float(neg["valor_negociado"]) == 500000.0 and float(neg["pct_comissao"]) == 5.0
        assert neg["imovel_codigo"] == CODIGO and neg["fgts"] is True
        # the intermediário split is read back as the tab's parceria
        assert neg["tem_parceria"] is True and float(neg["pct_parceria"]) == 3.0

        visita = _rows(scoped_db, "visitas")[0]
        assert visita["proposta_aceita_em"] and visita["proposta_em"]  # migration 104's CHECK

        contratos = _rows(scoped_db, "atendimento_contratos")
        assert len(contratos) == 1 and contratos[0]["origem"] == "gerado"
        assert contratos[0]["imobiliaria_id"] == ids["imobiliaria"]
        selecao = sorted(_rows(scoped_db, "contrato_testemunhas"), key=lambda x: x["ordem"])
        assert [s["testemunha_id"] for s in selecao] == [ids["t1"], ids["t2"]]

        row = _proposta(scoped_db, ids)
        assert row["status"] == "aceita" and row["aceita_em"] and row["aceita_por"] == str(ACTOR)
        assert row["contrato_id"] == contratos[0]["id"] == r["contrato_id"]
        assert r["proposta_row"]["status"] == "aceita"
        assert r["geracao"]["contrato_id"] == r["contrato_id"] and "pronto" in r["geracao"]
        # the presets reached the readiness report (computed AFTER them):
        assert "imobiliaria.testemunhas" not in {f["campo"] for f in r["geracao"]["faltando"]}
        assert r["pos_aceite"]["matricula"]["status"] == "faltando"
        assert modulos.chamadas == [
            ("funil", ids["atendimento"], "proposta_aceita"), ("pos_aceite", ids["atendimento"]),
        ]

    def test_a_proposta_without_visita_skips_that_step(self, scoped_db):
        ids = _seed(scoped_db, visita=False)
        passos = _por_passo(_run(scoped_db, ids))
        assert passos["visita"]["status"] == "pulado" and passos["status"]["status"] == "ok"

    def test_a_bare_deal_with_no_live_set_materializes_too(self, scoped_db):
        ids = _seed(scoped_db, com_vivo=False)
        assert _run(scoped_db, ids)["proposta_row"]["status"] == "aceita"
        assert len(_vivo(scoped_db, ids)[1]) == 2

    def test_derived_intermediaria_is_not_injected(self, scoped_db):
        """A financiamento parcela + a pre-existing valor_negociado would make
        `sincronizar_parcela_intermediaria_derivada` add a row the snapshot does
        not contain."""
        snap = _snapshot_json()
        snap["parcelas"] = [
            {"tipo": "sinal", "valor": "50000", "favorecido_ref": "fav:0"},
            {"tipo": "financiamento", "valor": "300000"},
        ]
        snap["termos"] = {}
        ids = _seed(scoped_db, snapshot=snap, imovel_negociacao=CODIGO)
        _run(scoped_db, ids)
        assert sorted(p["tipo"] for p in _vivo(scoped_db, ids)[1]) == ["financiamento", "sinal"]


# ── idempotency ──


class TestRetryConverges:
    def test_failure_at_step_1_aborts_leaves_the_proposta_and_retry_converges(self, scoped_db):
        ids = _seed(scoped_db)
        falho = ClienteQueFalha(scoped_db, "atendimento_negociacao_parcelas", "insert", pular=1)
        with pytest.raises(RuntimeError, match="falha injetada"):
            _run(scoped_db, ids, client=falho)
        assert falho.disparou
        row = _proposta(scoped_db, ids)
        assert row["status"] == "enviada" and row["contrato_id"] is None
        assert _rows(scoped_db, "atendimento_contratos") == []
        assert _rows(scoped_db, "visitas")[0]["proposta_aceita_em"] is None
        # half-built, as a failure leaves it:
        assert len(_vivo(scoped_db, ids)[1]) == 1

        r = _run(scoped_db, ids)
        assert all(p["status"] == "ok" for p in r["passos"])
        fav, parcelas, inter, termos = _vivo(scoped_db, ids)
        assert (len(fav), len(parcelas), len(inter), len(termos)) == (2, 2, 1, 1)
        assert len(_rows(scoped_db, "atendimento_contratos")) == 1

    def test_failure_at_step_3_leaves_it_enviada_and_retry_resumes(self, scoped_db):
        ids = _seed(scoped_db)
        falho = ClienteQueFalha(scoped_db, "atendimento_contratos", "insert")
        r = _run(scoped_db, ids, client=falho)
        passos = _por_passo(r)
        assert passos["materializar"]["status"] == "ok"
        assert passos["contrato"]["status"] == "erro" and passos["contrato"]["mensagem"]
        assert [passos[p]["status"] for p in ("status", "funil", "pos_aceite")] == ["pulado"] * 3
        assert r["proposta_row"]["status"] == "enviada" and r["pos_aceite"] is None
        assert _proposta(scoped_db, ids)["status"] == "enviada"

        modulos = Modulos()
        r2 = _run(scoped_db, ids, ports=modulos.ports())
        assert all(p["status"] == "ok" for p in r2["passos"]), r2["passos"]
        fav, parcelas, inter, termos = _vivo(scoped_db, ids)
        assert (len(fav), len(parcelas), len(inter), len(termos)) == (2, 2, 1, 1)
        assert len(_rows(scoped_db, "atendimento_contratos")) == 1
        assert _proposta(scoped_db, ids)["status"] == "aceita"
        assert len(modulos.chamadas) == 2

    def test_a_failure_after_the_contract_exists_reuses_that_contract(self, scoped_db):
        ids = _seed(scoped_db)
        falho = ClienteQueFalha(scoped_db, "contrato_testemunhas", "insert")
        r = _run(scoped_db, ids, client=falho)
        assert _por_passo(r)["contrato"]["status"] == "erro"
        contrato = _proposta(scoped_db, ids)["contrato_id"]
        assert contrato and r["contrato_id"] == contrato and r["proposta_row"]["status"] == "enviada"

        r2 = _run(scoped_db, ids)
        assert r2["contrato_id"] == contrato
        assert len(_rows(scoped_db, "atendimento_contratos")) == 1
        assert len(_rows(scoped_db, "contrato_testemunhas")) == 2

    def test_a_visita_failure_blocks_the_status(self, scoped_db):
        ids = _seed(scoped_db)
        falho = ClienteQueFalha(scoped_db, "visitas", "update")
        r = _run(scoped_db, ids, client=falho)
        passos = _por_passo(r)
        assert passos["visita"]["status"] == "erro"
        assert passos["status"]["status"] == "pulado"
        assert _proposta(scoped_db, ids)["status"] == "enviada"
        assert _run(scoped_db, ids)["proposta_row"]["status"] == "aceita"


# ── steps 5-6: other sessions' modules ──


class TestOtherSessionsModules:
    def test_missing_modules_are_reported_and_the_accept_stands(self, scoped_db):
        ids = _seed(scoped_db)
        r = _run(scoped_db, ids, ports=_sem_modulos())
        passos = _por_passo(r)
        assert passos["status"]["status"] == "ok"
        for nome in ("funil", "pos_aceite"):
            assert passos[nome] == {"passo": nome, "status": "erro", "mensagem": "módulo indisponível"}
        assert r["pos_aceite"] is None
        assert _proposta(scoped_db, ids)["status"] == "aceita"

    def test_funil_not_moved_is_pulado_with_the_motivo(self, scoped_db):
        ids = _seed(scoped_db)
        r = _run(scoped_db, ids, ports=Modulos(moveu=False, motivo=["falta documento", "falta CPF"]).ports())
        funil = _por_passo(r)["funil"]
        assert funil["status"] == "pulado" and "falta documento" in funil["mensagem"]
        assert _por_passo(r)["pos_aceite"]["status"] == "ok"

    def test_funil_failure_neither_undoes_the_accept_nor_stops_pos_aceite(self, scoped_db):
        ids = _seed(scoped_db)
        r = _run(scoped_db, ids, ports=Modulos(funil_levanta=RuntimeError("x")).ports())
        passos = _por_passo(r)
        assert passos["funil"]["status"] == "erro"
        assert passos["pos_aceite"]["status"] == "ok"
        assert _proposta(scoped_db, ids)["status"] == "aceita"

    def test_pos_aceite_failure_never_undoes_the_accept(self, scoped_db):
        ids = _seed(scoped_db)
        boom = aceite.AtendimentoDivergente()
        r = _run(scoped_db, ids, ports=Modulos(pos_levanta=boom).ports())
        passo = _por_passo(r)["pos_aceite"]
        assert passo["status"] == "erro" and passo["mensagem"] == boom.message
        assert _proposta(scoped_db, ids)["status"] == "aceita"


class TestAgendadorSeam:
    def test_the_agendador_reaches_disparar_and_a_model_result_is_dumped(self, scoped_db):
        from pydantic import BaseModel

        class PosAceite(BaseModel):
            certidoes: list = []
            matricula: dict = {"status": "faltando"}

        ids = _seed(scoped_db)
        modulos = Modulos()
        modulos._mods[aceite.MODULO_POS_ACEITE].disparar = lambda *a, agendador: (
            modulos.agendadores.append(agendador) or PosAceite()
        )
        sentinela = object()
        r = _run(scoped_db, ids, ports=modulos.ports(), agendador=sentinela)
        assert modulos.agendadores == [sentinela]
        assert r["pos_aceite"] == {"certidoes": [], "matricula": {"status": "faltando"}}

    def test_reexecutar_forwards_the_agendador(self, scoped_db):
        ids = _seed(scoped_db)
        _run(scoped_db, ids)
        modulos = Modulos()
        sentinela = object()
        reexecutar_pos_aceite(
            scoped_db, ORG, UUID(ids["atendimento"]), UUID(ids["proposta"]), ACTOR,
            agendador=sentinela, ports=modulos.ports(),
        )
        assert modulos.agendadores == [sentinela]


class TestReexecutarPosAceite:
    def test_409_unless_the_proposta_is_accepted(self, scoped_db):
        ids = _seed(scoped_db)
        with pytest.raises(AppException) as exc:
            reexecutar_pos_aceite(
                scoped_db, ORG, UUID(ids["atendimento"]), UUID(ids["proposta"]), ACTOR,
                ports=Modulos().ports(),
            )
        assert exc.value.status_code == 409 and exc.value.code == "proposta_nao_aceita"

    def test_404_for_an_unknown_proposta(self, scoped_db):
        ids = _seed(scoped_db)
        with pytest.raises(NotFoundError):
            reexecutar_pos_aceite(
                scoped_db, ORG, UUID(ids["atendimento"]), uuid4(), ACTOR, ports=Modulos().ports()
            )

    def test_retomar_refires_funil_then_pos_aceite_after_a_failed_first_run(self, scoped_db):
        # noc-2 ruling 2026-10-09: one endpoint resumes EVERYTHING after the
        # accept — the forward-only funnel event, then step 6.
        ids = _seed(scoped_db)
        _run(scoped_db, ids, ports=_sem_modulos())
        antes = _estado(scoped_db)
        modulos = Modulos()
        r = reexecutar_pos_aceite(
            scoped_db, ORG, UUID(ids["atendimento"]), UUID(ids["proposta"]), ACTOR,
            ports=modulos.ports(),
        )
        assert [p["passo"] for p in r["passos"]] == ["funil", "pos_aceite"]
        assert all(p["status"] == "ok" for p in r["passos"])
        assert r["pos_aceite"]["matricula"]
        assert r["contrato_id"] and r["geracao"] is None
        assert modulos.chamadas == [
            ("funil", ids["atendimento"], "proposta_aceita"),
            ("pos_aceite", ids["atendimento"]),
        ]
        # Neither step writes the negotiation, the contract or the proposta.
        assert _estado(scoped_db) == antes

    def test_retomar_reports_a_funil_refusal_and_still_runs_pos_aceite(self, scoped_db):
        ids = _seed(scoped_db)
        _run(scoped_db, ids)
        modulos = Modulos(moveu=False, motivo="ja_adiante")
        r = reexecutar_pos_aceite(
            scoped_db, ORG, UUID(ids["atendimento"]), UUID(ids["proposta"]), ACTOR,
            ports=modulos.ports(),
        )
        funil, pos = r["passos"]
        assert funil["status"] == "pulado" and "ja_adiante" in (funil["mensagem"] or "")
        assert pos["status"] == "ok"


class TestValorObrigatorio:
    """noc-2 ruling 2026-10-09: no price, no accept — never NULL the live
    valor_negociado (a contract cannot be generated without a price)."""

    @pytest.mark.parametrize("valor", [None, ""])
    def test_aceitar_without_valor_is_400_before_any_write(self, scoped_db, valor):
        ids = _seed(scoped_db)
        scoped_db.table("atendimento_propostas").update({"valor_proposto": valor}).eq(
            "id", ids["proposta"]
        ).execute()
        antes = _estado(scoped_db)
        with pytest.raises(AppException) as exc:
            _run(scoped_db, ids)
        assert exc.value.status_code == 400 and exc.value.code == "valor_obrigatorio"
        assert _estado(scoped_db) == antes



class TestParceriaDerivada:
    def test_valor_fixo_shares_become_a_pct_of_the_commission(self):
        snap = aceite._Snapshot(
            [], [({"tipo": "valor_fixo", "valor": "69000"}, None),
                 ({"tipo": "valor_fixo", "valor": "69000"}, None)], [], {}, {},
        )
        out = aceite._parceria_derivada(snap, {"valor_proposto": "2760000", "pct_comissao": "5"})
        assert out == {"tem_parceria": True, "pct_parceria": __import__("decimal").Decimal("100.00")}

    def test_no_intermediarios_means_no_parceria(self):
        snap = aceite._Snapshot([], [], [], {}, {})
        assert aceite._parceria_derivada(snap, {}) == {"tem_parceria": False}

    def test_without_a_computable_commission_pct_is_not_invented(self):
        snap = aceite._Snapshot([], [({"tipo": "valor_fixo", "valor": "10"}, None)], [], {}, {})
        assert aceite._parceria_derivada(snap, {"valor_proposto": "100"}) == {"tem_parceria": True}
