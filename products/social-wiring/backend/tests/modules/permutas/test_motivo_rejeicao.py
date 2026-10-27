"""Rejection reasons on permuta matches: required on reject, cleared on leave.

The reasons are the swap scorer's tuning labels. In-memory PostgREST stand-in
passed in as the client argument; nothing of ours is patched.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from noctusai_lib.testing.migrations import migration_sql
from noctusai_lib.primitives.exceptions import ValidationError_ as ValidationError

from app.modules.permutas import service as svc
from app.modules.permutas.router import router

ORG = UUID("00000000-0000-4000-8000-0000000000bb")
MID = UUID("00000000-0000-4000-8000-0000000000cc")
USER = UUID("00000000-0000-4000-8000-0000000000dd")
SQL = migration_sql(Path(__file__).resolve().parents[3] / "migrations", "permuta_matches_motivo_rejeicao")


class _Q:
    def __init__(self, db, table):
        self.db, self.table, self.preds, self.patch = db, table, [], None

    def select(self, *_a, **_k): return self
    def limit(self, *_a): return self

    def update(self, patch):
        self.patch = patch
        return self

    def eq(self, col, val):
        self.preds.append(lambda r, c=col, v=val: str(r.get(c)) == str(v))
        return self

    def execute(self):
        hit = [r for r in self.db.rows[self.table] if all(p(r) for p in self.preds)]
        if self.patch is not None:
            for r in hit:
                r.update(self.patch)
        return SimpleNamespace(data=[dict(r) for r in hit])


class _Db:
    def __init__(self, rows):
        self.rows = {"permuta_matches": rows}

    def schema(self, _s): return self
    def table(self, t): return _Q(self, t)


def _db(etapa="sugerido", **extra):
    return _Db([{"id": str(MID), "org_id": str(ORG), "etapa": etapa, **extra}])


def _move(db, etapa, **kw):
    return svc.atualizar_etapa(db, ORG, MID, etapa=etapa, user_id=USER, **kw)


def test_rejeitar_sem_motivo_e_recusado():
    with pytest.raises(ValidationError, match="Informe o motivo da rejeição."):
        _move(_db(), "rejeitado")


def test_motivo_invalido_e_recusado():
    with pytest.raises(ValidationError, match="Motivo de rejeição inválido."):
        _move(_db(), "rejeitado", motivo_rejeicao="porque_sim")


def test_outro_exige_detalhe():
    for detalhe in (None, "   "):
        with pytest.raises(ValidationError, match="Descreva o motivo da rejeição."):
            _move(_db(), "rejeitado", motivo_rejeicao="outro", motivo_rejeicao_detalhe=detalhe)


def test_lado_invalido_e_recusado():
    with pytest.raises(ValidationError):
        _move(_db(), "rejeitado", motivo_rejeicao="valor", motivo_lado="ninguem")


def test_rejeicao_valida_persiste_os_tres_campos_e_carimba():
    db = _db()
    out = _move(db, "rejeitado", motivo_rejeicao="outro",
                motivo_rejeicao_detalhe="  dono viajou  ", motivo_lado="ambos")
    assert out["etapa"] == "rejeitado"
    assert out["motivo_rejeicao"] == "outro"
    assert out["motivo_rejeicao_detalhe"] == "dono viajou"
    assert out["motivo_lado"] == "ambos"
    assert out["decidido_por"] == str(USER) and out["decidido_em"]


def test_detalhe_vazio_vira_none_e_lado_e_opcional():
    out = _move(_db(), "rejeitado", motivo_rejeicao="valor", motivo_rejeicao_detalhe="  ")
    assert out["motivo_rejeicao_detalhe"] is None and out["motivo_lado"] is None


@pytest.mark.parametrize("campo", ["motivo_rejeicao", "motivo_rejeicao_detalhe", "motivo_lado"])
def test_motivo_com_etapa_nao_rejeitada_e_recusado(campo):
    valor = "valor" if campo == "motivo_rejeicao" else "origem" if campo == "motivo_lado" else "x"
    with pytest.raises(ValidationError, match="Motivo só se aplica a uma rejeição."):
        _move(_db(), "avaliacao", **{campo: valor})


def test_sair_de_rejeitado_limpa_o_motivo():
    db = _db("rejeitado", motivo_rejeicao="valor", motivo_rejeicao_detalhe="d", motivo_lado="origem")
    out = _move(db, "avaliacao")
    assert out["etapa"] == "avaliacao"
    assert out["motivo_rejeicao"] is None
    assert out["motivo_rejeicao_detalhe"] is None
    assert out["motivo_lado"] is None


def test_match_fields_devolvem_as_colunas_novas():
    for col in ("motivo_rejeicao", "motivo_rejeicao_detalhe", "motivo_lado"):
        assert col in svc.MATCH_FIELDS.split(",")


def test_vocabulario_igual_ao_check_da_migracao():
    sql = SQL
    bloco = re.search(r"CHECK \(motivo_rejeicao IN \((.*?)\)\)", sql, re.S)
    assert bloco, "CHECK de motivo_rejeicao não encontrado na migração"
    no_sql = re.findall(r"'([a-z_]+)'", bloco.group(1))
    assert no_sql == [m["codigo"] for m in svc.MOTIVOS_REJEICAO]
    assert [m["codigo"] for m in svc.MOTIVOS_REJEICAO if m["exige_detalhe"]] == ["outro"]


def test_rota_motivos_declarada_antes_de_ativo_id():
    paths = [getattr(r, "path", "") for r in router.routes]
    assert paths.index("/api/permutas/motivos-rejeicao") < paths.index("/api/permutas/{ativo_id}")


def test_motivos_rejeicao_sem_autenticacao_e_401(anon_client):
    resp = anon_client.get("/api/permutas/motivos-rejeicao")
    assert resp.status_code == 401, resp.text


def test_motivos_rejeicao_autenticado(client):
    resp = client.get("/api/permutas/motivos-rejeicao")
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"][0] == {
        "codigo": "valor", "rotulo": "Valor / diferença incompatível", "exige_detalhe": False,
    }


def test_validacao_vira_http_400(client):
    """ValidationError must be the app exception (400), not pydantic's (500)."""
    from app.dependencies import get_user_client
    from app.main import app

    app.dependency_overrides[get_user_client] = lambda *_a, **_k: _db()
    try:
        resp = client.patch(f"/api/permutas/matches/{MID}", json={"etapa": "rejeitado"})
    finally:
        app.dependency_overrides.pop(get_user_client, None)
    assert resp.status_code == 400, resp.text
