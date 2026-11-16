"""An in-memory :class:`ImportStore` for the loader tests. Its ``rpc`` emulates ONLY what the loader depends on from
migration 350 (provenance default ``admin``, ``id`` kept on a block, hash stamp, version bump, the coded refusals); the
real SQL is exercised on PGlite in ``test_estruturas_import_on_replay.py``."""
from __future__ import annotations

import uuid
from typing import Any, Iterable, Optional

from app.modules.media_creation.estruturas_tipos_bloco import NOME_OUTRO

from ._estruturas_import_fixtures import TIPOS_CATALOGO


class FakeApiError(Exception):
    def __init__(self, message: str, details: str = "", code: str = "P0001"):
        super().__init__({"message": message, "details": details, "code": code})
        self.message, self.details, self.code = message, details, code


class FakeStore:
    def __init__(self, *, optouts: Iterable[str] = (), limite_estrutura: Optional[int] = None):
        self._tipos = {n: str(uuid.uuid4()) for n in TIPOS_CATALOGO}
        self._optouts = set(optouts)
        self.perfis_: dict[str, str] = {}
        self.estruturas: dict[str, dict[str, Any]] = {}  # id -> row
        self.blocos: dict[str, list[dict[str, Any]]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.eventos_perfil: list[tuple[str, str]] = []
        self.perfil_nomes: dict[str, Optional[str]] = {}
        self.fail_with: dict[str, Exception] = {}

    # reads
    def tipos(self): return dict(self._tipos)
    def optouts(self, handles): return {h for h in handles if h in self._optouts}
    def perfis(self, handles): return {h: self.perfis_[h] for h in handles if h in self.perfis_}
    def total_perfis(self): return len(self.perfis_)

    def existentes(self, fonte_externa, refs):
        refs = set(refs)
        return {e["ref_externa"]: dict(e) for e in self.estruturas.values() if e["fonte_externa"] == fonte_externa and e["ref_externa"] in refs}

    def blocos_de(self, estrutura_id): return [dict(b) for b in self.blocos.get(estrutura_id, [])]

    # writes
    def criar_perfil(self, handle, nome, ator_id):
        pid = str(uuid.uuid4())
        self.perfis_[handle] = pid
        self.perfil_nomes[handle] = nome
        self.calls.append(("criar_perfil", {"handle": handle}))
        return pid

    def evento_perfil(self, perfil_id, handle, tipo, ator_id):
        self.eventos_perfil.append((handle, tipo))
        self.calls.append(("evento_perfil", {"handle": handle, "tipo": tipo}))

    def rpc(self, nome, params):
        self.calls.append((nome, params))
        if nome in self.fail_with:
            raise self.fail_with[nome]
        if nome == "cs_estrutura_criar":
            p = params["p"]
            eid = str(uuid.uuid4())
            self.estruturas[eid] = {
                "id": eid, "ref_externa": p["ref_externa"], "fonte_externa": p["fonte_externa"], "versao": 1, "status": p["status"],
                "fonte_hash": p["fonte_hash"], "formula_headline": p["formula_headline"], "formato": p["formato"], "objetivos": p["objetivos"],
                "formula_origem": p["formula_origem"], "formato_origem": p["formato_origem"], "objetivos_origem": p["objetivos_origem"],
            }
            self.blocos[eid] = [{"id": str(uuid.uuid4()), "ordem": i, **{k: v for k, v in b.items() if k != "id"}} for i, b in enumerate(p["blocos"], 1)]
            return {"id": eid, "versao": 1}
        eid = params["p_id"]
        row = self.estruturas[eid]
        if params["p_expected_versao"] != row["versao"]:
            raise FakeApiError("versao_desatualizada")
        if row["status"] == "arquivada":
            raise FakeApiError("estrutura_inativa")
        if nome == "cs_estrutura_substituir_blocos":
            novos = []
            for i, b in enumerate(params["p_blocos"]["blocos"], 1):
                antigo = next((x for x in self.blocos[eid] if x["id"] == b.get("id")), None)
                novos.append({"id": b.get("id") or str(uuid.uuid4()), "ordem": i, **{k: v for k, v in b.items() if k != "id"}} if antigo or not b.get("id") else b)
            mudou = [{k: v for k, v in x.items()} for x in novos] != self.blocos[eid]
            self.blocos[eid] = novos
            if mudou:
                row["versao"] += 1
            return {"id": eid, "versao": row["versao"], "alterada": mudou}
        if nome == "cs_estrutura_atualizar":
            patch = params["p_patch"]
            for k, v in patch.items():
                if not k.startswith("_"):
                    row[k] = v
            row["versao"] += 1
            return {"id": eid, "versao": row["versao"], "alterada": True}
        raise AssertionError(nome)

    def escritas(self) -> list[str]:
        return [n for n, _ in self.calls]
