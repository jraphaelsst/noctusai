"""``noctus.agents.content`` -- the "Claude, change Julia's X" path (Julia v2 CONTRACT 2.5).

An agent's definition is DATA (CONTRACT D2/D3): sections, system texts, tool descriptions, decisions,
org-spec declarations, library skills (and their pins) and the qualification standard are rows in the agents
database. This tool writes those rows into a TARGET environment through the agents Studio API -- the same
validated, audited routes the Studio UI uses -- so a change is a DB write, visible on refresh.

Guarantees (each one is a test):

* **Drafts only, never publishes.** No publish route is ever called (a request to one is refused before it
  leaves the process); publishing stays a human act behind the eval gate.
* **Dry-run by default.** ``confirm=False`` only READS the target and returns a unified diff of what a write
  would change; ``confirm=True`` writes.
* **Content never enters git.** The JSON payload is read from a file OUTSIDE any git work tree (e.g.
  ``~/.noctusai/private/julia/...``); a path inside a repository is refused. Platform prompts are IP.
* **The token never leaves the process.** ``NOCTUS_AGENTS_CONTENT_TOKEN`` (the platform-only
  ``studio:content-write`` token, issuer ``noctus-platform``, minted by ``POST /api/studio/plataforma/content-token``)
  is read from the environment (or ``~/.config/noctus/agents.env``), sent only as a Bearer header to the
  target, and redacted from every returned string. Plain ``http`` is accepted for loopback only.
* **No silent partial writes.** A replace-set kind MERGES the payload into the current rows by default
  (``merge=True``); ``merge=False`` replaces the whole set and the diff shows every removal.

Payload (a JSON file, the exact request body of the underlying route):

====================  ==========================================================  =============================
kind                  payload                                                     route
====================  ==========================================================  =============================
``secao``             ``{"secoes": [{chave, titulo, ordem, conteudo, ativo}]}``   PUT agents/{agent}/draft/sections
``texto``             ``{"itens": [{chave, conteudo}]}``                          PUT .../draft/textos
``ferramenta``        ``{"itens": [{ferramenta, ativo, descricao, parametros,     PUT .../draft/ferramentas
                      obrigatoria_skill}]}``
``decisao``           ``{"itens": [{chave, titulo, regra, opcoes}]}``             PUT .../draft/decisoes
``spec``              ``{"itens": [{chave, rotulo, descricao, tipo, ...}]}``      PUT .../draft/specs
``skill``             ``{"itens": [{chave, nome, descricao_modelo, corpo,         /api/skills-biblioteca (draft)
                      arquivos: [{caminho, titulo, conteudo}]}]}``
``skill_ref``         ``{"itens": [{skill, versao?, obrigatoria_para, ordem}],    PUT .../draft/skills-biblioteca
                      "remover": [skill]}``
``padrao_criterio``   ``{"itens": [{chave, grupo, rotulo, tipo, ...}]}``          /api/qualificacao (draft)
``padrao_estagio``    ``{"itens": [{chave, rotulo, ordem, regra, ...}]}``         idem
``padrao_parametros`` the ParametrosIn body (an object)                           idem
``evals_mecanismo``   ``{"itens": [{slug, titulo, entrada, k, roteiro, asserts,   /api/studio/agents/{agent}/
                      tags, ativo}]}`` (mechanism cases; ``merge=False``          evals/cases
                      deactivates the ones left out)
``conformidade_regras`` ``{"itens": [{regra, ativo, politica, parametros}]}``     .../conformidade/regras/{regra}
====================  ==========================================================  =============================

``evals_mecanismo`` and ``conformidade_regras`` are not draft rows: a case is judged by the next mechanism run (nothing
is run here), and a rule applies from the next turn -- the dry-run diff is the review step. Both use the same platform
``studio:content-write`` token, are audited ``conteudo_editado_mcp`` and only ever touch the definition's own rows.

Lifecycle actions (no payload, no ``kind``; ``agent`` = the key; dry-run unless ``confirm=True``, like ``set``):

* ``criar_agente`` -- ``POST /api/studio/plataforma/agents``: the platform DEFINITION of ANY valid key (a DB row, never
  a code registry entry), as an EMPTY draft (an empty shell that grows over time; only publish is gated by
  completeness). Idempotent. ``payload_path`` (a JSON file OUTSIDE git, optional) carries the rest of the body:
  ``{nome (required for a NEW key), descricao?, runtime?, owner_product?, escopo_qualificacao?, padrao_qualificacao?,
  rascunho_padrao? ({provider, model, effort, max_turns, idioma, tool_policy}), instanciavel?, papel?
  (gerador|exemplar), briefing?, limite_usd?}``; with ``briefing`` an AI generation of the draft starts right away.
* ``configurar_agente`` -- ``PATCH /api/studio/plataforma/agents/{key}`` with the same data fields as a payload
  (runtime, owner product, qualification scope/standard, first-draft settings, role, instantiability); ``definicao``
  reads them back. Everything the old code registry carried is DATA here, set the way the UI sets it.
* ``gerar`` -- ``POST /api/studio/agents/{key}/geracoes``: an AI-generated first DRAFT from a briefing
  (``payload_path`` = ``{briefing, areas?, forcar?, limite_usd?}``; at most US$ 5 per run; the generator is the
  platform agent whose ``papel`` is ``gerador``). Dry-run makes NO request. Runs in the background; never publishes.
  ``geracao`` (``chave`` = the run id, empty = the list of runs) reads progress: per-area status, cost, lacunas, and
  which generated items are still ``gerado`` vs ``editado`` by the author.
* ``conceder`` -- ``POST /api/studio/plataforma/agents/{key}/grants`` with ``payload_path`` = ``{"org_id": "<uuid>"}``:
  the ONLY sanctioned way to give ONE org an instance of a closed (non-``instanciavel``) definition -- org/app
  configuration never reaches another org by default. Idempotent, audited; ``concessoes`` lists the granted orgs.
* ``excluir_agente`` -- ``DELETE /api/studio/agents/{key}``: needs the token minted with ``permitir_exclusao``
  (scope ``studio:agent-delete``); the server refuses (409 ``publicado`` / ``tem_instancias`` / ``tem_conversas`` /
  ``tem_canal`` / ``ativo``) anything that is published, in use or on. The audit rows survive the agent.

Neither publishes. Agent-scoped kinds need ``agent`` (the agent key, e.g. ``julia``); ``padrao_*`` need ``padrao`` (e.g.
``imob-lead``). Example (never inline a token)::

    NOCTUS_AGENTS_CONTENT_TOKEN=... noctus.agents.content(
        action="set", kind="texto", agent="julia",
        base_url="https://agents.noctusai.com",
        payload_path="~/.noctusai/private/julia/textos.json", confirm=False)
"""
from __future__ import annotations

