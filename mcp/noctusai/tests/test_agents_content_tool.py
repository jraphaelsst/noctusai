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
                return self._send(200, {"id": state.draft_id, "secoes": state.secoes})
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
            # conformance rules
            if m == "GET" and path == f"{A}/conformidade/regras":
                return self._send(200, {"items": list(state.regras.values())})
            mo = re.fullmatch(rf"{A}/conformidade/regras/([a-z_]+)", path)
            if mo and m == "PUT" and mo.group(1) in state.regras:
                state.regras[mo.group(1)].update({k: v for k, v in b.items() if v is not None})
                return self._send(200, state.regras[mo.group(1)])
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

    def test_conformance_rules_dry_run_then_write_and_say_it_is_live(self, srv, private):
        payload = {"itens": [{"regra": "termina_sem_pergunta", "ativo": False}]}
        plan = run(srv, private, payload, action="set", kind="conformidade_regras", agent="julia")
        assert plan["status"] == "planned" and plan["mudancas"][0]["op"] == "update" and srv.writes() == []
        out = run(srv, private, payload, action="set", kind="conformidade_regras", agent="julia", confirm=True)
        assert out["status"] == "written" and "próximo turno" in out["mensagem"]
        assert srv.writes() == [("PUT", "/api/studio/agents/julia/conformidade/regras/termina_sem_pergunta")]
        assert srv.regras["termina_sem_pergunta"]["ativo"] is False
        got = run(srv, private, action="get", kind="conformidade_regras", agent="julia", chave="termina_sem_pergunta")
        assert got["itens"] == {"termina_sem_pergunta": {"ativo": False, "politica": "registrar", "parametros": {}}}

    @pytest.mark.parametrize("payload,merge,codigo", [
        ({"itens": [{"regra": "inventada", "ativo": True}]}, True, "regra_desconhecida"),
        ({"itens": [{"regra": "vazamento_prompt", "texto": "x"}]}, True, "payload_invalido"),
        ({"itens": [{"regra": "vazamento_prompt", "ativo": True}]}, False, "merge_invalido"),
    ])
    def test_conformance_rules_refuse_unknowns(self, srv, private, payload, merge, codigo):
        out = run(srv, private, payload, action="set", kind="conformidade_regras", agent="julia", merge=merge)
        assert out["status"] == "error" and out["codigo"] == codigo and srv.writes() == []

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
        assert [(m, p, b) for m, p, b, _a in srv.log] == [("POST", "/api/studio/plataforma/agents", {"key": "julia"})]
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
        assert srv.log[0][2] == {"key": "novo-agente", **body}
        assert run(srv, private, {"nome": "x", "inventado": 1}, action="criar_agente", agent="k")["codigo"] == "payload_invalido"

    def test_configurar_agente_patches_and_definicao_reads(self, srv, private):
        plan = run(srv, private, {"papel": "exemplar"}, action="configurar_agente", agent="novo")
        assert plan["status"] == "planned" and srv.log == []
        out = run(srv, private, {"papel": "exemplar"}, action="configurar_agente", agent="novo", confirm=True)
        assert out["status"] == "updated" and out["agente"]["papel"] == "exemplar"
        assert srv.log[-1][:3] == ("PATCH", "/api/studio/plataforma/agents/novo", {"papel": "exemplar"})
        got = C.content("definicao", agent="novo", base_url=srv.url)
        assert got["status"] == "ok" and got["resultado"]["key"] == "novo"
