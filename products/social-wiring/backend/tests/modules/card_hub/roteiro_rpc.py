"""A Python MIRROR of `social_wiring.roteiro_gerar` (migration 338) for the HTTP/service tests over the mock client.

The mock cannot run a transaction, so the SQL itself (the guards, the status flip, the lead link, the atomic rollback)
is proven on a real Postgres by `tests/test_migration_338_roteiro_ciclo.py`. This mirror only lets the Python layers
(routes, typed errors, `permissoes`, the funnel step, the feedback flow) be exercised end to end against the mock; it
follows the SQL line by line and is deliberately small. If the two ever disagree, the PGlite suite is the authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import uuid4


class _Result:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def execute(self) -> Any:
        return SimpleNamespace(data=self._payload, count=None)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows(mock: Any, table: str, **eq: Any) -> list[dict]:
    q = mock.table(table).select("*")
    for k, v in eq.items():
        q = q.eq(k, v)
    return [dict(r) for r in (q.execute().data or [])]


def roteiro_gerar(mock: Any, p: dict) -> dict:
    org, rid, uid = str(p["p_org_id"]), str(p["p_roteiro_id"]), p.get("p_user_id")
    rows = [r for r in _rows(mock, "roteiros", id=rid, org_id=org) if not r.get("deleted_at")]
    if not rows:
        return {"status": "recusado", "code": "nao_encontrado"}
    r = rows[0]
    if r.get("status") == "gerado":
        return {"status": "recusado", "code": "roteiro_ja_gerado"}
    visitas = [v for v in _rows(mock, "visitas", roteiro_id=rid, org_id=org) if not v.get("deleted_at")]
    if not visitas:
        return {"status": "recusado", "code": "roteiro_sem_imoveis"}
    if not r.get("data_visita"):
        return {"status": "recusado", "code": "roteiro_sem_data"}

    agora = _now()
    mock.table("roteiros").update(
        {"status": "gerado", "gerado_em": agora, "gerado_por": uid, "updated_at": agora}
    ).eq("id", rid).execute()

    criados = preenchidos = 0
    atendimento = next(iter(_rows(mock, "atendimentos", id=str(r["atendimento_id"]), org_id=org)), None)
    if atendimento and atendimento.get("cliente_id"):
        cliente = str(atendimento["cliente_id"])
        lead, meta = atendimento.get("lead_id"), atendimento.get("meta_ads_lead_id")
        existentes = _rows(mock, "cliente_imovel_interesses", cliente_id=cliente)
        for v in visitas:
            do_par = [i for i in existentes if i["codigo"] == v["codigo"]]
            vivas = [i for i in do_par if not i.get("deleted_at")]
            if vivas:
                i = vivas[0]
                if (lead or meta) and not i.get("lead_id") and not i.get("meta_ads_lead_id"):
                    mock.table("cliente_imovel_interesses").update(
                        {"lead_id": lead, "meta_ads_lead_id": meta}
                    ).eq("id", i["id"]).execute()
                    preenchidos += 1
            elif not do_par:
                mock.table("cliente_imovel_interesses").insert(
                    {
                        "id": str(uuid4()), "org_id": org, "cliente_id": cliente, "codigo": v["codigo"],
                        "origem": "roteiro", "lead_id": lead, "meta_ads_lead_id": meta,
                        "created_by": uid, "created_at": agora, "deleted_at": None,
                    }
                ).execute()
                criados += 1
    return {"status": "ok", "interesses_criados": criados, "interesses_preenchidos": preenchidos}


def instalar(mock: Any) -> Any:
    """Route `rpc("roteiro_gerar", ...)` on `mock` to the mirror; every other RPC keeps the mock's own behaviour."""
    original = mock.rpc

    def rpc(name: str, params: Any = None) -> Any:
        if name == "roteiro_gerar":
            p = dict(params or {})
            mock.rpc_calls.append((name, p))
            return _Result(roteiro_gerar(mock, p))
        return original(name, params)

    mock.rpc = rpc
    return mock