import difflib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlsplit

import httpx

ENV_TOKEN = "NOCTUS_AGENTS_CONTENT_TOKEN"
ENV_URL = "NOCTUS_AGENTS_URL"
DEFAULT_ENV_FILE = Path("~/.config/noctus/agents.env")
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024
_HTTP_TIMEOUT = httpx.Timeout(60.0, connect=15.0)
ACTIONS = ("list", "get", "set")
LIFECYCLE_ACTIONS = (
    "criar_agente", "excluir_agente", "configurar_agente", "definicao", "gerar", "geracao", "conceder", "concessoes",
)
_DEFINICAO_CAMPOS = (
    "nome", "descricao", "runtime", "owner_product", "escopo_qualificacao", "padrao_qualificacao", "rascunho_padrao",
    "instanciavel", "papel",
)
_CRIAR_CAMPOS = (*_DEFINICAO_CAMPOS, "briefing", "limite_usd")
_GERAR_CAMPOS = ("briefing", "areas", "forcar", "limite_usd")
_AGENT_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})


class ContentError(Exception):
    """A refusal or failure with a machine code. The message is already free of the token."""

    def __init__(self, codigo: str, mensagem: str) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


# ── safety: URL, token, payload file ────────────────────────────────────────


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        k, _, v = line.partition("=")
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        out[k.strip()] = v
    return out


def _token() -> str:
    tok = os.environ.get(ENV_TOKEN, "").strip()
    if not tok:
        tok = _parse_env_file(Path(os.environ.get("NOCTUS_AGENTS_ENV_FILE") or DEFAULT_ENV_FILE).expanduser()).get(ENV_TOKEN, "").strip()
    if not tok:
        raise ContentError(
            "nao_configurado",
            f"{ENV_TOKEN} ausente (o token studio:content-write, emitido por POST /api/studio/plataforma/content-token). "
            "Defina no ambiente ou em ~/.config/noctus/agents.env.",
        )
    return tok


def _base_url(base_url: str | None) -> str:
    url = (base_url or os.environ.get(ENV_URL, "")).strip().rstrip("/")
    if not url:
        raise ContentError("base_url_ausente", "Informe base_url (o ambiente alvo) ou defina NOCTUS_AGENTS_URL.")
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.username or parts.password or not host:
        raise ContentError("base_url_invalida", "base_url invalida (sem credenciais na URL).")
    if parts.scheme == "https":
        return url
    if parts.scheme == "http" and host in LOOPBACK:
        return url
    raise ContentError("base_url_insegura", "base_url precisa ser https (http so para loopback): o token vai nela.")


def _inside_git(path: Path) -> bool:
    for parent in (path, *path.parents):
        if (parent / ".git").exists():
            return True
    return False


def _load_payload(payload_path: str | None) -> Any:
    if not payload_path:
        raise ContentError("payload_ausente", "Informe payload_path (um arquivo JSON fora do git).")
    p = Path(payload_path).expanduser()
    try:
        p = p.resolve(strict=True)
    except OSError:
        raise ContentError("payload_invalido", "Arquivo de payload nao encontrado.") from None
    if not p.is_file():
        raise ContentError("payload_invalido", "payload_path nao e um arquivo.")
    if _inside_git(p):
        raise ContentError(
            "payload_dentro_do_git",
            "O payload esta dentro de um repositorio git. Conteudo de agente e IP da plataforma: "
            "guarde-o fora do git (ex.: ~/.noctusai/private/julia/).",
        )
    if p.stat().st_size > MAX_PAYLOAD_BYTES:
        raise ContentError("payload_grande", "Payload acima de 2 MB.")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ContentError("payload_invalido", "O payload nao e um JSON valido.") from None


# ── HTTP ────────────────────────────────────────────────────────────────────


class _Api:
    def __init__(self, base: str, token: str, transport: httpx.BaseTransport | None) -> None:
        self._token = token
        self._client = httpx.Client(
            base_url=base, headers={"Authorization": f"Bearer {token}", "User-Agent": "Mozilla/5.0 (noctus-agents-content)"},
            timeout=_HTTP_TIMEOUT, transport=transport,
        )
        self.writes = 0

    def close(self) -> None:
        self._client.close()

    def _redact(self, text: str) -> str:
        return text.replace(self._token, "<token>") if self._token else text

    def call(self, method: str, path: str, body: Any = None, *, ok_404: bool = False) -> Any:
        if path.rstrip("/").endswith(("/publish", "/publicar")):
            # Structural, not a convention: this tool has no code path that publishes.
            raise ContentError("publicar_proibido", "Esta ferramenta nunca publica; publicar e um ato humano.")
        try:
            resp = self._client.request(method, path, json=body)
        except httpx.HTTPError as exc:
            raise ContentError("erro_de_rede", self._redact(f"{type(exc).__name__}: {exc}")[:300]) from None
        if method != "GET":
            self.writes += 1
        if resp.status_code == 404 and ok_404:
            return None
        if resp.status_code >= 400:
            codigo, detalhe = f"http_{resp.status_code}", ""
            try:
                data = resp.json()
                env = data.get("detail") if isinstance(data, dict) else None
                env = env if isinstance(env, dict) else data
                if isinstance(env, dict):
                    codigo = str(env.get("code") or codigo)
                    detalhe = str(env.get("detail") or "")
            except ValueError:
                pass
            raise ContentError(codigo, self._redact(f"{method} {path}: {resp.status_code} {detalhe}")[:300])
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()


