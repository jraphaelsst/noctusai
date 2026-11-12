"""``noctus.agents.content`` against a FAKE HTTP SERVER (a real loopback ``http.server`` speaking the subset of
the agents Studio API the tool uses). Skill/prompt text below is TEST DATA, written to a temp dir that is not
a git work tree."""
from __future__ import annotations

import json
import re
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

MCP_ROOT = Path(__file__).resolve().parents[1]
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

from tools.noctus.agents import content as C  # noqa: E402

TOKEN = "pk_content_secret_value"


class FakeAgents:
    """In-memory state + request log for one test."""

    def __init__(self) -> None:
        self.log: list[tuple[str, str, dict | None, str | None]] = []
        self.draft_id = str(uuid.uuid4())
        self.config = {"provider": "anthropic", "model": "sonnet", "effort": "medium", "max_turns": 8, "idioma": "pt-BR",
                       "tool_policy": {"web_search": True, "knowledge": True}, "notas": None}
        self.secoes: list[dict] = [{"chave": "persona", "titulo": "Quem", "ordem": 1, "conteudo": "velho", "ativo": True}]
        self.textos: list[dict] = [{"chave": "a.b", "conteudo": "um"}, {"chave": "a.c", "conteudo": "dois"}]
        self.ferramentas: list[dict] = []
        self.decisoes: list[dict] = []
        self.specs: list[dict] = []
        self.skills: dict[str, dict] = {}  # chave -> {nome, descricao, versoes: [ {id, versao, status, ...} ]}
        self.casos: list[dict] = [{"id": str(uuid.uuid4()), "slug": "juiz-1", "suite": "comportamento", "titulo": "J",
                                   "entrada": "e", "k": 3, "roteiro": None, "asserts": None, "tags": [], "ativo": True}]
        self.regras: dict[str, dict] = {r: {"regra": r, "ativo": True, "politica": "registrar", "parametros": {}}
                                        for r in ("vazamento_prompt", "termina_sem_pergunta")}
        self.pins: dict[str, dict] = {}
        self.padroes: list[str] = ["imob-lead"]
        self.padrao_novo_versoes: list[dict] = []
        self.padrao_versoes: list[dict] = [{
            "id": str(uuid.uuid4()), "versao": 1, "status": "publicada", "notas": None, "publicada_em": "2026-01-01T00:00:00Z",
            "criterios": [{"chave": "operacao", "grupo": "prontidao", "rotulo": "Operacao", "descricao_modelo": "d", "tipo": "enum",
                           "opcoes": [{"valor": "compra", "rotulo": "", "descricao_modelo": "", "sinonimos": []}],
                           "unidade": None, "sensivel": None, "pontuacao": {}, "ordem": 1, "ativo": True,
                           "eixo": None, "escopo": None, "validade_dias": None}],
            "estagios": [], "parametros": {"minimo_para_ofertar": {"todos": []}, "lote_ofertas": 3, "score_max": 100,
                                           "eixos": {}, "pedir_identificacao_quando": None},
        }]

    def writes(self) -> list[tuple[str, str]]:
        return [(m, p) for m, p, _b, _a in self.log if m != "GET"]


