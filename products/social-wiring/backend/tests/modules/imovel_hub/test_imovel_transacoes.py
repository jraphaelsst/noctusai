"""imovel_transacoes (migration 266) -- list + confirm / reject the proposed link.

PINS: admin-only on the TRUSTED role (member -> 403, nothing changes); confirm
needs a code that exists in `imovel_registry` (404 otherwise) and reports whether
it was a proposed candidate or a typed code; `pendente` is the only resolvable
state (409); reject clears any code; `confirmado` always carries a code.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from noctusai_lib.primitives.exceptions import AppException, NotFoundError

from app.modules.imovel_hub import transacoes_service as svc
from app.modules.imovel_hub.deps import get_imovel_hub_client
from tests.modules.imovel_hub.conftest import ORG_ID, auth, registry_row

ORG = UUID(ORG_ID)
ATOR = uuid4()
BASE = "/api/imovel-transacoes"


def transacao(**extra) -> dict:
    row = {
        "id": str(uuid4()), "org_id": ORG_ID, "codigo_canonical": None, "processo_numero": "782",
        "tipo": "venda", "valor_transacao": "2600000.00", "data_transacao": "2026-01-20",
        "financiamento": True, "fgts": False, "permuta": False, "n_parcelas": 3,
        "fonte": "contrato_d4sign", "fonte_ref": "782", "vinculo_status": "pendente",
        "vinculo_candidatos": [{"codigo": "CA0001", "pontos": 80, "forca": "forte", "evidencias": ["matricula"]}],
        "confirmado_por": None, "confirmado_em": None, "observacoes": None,
    }
    row.update(extra)
    return row


def seed(scoped, *linhas, registry=("CA0001", "CA0002")):
    scoped.table("imovel_transacoes")._data.extend(linhas)
    scoped.table("imovel_registry")._data.extend(registry_row(c) for c in registry)


def dado(scoped, tid) -> dict:
    return next(r for r in scoped.table("imovel_transacoes")._data if r["id"] == tid)


class TestService:
    def test_confirma_candidato(self, scoped):
        t = transacao()
        seed(scoped, t)
        out = svc.confirmar(scoped, ORG, t["id"], "ca0001", ATOR)
        assert out["origem_codigo"] == "candidato"
        d = dado(scoped, t["id"])
        assert d["vinculo_status"] == "confirmado" and d["codigo_canonical"] == "CA0001"
        assert d["confirmado_por"] == str(ATOR) and d["confirmado_em"]

    def test_confirma_codigo_digitado_existente(self, scoped):
        t = transacao()
        seed(scoped, t)
        assert svc.confirmar(scoped, ORG, t["id"], "CA0002", ATOR)["origem_codigo"] == "digitado"

    def test_codigo_fora_do_registry_leva_404_e_nada_muda(self, scoped):
        t = transacao()
        seed(scoped, t)
        with pytest.raises(NotFoundError):
            svc.confirmar(scoped, ORG, t["id"], "ZZ9999", ATOR)
        assert dado(scoped, t["id"])["vinculo_status"] == "pendente"
        assert dado(scoped, t["id"])["codigo_canonical"] is None

    @pytest.mark.parametrize("status", ["confirmado", "rejeitado"])
    def test_so_pendente_resolve(self, scoped, status):
        t = transacao(vinculo_status=status, codigo_canonical="CA0001" if status == "confirmado" else None)
        seed(scoped, t)
        for fn in (lambda: svc.confirmar(scoped, ORG, t["id"], "CA0002", ATOR), lambda: svc.rejeitar(scoped, ORG, t["id"], ATOR)):
            with pytest.raises(AppException) as exc:
                fn()
            assert exc.value.code == "transacao_ja_resolvida" and exc.value.status_code == 409

    def test_rejeita_limpa_codigo(self, scoped):
        t = transacao()
        seed(scoped, t)
        svc.rejeitar(scoped, ORG, t["id"], ATOR)
        d = dado(scoped, t["id"])
        assert d["vinculo_status"] == "rejeitado" and d["codigo_canonical"] is None and d["confirmado_por"] == str(ATOR)

    def test_isola_por_org(self, scoped):
        t = transacao(org_id=str(uuid4()))
        seed(scoped, t)
        with pytest.raises(NotFoundError):
            svc.rejeitar(scoped, ORG, t["id"], ATOR)

    def test_lista_filtra_por_status_e_valida(self, scoped):
        seed(scoped, transacao(), transacao(vinculo_status="rejeitado"), transacao(org_id=str(uuid4())))
        assert len(svc.listar(scoped, ORG)["items"]) == 2
        only = svc.listar(scoped, ORG, vinculo_status="pendente")["items"]
        assert [r["vinculo_status"] for r in only] == ["pendente"]
        with pytest.raises(AppException) as exc:
            svc.listar(scoped, ORG, vinculo_status="qualquer")
        assert exc.value.status_code == 422


class TestRotasAdmin:
    def test_membro_leva_403_estrito_em_tudo_e_nada_muda(self, member_client):
        scoped = get_imovel_hub_client()
        t = transacao()
        seed(scoped, t)
        assert member_client.get(BASE, headers=auth()).status_code == 403
        assert member_client.post(f"{BASE}/{t['id']}/confirmar", json={"codigo": "CA0001"}, headers=auth()).status_code == 403
        assert member_client.post(f"{BASE}/{t['id']}/rejeitar", headers=auth()).status_code == 403
        assert dado(scoped, t["id"])["vinculo_status"] == "pendente"

    def test_admin_lista_confirma_e_rejeita(self, admin_client):
        scoped = get_imovel_hub_client()
        a, b = transacao(), transacao(fonte_ref="783")
        seed(scoped, a, b)
        r = admin_client.get(BASE, params={"vinculo_status": "pendente"}, headers=auth())
        assert r.status_code == 200 and len(r.json()["items"]) == 2

        r = admin_client.post(f"{BASE}/{a['id']}/confirmar", json={"codigo": "CA0001"}, headers=auth())
        assert r.status_code == 200, r.text
        assert r.json()["origem_codigo"] == "candidato" and dado(scoped, a["id"])["confirmado_por"]

        r = admin_client.post(f"{BASE}/{a['id']}/rejeitar", headers=auth())
        assert r.status_code == 409 and r.json()["error"]["code"] == "transacao_ja_resolvida"

        r = admin_client.post(f"{BASE}/{b['id']}/rejeitar", headers=auth())
        assert r.status_code == 200 and dado(scoped, b["id"])["vinculo_status"] == "rejeitado"

    def test_corpo_estrito_rejeita_campo_extra(self, admin_client):
        scoped = get_imovel_hub_client()
        t = transacao()
        seed(scoped, t)
        r = admin_client.post(f"{BASE}/{t['id']}/confirmar", json={"codigo": "CA0001", "valor": 1}, headers=auth())
        assert r.status_code == 422
        assert dado(scoped, t["id"])["vinculo_status"] == "pendente"