def _q(segment: str) -> str:
    return quote(segment, safe="/")


# ── diff ────────────────────────────────────────────────────────────────────


def _dump(value: Any) -> list[str]:
    return [] if value is None else json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).splitlines()


def _diff(label: str, before: Any, after: Any) -> str:
    return "\n".join(difflib.unified_diff(_dump(before), _dump(after), f"db/{label}", f"payload/{label}", lineterm="", n=2))


def _change(chave: str, before: Any, after: Any) -> dict[str, Any]:
    op = "create" if before is None else ("remove" if after is None else ("unchanged" if before == after else "update"))
    return {"chave": chave, "op": op, "diff": "" if op == "unchanged" else _diff(chave, before, after)}


def _items(payload: Any, key: str = "itens") -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get(key), list) or not all(isinstance(i, dict) for i in payload[key]):
        raise ContentError("payload_invalido", f'O payload deve ser {{"{key}": [ ... ]}}.')
    return payload[key]


# ── replace-set kinds (secao / texto / ferramenta / decisao / spec) ─────────


class _ReplaceSet:
    def __init__(self, body_key: str, id_field: str, fields: tuple[str, ...], put_path: str, read: str) -> None:
        self.body_key, self.id_field, self.fields, self.put_path, self.read = body_key, id_field, fields, put_path, read

    def current(self, api: _Api, agent: str) -> dict[str, dict[str, Any]]:
        draft = api.call("GET", f"/api/studio/agents/{_q(agent)}/draft")
        if self.read == "draft":
            rows = draft.get("secoes", [])
        else:
            rows = api.call("GET", f"/api/studio/agents/{_q(agent)}/versions/{draft['id']}/{self.read}").get("itens", [])
        return {r[self.id_field]: {f: r.get(f) for f in self.fields} for r in rows}

    def plan(self, api: _Api, agent: str, payload: Any, merge: bool) -> tuple[list[dict[str, Any]], Callable[[], None] | None]:
        items = _items(payload, self.body_key)
        cur = self.current(api, agent)
        proposed: dict[str, dict[str, Any]] = {}
        for it in items:
            if self.id_field not in it:
                raise ContentError("payload_invalido", f"Cada item precisa de '{self.id_field}'.")
            unknown = set(it) - set(self.fields) - {self.id_field}
            if unknown:
                raise ContentError("payload_invalido", f"Campos desconhecidos: {', '.join(sorted(unknown))}.")
            base = dict(cur.get(it[self.id_field]) or {})
            proposed[it[self.id_field]] = {**base, **{k: v for k, v in it.items() if k != self.id_field}}
        changes = []
        for chave, new in proposed.items():
            old = cur.get(chave)
            # compare only the fields the payload touches: a field the author left out is not a change
            touched = {k for it in items if it[self.id_field] == chave for k in it if k != self.id_field}
            before = None if old is None else {k: old.get(k) for k in touched}
            changes.append(_change(chave, before, {k: new.get(k) for k in touched} if old is not None else new))
        if not merge:
            changes += [_change(chave, old, None) for chave, old in cur.items() if chave not in proposed]
        if all(c["op"] == "unchanged" for c in changes):
            return changes, None
        final = {**({} if not merge else cur), **proposed}
        body = [{self.id_field: k, **v} for k, v in final.items()]

        def apply() -> None:
            api.call("PUT", f"/api/studio/agents/{_q(agent)}/draft/{self.put_path}", {self.body_key: body})

        return changes, apply

    def listing(self, api: _Api, agent: str) -> list[str]:
        return sorted(self.current(api, agent))


# ── library skills ──────────────────────────────────────────────────────────