def _handler(state: FakeAgents):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silence
            pass

        def _send(self, code: int, data=None):
            raw = json.dumps(data).encode() if data is not None else b""
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _err(self, code, key, detail="erro"):
            self._send(code, {"detail": {"detail": detail, "code": key}})

        def _go(self, method: str):
            body = None
            n = int(self.headers.get("Content-Length") or 0)
            if n:
                body = json.loads(self.rfile.read(n))
            state.log.append((method, self.path, body, self.headers.get("Authorization")))
            if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                return self._err(401, "unauthorized")
            if self.path == "/boom":
                return self._err(500, "boom", f"falhou com {TOKEN}")
            return self._route(method, self.path, body)

        do_GET = lambda self: self._go("GET")  # noqa: E731
        do_PUT = lambda self: self._go("PUT")  # noqa: E731
        do_POST = lambda self: self._go("POST")  # noqa: E731
        do_PATCH = lambda self: self._go("PATCH")  # noqa: E731
        do_DELETE = lambda self: self._go("DELETE")  # noqa: E731

        def _geracao_route(self, m: str, path: str, b):
            """The S3a subset: definition config + generation runs (what the tool calls)."""
            if path == "/api/studio/plataforma/agents/novo" and m in ("GET", "PATCH"):
                return self._send(200, {"key": "novo", "papel": (b or {}).get("papel"), "runtime": "llm"})
            if path.endswith("/grants"):
                if m == "POST":
                    return self._send(201, {"key": "julia", "instanciavel": False, "org_ids": [b["org_id"]], "created": True})
                return self._send(200, {"key": "julia", "instanciavel": False, "org_ids": [], "created": None})
            if m == "POST" and path.endswith("/geracoes"):
                if "/julia/" not in path:
                    return self._err(404, "agente_nao_encontrado")
                return self._send(202, {"id": "11111111-1111-4111-8111-111111111111", "status": "pendente", "agent_key": "julia"})
            if m == "GET" and path.endswith("/geracoes"):
                return self._send(200, {"items": [{"id": "11111111-1111-4111-8111-111111111111", "status": "concluida"}]})
            if m == "GET" and "/geracoes/" in path:
                return self._send(200, {"id": path.rsplit("/", 1)[1], "status": "executando", "areas": []})
            return self._err(404, "nao_encontrado")

        def _evals_route(self, m: str, path: str, b):
            """The eval-loop gate subset (contract eval-loop-gate-contract.md)."""
            lid = "22222222-2222-4222-8222-222222222222"
            if m == "POST" and path.endswith("/evals/loops"):
                return self._send(201, {"id": lid, "suite": b["suite"], "status": "ativo", "rodadas_planejadas": b.get("rodadas_planejadas")})
            if m == "GET" and "/evals/loops" in path and path.split("?")[0].endswith("/loops"):
                return self._send(200, {"items": [{"id": lid, "status": "ativo", "q": path.partition("?")[2]}]})
            if m == "GET" and path.endswith(f"/evals/loops/{lid}"):
                return self._send(200, {"id": lid, "status": "ativo", "rodadas": []})
            if m == "POST" and path.endswith(f"/evals/loops/{lid}/stop"):
                return self._send(200, {"id": lid, "status": "parado", "motivo_parada": "parado_manualmente"})
            if m == "POST" and path.endswith("/evals/runs"):
                if b["loop_id"] == "33333333-3333-4333-8333-333333333333":
                    return self._send(409, {"detail": {"code": "rodada_em_aberto", "detail": "ha uma rodada aberta"}})
                return self._send(202, {"id": "44444444-4444-4444-8444-444444444444", "status": "executando"})
            if m == "POST" and "/draft/mecanismo-runs" in path:
                return self._send(202, {"run_id": "55555555-5555-4555-8555-555555555555", "q": path.partition("?")[2]})
            if m == "GET" and "/evals/runs/" in path:
                return self._send(200, {"id": path.rsplit("/", 1)[1], "status": "concluida",
                                        "resultados": [{"saida": "x", "notas_juiz": [], "veredito": "passou"}]})
            if m == "GET" and "/mecanismo-runs/" in path:
                return self._send(200, {"id": path.rsplit("/", 1)[1], "status": "concluida", "casos": []})
            return self._err(404, "nao_encontrado")

        def _route(self, m: str, path: str, b):
            A = r"/api/studio/agents/julia"
            if path.startswith("/api/studio/plataforma/agents/") or "/geracoes" in path:
                return self._geracao_route(m, path, b)
            if m == "POST" and path == "/api/studio/plataforma/agents":
                return self._send(201, {"id": str(uuid.uuid4()), "key": b["key"], "definition_scope": "plataforma", "conteudo_modo": "linhas"})
            mo = re.fullmatch(r"/api/studio/agents/([A-Za-z0-9_.-]+)", path)
            if m == "DELETE" and mo:
                if mo.group(1) == "publicada":
                    return self._send(409, {"code": "publicado", "message": "tem versão publicada", "detail": "tem versão publicada"})
                if mo.group(1) == "sem-escopo":
                    return self._send(403, {"code": "scope_missing", "detail": "Missing scope(s): studio:agent-delete"})
                return self._send(204)
            if m == "GET" and path == f"{A}/draft":
                return self._send(200, {"id": state.draft_id, "secoes": state.secoes, **state.config})
            if m == "PATCH" and path == f"{A}/draft":
                state.config.update(b)
                return self._send(200, {"id": state.draft_id, **state.config})
            sets = {"sections": "secoes", "textos": "textos", "ferramentas": "ferramentas", "decisoes": "decisoes", "specs": "specs"}
            mo = re.fullmatch(rf"{A}/versions/{state.draft_id}/(textos|ferramentas|decisoes|specs)", path)
            if m == "GET" and mo:
                return self._send(200, {"version_id": state.draft_id, "itens": getattr(state, mo.group(1))})
            mo = re.fullmatch(rf"{A}/draft/(sections|textos|ferramentas|decisoes|specs)", path)
            if m == "PUT" and mo:
                key = "secoes" if mo.group(1) == "sections" else "itens"
                setattr(state, sets[mo.group(1)], b[key])
                return self._send(200, {"ok": True})
            # skill library
            if m == "GET" and path == "/api/skills-biblioteca":
                return self._send(200, {"items": [
                    {"id": "x", "chave": k, "nome": v["nome"], "descricao": v["descricao"],
                     "versao_publicada": next((x["versao"] for x in v["versoes"] if x["status"] == "publicada"), None),
                     "tem_rascunho": any(x["status"] == "rascunho" for x in v["versoes"])}
                    for k, v in sorted(state.skills.items())]})
            if m == "POST" and path == "/api/skills-biblioteca":
                state.skills[b["chave"]] = {"nome": b["nome"], "descricao": b.get("descricao"), "versoes": []}
                return self._send(201, {"chave": b["chave"]})
            mo = re.fullmatch(r"/api/skills-biblioteca/([a-z0-9-]+)/versoes", path)
            if mo and mo.group(1) in state.skills:
                sk = state.skills[mo.group(1)]
                if m == "GET":
                    return self._send(200, {"items": [{k: x[k] for k in ("id", "versao", "status")} for x in sk["versoes"]]})
                if m == "POST":
                    src = next((x for x in sk["versoes"] if x["id"] == b.get("copiar_de")), None)
                    v = {"id": str(uuid.uuid4()), "versao": len(sk["versoes"]) + 1, "status": "rascunho",
                         "descricao_modelo": src["descricao_modelo"] if src else "", "corpo": src["corpo"] if src else "",
                         "arquivos": list(src["arquivos"]) if src else []}
                    sk["versoes"].append(v)
                    return self._send(201, v)
            mo = re.fullmatch(r"/api/skills-biblioteca/([a-z0-9-]+)", path)
            if m == "PATCH" and mo:
                state.skills[mo.group(1)].update(b)
                return self._send(200, {})
            mo = re.fullmatch(r"/api/skills-biblioteca/versoes/([0-9a-f-]+)(/arquivos/(.+))?", path)
            if mo:
                v = next(x for s in state.skills.values() for x in s["versoes"] if x["id"] == mo.group(1))
                if m == "GET":
                    return self._send(200, v)
                if m == "PATCH":
                    assert v["status"] == "rascunho"
                    v.update(b)
                    return self._send(200, v)
                if m == "PUT":
                    assert v["status"] == "rascunho"
                    v["arquivos"] = [a for a in v["arquivos"] if a["caminho"] != mo.group(3)] + [{"caminho": mo.group(3), **b}]
                    return self._send(200, v)
            # eval cases
            if path == f"{A}/evals/cases":
                if m == "GET":
                    return self._send(200, {"items": state.casos})
                if m == "POST":
                    caso = {"id": str(uuid.uuid4()), "tags": [], "ativo": True, "k": 3, **b}
                    state.casos.append(caso)
                    return self._send(201, caso)
            mo = re.fullmatch(rf"{A}/evals/cases/([0-9a-f-]+)", path)
            if mo and m == "PATCH":
                caso = next(c for c in state.casos if c["id"] == mo.group(1))
                caso.update(b)
                return self._send(200, caso)
            # eval consolidation (criticality + declared dependencies, both suites)
            if m == "GET" and path == f"{A}/evals/consolidacao":
                return self._send(200, {"items": [
                    {"case_id": c["id"], "slug": c["slug"], "criticidade": c.get("criticidade", "normal"),
                     "depende_de": c.get("depende_de")} for c in state.casos]})
            mo = re.fullmatch(rf"{A}/evals/cases/([0-9a-f-]+)/consolidacao", path)
            if mo and m == "PUT":
                caso = next(c for c in state.casos if c["id"] == mo.group(1))
                caso.update(b)
                return self._send(200, caso)
            # conformance rules
            if m == "GET" and path == f"{A}/conformidade/regras":
                return self._send(200, {"items": list(state.regras.values())})
            mo = re.fullmatch(rf"{A}/conformidade/regras/([a-z_]+)", path)
            if mo and m == "PUT" and mo.group(1) in state.regras:
                state.regras[mo.group(1)].update({k: v for k, v in b.items() if v is not None})
                return self._send(200, state.regras[mo.group(1)])
            if "/evals/" in path or "/mecanismo-runs" in path:
                return self._evals_route(m, path, b)
            # readiness + re-pin (the agents API: GET .../prontidao, POST .../draft/skills-biblioteca/atualizar)
            if m == "GET" and path == f"{A}/prontidao":
                return self._send(200, {
                    "agent_key": "julia", "version_id": state.draft_id, "hash": "sha256:x", "pronto_para_publicar": False,
                    "bloqueantes": 1, "avisos": 0, "itens": [{
                        "codigo": "eval_juiz_sem_execucao", "grupo": "avaliacao", "severidade": "bloqueante",
                        "mensagem": "Nenhuma avaliação.", "acao_sugerida": "Rode.", "recusa_publicacao": "eval_required",
                        "detalhe": None}]})
            if m == "POST" and path == f"{A}/draft/skills-biblioteca/atualizar":
                movidas = [{"skill": k, "de": p["versao"], "para": p["nova_versao"]} for k, p in state.pins.items() if p.get("nova_versao")]
                for mv in movidas:
                    state.pins[mv["skill"]].update({"versao": mv["para"], "nova_versao": None})
                return self._send(200, {"version_id": state.draft_id, "atualizadas": movidas,
                                        "ja_atuais": [k for k in state.pins if k not in {mv["skill"] for mv in movidas}],
                                        "items": list(state.pins.values())})
            # pins
            if m == "GET" and path == f"{A}/draft/skills-biblioteca":
                return self._send(200, {"version_id": state.draft_id, "items": list(state.pins.values())})
            mo = re.fullmatch(rf"{A}/draft/skills-biblioteca/([a-z0-9-]+)", path)
            if mo and m == "PUT":
                state.pins[mo.group(1)] = {"skill": mo.group(1), "versao": b.get("versao") or 1, "nova_versao": None,
                                           "obrigatoria_para": b["obrigatoria_para"], "ordem": b["ordem"]}
                return self._send(200, {})
            if mo and m == "DELETE":
                state.pins.pop(mo.group(1), None)
                return self._send(200, {})
            # qualification standard
            if path == "/api/qualificacao/padroes":
                if m == "GET":
                    return self._send(200, {"items": [{"id": "p", "chave": k, "nome": k, "descricao": None} for k in state.padroes]})
                if m == "POST":
                    if b["chave"] in state.padroes:
                        return self._err(409, "padrao_ja_existe")
                    state.padroes.append(b["chave"])
                    state.padrao_novo_versoes = []
                    return self._send(201, {"id": "p", "chave": b["chave"], "nome": b["nome"], "descricao": b.get("descricao")})
            if path == "/api/qualificacao/padroes/novo-padrao/versoes" and "novo-padrao" in state.padroes:
                if m == "GET":
                    return self._send(200, {"items": state.padrao_novo_versoes})
                if m == "POST":
                    v = {"id": str(uuid.uuid4()), "versao": 1, "status": "rascunho", "notas": b.get("notas"), "publicada_em": None}
                    state.padrao_novo_versoes.append(v)
                    return self._send(201, v)
            if path == "/api/qualificacao/padroes/imob-lead/versoes":
                if m == "GET":
                    return self._send(200, {"items": [{k: x[k] for k in ("id", "versao", "status", "notas", "publicada_em")}
                                                      for x in state.padrao_versoes]})
                if m == "POST":
                    src = next(x for x in state.padrao_versoes if x["id"] == b["copiar_de"])
                    novo = {**json.loads(json.dumps(src)), "id": str(uuid.uuid4()), "versao": len(state.padrao_versoes) + 1, "status": "rascunho"}
                    state.padrao_versoes.append(novo)
                    return self._send(201, novo)
            if path == "/api/qualificacao/padroes/nada/versoes":
                return self._err(404, "not_found")
            mo = re.fullmatch(r"/api/qualificacao/versoes/([0-9a-f-]+)(?:/(criterios|estagios)/([a-z_]+)|/parametros)?", path)
            if mo:
                v = next(x for x in state.padrao_versoes if x["id"] == mo.group(1))
                if m == "GET":
                    return self._send(200, v)
                assert v["status"] == "rascunho", "the tool must write into a DRAFT"
                if mo.group(2):
                    rows = [r for r in v[mo.group(2)] if r["chave"] != mo.group(3)]
                    v[mo.group(2)] = rows + [{"chave": mo.group(3), **b}]
                else:
                    v["parametros"] = b
                return self._send(200, v)
            return self._err(404, "no_route", f"{m} {path}")

    return H


