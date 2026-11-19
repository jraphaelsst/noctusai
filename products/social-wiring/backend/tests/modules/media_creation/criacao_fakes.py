"""In-memory stand-in for the schema-pinned admin client + the four definer RPCs of the criação pipeline.

Only the surface the criação ports use: ``table().select/insert/update/eq/in_/order/limit/execute`` and ``rpc().execute``.
The RPC bodies mirror the SQL of migrations 363 (``cs_criacao_passo_registrar``: forward-only status, the
``medicao_ausente`` rule, the step's event), 364/368 (S5's mover is faked by ``FakeSistema`` below; ), 365 (``cs_consentimento_voz_vigente``)
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


class FakeSistema:
    """S5's ``CriacaoMover`` over the FakeDb: the REAL transition matrix (``criacao_estado``), the card moves with their
    ``motivo`` / system actor, the intent-named events. (The real mover is pinned by ``test_criacao_stages``.)"""

    ATOR = "00000000-0000-0000-0000-00000000c0de"

    def __init__(self, db: FakeDb, org: str):
        self.db, self.org = db, org
        self.estados: list[tuple[str | None, str]] = []

    def _post(self, post_id):
        return next(r for r in self.db.rows("cs_posts") if r["id"] == post_id and r["org_id"] == self.org)

    def _estado(self, post, para, tipo=None, falha=None, dados=None):
        from app.modules.media_creation import criacao_estado as est

        de = post.get("criacao_estado")
        if not est.transicao_valida(de, para):
            raise RpcRefused(f"transicao_invalida {de}->{para}")
        post["criacao_estado"], post["falha_codigo"] = para, (falha if para == "falhou" else None)
        self.estados.append((de, para))
        ev = est.evento_da_entrada(para, tipo)
        if ev:
            self.db._evento(self.org, post["id"], ev, de, para, dados, self.ATOR)

    def _mover(self, post, papel, motivo):
        etapas = sorted((e for e in self.db.rows("pipeline_stages") if e["org_id"] == self.org), key=lambda e: e["posicao"])
        ids = [e["id"] for e in etapas]
        alvo = next(e for e in etapas if e["papel"] == papel)
        atual = post["etapa_id"]
        if atual == alvo["id"]:
            return
        for meio in etapas[ids.index(atual) + 1: ids.index(alvo["id"])]:
            self._uma(post, meio, "rota:pulado")
        self._uma(post, alvo, motivo)

    def _uma(self, post, etapa, motivo):
        self.db.tables.setdefault("pipeline_movimentos", []).append(
            {"entidade_id": post["id"], "de_etapa_id": post["etapa_id"], "para_etapa_id": etapa["id"], "motivo": motivo,
             "responsavel_id": self.ATOR})
        post["etapa_id"] = etapa["id"]
        self.db._evento(self.org, post["id"], "card_movido_automaticamente", None, etapa["id"], {"motivo": motivo}, self.ATOR)

    # the CriacaoMover surface the worker uses
    def entrar_em_criacao(self, post_id):
        post = self._post(post_id)
        self._mover(post, "criacao", "auto:criacao_enfileirada")
        if post.get("criacao_estado") in (None, "aguardando_aprovacao", "refinando", "cancelado"):
            self._estado(post, "aprovado")
        if post.get("criacao_estado") != "na_fila":
            self._estado(post, "na_fila", dados={"rota": post.get("criacao_rota") or "reel_narrado"})

    def iniciar_geracao(self, post_id):
        self._estado(self._post(post_id), "gerando")

    def progresso(self, post_id, **kw):
        self.estados.append(("progresso", kw.get("mensagem")))

    def concluir_geracao(self, post_id):
        post = self._post(post_id)
        self._estado(post, "aguardando_aprovacao_midia")
        self._mover(post, "aprovacao_midia", "auto:criacao_concluida")

    def falhar(self, post_id, *, codigo, mensagem):
        self._estado(self._post(post_id), "falhou", falha=codigo, dados={"mensagem": mensagem})