class _Skill:
    def _base(self, api: _Api, chave: str) -> tuple[dict | None, dict | None, dict | None]:
        """(library row, working version id row {id,status,versao}, its detail)."""
        lib = next((s for s in api.call("GET", "/api/skills-biblioteca")["items"] if s["chave"] == chave), None)
        if lib is None:
            return None, None, None
        versoes = api.call("GET", f"/api/skills-biblioteca/{_q(chave)}/versoes")["items"]
        rasc = next((v for v in versoes if v["status"] == "rascunho"), None)
        base = rasc or (max(versoes, key=lambda v: v["versao"]) if versoes else None)
        detail = api.call("GET", f"/api/skills-biblioteca/versoes/{base['id']}") if base else None
        return lib, base, detail

    @staticmethod
    def _view(lib: dict, detail: dict | None) -> dict[str, Any]:
        d = detail or {}
        return {
            "nome": lib["nome"], "descricao": lib.get("descricao"),
            "descricao_modelo": d.get("descricao_modelo", ""), "corpo": d.get("corpo", ""),
            "arquivos": {a["caminho"]: {"titulo": a.get("titulo"), "conteudo": a["conteudo"]} for a in d.get("arquivos", [])},
        }

    def plan(self, api: _Api, _agent: str | None, payload: Any, _merge: bool):
        items = _items(payload)
        changes: list[dict[str, Any]] = []
        steps: list[Callable[[], None]] = []
        for it in items:
            chave = it.get("chave")
            if not isinstance(chave, str):
                raise ContentError("payload_invalido", "Cada skill precisa de 'chave'.")
            unknown = set(it) - {"chave", "nome", "descricao", "descricao_modelo", "corpo", "notas", "arquivos"}
            if unknown:
                raise ContentError("payload_invalido", f"Campos desconhecidos: {', '.join(sorted(unknown))}.")
            lib, base, detail = self._base(api, chave)
            files = {a["caminho"]: {"titulo": a.get("titulo"), "conteudo": a.get("conteudo", "")} for a in it.get("arquivos", [])}
            if lib is None and not isinstance(it.get("nome"), str):
                raise ContentError("nome_obrigatorio", f"A skill nova '{chave}' precisa de 'nome'.")
            cur = None if lib is None else self._view(lib, detail)
            touched = {k: it[k] for k in ("nome", "descricao", "descricao_modelo", "corpo") if k in it}
            if files:
                touched["arquivos"] = files
            before = None if cur is None else {k: ({p: cur["arquivos"].get(p) for p in files} if k == "arquivos" else cur.get(k)) for k in touched}
            ch = _change(chave, before, touched)
            changes.append(ch)
            if ch["op"] == "unchanged":
                continue
            steps.append(self._apply(api, chave, it, lib, base, touched, files))
        if not steps:
            return changes, None

        def apply() -> None:
            for step in steps:
                step()

        return changes, apply

    def _apply(self, api: _Api, chave: str, it: dict, lib, base, touched: dict, files: dict) -> Callable[[], None]:
        def run() -> None:
            if lib is None:
                api.call("POST", "/api/skills-biblioteca", {"chave": chave, "nome": it["nome"], "descricao": it.get("descricao")})
            elif "nome" in touched or "descricao" in touched:
                patch = {k: touched[k] for k in ("nome", "descricao") if k in touched}
                if any(lib.get(k) != v for k, v in patch.items()):
                    api.call("PATCH", f"/api/skills-biblioteca/{_q(chave)}", patch)
            texto = {k: touched[k] for k in ("descricao_modelo", "corpo") if k in touched}
            if "notas" in it:
                texto["notas"] = it["notas"]
            if not texto and not files:
                return
            rasc = base if base and base["status"] == "rascunho" else None
            if rasc is None:
                novo = api.call("POST", f"/api/skills-biblioteca/{_q(chave)}/versoes", {"copiar_de": base["id"] if base else None})
                vid = novo["id"]
            else:
                vid = rasc["id"]
            if texto:
                api.call("PATCH", f"/api/skills-biblioteca/versoes/{vid}", texto)
            for caminho, f in files.items():
                api.call("PUT", f"/api/skills-biblioteca/versoes/{vid}/arquivos/{_q(caminho)}", f)

        return run

    def listing(self, api: _Api, _agent: str | None) -> list[Any]:
        return [
            {"chave": s["chave"], "versao_publicada": s.get("versao_publicada"), "tem_rascunho": s.get("tem_rascunho")}
            for s in api.call("GET", "/api/skills-biblioteca")["items"]
        ]

    def read(self, api: _Api, chave: str | None) -> Any:
        out = {}
        for s in api.call("GET", "/api/skills-biblioteca")["items"]:
            if chave is None or s["chave"] == chave:
                lib, _base, detail = self._base(api, s["chave"])
                out[s["chave"]] = self._view(lib, detail)
        return out


# ── pins of library skills on an agent draft ────────────────────────────────


class _SkillRef:
    def _current(self, api: _Api, agent: str) -> dict[str, dict[str, Any]]:
        got = api.call("GET", f"/api/studio/agents/{_q(agent)}/draft/skills-biblioteca")
        return {i["skill"]: i for i in got["items"]}

    def plan(self, api: _Api, agent: str, payload: Any, _merge: bool):
        items = _items(payload)
        remover = payload.get("remover", []) if isinstance(payload, dict) else []
        if not isinstance(remover, list) or not all(isinstance(r, str) for r in remover):
            raise ContentError("payload_invalido", "'remover' deve ser uma lista de chaves de skill.")
        cur = self._current(api, agent)
        changes, steps = [], []
        for it in items:
            skill = it.get("skill")
            if not isinstance(skill, str):
                raise ContentError("payload_invalido", "Cada pin precisa de 'skill'.")
            unknown = set(it) - {"skill", "versao", "obrigatoria_para", "ordem"}
            if unknown:
                raise ContentError("payload_invalido", f"Campos desconhecidos: {', '.join(sorted(unknown))}.")
            old = cur.get(skill)
            touched = {k: v for k, v in it.items() if k != "skill"}
            before = None if old is None else {k: old.get({"versao": "versao"}.get(k, k)) for k in touched}
            ch = _change(skill, before, touched)
            changes.append(ch)
            if ch["op"] != "unchanged":
                body = {"obrigatoria_para": (old or {}).get("obrigatoria_para", []), "ordem": (old or {}).get("ordem", 0), **touched}
                steps.append(("PUT", f"/api/studio/agents/{_q(agent)}/draft/skills-biblioteca/{_q(skill)}", body))
        for skill in remover:
            changes.append(_change(skill, cur.get(skill), None) if skill in cur else {"chave": skill, "op": "unchanged", "diff": ""})
            if skill in cur:
                steps.append(("DELETE", f"/api/studio/agents/{_q(agent)}/draft/skills-biblioteca/{_q(skill)}", None))
        if not steps:
            return changes, None

        def apply() -> None:
            for method, path, body in steps:
                api.call(method, path, body)

        return changes, apply

    def listing(self, api: _Api, agent: str) -> list[Any]:
        return [
            {"skill": k, "versao": v["versao"], "nova_versao": v.get("nova_versao")} for k, v in sorted(self._current(api, agent).items())
        ]

    def read(self, api: _Api, agent: str, chave: str | None) -> Any:
        return {k: v for k, v in self._current(api, agent).items() if chave in (None, k)}


