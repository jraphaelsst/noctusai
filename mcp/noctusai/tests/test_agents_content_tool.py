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

        def _route(self, m: str, path: str, b):
            A = r"/api/studio/agents/julia"
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