@pytest.fixture
def srv():
    state = FakeAgents()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _handler(state))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    state.url = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        yield state
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv(C.ENV_TOKEN, TOKEN)
    monkeypatch.delenv(C.ENV_URL, raising=False)
    monkeypatch.setenv("NOCTUS_AGENTS_ENV_FILE", str(tmp_path / "none.env"))


@pytest.fixture
def private(tmp_path_factory):
    """A directory that is NOT inside a git work tree (pytest's tmp area)."""
    d = tmp_path_factory.mktemp("private")
    assert not C._inside_git(d)

    def write(name: str, data) -> str:
        p = d / name
        p.write_text(json.dumps(data), encoding="utf-8")
        return str(p)

    return write


def run(srv, private, payload=None, **kw):
    args = dict(base_url=srv.url)
    if payload is not None:
        args["payload_path"] = private("p.json", payload)
    args.update(kw)
    return C.content(**args)


class TestDryRunIsTheDefault:
    def test_set_without_confirm_only_reads_and_returns_a_diff(self, srv, private):
        out = run(srv, private, {"itens": [{"chave": "a.b", "conteudo": "UM NOVO"}]}, action="set", kind="texto", agent="julia")
        assert out["status"] == "planned" and out["dry_run"] is True
        (ch,) = out["mudancas"]
        assert ch["chave"] == "a.b" and ch["op"] == "update"
        assert '-  "conteudo": "um"' in ch["diff"] and '+  "conteudo": "UM NOVO"' in ch["diff"]
        assert srv.writes() == []
        assert srv.textos[0]["conteudo"] == "um"

    def test_confirm_writes_the_draft_merging_into_the_current_rows(self, srv, private):
        out = run(srv, private, {"itens": [{"chave": "a.b", "conteudo": "NOVO"}, {"chave": "a.d", "conteudo": "tres"}]},
                  action="set", kind="texto", agent="julia", confirm=True)
        assert out["status"] == "written" and out["escritas"] == 1
        assert {t["chave"]: t["conteudo"] for t in srv.textos} == {"a.b": "NOVO", "a.c": "dois", "a.d": "tres"}
        assert srv.writes() == [("PUT", "/api/studio/agents/julia/draft/textos")]

    def test_merge_false_replaces_the_set_and_the_diff_shows_the_removal(self, srv, private):
        out = run(srv, private, {"itens": [{"chave": "a.b", "conteudo": "um"}]}, action="set", kind="texto", agent="julia", merge=False)
        ops = {c["chave"]: c["op"] for c in out["mudancas"]}
        assert ops == {"a.b": "unchanged", "a.c": "remove"}
        assert out["status"] == "planned"
        run(srv, private, {"itens": [{"chave": "a.b", "conteudo": "um"}]}, action="set", kind="texto", agent="julia", merge=False, confirm=True)
        assert [t["chave"] for t in srv.textos] == ["a.b"]

    def test_an_unchanged_payload_writes_nothing_even_with_confirm(self, srv, private):
        out = run(srv, private, {"itens": [{"chave": "a.b", "conteudo": "um"}]}, action="set", kind="texto", agent="julia", confirm=True)
        assert out["status"] == "no_change" and srv.writes() == []