# ── the qualification standard (criteria / stages / parameters) ─────────────

_CRITERIO_FIELDS = ("grupo", "rotulo", "descricao_modelo", "tipo", "opcoes", "unidade", "sensivel", "pontuacao", "ordem", "ativo", "eixo", "escopo", "validade_dias")
_ESTAGIO_FIELDS = ("rotulo", "descricao", "ordem", "regra", "conclusivo", "terminal")
_PARAM_FIELDS = ("minimo_para_ofertar", "lote_ofertas", "score_max", "eixos", "pedir_identificacao_quando")


def _norm_opcoes(opcoes: Any) -> Any:
    if not isinstance(opcoes, list):
        return opcoes
    return [
        {"valor": o.get("valor"), "rotulo": o.get("rotulo", ""), "descricao_modelo": o.get("descricao_modelo", ""),
         "sinonimos": list(o.get("sinonimos") or [])} if isinstance(o, dict) else o
        for o in opcoes
    ]


class _Padrao:
    def __init__(self, what: str) -> None:
        self.what = what  # "criterios" | "estagios" | "parametros"
        self.fields = {"criterios": _CRITERIO_FIELDS, "estagios": _ESTAGIO_FIELDS, "parametros": _PARAM_FIELDS}[what]

    def _version(self, api: _Api, padrao: str) -> tuple[dict, dict]:
        versoes = api.call("GET", f"/api/qualificacao/padroes/{_q(padrao)}/versoes", ok_404=True)
        if versoes is None or not versoes["items"]:
            raise ContentError("padrao_inexistente", f"O padrao '{padrao}' nao existe ou nao tem versao.")
        items = versoes["items"]
        base = next((v for v in items if v["status"] == "rascunho"), None) or max(items, key=lambda v: v["versao"])
        return base, api.call("GET", f"/api/qualificacao/versoes/{base['id']}")

    def _rows(self, detail: dict) -> dict[str, dict[str, Any]]:
        if self.what == "parametros":
            return {"parametros": {f: detail["parametros"].get(f) for f in self.fields}}
        return {r["chave"]: {f: r.get(f) for f in self.fields} for r in detail[self.what]}

    def plan(self, api: _Api, padrao: str, payload: Any, _merge: bool):
        base, detail = self._version(api, padrao)
        cur = self._rows(detail)
        if self.what == "parametros":
            if not isinstance(payload, dict):
                raise ContentError("payload_invalido", "O payload de parametros deve ser um objeto.")
            wanted = {"parametros": payload}
        else:
            wanted = {}
            for it in _items(payload):
                if not isinstance(it.get("chave"), str):
                    raise ContentError("payload_invalido", "Cada item precisa de 'chave'.")
                wanted[it["chave"]] = {k: v for k, v in it.items() if k != "chave"}
        changes, puts = [], []
        for chave, item in wanted.items():
            unknown = set(item) - set(self.fields)
            if unknown:
                raise ContentError("payload_invalido", f"Campos desconhecidos: {', '.join(sorted(unknown))}.")
            old = cur.get(chave)
            if "opcoes" in item:
                item = {**item, "opcoes": _norm_opcoes(item["opcoes"])}
            before = None if old is None else {k: (_norm_opcoes(old[k]) if k == "opcoes" else old[k]) for k in item}
            ch = _change(chave, before, item)
            changes.append(ch)
            if ch["op"] != "unchanged":
                merged = {**{k: v for k, v in (old or {}).items() if v is not None or k in item}, **item}
                if "opcoes" in merged:
                    merged["opcoes"] = _norm_opcoes(merged["opcoes"])
                puts.append((chave, merged))
        if not puts:
            return changes, None

        def apply() -> None:
            vid = base["id"]
            if base["status"] != "rascunho":
                vid = api.call("POST", f"/api/qualificacao/padroes/{_q(padrao)}/versoes", {"copiar_de": base["id"]})["id"]
            for chave, body in puts:
                path = "parametros" if self.what == "parametros" else f"{self.what}/{_q(chave)}"
                api.call("PUT", f"/api/qualificacao/versoes/{vid}/{path}", body)

        return changes, apply

    def listing(self, api: _Api, padrao: str) -> list[str]:
        return sorted(self._rows(self._version(api, padrao)[1]))

    def read(self, api: _Api, padrao: str, chave: str | None) -> Any:
        return {k: v for k, v in self._rows(self._version(api, padrao)[1]).items() if chave in (None, k)}


# ── mechanism eval cases (the publish gate's scripted suite) ────────────────

_CASO_FIELDS = ("titulo", "entrada", "k", "roteiro", "asserts", "tags", "ativo")
_CASO_NOVO = ("titulo", "entrada", "roteiro", "asserts")


