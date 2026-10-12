"""`listar_ativos` attaches the catalog listing under its own key.

The registry page shows título/bairro/valor for a natureza='imovel' row, whose
own columns are mostly empty (the row is a pointer). The catalog data must NOT
be folded over the row's columns: the edit form is prefilled from this payload
and would otherwise write catalog values back into the intent on save.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.modules.permutas import service as svc


class _Q:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._preds: list = []

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._preds.append(lambda r: str(r.get(col)) == str(val))
        return self

    def in_(self, col, vals):
        vals = {str(v) for v in vals}
        self._preds.append(lambda r: str(r.get(col)) in vals)
        return self

    def order(self, *_a, **_k):
        return self

    def execute(self):
        return SimpleNamespace(
            data=[dict(r) for r in self._rows if all(p(r) for p in self._preds)]
        )


class _Client:
    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables

    def schema(self, _n):
        return self

    def table(self, name):
        return _Q(self.tables.get(name, []))


ORG = uuid4()


def _ativo(id_: str, **over) -> dict:
    base = {
        "id": id_,
        "org_id": str(ORG),
        "natureza": "imovel",
        "imovel_codigo": None,
        "bairro": None,
        "valor": None,
        "status": "ativo",
        "embedding": None,
        "embedding_interesses": [0.1],
        "created_at": "2026-09-06T00:00:00Z",
    }
    base.update(over)
    return base


def test_anexa_catalogo_sem_sobrescrever_as_colunas_do_ativo():
    client = _Client(
        {
            "permuta_ativos": [
                _ativo("a", imovel_codigo="ONE1"),
                _ativo("b", natureza="permuta_imovel", bairro="Centro", valor=500000),
                _ativo("c", imovel_codigo="ONE_SUMIU"),
            ],
            "permuta_interesses": [{"id": "i1", "ativo_id": "a", "tipo": "imovel"}],
            "imoveis": [
                {
                    "codigo": "ONE1",
                    "org_id": str(ORG),
                    "titulo": "Casa na Granja",
                    "categoria": "Casa",
                    "bairro": "Fazendinha - Km 23",
                    "cidade": "Carapicuíba",
                    "uf": "SP",
                    "valor_venda": 900000,
                }
            ],
        }
    )

    out = svc.listar_ativos(client, ORG)
    por_id = {i["id"]: i for i in out["items"]}

    a = por_id["a"]
    assert a["catalogo"]["titulo"] == "Casa na Granja"
    assert a["catalogo"]["valor_venda"] == 900000
    # The intent row's own columns are untouched.
    assert a["bairro"] is None and a["valor"] is None
    assert a["interesses"] == [{"id": "i1", "ativo_id": "a", "tipo": "imovel"}]
    assert a["tem_embedding"] is False and a["tem_embedding_interesses"] is True
    assert "embedding" not in a

    assert por_id["b"]["catalogo"] is None
    # A código no longer in the catalog is reported as None, not dropped.
    assert por_id["c"]["catalogo"] is None
    assert out["total"] == 3


def test_sem_codigos_nao_consulta_o_catalogo():
    client = _Client(
        {"permuta_ativos": [_ativo("b", natureza="permuta_imovel")], "permuta_interesses": []}
    )
    out = svc.listar_ativos(client, ORG)
    assert out["items"][0]["catalogo"] is None
