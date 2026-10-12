"""2026-10-12 live smoke on prod (One Consultoria, 113 ativos):

1. The top suggestion paired two properties of the SAME owner ("MPM", 22
   ativos under 2 phones) — a swap with yourself. The lib already excludes a
   same-owner pair; the adapter just never gave it an owner identity.
2. Re-running the engine grew the list 128 → 193: suggestions it no longer
   produced were never removed.
"""
from __future__ import annotations

from uuid import UUID

from noctusai_lib.domain.real_estate.matching import gerar_matches_para_imovel

from app.modules.permutas import adapter, service

ORG = UUID("00000000-0000-4000-8000-0000000000aa")


class TestIdentidadeProprietario:
    def test_telefone_normalizado_concorda_entre_formatos(self):
        a = adapter.identidade_proprietario({"proprietario_telefone": "+55 (11) 97469-3365"})
        b = adapter.identidade_proprietario({"proprietario_telefone": "11974693365"})
        assert a == b == "tel:11974693365"

    def test_email_quando_nao_ha_telefone(self):
        assert adapter.identidade_proprietario(
            {"proprietario_telefone": "", "proprietario_email": " Dono@Ex.com "}
        ) == "email:dono@ex.com"

    def test_nome_sozinho_nao_e_identidade(self):
        # "Larissa" x2 are two people: a shared first name is not a shared owner.
        assert adapter.identidade_proprietario({"proprietario_nome": "Larissa"}) is None

    def test_poucos_digitos_nao_e_telefone(self):
        assert adapter.identidade_proprietario({"proprietario_telefone": "1234"}) is None


def _listagem(id_: str, owner: str | None, **over) -> dict:
    base = {
        "id": id_, "natureza": "imovel", "aceita_permutas": True, "status": "ativo",
        "tipo_imovel": "Casa em Condomínio", "cidade": "Cotia", "bairro": "Granja Viana",
        "estado": "SP", "valor": 1_200_000.0, "quartos": 3, "vagas": 2,
        "area_total": 300.0, "interesses": [], "owner_id": owner,
    }
    base.update(over)
    return base


class TestMesmoDonoNaoCasa:
    def test_mesmo_dono_e_excluido(self):
        a = _listagem("a", "tel:11999990000")
        b = _listagem("b", "tel:11999990000", valor=1_150_000.0)
        assert gerar_matches_para_imovel(a, [adapter.como_oferta(b)]) == []

    def test_donos_diferentes_ainda_casam(self):
        a = _listagem("a", "tel:11999990000")
        b = _listagem("b", "tel:11888880000", valor=1_150_000.0)
        assert gerar_matches_para_imovel(a, [adapter.como_oferta(b)])

    def test_dono_desconhecido_nao_exclui(self):
        a, b = _listagem("a", None), _listagem("b", None, valor=1_150_000.0)
        assert gerar_matches_para_imovel(a, [adapter.como_oferta(b)])


class _Q:
    """Records one PostgREST-style chain against an in-memory table."""

    def __init__(self, db: "_Db", table: str):
        self.db, self.table, self.filters, self.op = db, table, [], "select"

    def select(self, *_a, **_k):
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, col, val):
        self.filters.append(lambda r, c=col, v=val: r.get(c) == v)
        return self

    def in_(self, col, vals):
        vals = set(vals)
        self.filters.append(lambda r, c=col: r.get(c) in vals)
        return self

    def execute(self):
        rows = self.db.rows[self.table]
        hit = [r for r in rows if all(f(r) for f in self.filters)]
        if self.op == "delete":
            self.db.rows[self.table] = [r for r in rows if r not in hit]

        class R:
            data = hit
        return R()


class _Db:
    def __init__(self, rows):
        self.rows = {service.MATCHES: rows}

    def schema(self, _s):
        return self

    def table(self, t):
        return _Q(self, t)


def _m(id_, o, d, etapa="sugerido", origem="motor"):
    return {"id": id_, "org_id": str(ORG), "ativo_origem_id": o, "ativo_destino_id": d,
            "etapa": etapa, "origem": origem}


class TestRemoveSugestoesObsoletas:
    def test_remove_so_sugestao_do_motor_que_saiu_do_resultado(self):
        db = _Db([
            _m("1", "a", "b"),                                  # still produced → kept
            _m("2", "a", "c"),                                  # stale suggestion → removed
            _m("3", "a", "d", etapa="avaliacao"),               # a person's decision → kept
            _m("4", "a", "e", origem="permutas_legacy"),        # imported legacy → kept
            {**_m("5", "a", "f"), "org_id": "outra-org"},       # another org → kept
        ])
        removidos = service._remover_sugestoes_obsoletas(
            db, ORG, [{"ativo_origem_id": "a", "ativo_destino_id": "b"}])
        assert removidos == 1
        assert {r["id"] for r in db.rows[service.MATCHES]} == {"1", "3", "4", "5"}


class TestProjecaoCarregaDono:
    def test_ativo_projetado_leva_owner_id(self):
        linha = {"id": "x", "natureza": "permuta_imovel", "status": "ativo",
                 "proprietario_nome": "MPM", "proprietario_telefone": "(11) 4000-1234"}
        projetado = adapter.ativo_para_scorer(linha)
        assert projetado["owner_id"] == "tel:1140001234"
