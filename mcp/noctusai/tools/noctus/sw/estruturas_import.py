"""``noctus.sw.estruturas_import`` — load the two Estruturas files into the platform library, from the toolkit.

  action="plan"    POST /api/media-creation/estruturas/importacoes (dry_run=true) -> the ImportacaoRelatorio of a SIMULATION: counts and
                   coded reasons only. The server writes nothing but the ``simulada`` lote row.
  action="apply"   needs ``confirm=True``; POST (dry_run=false). The server refuses (409 ``simulacao_obrigatoria``) unless a ``plan`` of the SAME
                   file (same sha256, same ``fonte``) ran within the last 24 h, and (409 ``importacao_em_andamento``) while another run is open.
                   Returns the run id; the job ``estruturas.importar`` does the writing.
  action="status"  GET the run (``importacao_id``) or, without one, the latest runs. Poll until status is concluida / falhou.

``fonte`` = "referencia" (the only source; any other is refused locally with the server's code, arquivo_invalido / fonte_nao_suportada); ``arquivo`` = a local path (default: the owner's private directory, see ``DIRETORIO_PADRAO``).
Idempotent by construction (the same file twice is all ``estruturas_inalteradas``).

PRIVACY (contract 12.3): the two files are vendor-derived. This tool reads the file locally, sends the parsed JSON to the platform API and returns ONLY
counts and reason codes — never a row's text, never the file's content, never the bearer token, and it logs nothing. Error output carries a code, the HTTP
status and the server's ``motivo`` code at most.

Config (env, loaded from the repo-root ``.env``): ``NOCTUS_SW_URL`` and ``NOCTUS_SW_TOKEN`` — here a PLATFORM ADMIN's bearer session token (the endpoints
are ``platform`` tier). CONTRACT: products/social-wiring/projects/core-studio-build/specs/estruturas-contract.md §6.3 / §7.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

ACOES = ("plan", "apply", "status")
FONTES = ("referencia",)
ARQUIVO_PADRAO = {"referencia": "estruturas-referencia.json"}
DIRETORIO_PADRAO = Path.home() / "Documents/repository/NoctusAI/_private-studies/core-studio/estruturas-import"
MAX_BYTES = 16 * 1024 * 1024  # the API's 16 MiB body override on this one route
_BASE = "/api/media-creation/estruturas/importacoes"
_TIMEOUT = httpx.Timeout(900.0, connect=10.0)
#: The ONLY keys of the report that leave this tool (counts, codes, ids, timestamps).
_RELATORIO = (
    "id", "fonte", "status", "dry_run", "arquivo_sha256", "linhas_total", "perfis_criados", "perfis_mesclados", "estruturas_criadas",
    "estruturas_atualizadas", "estruturas_inalteradas", "estruturas_ignoradas", "ignoradas_motivos", "blocos_criados", "campos_nao_importados",
    "erro", "created_at", "finished_at",
)


def _error(codigo: str, mensagem: str, **extra: Any) -> dict[str, Any]:
    return {"error": {"codigo": codigo, "mensagem": mensagem, **extra}}


_LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})


def _url_segura(url: str) -> bool:
    """The bearer token of a platform admin travels in this request: ``https`` only (``http`` only to a loopback host, the
    local dev stack), a host, no userinfo (security review F8)."""
    try:
        partes = urlsplit(url)
        host = (partes.hostname or "").lower()
        sem_userinfo = partes.netloc.lower() == (f"{host}:{partes.port}" if partes.port else host)
    except ValueError:
        return False
    if not host or not sem_userinfo:
        return False
    return partes.scheme == "https" or (partes.scheme == "http" and host in _LOOPBACK)


def _config() -> tuple[str, str] | dict[str, Any]:
    url = os.environ.get("NOCTUS_SW_URL", "").strip().rstrip("/")
    token = os.environ.get("NOCTUS_SW_TOKEN", "").strip()
    if not url or not token:
        return _error("nao_configurado", "NOCTUS_SW_URL e NOCTUS_SW_TOKEN (token de sessão de um admin da plataforma) precisam estar no .env da raiz.")
    if not _url_segura(url):
        return _error("url_insegura", "NOCTUS_SW_URL precisa ser https (http só para localhost): o token de admin viaja nessa chamada.")
    return url, token


def _importacao_id_valido(valor: str) -> bool:
    """The run id is interpolated into the request path: only a canonical UUID may go there (F8)."""
    try:
        return str(uuid.UUID(valor)) == valor.lower()
    except ValueError:
        return False


def sha256_documento(conteudo: Any) -> str:
    """The file identity the API computes (``estruturas_import.sha256_documento``): sha256 of the canonical JSON of the parsed document."""
    return hashlib.sha256(json.dumps(conteudo, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _resolver_arquivo(fonte: str, arquivo: str) -> Path | dict[str, Any]:
    if arquivo:
        caminho = Path(arquivo).expanduser()
    else:
        base = Path(os.environ.get("NOCTUS_ESTRUTURAS_IMPORT_DIR", "") or DIRETORIO_PADRAO)
        achados = sorted(base.glob(ARQUIVO_PADRAO[fonte]))
        if not achados:
            return _error("arquivo_nao_encontrado", "Nenhum arquivo padrão para esta fonte; passe `arquivo`.")
        caminho = achados[-1]
    if not caminho.is_file():
        return _error("arquivo_nao_encontrado", "O arquivo informado não existe.")
    return caminho


def _ler(caminho: Path) -> Any | dict[str, Any]:
    try:
        if caminho.stat().st_size > MAX_BYTES:
            return _error("arquivo_grande_demais", "O arquivo passa do limite de 16 MiB da rota.")
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # the class only: a JSON error message can quote content
        return _error("arquivo_ilegivel", f"Não foi possível ler o arquivo como JSON ({type(exc).__name__}).")


def _relatorio(dados: Any) -> dict[str, Any]:
    return {k: dados.get(k) for k in _RELATORIO if k in dados} if isinstance(dados, dict) else {}


def _erro_http(resp: httpx.Response) -> dict[str, Any]:
    try:
        corpo = resp.json()
    except ValueError:
        corpo = {}
    corpo = corpo if isinstance(corpo, dict) else {}
    aninhado = corpo.get("error") if isinstance(corpo.get("error"), dict) else {}
    codigo = corpo.get("code") or aninhado.get("code") or f"http_{resp.status_code}"
    extra: dict[str, Any] = {"http_status": resp.status_code}
    if isinstance(corpo.get("motivo"), str):
        extra["motivo"] = corpo["motivo"][:80]
    return _error(str(codigo), str(corpo.get("detail") or aninhado.get("message") or "Falha na chamada ao social-wiring.")[:300] if resp.status_code != 422 else "Arquivo recusado pelo servidor.", **extra)


def estruturas_import(
    action: str = "plan", fonte: str = "referencia", arquivo: str = "", confirm: bool = False, importacao_id: str = "",
    *, _transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    if action not in ACOES:
        return _error("acao_invalida", f"action deve ser um de {ACOES}.")
    if fonte not in FONTES:
        return _error("arquivo_invalido", "Esta fonte não é carregada na biblioteca de Estruturas.", motivo="fonte_nao_suportada", http_status=422)
    if importacao_id and not _importacao_id_valido(importacao_id):
        return _error("importacao_id_invalido", "importacao_id precisa ser um UUID.")
    if action == "apply" and not confirm:
        return _error("confirmacao_obrigatoria", "apply precisa de confirm=True (e de um plan do mesmo arquivo nas últimas 24 h).")
    cfg = _config()
    if isinstance(cfg, dict):
        return cfg
    base, token = cfg
    conteudo: Any = None
    caminho: Path | dict[str, Any] = Path()
    if action in ("plan", "apply"):
        caminho = _resolver_arquivo(fonte, arquivo)
        if isinstance(caminho, dict):
            return caminho
        conteudo = _ler(caminho)
        if isinstance(conteudo, dict) and "error" in conteudo and len(conteudo) == 1:
            return conteudo
    with httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT, transport=_transport) as c:
        try:
            if action == "status":
                resp = c.get(f"{_BASE}/{importacao_id}") if importacao_id else c.get(_BASE, params={"limit": 5})
            else:
                resp = c.post(_BASE, json={"fonte": fonte, "conteudo": conteudo, "arquivo_nome": Path(caminho).name, "dry_run": action == "plan"})
        except httpx.HTTPError as exc:
            return _error("erro_de_rede", f"{type(exc).__name__}")
        if resp.status_code >= 400:
            return _erro_http(resp)
        try:
            dados = (resp.json() or {}).get("data")
        except ValueError:
            return _error("resposta_invalida", "O servidor respondeu algo que não é JSON.", http_status=resp.status_code)
    if action == "status" and not importacao_id:
        itens = [_relatorio(i) for i in (dados or {}).get("items", [])] if isinstance(dados, dict) else []
        return {"status": "ok", "importacoes": itens}
    if action == "apply":
        return {"status": "em_andamento", "importacao_id": (dados or {}).get("id") if isinstance(dados, dict) else None, "proximo_passo": "action=status importacao_id=<id>"}
    relatorio = _relatorio(dados)
    saida: dict[str, Any] = {"status": "planned" if action == "plan" else "ok", "relatorio": relatorio}
    if action == "plan":
        saida["sha256_confere"] = relatorio.get("arquivo_sha256") == sha256_documento(conteudo)
        saida["fechado"] = relatorio.get("linhas_total") == sum(int(relatorio.get(k) or 0) for k in (
            "estruturas_criadas", "estruturas_atualizadas", "estruturas_inalteradas", "estruturas_ignoradas"))
    return saida


def register(server) -> None:
    @server.tool(
        name="noctus.sw.estruturas_import",
        description=("Load the CoreStudio reference dataset into the platform Estruturas library (a pure loader: no model call). "
                     "action=plan = SIMULATION (server writes only the `simulada` lote), returns counts + coded ignore reasons only; action=apply needs confirm=True "
                     "AND a plan of the SAME file within 24 h (server-enforced 409 simulacao_obrigatoria), runs as job estruturas.importar; action=status polls "
                     "(importacao_id) or lists the latest runs. fonte=referencia (the only source), arquivo=local path (default: the owner's private dir). "
                     "Never returns or logs row text. Needs NOCTUS_SW_URL + NOCTUS_SW_TOKEN (a platform admin's bearer)."),
    )
    def _estruturas_import(action: str = "plan", fonte: str = "referencia", arquivo: str = "", confirm: bool = False, importacao_id: str = "") -> dict:
        return estruturas_import(action=action, fonte=fonte, arquivo=arquivo, confirm=confirm, importacao_id=importacao_id)


__all__ = ["register", "estruturas_import", "sha256_documento"]