class _EvalsMecanismo:
    """The ``mecanismo`` eval cases of an agent (``/api/studio/agents/{agent}/evals/cases``), keyed by ``slug``.
    Not versioned: a case is judged by the NEXT mechanism run; nothing here starts a run or publishes. Fixtures are
    synthetic (the server refuses personal data; ``[[cpf_sintetico_valido]]`` / ``[[email_sintetico]]`` tokens are
    the way to script identity). ``merge=False`` DEACTIVATES the cases left out (a case with results cannot be
    deleted, and deleting stays a human act)."""

    def _rows(self, api: _Api, agent: str) -> dict[str, dict[str, Any]]:
        got = api.call("GET", f"/api/studio/agents/{_q(agent)}/evals/cases")["items"]
        return {c["slug"]: c for c in got if c.get("suite") == "mecanismo"}

    def current(self, api: _Api, agent: str) -> dict[str, dict[str, Any]]:
        return {k: {f: v.get(f) for f in _CASO_FIELDS} for k, v in self._rows(api, agent).items()}

    def plan(self, api: _Api, agent: str, payload: Any, merge: bool):
        items = _items(payload)
        rows = self._rows(api, agent)
        changes: list[dict[str, Any]] = []
        steps: list[tuple[str, str, dict[str, Any]]] = []
        base = f"/api/studio/agents/{_q(agent)}/evals/cases"
        vistos: set[str] = set()
        for it in items:
            slug = it.get("slug")
            if not isinstance(slug, str) or not slug:
                raise ContentError("payload_invalido", "Cada caso precisa de 'slug'.")
            unknown = set(it) - set(_CASO_FIELDS) - {"slug"}
            if unknown:
                raise ContentError("payload_invalido", f"Campos desconhecidos: {', '.join(sorted(unknown))}.")
            vistos.add(slug)
            touched = {k: v for k, v in it.items() if k != "slug"}
            old = rows.get(slug)
            if old is None:
                faltam = [f for f in _CASO_NOVO if f not in touched]
                if faltam:
                    raise ContentError("caso_incompleto", f"O caso novo '{slug}' precisa de: {', '.join(faltam)}.")
                ch = _change(slug, None, touched)
                steps.append(("POST", base, {"slug": slug, "suite": "mecanismo", **touched}))
            else:
                ch = _change(slug, {k: old.get(k) for k in touched}, touched)
                if ch["op"] != "unchanged":
                    steps.append(("PATCH", f"{base}/{_q(old['id'])}", touched))
            changes.append(ch)
        if not merge:
            for slug, old in rows.items():
                if slug not in vistos and old.get("ativo"):
                    changes.append({**_change(slug, {"ativo": True}, {"ativo": False}), "op": "deactivate"})
                    steps.append(("PATCH", f"{base}/{_q(old['id'])}", {"ativo": False}))
        if not steps:
            return changes, None

        def apply() -> None:
            for method, path, body in steps:
                api.call(method, path, body)

        return changes, apply

    def listing(self, api: _Api, agent: str) -> list[str]:
        return sorted(self._rows(api, agent))


# ── conformance rules (switches of the deterministic output checks) ─────────

_REGRA_FIELDS = ("ativo", "politica", "parametros")


class _ConformidadeRegras:
    """The conformance rules of an agent's DEFINITION row (``/api/studio/agents/{agent}/conformidade/regras``),
    keyed by ``regra``. The rule set is fixed by code (an unknown rule is refused) and the rows are NOT versioned: a
    confirmed write applies from the next turn -- the dry-run diff is the review step. Never another org's row."""

    def current(self, api: _Api, agent: str) -> dict[str, dict[str, Any]]:
        got = api.call("GET", f"/api/studio/agents/{_q(agent)}/conformidade/regras")["items"]
        return {r["regra"]: {f: r.get(f) for f in _REGRA_FIELDS} for r in got}

    def plan(self, api: _Api, agent: str, payload: Any, merge: bool):
        if not merge:
            raise ContentError("merge_invalido", "As regras de conformidade são um conjunto fixo: use merge=True.")
        items = _items(payload)
        cur = self.current(api, agent)
        changes, steps = [], []
        for it in items:
            regra = it.get("regra")
            if not isinstance(regra, str) or regra not in cur:
                raise ContentError("regra_desconhecida", f"Regra desconhecida: {regra!r}.")
            unknown = set(it) - set(_REGRA_FIELDS) - {"regra"}
            if unknown:
                raise ContentError("payload_invalido", f"Campos desconhecidos: {', '.join(sorted(unknown))}.")
            touched = {k: v for k, v in it.items() if k != "regra"}
            ch = _change(regra, {k: cur[regra].get(k) for k in touched}, touched)
            changes.append(ch)
            if ch["op"] != "unchanged":
                steps.append((f"/api/studio/agents/{_q(agent)}/conformidade/regras/{_q(regra)}", touched))
        if not steps:
            return changes, None

        def apply() -> None:
            for path, body in steps:
                api.call("PUT", path, body)

        return changes, apply

    def listing(self, api: _Api, agent: str) -> list[str]:
        return sorted(self.current(api, agent))


# ── dispatch ────────────────────────────────────────────────────────────────

_REPLACE_SETS: dict[str, _ReplaceSet] = {
    "secao": _ReplaceSet("secoes", "chave", ("titulo", "ordem", "conteudo", "ativo"), "sections", "draft"),
    "texto": _ReplaceSet("itens", "chave", ("conteudo",), "textos", "textos"),
    "ferramenta": _ReplaceSet("itens", "ferramenta", ("ativo", "descricao", "parametros", "obrigatoria_skill"), "ferramentas", "ferramentas"),
    "decisao": _ReplaceSet("itens", "chave", ("titulo", "regra", "opcoes"), "decisoes", "decisoes"),
    "spec": _ReplaceSet("itens", "chave", ("rotulo", "descricao", "tipo", "obrigatoria", "exemplo"), "specs", "specs"),
}
_SKILL, _SKILL_REF = _Skill(), _SkillRef()
_PADRAO = {"padrao_criterio": _Padrao("criterios"), "padrao_estagio": _Padrao("estagios"), "padrao_parametros": _Padrao("parametros")}
#: Agent-scoped kinds that are NOT draft rows: what a confirmed write does, said in the result.
_AGENTE = {"evals_mecanismo": _EvalsMecanismo(), "conformidade_regras": _ConformidadeRegras()}
_EFEITO = {
    "evals_mecanismo": "Casos gravados: valem na PRÓXIMA execução da suíte mecanismo. Nada foi executado nem publicado.",
    "conformidade_regras": "Regras não são versionadas: valem a partir do próximo turno. Nada foi publicado.",
}
KINDS = (*_REPLACE_SETS, "skill", "skill_ref", *_PADRAO, *_AGENTE)