class TestKinds:
    def test_secao_replace_set_only_changes_touched_fields(self, srv, private):
        out = run(srv, private, {"secoes": [{"chave": "persona", "conteudo": "novo texto"}]}, action="set", kind="secao", agent="julia", confirm=True)
        assert out["status"] == "written"
        (sec,) = srv.secoes
        assert sec["conteudo"] == "novo texto" and sec["titulo"] == "Quem" and sec["ordem"] == 1  # untouched fields kept

    def test_ferramenta_decisao_spec_round_trip(self, srv, private):
        for kind, item, attr in (
            ("ferramenta", {"ferramenta": "handoff", "ativo": True, "descricao": "d", "parametros": {}, "obrigatoria_skill": None}, "ferramentas"),
            ("decisao", {"chave": "x", "titulo": "X", "regra": "r", "opcoes": [{"valor": "a", "rotulo": "A", "padrao": True}]}, "decisoes"),
            ("spec", {"chave": "agencia", "rotulo": "Agencia", "tipo": "texto", "obrigatoria": True}, "specs"),
        ):
            out = run(srv, private, {"itens": [item]}, action="set", kind=kind, agent="julia", confirm=True)
            assert out["status"] == "written", out
            assert getattr(srv, attr)[0].items() >= item.items()
            again = run(srv, private, {"itens": [item]}, action="set", kind=kind, agent="julia")
            assert again["status"] == "no_change", again

    def test_list_and_get(self, srv, private):
        assert run(srv, private, action="list", kind="texto", agent="julia")["itens"] == ["a.b", "a.c"]
        got = run(srv, private, action="get", kind="texto", agent="julia", chave="a.c")["itens"]
        assert got == {"a.c": {"conteudo": "dois"}}

    def test_library_skill_is_created_as_a_draft_with_files_and_never_published(self, srv, private):
        item = {"chave": "qualificar-lead", "nome": "Qualificar lead", "descricao_modelo": "quando abrir", "corpo": "passos",
                "arquivos": [{"caminho": "ref/a.md", "titulo": "A", "conteudo": "x"}]}
        plan = run(srv, private, {"itens": [item]}, action="set", kind="skill")
        assert plan["status"] == "planned" and plan["mudancas"][0]["op"] == "create" and srv.skills == {}
        out = run(srv, private, {"itens": [item]}, action="set", kind="skill", confirm=True)
        assert out["status"] == "written"
        (v,) = srv.skills["qualificar-lead"]["versoes"]
        assert v["status"] == "rascunho" and v["corpo"] == "passos" and v["arquivos"][0]["caminho"] == "ref/a.md"
        assert not any("publicar" in p for _m, p in srv.writes())
        assert run(srv, private, {"itens": [item]}, action="set", kind="skill")["status"] == "no_change"

    def test_editing_a_published_skill_forks_a_draft_from_it(self, srv, private):
        srv.skills["s1"] = {"nome": "S1", "descricao": None, "versoes": [
            {"id": "11111111-1111-1111-1111-111111111111", "versao": 1, "status": "publicada",
             "descricao_modelo": "d", "corpo": "velho", "arquivos": []}]}
        run(srv, private, {"itens": [{"chave": "s1", "corpo": "novo"}]}, action="set", kind="skill", confirm=True)
        v1, v2 = srv.skills["s1"]["versoes"]
        assert (v1["status"], v1["corpo"]) == ("publicada", "velho")  # the published one is untouched
        assert (v2["status"], v2["corpo"], v2["descricao_modelo"]) == ("rascunho", "novo", "d")

    def test_new_skill_needs_a_name(self, srv, private):
        out = run(srv, private, {"itens": [{"chave": "sem-nome", "corpo": "x"}]}, action="set", kind="skill")
        assert out["status"] == "error" and out["codigo"] == "nome_obrigatorio"

    def test_skill_pins(self, srv, private):
        srv.skills["qualificar-lead"] = {"nome": "Q", "descricao": None, "versoes": [{"id": "1", "versao": 1, "status": "publicada"}]}
        srv.pins["velha"] = {"skill": "velha", "versao": 1, "nova_versao": None, "obrigatoria_para": [], "ordem": 0}
        payload = {"itens": [{"skill": "qualificar-lead", "obrigatoria_para": ["registrar_perfil"], "ordem": 10}], "remover": ["velha"]}
        plan = run(srv, private, payload, action="set", kind="skill_ref", agent="julia")
        assert {c["chave"]: c["op"] for c in plan["mudancas"]} == {"qualificar-lead": "create", "velha": "remove"}
        assert srv.writes() == []
        run(srv, private, payload, action="set", kind="skill_ref", agent="julia", confirm=True)
        assert set(srv.pins) == {"qualificar-lead"} and srv.pins["qualificar-lead"]["obrigatoria_para"] == ["registrar_perfil"]

    def test_standard_criteria_write_into_a_draft_forked_from_the_published_version(self, srv, private):
        new = {"chave": "operacao", "rotulo": "Operacao (compra ou aluguel)", "opcoes": [{"valor": "compra"}, {"valor": "aluguel"}]}
        plan = run(srv, private, {"itens": [new]}, action="set", kind="padrao_criterio", padrao="imob-lead")
        assert plan["status"] == "planned" and plan["mudancas"][0]["op"] == "update" and len(srv.padrao_versoes) == 1
        out = run(srv, private, {"itens": [new]}, action="set", kind="padrao_criterio", padrao="imob-lead", confirm=True)
        assert out["status"] == "written"
        pub, rasc = srv.padrao_versoes
        assert pub["criterios"][0]["rotulo"] == "Operacao" and rasc["status"] == "rascunho"
        crit = rasc["criterios"][0]
        assert crit["rotulo"] == "Operacao (compra ou aluguel)" and crit["grupo"] == "prontidao" and crit["tipo"] == "enum"  # merged
        assert [o["valor"] for o in crit["opcoes"]] == ["compra", "aluguel"]
        # an identical re-run is a no-op (option defaults are normalised on both sides)
        again = run(srv, private, {"itens": [new]}, action="set", kind="padrao_criterio", padrao="imob-lead")
        assert again["status"] == "no_change"

    def test_standard_parameters_and_stages(self, srv, private):
        out = run(srv, private, {"lote_ofertas": 2}, action="set", kind="padrao_parametros", padrao="imob-lead", confirm=True)
        assert out["status"] == "written" and srv.padrao_versoes[-1]["parametros"]["lote_ofertas"] == 2
        est = {"chave": "novo", "rotulo": "Novo", "ordem": 1, "regra": {"todos": []}}
        out = run(srv, private, {"itens": [est]}, action="set", kind="padrao_estagio", padrao="imob-lead", confirm=True)
        assert out["status"] == "written" and srv.padrao_versoes[-1]["estagios"][0]["chave"] == "novo"

    def test_unknown_standard(self, srv, private):
        out = run(srv, private, action="list", kind="padrao_criterio", padrao="nada")
        assert out["status"] == "error" and out["codigo"] == "padrao_inexistente"


class TestSecaoRegras:
    """Section ``regras`` (migration 078): a set must never silently drop a rule tag."""

    def test_a_set_without_regras_keeps_the_current_tags(self, srv, private):
        srv.secoes[0]["regras"] = ["discordar-com-respeito"]
        out = run(srv, private, {"secoes": [{"chave": "persona", "conteudo": "novo"}]}, action="set", kind="secao", agent="julia", confirm=True)
        assert out["status"] == "written"
        assert srv.secoes[0]["regras"] == ["discordar-com-respeito"] and srv.secoes[0]["conteudo"] == "novo"

    def test_other_sections_keep_their_tags_too(self, srv, private):
        srv.secoes.append({"chave": "honestidade", "titulo": "H", "ordem": 2, "conteudo": "h", "ativo": True, "regras": ["discordar-com-respeito"]})
        run(srv, private, {"secoes": [{"chave": "persona", "conteudo": "novo"}]}, action="set", kind="secao", agent="julia", confirm=True)
        assert {s["chave"]: s["regras"] for s in srv.secoes} == {"persona": [], "honestidade": ["discordar-com-respeito"]}

    def test_regras_can_be_set_and_cleared(self, srv, private):
        run(srv, private, {"secoes": [{"chave": "persona", "regras": ["discordar-com-respeito"]}]}, action="set", kind="secao", agent="julia", confirm=True)
        assert srv.secoes[0]["regras"] == ["discordar-com-respeito"]
        run(srv, private, {"secoes": [{"chave": "persona", "regras": []}]}, action="set", kind="secao", agent="julia", confirm=True)
        assert srv.secoes[0]["regras"] == []

    def test_regras_must_be_a_list_of_strings(self, srv, private):
        out = run(srv, private, {"secoes": [{"chave": "persona", "regras": "x"}]}, action="set", kind="secao", agent="julia")
        assert out["status"] == "error" and out["codigo"] == "payload_invalido"

    def test_get_shows_regras(self, srv, private):
        srv.secoes[0]["regras"] = ["discordar-com-respeito"]
        got = run(srv, private, action="get", kind="secao", agent="julia")["itens"]
        assert got["persona"]["regras"] == ["discordar-com-respeito"]


class TestCriarPadrao:
    def test_dry_run_reads_only(self, srv, private):
        out = run(srv, private, {"nome": "Novo", "descricao": "d"}, action="criar_padrao", padrao="novo-padrao")
        assert out["status"] == "planned" and out["dry_run"] is True and srv.writes() == []
        assert "novo-padrao" not in srv.padroes

    def test_confirm_creates_padrao_and_a_draft_never_publishes(self, srv, private):
        out = run(srv, private, {"nome": "Novo", "descricao": "d"}, action="criar_padrao", padrao="novo-padrao", confirm=True)
        assert out["status"] == "created" and "novo-padrao" in srv.padroes
        (v,) = srv.padrao_novo_versoes
        assert v["status"] == "rascunho"
        assert not any("publicar" in p or "publish" in p for _m, p in srv.writes())

    def test_existing_padrao_is_a_no_op(self, srv, private):
        out = run(srv, private, {"nome": "X"}, action="criar_padrao", padrao="imob-lead", confirm=True)
        assert out["status"] == "no_change" and srv.writes() == []

    def test_existing_padrao_without_a_version_gets_the_draft(self, srv, private):
        srv.padroes.append("novo-padrao")
        out = run(srv, private, {"nome": "X"}, action="criar_padrao", padrao="novo-padrao", confirm=True)
        assert out["status"] == "created" and len(srv.padrao_novo_versoes) == 1
        assert srv.writes() == [("POST", "/api/qualificacao/padroes/novo-padrao/versoes")]

    def test_validation(self, srv, private):
        assert run(srv, private, {"nome": "X"}, action="criar_padrao")["codigo"] == "padrao_ausente"
        assert run(srv, private, {"nome": "X"}, action="criar_padrao", padrao="Ruim Key")["codigo"] == "padrao_invalido"
        assert run(srv, private, {"descricao": "d"}, action="criar_padrao", padrao="novo-padrao")["codigo"] == "payload_invalido"
        assert run(srv, private, {"nome": "X", "x": 1}, action="criar_padrao", padrao="novo-padrao")["codigo"] == "payload_invalido"

    def test_usable_after_creation(self, srv, private):
        run(srv, private, {"nome": "Novo"}, action="criar_padrao", padrao="novo-padrao", confirm=True)
        out = run(srv, private, action="list", kind="padrao_criterio", padrao="novo-padrao")
        assert out["codigo"] != "padrao_inexistente" if out["status"] == "error" else True


