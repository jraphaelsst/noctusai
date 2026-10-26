"""`gerar_matches` end to end: rows in, the swap scorer's verdicts persisted.

The scorer has its own suite in the seed lib. This pins the WIRING — that the
service hands the adapter's projection to `permuta.emitir_permuta` (not to the
similarity engine), so a stated ceiling actually removes a pair and a
cross-type swap actually lands, with its justification, as a `sugerido` row.
The client is an in-memory PostgREST stand-in passed in as the argument the
service already takes; nothing of ours is patched.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

from noctusai_lib.domain.real_estate.permuta import MODELO

from app.modules.permutas import service as svc

ORG = UUID("00000000-0000-4000-8000-0000000000bb")


class _Q:
    def __init__(self, db: "_Db", table: str):
        self.db, self.table, self.preds, self.op, self.payload = db, table, [], "select", None

    def select(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self.preds.append(lambda r, c=col, v=val: str(r.get(c)) == str(v))
        return self

    def neq(self, col, val):
        self.preds.append(lambda r, c=col, v=val: str(r.get(c)) != str(v))
        return self

    def in_(self, col, vals):
        vals = {str(v) for v in vals}
        self.preds.append(lambda r, c=col: str(r.get(c)) in vals)
        return self

    def upsert(self, rows, on_conflict=None):
        self.op, self.payload = "upsert", rows
        return self

    def delete(self):
        self.op = "delete"
        return self

    def execute(self):
        rows = self.db.rows.setdefault(self.table, [])
        if self.op == "upsert":
            rows.extend(self.payload)
            return SimpleNamespace(data=self.payload)
        hit = [r for r in rows if all(p(r) for p in self.preds)]
        if self.op == "delete":
            self.db.rows[self.table] = [r for r in rows if r not in hit]
        return SimpleNamespace(data=[dict(r) for r in hit])


class _Db:
    def __init__(self, **rows):
        self.rows = rows

    def schema(self, _s):
        return self

    def table(self, t):
        return _Q(self, t)


def _ativo(id_, codigo, tel):
    return {"id": id_, "org_id": str(ORG), "natureza": "imovel", "imovel_codigo": codigo,
            "status": "ativo", "proprietario_telefone": tel}


def _imovel(codigo, categoria, valor, bairro, cidade="Cotia"):
    return {"codigo": codigo, "org_id": str(ORG), "categoria": categoria, "valor_venda": valor,
            "bairro": bairro, "cidade": cidade, "uf": "SP"}


def _interesse(ativo_id, **kw):
    return {"id": f"i-{ativo_id}", "org_id": str(ORG), "ativo_id": ativo_id, "tipo": "imovel", **kw}


def _db():
    # casa  — R$1.98M house, owner wants an APARTMENT
    # apto  — R$1.20M apartment, owner wants a HOUSE IN A CONDOMINIUM
    # mansao — R$14M house, owner trades down to at most R$2M: no one here fits
    return _Db(
        permuta_ativos=[
            _ativo("casa", "C1", "11911110000"),
            _ativo("apto", "A1", "11922220000"),
            _ativo("mansao", "M1", "11933330000"),
        ],
        permuta_interesses=[
            _interesse("casa", tipo_imovel="Apartamento", valor_maximo=1_300_000),
            _interesse("apto", tipo_imovel="Casa em condomínio"),
            _interesse("mansao", tipo_imovel="Casa em condomínio", valor_maximo=2_000_000),
        ],
        imoveis=[
            _imovel("C1", "Casa em Condomínio", 1_980_000, "Pousada dos Bandeirantes - Km 23"),
            _imovel("A1", "Apartamento", 1_200_000, "Tamboré", cidade="Barueri"),
            _imovel("M1", "Casa em Condomínio", 14_000_000, "São Paulo 2"),
        ],
        permuta_matches=[],
    )


def test_troca_cruzada_e_persistida_com_justificativa():
    db = _db()
    r = svc.gerar_matches(db, ORG)

    gravados = db.rows["permuta_matches"]
    pares = {frozenset((m["ativo_origem_id"], m["ativo_destino_id"])) for m in gravados}
    assert frozenset(("casa", "apto")) in pares
    assert r["gravados"] == len(gravados)

    m = next(m for m in gravados if {m["ativo_origem_id"], m["ativo_destino_id"]} == {"casa", "apto"})
    assert m["etapa"] == "sugerido" and m["origem"] == "motor"
    assert m["detalhes"]["modelo"] == MODELO
    assert "tipo ✓ (Apartamento)" in m["justificativa"]


def test_teto_declarado_remove_o_par():
    """The house owner accepts at most R$1.3M; the R$14M house is out.

    The similarity engine ignored a ceiling with no floor and would have kept
    this pair on "same type, same state"."""
    db = _db()
    svc.gerar_matches(db, ORG)
    pares = {frozenset((m["ativo_origem_id"], m["ativo_destino_id"]))
             for m in db.rows["permuta_matches"]}
    assert frozenset(("casa", "mansao")) not in pares


def test_reporta_ausencia_de_semantica():
    db = _db()
    r = svc.gerar_matches(db, ORG)
    assert r["sem_semantica"] == r["encontrados"] > 0