def content(
    action: str, kind: str | None = None, agent: str | None = None, padrao: str | None = None, chave: str | None = None,
    payload_path: str | None = None, base_url: str | None = None, confirm: bool = False, merge: bool = True,
    *, _transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """List / get / set an agent's content rows in the target environment. See the module docstring."""
    try:
        if action in LIFECYCLE_ACTIONS:
            return _lifecycle(action, agent, base_url, bool(confirm), _transport, payload_path=payload_path, chave=chave)
        if action not in ACTIONS:
            raise ContentError(
                "acao_invalida", f"action deve ser um de {(*ACTIONS, *LIFECYCLE_ACTIONS)} (esta ferramenta nunca publica).",
            )
        if kind not in KINDS:
            raise ContentError("kind_invalido", f"kind deve ser um de {KINDS}.")
        scoped = kind in _REPLACE_SETS or kind == "skill_ref" or kind in _AGENTE
        if scoped and not agent:
            raise ContentError("agent_ausente", f"O kind '{kind}' precisa de 'agent' (a chave do agente).")
        if kind in _PADRAO and not padrao:
            raise ContentError("padrao_ausente", f"O kind '{kind}' precisa de 'padrao' (ex.: imob-lead).")
        payload = _load_payload(payload_path) if action == "set" else None  # fail before any network I/O
        base = _base_url(base_url)
        token = _token()
        api = _Api(base, token, _transport)
        try:
            return _run(api, action, kind, agent, padrao, chave, payload, bool(confirm), bool(merge), base)
        finally:
            api.close()
    except ContentError as exc:
        return {"status": "error", "codigo": exc.codigo, "mensagem": exc.mensagem}


def _only(payload: Any, allowed: tuple[str, ...], what: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ContentError("payload_invalido", f"O payload de {what} deve ser um objeto JSON.")
    extra = sorted(set(payload) - set(allowed))
    if extra:
        raise ContentError("payload_invalido", f"Campos desconhecidos em {what}: {extra}. Permitidos: {list(allowed)}.")
    return payload


def _lifecycle(
    action: str, agent: str | None, base_url: str | None, confirm: bool, transport: httpx.BaseTransport | None, *,
    payload_path: str | None = None, chave: str | None = None,
) -> dict[str, Any]:
    """The agent lifecycle + AI generation actions: one route each. The dry-run makes NO request -- the server's guards
    (published / instances / conversations / channel / on; the cap, the generator, edited content) are re-checked at the
    confirmed call, so a pre-read here would only be a second, stale opinion."""
    if not agent or not _AGENT_KEY_RE.match(agent):
        raise ContentError("agent_invalido", "Informe 'agent' (a chave do agente: letras, digitos, '_', '-', '.').")
    reading = action in ("definicao", "geracao", "concessoes")
    body: Any = None
    if action == "criar_agente":
        body = {"key": agent, **(_only(_load_payload(payload_path), _CRIAR_CAMPOS, "criar_agente") if payload_path else {})}
        method, path = "POST", "/api/studio/plataforma/agents"
    elif action == "configurar_agente":
        body = _only(_load_payload(payload_path), _DEFINICAO_CAMPOS, "configurar_agente")
        method, path = "PATCH", f"/api/studio/plataforma/agents/{_q(agent)}"
    elif action == "definicao":
        method, path = "GET", f"/api/studio/plataforma/agents/{_q(agent)}"
    elif action == "gerar":
        body = _only(_load_payload(payload_path), _GERAR_CAMPOS, "gerar")
        if not isinstance(body.get("briefing"), dict):
            raise ContentError("payload_invalido", "O payload de gerar precisa de 'briefing' (objeto).")
        method, path = "POST", f"/api/studio/agents/{_q(agent)}/geracoes"
    elif action == "conceder":
        body = _only(_load_payload(payload_path), ("org_id",), "conceder")
        if not isinstance(body.get("org_id"), str) or not re.fullmatch(r"[0-9a-fA-F-]{36}", body["org_id"]):
            raise ContentError("payload_invalido", "O payload de conceder precisa de 'org_id' (uuid da organização).")
        method, path = "POST", f"/api/studio/plataforma/agents/{_q(agent)}/grants"
    elif action == "concessoes":
        method, path = "GET", f"/api/studio/plataforma/agents/{_q(agent)}/grants"
    elif action == "geracao":
        if chave and not re.fullmatch(r"[0-9a-fA-F-]{36}", chave):
            raise ContentError("chave_invalida", "chave deve ser o id (uuid) da geracao, ou vazia para listar.")
        method, path = "GET", f"/api/studio/agents/{_q(agent)}/geracoes" + (f"/{chave}" if chave else "")
    else:  # excluir_agente
        method, path = "DELETE", f"/api/studio/agents/{_q(agent)}"
    base = _base_url(base_url)
    token = _token()
    head = {"action": action, "agent": agent, "alvo": base, "requisicao": f"{method} {path}"}
    if not reading and not confirm:
        planned = {
            "criar_agente": "Cria a definição vazia (rascunho sem texto); com briefing no payload, também inicia a geração.",
            "configurar_agente": "Atualiza os dados da definição (runtime, produto, padrão de qualificação, rascunho padrão, papel...).",
            "conceder": "Concede à organização do payload o direito de ter uma INSTÂNCIA deste agente (idempotente; auditado).",
            "gerar": "Inicia a geração por IA do RASCUNHO (no máximo US$ 5 por execução; roda em segundo plano; nada é publicado).",
        }.get(action, "Exige token com permitir_exclusao (studio:agent-delete); o servidor recusa agente publicado, com instâncias, "
                      "com conversas, com canal ativo ou ligado.")
        out = {"status": "planned", **head, "dry_run": True, "mensagem": "Nada foi feito. Repita com confirm=True. " + planned}
        if isinstance(body, dict) and body:
            out["campos"] = sorted(body)  # the field NAMES only: a briefing / settings are not echoed
        return out
    api = _Api(base, token, transport)
    try:
        result = api.call(method, path, body)
    finally:
        api.close()
    if reading:
        return {"status": "ok", **head, "dry_run": False, "resultado": result}
    if action == "criar_agente":
        return {"status": "created", **head, "dry_run": False, "agente": result,
                "mensagem": "Definição criada como rascunho VAZIO (idempotente). Nada foi publicado."}
    if action == "configurar_agente":
        return {"status": "updated", **head, "dry_run": False, "agente": result,
                "mensagem": "Dados da definição atualizados. Instâncias já criadas mantêm o runtime/produto com que nasceram."}
    if action == "conceder":
        return {"status": "granted", **head, "dry_run": False, "concessoes": result,
                "mensagem": "Concessão registrada. A organização passa a poder ter uma instância (criada no primeiro uso)."}
    if action == "gerar":
        return {"status": "started", **head, "dry_run": False, "geracao": result,
                "mensagem": "Geração iniciada em segundo plano (rascunho; nada publicado). Acompanhe com action=geracao."}
    return {"status": "deleted", **head, "dry_run": False,
            "mensagem": "Agente excluído; a auditoria permanece (agent_id nulo + registro agente_excluido)."}


def _run(api: _Api, action: str, kind: str, agent, padrao, chave, payload, confirm: bool, merge: bool, base: str) -> dict[str, Any]:
    head = {"kind": kind, "agent": agent, "padrao": padrao, "alvo": base}
    if kind in _REPLACE_SETS:
        impl, scope = _REPLACE_SETS[kind], agent
    elif kind == "skill":
        impl, scope = _SKILL, None
    elif kind == "skill_ref":
        impl, scope = _SKILL_REF, agent
    elif kind in _AGENTE:
        impl, scope = _AGENTE[kind], agent
    else:
        impl, scope = _PADRAO[kind], padrao

    if action == "list":
        return {"status": "ok", **head, "itens": impl.listing(api, scope)}
    if action == "get":
        if kind in _REPLACE_SETS or kind in _AGENTE:
            rows = impl.current(api, scope)
            data = {k: v for k, v in rows.items() if chave in (None, k)}
        elif kind == "skill":
            data = impl.read(api, chave)
        else:
            data = impl.read(api, scope, chave)
        return {"status": "ok", **head, "itens": data}

    changes, apply = impl.plan(api, scope, payload, merge)
    if apply is None:
        return {"status": "no_change", **head, "mudancas": changes, "dry_run": not confirm}
    if not confirm:
        return {"status": "planned", **head, "mudancas": changes, "dry_run": True,
                "mensagem": "Nada foi escrito. Repita com confirm=True para gravar o RASCUNHO."}
    apply()
    return {"status": "written", **head, "mudancas": changes, "dry_run": False, "escritas": api.writes,
            "mensagem": _EFEITO.get(kind, "Rascunho atualizado. Publicar e um ato humano (eval gate).")}


def register(server) -> None:
    """Register ``noctus.agents.content``."""

    @server.tool(
        name="noctus.agents.content",
        description=(
            "Write an agent's CONTENT rows (the 'Claude, change Julia's X' path) into a target environment through the "
            "agents Studio API, DRAFTS ONLY (never publishes). action=list|get|set; kind=secao|texto|ferramenta|decisao|"
            "spec (need agent=<key>), skill|skill_ref (library skills / pins on the agent draft), padrao_criterio|"
            "padrao_estagio|padrao_parametros (need padrao=<key>), evals_mecanismo (mechanism eval cases) | "
            "conformidade_regras (rule switches; NOT versioned - live from the next turn) (need agent=<key>). Lifecycle: "
            "action=criar_agente (agent=<any valid key>: creates the EMPTY platform definition; optional payload_path with nome, "
            "runtime, owner_product, escopo/padrao_qualificacao, rascunho_padrao, instanciavel, papel and a briefing that "
            "also starts an AI generation) | configurar_agente (payload_path: the same data fields, PATCH) | definicao "
            "(reads them) | gerar (payload_path = {briefing, areas?, forcar?, limite_usd? <= 5}: AI-generated first DRAFT, "
            "background, never publishes) | geracao (chave = run id, empty = list: progress, cost, lacunas, gerado vs "
            "editado) | excluir_agente (agent=<key>: deletes it; needs a token minted with permitir_exclusao; the server "
            "refuses published/in-use/on agents) - writes are dry-run unless confirm=True. set reads a JSON payload from payload_path (a file "
            "OUTSIDE git) and is a DRY-RUN returning a unified diff unless confirm=True. Token from "
            "NOCTUS_AGENTS_CONTENT_TOKEN (studio:content-write), never echoed. base_url = the target environment "
            "(https, or http on loopback)."
        ),
    )
    def _content(
        action: str, kind: str = "", base_url: str = "", agent: str = "", padrao: str = "", chave: str = "",
        payload_path: str = "", confirm: bool = False, merge: bool = True,
    ) -> dict:
        return content(
            action, kind, agent=agent or None, padrao=padrao or None, chave=chave or None,
            payload_path=payload_path or None, base_url=base_url or None, confirm=confirm, merge=merge,
        )