class TestSkillRefSemVersaoPublicada:
    def test_pin_of_a_skill_with_only_a_draft_says_the_real_cause(self, srv, private):
        srv.skills["so-rascunho"] = {"nome": "S", "descricao": None, "versoes": [{"id": "1", "versao": 1, "status": "rascunho"}]}
        out = run(srv, private, {"itens": [{"skill": "so-rascunho", "obrigatoria_para": [], "ordem": 1}]}, action="set", kind="skill_ref", agent="julia")
        assert out["status"] == "error" and out["codigo"] == "skill_sem_versao_publicada"
        assert "publique" in out["mensagem"].lower() and srv.writes() == []

    def test_unknown_skill_is_its_own_error(self, srv, private):
        out = run(srv, private, {"itens": [{"skill": "nao-existe", "obrigatoria_para": [], "ordem": 1}]}, action="set", kind="skill_ref", agent="julia")
        assert out["status"] == "error" and out["codigo"] == "skill_inexistente"

    def test_server_code_is_passed_through(self, srv, private):
        srv.skills["pub"] = {"nome": "S", "descricao": None, "versoes": [{"id": "1", "versao": 1, "status": "publicada"}]}
        out = run(srv, private, {"itens": [{"skill": "pub", "obrigatoria_para": [], "ordem": 1}]}, action="set", kind="skill_ref", agent="julia", confirm=True)
        assert out["status"] == "written"


class TestEvalAndConformanceKinds:
    """A-polish #3: mechanism eval cases + conformance rules, same dry-run / token / never-publish discipline."""

    CASO = {"slug": "minimo-antes-de-ofertar", "titulo": "Sem oferta antes do mínimo", "entrada": "roteiro",
            "k": 2, "roteiro": {"turnos": [{"lead": "oi"}]}, "asserts": {"ferramentas_proibidas": ["oferecer_imoveis"]}}

    def test_a_mechanism_case_is_planned_then_created_as_mecanismo_and_never_runs(self, srv, private):
        plan = run(srv, private, {"itens": [self.CASO]}, action="set", kind="evals_mecanismo", agent="julia")
        assert plan["status"] == "planned" and plan["mudancas"][0]["op"] == "create" and srv.writes() == []
        out = run(srv, private, {"itens": [self.CASO]}, action="set", kind="evals_mecanismo", agent="julia", confirm=True)
        assert out["status"] == "written" and "próxima execução" in out["mensagem"].lower()
        assert srv.writes() == [("POST", "/api/studio/agents/julia/evals/cases")]
        criado = srv.casos[-1]
        assert criado["suite"] == "mecanismo" and criado["roteiro"] == self.CASO["roteiro"]
        assert not any("runs" in p or "publish" in p for _m, p in srv.writes())
        again = run(srv, private, {"itens": [self.CASO]}, action="set", kind="evals_mecanismo", agent="julia")
        assert again["status"] == "no_change"

    def test_only_mecanismo_cases_are_listed_edited_and_deactivated(self, srv, private):
        run(srv, private, {"itens": [self.CASO]}, action="set", kind="evals_mecanismo", agent="julia", confirm=True)
        assert run(srv, private, action="list", kind="evals_mecanismo", agent="julia")["itens"] == [self.CASO["slug"]]
        upd = run(srv, private, {"itens": [{"slug": self.CASO["slug"], "k": 4}]}, action="set", kind="evals_mecanismo",
                  agent="julia", confirm=True)
        assert upd["status"] == "written" and srv.casos[-1]["k"] == 4 and srv.writes()[-1][0] == "PATCH"
        outro = {**self.CASO, "slug": "outro"}
        plan = run(srv, private, {"itens": [outro]}, action="set", kind="evals_mecanismo", agent="julia", merge=False)
        assert {c["chave"]: c["op"] for c in plan["mudancas"]} == {"outro": "create", self.CASO["slug"]: "deactivate"}
        assert srv.casos[0]["slug"] == "juiz-1"  # the judge case is never touched by this kind

    def test_a_new_case_must_be_complete(self, srv, private):
        out = run(srv, private, {"itens": [{"slug": "x", "titulo": "t"}]}, action="set", kind="evals_mecanismo", agent="julia")
        assert out["status"] == "error" and out["codigo"] == "caso_incompleto" and srv.writes() == []

    @pytest.mark.parametrize("confirm", [False, True])
    def test_conformance_rules_are_read_only_here_a_human_changes_them_in_the_studio(self, srv, private, confirm):
        payload = {"itens": [{"regra": "vazamento_prompt", "ativo": False}]}
        out = run(srv, private, payload, action="set", kind="conformidade_regras", agent="julia", confirm=confirm)
        assert out["status"] == "error" and out["codigo"] == "regra_seguranca_exige_humano"
        assert "Studio" in out["mensagem"] and srv.writes() == [] and srv.log == []  # no request at all

    def test_consolidation_criticality_and_deps_are_planned_then_written_per_slug(self, srv, private):
        run(srv, private, {"itens": [self.CASO]}, action="set", kind="evals_mecanismo", agent="julia", confirm=True)
        slug = self.CASO["slug"]
        payload = {"itens": [{"slug": slug, "criticidade": "critico", "depende_de": ["secao:persona", "skill:*"]}]}
        plan = run(srv, private, payload, action="set", kind="evals_consolidacao", agent="julia")
        assert plan["status"] == "planned" and plan["mudancas"][0]["chave"] == slug and srv.writes()[-1][0] == "POST"
        out = run(srv, private, payload, action="set", kind="evals_consolidacao", agent="julia", confirm=True)
        assert out["status"] == "written" and srv.writes()[-1][0] == "PUT" and srv.writes()[-1][1].endswith("/consolidacao")
        got = run(srv, private, action="get", kind="evals_consolidacao", agent="julia", chave=slug)
        assert got["itens"] == {slug: {"criticidade": "critico", "depende_de": ["secao:persona", "skill:*"]}}
        assert run(srv, private, payload, action="set", kind="evals_consolidacao", agent="julia")["status"] == "no_change"

    def test_consolidation_refuses_unknown_cases_fields_and_replace_mode(self, srv, private):
        for body, merge, codigo in (
            ({"itens": [{"slug": "nao-existe", "criticidade": "critico"}]}, True, "caso_desconhecido"),
            ({"itens": [{"slug": "x", "ativo": False}]}, False, "merge_invalido"),
        ):
            out = run(srv, private, body, action="set", kind="evals_consolidacao", agent="julia", merge=merge)
            assert out["status"] == "error" and out["codigo"] == codigo

    def test_conformance_rules_can_still_be_read(self, srv, private):
        got = run(srv, private, action="get", kind="conformidade_regras", agent="julia", chave="termina_sem_pergunta")
        assert got["itens"] == {"termina_sem_pergunta": {"ativo": True, "politica": "registrar", "parametros": {}}}
        assert run(srv, private, action="list", kind="conformidade_regras", agent="julia")["status"] != "error"

    def test_both_kinds_need_an_agent_and_carry_the_token_only_as_a_header(self, srv, private):
        out = run(srv, private, action="list", kind="conformidade_regras")
        assert out["status"] == "error" and out["codigo"] == "agent_ausente"
        run(srv, private, action="list", kind="evals_mecanismo", agent="julia")
        assert all(a == f"Bearer {TOKEN}" for _m, _p, _b, a in srv.log)
        assert TOKEN not in json.dumps(run(srv, private, action="list", kind="evals_mecanismo", agent="julia"))


