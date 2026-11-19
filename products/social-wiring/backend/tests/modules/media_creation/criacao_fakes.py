"""In-memory stand-in for the schema-pinned admin client + the four definer RPCs of the criação pipeline.

Only the surface the criação ports use: ``table().select/insert/update/eq/in_/order/limit/execute`` and ``rpc().execute``.
The RPC bodies mirror the SQL of migrations 363 (``cs_criacao_passo_registrar``: forward-only status, the
``medicao_ausente`` rule, the step's event), 364/368 (``cs_post_criacao_projetar``), 365 (``cs_consentimento_voz_vigente``)
and 366 (``cs_criacao_cota_estado``). The SQL itself is replayed on a real Postgres in ``test_migration_cs_criacao*.py``;
this fake exists to run the PYTHON side end to end, and it refuses what the real SQL refuses.
"""
from __future__ import annotations

import copy
import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

RANK = {"pendente": 0, "em_andamento": 1, "concluido": 2, "falhou": 2, "cancelado": 2, "pulado": 2}
EVENTO_TIPOS = {
    "criacao_enfileirada", "passo_iniciado", "passo_concluido", "passo_falhou", "criacao_concluida",
    "card_movido_automaticamente", "cota_excedida", "midia_versao_criada",
}


class RpcRefused(Exception):
    """The SQL RAISEs (message = the exception text the function raises)."""


class _Q:
    def __init__(self, db: "FakeDb", table: str) -> None:
        self.db, self.t = db, table
        self._op, self._payload = "select", None
        self._filters: list[tuple[str, str, Any]] = []
        self._order: list[tuple[str, bool]] = []
        self._limit: int | None = None

    def select(self, *_a, **_k):
        self._op = "select"
        return self

    def insert(self, row):
        self._op, self._payload = "insert", row
        return self

    def update(self, values):
        self._op, self._payload = "update", values
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
        return self

    def order(self, col, desc=False):
        self._order.append((col, desc))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _match(self, row) -> bool:
        for kind, col, val in self._filters:
            if kind == "eq" and str(row.get(col)) != str(val) and row.get(col) != val:
                return False
            if kind == "in" and row.get(col) not in val:
                return False
        return True

    def execute(self):
        rows = self.db.tables.setdefault(self.t, [])
        if self._op == "insert":
            row = {"id": str(uuid.uuid4()), **copy.deepcopy(self._payload)}
            rows.append(row)
            return SimpleNamespace(data=[copy.deepcopy(row)])
        hits = [r for r in rows if self._match(r)]
        if self._op == "update":
            for r in hits:
                r.update(copy.deepcopy(self._payload))
            return SimpleNamespace(data=copy.deepcopy(hits))
        out = copy.deepcopy(hits)
        for col, desc in reversed(self._order):
            out.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
        if self._limit is not None:
            out = out[: self._limit]
        return SimpleNamespace(data=out)


class _Rpc:
    def __init__(self, fn, params):
        self.fn, self.params = fn, params

    def execute(self):
        return SimpleNamespace(data=self.fn(**self.params))