class TestNeverPublishesAndKeepsTheSecret:
    def test_publish_is_not_an_action(self, srv, private):
        out = run(srv, private, {"itens": []}, action="publish", kind="texto", agent="julia")
        assert out["status"] == "error" and out["codigo"] == "acao_invalida" and srv.log == []

    def test_the_api_layer_refuses_a_publish_route_outright(self, srv):
        api = C._Api(srv.url, TOKEN, None)
        try:
            for path in ("/api/studio/agents/julia/draft/publish", "/api/skills-biblioteca/versoes/x/publicar"):
                with pytest.raises(C.ContentError) as e:
                    api.call("POST", path)
                assert e.value.codigo == "publicar_proibido"
        finally:
            api.close()
        assert srv.log == []

    def test_the_token_is_sent_as_bearer_and_never_returned(self, srv, private):
        run(srv, private, action="list", kind="texto", agent="julia")
        assert {a for *_x, a in srv.log} == {f"Bearer {TOKEN}"}
        api = C._Api(srv.url, TOKEN, None)
        try:
            with pytest.raises(C.ContentError) as e:
                api.call("GET", "/boom")
        finally:
            api.close()
        assert TOKEN not in e.value.mensagem and "<token>" in e.value.mensagem
        out = run(srv, private, {"itens": [{"chave": "a.b", "conteudo": "x"}]}, action="set", kind="texto", agent="julia", confirm=True)
        assert TOKEN not in json.dumps(out)

    def test_a_wrong_token_is_a_clean_error(self, srv, private, monkeypatch):
        monkeypatch.setenv(C.ENV_TOKEN, "outro")
        out = run(srv, private, action="list", kind="texto", agent="julia")
        assert out["status"] == "error" and out["codigo"] == "unauthorized" and "outro" not in json.dumps(out)

    def test_missing_token_makes_no_request(self, srv, private, monkeypatch):
        monkeypatch.delenv(C.ENV_TOKEN)
        out = run(srv, private, action="list", kind="texto", agent="julia")
        assert out["codigo"] == "nao_configurado" and srv.log == []

    def test_the_token_can_come_from_the_agents_env_file(self, srv, private, monkeypatch, tmp_path):
        f = tmp_path / "agents.env"
        f.write_text(f"export {C.ENV_TOKEN}='{TOKEN}'\n", encoding="utf-8")
        monkeypatch.delenv(C.ENV_TOKEN)
        monkeypatch.setenv("NOCTUS_AGENTS_ENV_FILE", str(f))
        assert run(srv, private, action="list", kind="texto", agent="julia")["status"] == "ok"

    def test_the_url_can_come_from_the_agents_env_file_too(self, srv, private, monkeypatch, tmp_path):
        # 2026-11-11: the file carried both keys, the token was read from it and the URL was not -> base_url_ausente
        f = tmp_path / "agents.env"
        f.write_text(f"{C.ENV_URL}={srv.url}\n", encoding="utf-8")
        monkeypatch.delenv(C.ENV_URL, raising=False)
        monkeypatch.setenv("NOCTUS_AGENTS_ENV_FILE", str(f))
        out = C.content("list", "texto", agent="julia")
        assert out["status"] == "ok" and srv.log, out


class TestInputsAreGuarded:
    def test_a_payload_inside_a_git_work_tree_is_refused(self, srv, tmp_path):
        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        p = repo / "conteudo.json"
        p.write_text('{"itens": []}', encoding="utf-8")
        out = C.content("set", "texto", agent="julia", payload_path=str(p), base_url=srv.url)
        assert out["codigo"] == "payload_dentro_do_git" and srv.log == []

    def test_plain_http_is_loopback_only_and_urls_carry_no_credentials(self, private):
        for url in ("http://agents.example.com", "ftp://x", "https://user:pw@agents.example.com", ""):
            out = C.content("list", "texto", agent="julia", base_url=url)
            assert out["status"] == "error" and out["codigo"] in {"base_url_insegura", "base_url_invalida", "base_url_ausente"}, url
        assert C._base_url("https://agents.noctusai.com/") == "https://agents.noctusai.com"

    def test_bad_arguments(self, srv, private):
        assert run(srv, private, action="list", kind="nada")["codigo"] == "kind_invalido"
        assert run(srv, private, action="list", kind="texto")["codigo"] == "agent_ausente"
        assert run(srv, private, action="list", kind="padrao_criterio")["codigo"] == "padrao_ausente"
        assert C.content("set", "texto", agent="julia", base_url=srv.url)["codigo"] == "payload_ausente"
        assert run(srv, private, {"x": 1}, action="set", kind="texto", agent="julia")["codigo"] == "payload_invalido"
        assert run(srv, private, {"itens": [{"chave": "a", "nope": 1}]}, action="set", kind="texto", agent="julia")["codigo"] == "payload_invalido"
        assert srv.writes() == []

    def test_the_tool_is_registered_under_the_agents_namespace(self):
        names = []

        class Server:
            def tool(self, name, description):
                names.append(name)
                return lambda fn: fn

        C.register(Server())
        assert names == ["noctus.agents.content"]


class TestAgentLifecycle:
    """criar_agente / excluir_agente: dry-run by default (no request at all), one route each, never publishes."""

    def test_criar_agente_is_a_dry_run_then_posts_the_key_only(self, srv):
        plan = C.content("criar_agente", agent="julia", base_url=srv.url)
        assert plan["status"] == "planned" and plan["dry_run"] is True and srv.log == []
        assert plan["requisicao"] == "POST /api/studio/plataforma/agents"
        out = C.content("criar_agente", agent="julia", base_url=srv.url, confirm=True)
        assert out["status"] == "created" and out["agente"]["key"] == "julia" and out["agente"]["conteudo_modo"] == "linhas"
        assert [(m, p, b) for m, p, b, _a in srv.log] == [("POST", "/api/studio/plataforma/agents", {"key": "julia", "reutilizar": True})]
        assert TOKEN not in json.dumps(out)

    def test_excluir_agente_is_a_dry_run_then_deletes(self, srv):
        plan = C.content("excluir_agente", agent="casca", base_url=srv.url)
        assert plan["status"] == "planned" and srv.log == []
        out = C.content("excluir_agente", agent="casca", base_url=srv.url, confirm=True)
        assert out["status"] == "deleted" and out["dry_run"] is False
        assert [(m, p) for m, p, _b, _a in srv.log] == [("DELETE", "/api/studio/agents/casca")]
        assert {a for *_x, a in srv.log} == {f"Bearer {TOKEN}"}

    def test_a_server_refusal_is_a_clean_error_with_its_code(self, srv):
        out = C.content("excluir_agente", agent="publicada", base_url=srv.url, confirm=True)
        assert out["status"] == "error" and out["codigo"] == "publicado"
        out = C.content("excluir_agente", agent="sem-escopo", base_url=srv.url, confirm=True)
        assert out["codigo"] == "scope_missing" and TOKEN not in json.dumps(out)

    def test_no_kind_payload_or_publish_is_involved_and_the_key_is_validated(self, srv):
        for bad in (None, "", "a/b", "../x", "x y"):
            out = C.content("excluir_agente", agent=bad, base_url=srv.url, confirm=True)
            assert out["codigo"] == "agent_invalido"
        assert srv.log == []

    def test_missing_token_makes_no_request(self, srv, monkeypatch):
        monkeypatch.delenv(C.ENV_TOKEN)
        assert C.content("criar_agente", agent="julia", base_url=srv.url, confirm=True)["codigo"] == "nao_configurado"
        assert srv.log == []


BRIEFING = {"nome": "Atendente", "objetivo": "Atender clientes de uma loja.", "publico": "Ciclistas", "canal": "web",
            "exemplos": "NUNCA-ECOAR-ESTE-TEXTO"}


class TestConceder:
    """conceder / concessoes: the sanctioned way to give ONE org a closed definition (org-config isolation)."""

    ORG = "11111111-2222-4333-8444-555555555555"

    def test_conceder_is_a_dry_run_then_posts_the_org(self, srv, private):
        plan = run(srv, private, {"org_id": self.ORG}, action="conceder", agent="julia")
        assert plan["status"] == "planned" and srv.log == []
        assert plan["requisicao"] == "POST /api/studio/plataforma/agents/julia/grants"
        out = run(srv, private, {"org_id": self.ORG}, action="conceder", agent="julia", confirm=True)
        assert out["status"] == "granted" and out["concessoes"]["org_ids"] == [self.ORG]
        [(method, path, body, _a)] = srv.log
        assert (method, path, body) == ("POST", "/api/studio/plataforma/agents/julia/grants", {"org_id": self.ORG})

    def test_conceder_needs_a_valid_org_id_and_nothing_else(self, srv, private):
        assert run(srv, private, {"org_id": "not-a-uuid"}, action="conceder", agent="julia")["codigo"] == "payload_invalido"
        assert run(srv, private, {"org_id": self.ORG, "x": 1}, action="conceder", agent="julia")["codigo"] == "payload_invalido"
        assert srv.log == []

    def test_concessoes_lists(self, srv):
        out = C.content("concessoes", agent="julia", base_url=srv.url)
        assert out["status"] == "ok" and out["resultado"]["org_ids"] == []


class TestGeracao:
    """criar_agente (data payload) / configurar_agente / definicao / gerar / geracao: dry-run makes NO request."""

    def test_gerar_is_a_dry_run_that_makes_no_request_and_never_echoes_the_briefing(self, srv, private):
        out = run(srv, private, {"briefing": BRIEFING, "limite_usd": 2.0}, action="gerar", agent="julia")
        assert out["status"] == "planned" and out["dry_run"] is True and srv.log == []
        assert out["requisicao"] == "POST /api/studio/agents/julia/geracoes"
        assert out["campos"] == ["briefing", "limite_usd"] and "NUNCA-ECOAR" not in json.dumps(out)

    def test_gerar_posts_the_payload_when_confirmed_and_never_publishes(self, srv, private):
        out = run(srv, private, {"briefing": BRIEFING, "areas": ["secoes"], "forcar": True}, action="gerar", agent="julia", confirm=True)
        assert out["status"] == "started" and out["geracao"]["status"] == "pendente" and TOKEN not in json.dumps(out)
        [(method, path, body, _a)] = srv.log
        assert (method, path) == ("POST", "/api/studio/agents/julia/geracoes")
        assert body == {"briefing": BRIEFING, "areas": ["secoes"], "forcar": True}
        assert not [p for _m, p, _b, _a in srv.log if p.endswith(("/publish", "/publicar"))]

    def test_gerar_needs_a_briefing_and_known_fields_and_a_payload_outside_git(self, srv, private):
        assert run(srv, private, {"areas": ["secoes"]}, action="gerar", agent="julia")["codigo"] == "payload_invalido"
        assert run(srv, private, {"briefing": BRIEFING, "modelo": "x"}, action="gerar", agent="julia")["codigo"] == "payload_invalido"
        assert C.content("gerar", agent="julia", base_url=srv.url)["codigo"] == "payload_ausente"
        assert srv.log == []

    def test_a_server_refusal_keeps_its_code(self, srv, private):
        out = run(srv, private, {"briefing": BRIEFING}, action="gerar", agent="desconhecido", confirm=True)
        assert out["status"] == "error" and out["codigo"] == "agente_nao_encontrado"

    def test_geracao_lists_or_reads_one_run(self, srv):
        lst = C.content("geracao", agent="julia", base_url=srv.url)
        assert lst["status"] == "ok" and lst["resultado"]["items"][0]["status"] == "concluida"
        one = C.content("geracao", agent="julia", chave="22222222-2222-4222-8222-222222222222", base_url=srv.url)
        assert one["resultado"]["status"] == "executando"
        assert [(m, p) for m, p, _b, _a in srv.log] == [
            ("GET", "/api/studio/agents/julia/geracoes"),
            ("GET", "/api/studio/agents/julia/geracoes/22222222-2222-4222-8222-222222222222")]
        assert C.content("geracao", agent="julia", chave="../x", base_url=srv.url)["codigo"] == "chave_invalida"

    def test_criar_agente_carries_the_data_payload(self, srv, private):
        body = {"nome": "Novo", "papel": "gerador", "rascunho_padrao": {"model": "claude-opus-5"}, "instanciavel": False}
        out = run(srv, private, body, action="criar_agente", agent="novo-agente", confirm=True)
        assert out["status"] == "created"
        assert srv.log[0][2] == {"key": "novo-agente", **body, "reutilizar": True}
        assert run(srv, private, {"nome": "x", "inventado": 1}, action="criar_agente", agent="k")["codigo"] == "payload_invalido"

    def test_configurar_agente_patches_and_definicao_reads(self, srv, private):
        plan = run(srv, private, {"papel": "gerador"}, action="configurar_agente", agent="novo")
        assert plan["status"] == "planned" and srv.log == []
        out = run(srv, private, {"papel": "gerador"}, action="configurar_agente", agent="novo", confirm=True)
        assert out["status"] == "updated" and out["agente"]["papel"] == "gerador"
        assert srv.log[-1][:3] == ("PATCH", "/api/studio/plataforma/agents/novo", {"papel": "gerador"})
        got = C.content("definicao", agent="novo", base_url=srv.url)
        assert got["status"] == "ok" and got["resultado"]["key"] == "novo"


class TestProntidaoEAtualizarSkills:
    """The complete-agent recipe's two new actions (agent-creation guide): the readiness read and the explicit re-pin."""

    def test_prontidao_reads_the_readiness_list_and_never_writes(self, srv):
        out = C.content("prontidao", agent="julia", base_url=srv.url)
        assert out["status"] == "ok" and out["requisicao"] == "GET /api/studio/agents/julia/prontidao"
        assert out["resultado"]["pronto_para_publicar"] is False
        assert out["resultado"]["itens"][0]["recusa_publicacao"] == "eval_required"
        assert srv.writes() == [] and TOKEN not in json.dumps(out)

    def test_prontidao_needs_a_valid_agent_key(self, srv):
        assert C.content("prontidao", agent="../x", base_url=srv.url)["codigo"] == "agent_invalido"
        assert C.content("prontidao", base_url=srv.url)["codigo"] == "agent_invalido"
        assert srv.log == []

    def test_atualizar_skills_dry_run_reads_the_pins_and_lists_what_would_move_without_writing(self, srv):
        srv.pins = {
            "qualificar": {"skill": "qualificar", "versao": 1, "nova_versao": 2, "obrigatoria_para": [], "ordem": 0},
            "fechar": {"skill": "fechar", "versao": 3, "nova_versao": None, "obrigatoria_para": [], "ordem": 1},
        }
        out = C.content("atualizar_skills", agent="julia", base_url=srv.url)
        assert out["status"] == "planned" and out["dry_run"] is True
        assert out["atualizaria"] == [{"skill": "qualificar", "de": 1, "para": 2}] and out["ja_atuais"] == ["fechar"]
        assert out["requisicao"] == "POST /api/studio/agents/julia/draft/skills-biblioteca/atualizar"
        assert srv.writes() == [] and srv.pins["qualificar"]["versao"] == 1

    def test_atualizar_skills_posts_when_confirmed_and_returns_the_diff(self, srv):
        srv.pins = {"qualificar": {"skill": "qualificar", "versao": 1, "nova_versao": 2, "obrigatoria_para": [], "ordem": 0}}
        out = C.content("atualizar_skills", agent="julia", base_url=srv.url, confirm=True)
        assert out["status"] == "updated" and out["atualizadas"] == [{"skill": "qualificar", "de": 1, "para": 2}]
        assert srv.writes() == [("POST", "/api/studio/agents/julia/draft/skills-biblioteca/atualizar")]
        assert srv.pins["qualificar"]["versao"] == 2
        assert not [p for _m, p, _b, _a in srv.log if p.endswith(("/publish", "/publicar"))]

    def test_gerar_accepts_a_referencia_and_the_evals_area(self, srv, private):
        out = run(srv, private, {"briefing": BRIEFING, "areas": ["evals"], "referencia": "julia"}, action="gerar", agent="julia", confirm=True)
        assert out["status"] == "started"
        assert srv.log[0][2] == {"briefing": BRIEFING, "areas": ["evals"], "referencia": "julia"}

    def test_the_description_names_the_new_actions(self):
        from tools.noctus.agents import content as mod

        captured = {}

        class _Srv:
            def tool(self, name, description):
                captured["d"] = description
                return lambda fn: fn

        mod.register(_Srv())
        assert "prontidao" in captured["d"] and "atualizar_skills" in captured["d"]