class FakeDb:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict]] = {}
        self.calls: list[str] = []
        self.rpc_log: list[tuple[str, dict]] = []
        self.limite_usd_mes = Decimal("15")
        self.cota_legivel = True

    def table(self, name: str) -> _Q:
        self.calls.append(name)
        return _Q(self, name)

    def rows(self, name: str) -> list[dict]:
        return self.tables.get(name, [])

    def rpc(self, name: str, params: dict | None = None) -> _Rpc:
        self.rpc_log.append((name, params or {}))
        return _Rpc(getattr(self, f"_rpc_{name}"), params or {})

    # -- cs_post_eventos --
    def _evento(self, org, post, tipo, de=None, para=None, dados=None, ator=None) -> None:
        if tipo not in EVENTO_TIPOS:
            raise RpcRefused("check_violation: cs_post_eventos.tipo")
        self.tables.setdefault("cs_post_eventos", []).append({
            "id": str(uuid.uuid4()), "org_id": org, "post_id": post, "tipo": tipo, "de": de, "para": para,
            "dados": dados or {}, "ator_id": ator,
        })

    # -- 363 --
    def _rpc_cs_criacao_passo_registrar(self, p_org, p_post, p_rodada, p_passo, p_status, p_dados):
        if p_status not in RANK:
            raise RpcRefused("status_invalido")
        post = next((r for r in self.rows("cs_posts") if r["id"] == p_post and r["org_id"] == p_org), None)
        if post is None:
            raise RpcRefused("post_nao_encontrado")
        for k in ("depende_de",):
            for d in p_dados.get(k, []):
                uuid.UUID(d)  # the column is uuid[]: a step NAME would be refused by Postgres
        if "job_id" in p_dados:
            uuid.UUID(p_dados["job_id"])
        jobs = self.tables.setdefault("cs_criacao_jobs", [])
        old = next((r for r in jobs if r["post_id"] == p_post and r["rodada"] == p_rodada and r["passo"] == p_passo), None)
        if old and old["status"] == p_status:
            return {"id": old["id"], "status": old["status"], "mudou": False}
        if old and RANK[p_status] <= RANK[old["status"]]:
            raise RpcRefused(f"transicao_invalida: {old['status']} -> {p_status}")
        row = old or {
            "id": str(uuid.uuid4()), "org_id": p_org, "post_id": p_post, "rodada": p_rodada, "passo": p_passo,
            "depende_de": [], "unidades": {}, "medicoes": {}, "resultado": {}, "nao_medido": [],
            "job_id": None, "vendor": None, "modelo": None, "request_id": None, "cpu_s": None, "custo_usd": None,
            "velocidade_render_x": None, "erro_codigo": None, "duracao_s": None, "terminado_em": None, "created_at": len(jobs),
        }
        row["status"] = p_status
        for k in ("depende_de", "job_id", "vendor", "modelo", "request_id", "cpu_s", "custo_usd", "velocidade_render_x",
                  "unidades", "medicoes", "resultado", "nao_medido"):
            if k in p_dados:
                row[k] = p_dados[k]
        row["erro_codigo"] = p_dados.get("erro_codigo", row["erro_codigo"]) if p_status == "falhou" else None
        if p_status in ("concluido", "falhou", "cancelado", "pulado"):
            row["terminado_em"] = len(jobs) + 1
        if p_status == "falhou" and not row["erro_codigo"]:
            raise RpcRefused("erro_obrigatorio")
        if p_status == "concluido" and (
            (row["custo_usd"] is None and "custo_usd" not in row["nao_medido"])
            or (row["cpu_s"] is None and "cpu_s" not in row["nao_medido"])
        ):
            raise RpcRefused("medicao_ausente")  # measured or declared nao_medido, never an estimate
        if not old:
            jobs.append(row)
        tipo = {"em_andamento": "passo_iniciado", "concluido": "passo_concluido", "falhou": "passo_falhou"}.get(p_status)
        if tipo:
            dados = {"passo": p_passo, "rodada": p_rodada, "erro_codigo": row["erro_codigo"]}
            self._evento(p_org, p_post, tipo, old["status"] if old else None, p_status, dados)
            if p_status == "falhou" and row["erro_codigo"] == "cota":
                self._evento(p_org, p_post, "cota_excedida", None, p_status, dados)
        return {"id": row["id"], "status": p_status, "mudou": True}

    # -- 368 --
    def _rpc_cs_post_criacao_projetar(self, p_org, p_post, p_estado, p_falha, p_eventos, p_somente_de):
        post = next((r for r in self.rows("cs_posts") if r["id"] == p_post and r["org_id"] == p_org), None)
        if post is None:
            raise RpcRefused("post_nao_encontrado")
        if p_estado == "falhou" and not p_falha:
            raise RpcRefused("falha_obrigatoria")
        old, falha = post.get("criacao_estado"), (p_falha if p_estado == "falhou" else None)
        if p_somente_de is not None and (old is None or old not in p_somente_de):
            return {"mudou": False, "estado": old}
        if old == p_estado and post.get("falha_codigo") == falha:
            return {"mudou": False, "estado": old}
        post["criacao_estado"], post["falha_codigo"] = p_estado, falha
        for ev in p_eventos or []:
            self._evento(p_org, p_post, ev["tipo"], old, p_estado, ev.get("dados"), ev.get("ator_id"))
        return {"mudou": True, "estado": p_estado, "de": old}

    # -- 365 --
    def _rpc_cs_consentimento_voz_vigente(self, p_org, p_marca, p_vendor, p_voice_id):
        for c in sorted(self.rows("cs_consentimentos_voz"), key=lambda r: r["created_at"], reverse=True):
            if (c["org_id"], c["marca_id"], c["vendor"], c["voice_id"], c["fase"]) == (
                p_org, p_marca, p_vendor, p_voice_id, "concedido"
            ) and not any(r.get("revoga_id") == c["id"] for r in self.rows("cs_consentimentos_voz")):
                return c["id"]
        return None

    # -- 366 --
    def _rpc_cs_criacao_cota_estado(self, p_org):
        if not self.cota_legivel:
            raise RpcRefused("cota ilegivel")
        gasto = sum(
            Decimal(str(r["custo_usd"])) for r in self.rows("cs_criacao_jobs")
            if r["org_id"] == p_org and r["status"] in ("concluido", "falhou") and r["custo_usd"] is not None
        )
        lim = self.limite_usd_mes
        return {"limite_usd_mes": str(lim), "gasto_usd_mes": str(gasto), "restante_usd": str(lim - gasto), "passos_sem_custo": 0}