class TestRascunhoKind:
    def test_only_the_fields_sent_are_patched_after_a_dry_run(self, srv, private):
        body = {"configuracoes": {"tool_policy": {"web_search": False, "knowledge": False}, "effort": "medium"}}
        plan = run(srv, private, body, action="set", kind="rascunho", agent="julia")
        assert plan["status"] == "planned" and srv.writes() == []
        assert {c["chave"]: c["op"] for c in plan["mudancas"]} == {"effort": "unchanged", "tool_policy": "update"}
        out = run(srv, private, body, action="set", kind="rascunho", agent="julia", confirm=True)
        assert out["status"] == "written" and srv.writes() == [("PATCH", "/api/studio/agents/julia/draft")]
        assert srv.config["tool_policy"] == {"web_search": False, "knowledge": False} and srv.config["effort"] == "medium"

    def test_an_unknown_setting_is_refused_before_any_write(self, srv, private):
        out = run(srv, private, {"configuracoes": {"temperature": 0}}, action="set", kind="rascunho", agent="julia", confirm=True)
        assert out["status"] == "error" and out["codigo"] == "payload_invalido" and srv.writes() == []

    def test_get_reads_the_settings(self, srv, private):
        out = run(srv, private, action="get", kind="rascunho", agent="julia", chave="model")
        assert out["itens"] == {"model": "sonnet"}


LID = "22222222-2222-4222-8222-222222222222"


class TestEvalLoopActions:
    def test_loop_iniciar_dry_run_makes_no_request_then_confirm_posts(self, srv, private):
        pl = private("l.json", {"suite": "comportamento", "rodadas_planejadas": 5, "orcamento_usd": 10})
        out = C.content("loop_iniciar", agent="julia", base_url=srv.url, payload_path=pl)
        assert out["status"] == "planned" and out["requisicao"] == "POST /api/studio/agents/julia/evals/loops" and srv.log == []
        out = C.content("loop_iniciar", agent="julia", base_url=srv.url, payload_path=pl, confirm=True)
        assert out["status"] == "done" and out["resultado"]["id"] == LID
        assert srv.log[0][2] == {"suite": "comportamento", "rodadas_planejadas": 5, "orcamento_usd": 10}
        assert TOKEN not in json.dumps(out)

    def test_loop_iniciar_suite_alone_passes_through_without_defaults(self, srv, private):
        pl = private("l.json", {"suite": "mecanismo"})
        out = C.content("loop_iniciar", agent="julia", base_url=srv.url, payload_path=pl, confirm=True)
        assert out["status"] == "done" and srv.log[0][2] == {"suite": "mecanismo"}

    def test_loop_iniciar_validates_the_payload(self, srv, private):
        pl = private("l.json", {"suite": "x", "rodadas_planejadas": 5})
        assert C.content("loop_iniciar", agent="julia", base_url=srv.url, payload_path=pl)["codigo"] == "payload_invalido"
        pl = private("l2.json", {"suite": "mecanismo", "rodadas_planejadas": 5, "extra": 1})
        assert C.content("loop_iniciar", agent="julia", base_url=srv.url, payload_path=pl)["status"] == "error"
        assert srv.log == []

    def test_reads_need_no_confirm(self, srv, private):
        out = C.content("loops", agent="julia", base_url=srv.url, payload_path=private("f.json", {"suite": "mecanismo", "status": "ativo"}))
        assert out["status"] == "ok" and out["resultado"]["items"][0]["q"] == "suite=mecanismo&status=ativo"
        assert C.content("loop", agent="julia", base_url=srv.url, chave=LID)["resultado"]["id"] == LID
        run = C.content("run", agent="julia", base_url=srv.url, chave="44444444-4444-4444-8444-444444444444")
        assert run["resultado"]["resultados"][0]["veredito"] == "passou"
        mec = C.content("run", agent="julia", base_url=srv.url, chave=LID, payload_path=private("m.json", {"suite": "mecanismo"}))
        assert mec["requisicao"].endswith(f"/mecanismo-runs/{LID}")
        assert srv.writes() == []

    def test_chave_must_be_a_uuid(self, srv):
        assert C.content("loop", agent="julia", base_url=srv.url, chave="x")["codigo"] == "chave_invalida"
        assert C.content("run", agent="julia", base_url=srv.url)["codigo"] == "chave_invalida"

    def test_loop_parar(self, srv, private):
        assert C.content("loop_parar", agent="julia", base_url=srv.url, chave=LID)["status"] == "planned" and srv.log == []
        out = C.content("loop_parar", agent="julia", base_url=srv.url, chave=LID, confirm=True,
                        payload_path=private("s.json", {"motivo": "chega"}))
        assert out["resultado"]["motivo_parada"] == "parado_manualmente" and srv.log[0][2] == {"motivo": "chega"}

    def test_rodada_behaviour_uses_the_current_draft_version(self, srv, private):
        pl = private("r.json", {"suite": "comportamento", "loop_id": LID})
        out = C.content("rodada", agent="julia", base_url=srv.url, payload_path=pl)
        assert out["status"] == "planned" and srv.log == []
        out = C.content("rodada", agent="julia", base_url=srv.url, payload_path=pl, confirm=True)
        assert out["status"] == "started"
        assert srv.log[-1][:2] == ("POST", "/api/studio/agents/julia/evals/runs")
        assert srv.log[-1][2] == {"version_id": srv.draft_id, "loop_id": LID}

    def test_rodada_mecanismo_posts_with_loop_id_query(self, srv, private):
        pl = private("r.json", {"suite": "mecanismo"})
        out = C.content("rodada", agent="julia", base_url=srv.url, payload_path=pl, chave=LID, confirm=True)
        assert srv.log[-1][1] == f"/api/studio/agents/julia/draft/mecanismo-runs?loop_id={LID}"
        assert out["resultado"]["run_id"].startswith("5555")

    def test_gate_refusals_surface_code_and_detail_verbatim(self, srv, private):
        pl = private("r.json", {"suite": "comportamento", "loop_id": "33333333-3333-4333-8333-333333333333", "version_id": srv.draft_id})
        out = C.content("rodada", agent="julia", base_url=srv.url, payload_path=pl, confirm=True)
        assert out["status"] == "error" and out["codigo"] == "rodada_em_aberto"
        assert out["servidor"] == {"http": 409, "code": "rodada_em_aberto", "detail": "ha uma rodada aberta"}

    def test_evals_token_is_preferred_for_loop_actions(self, srv, monkeypatch):
        monkeypatch.setenv(C.ENV_EVALS_TOKEN, "pk_evals_other")
        out = C.content("loops", agent="julia", base_url=srv.url)
        assert out["codigo"] == "unauthorized" and "pk_evals_other" not in json.dumps(out)
