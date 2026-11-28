"""``noctus.sw.imovel_videos_vista_import`` — fill the imóveis' YouTube field from the videos ALREADY in Vista, from the toolkit.

  action="dry_run" (default)  POST /api/imoveis/videos-youtube/importar-vista {dry_run: true}  -> 202 + execucao_id; ZERO writes
  action="run"                needs ``confirm=True``; POST {dry_run: false} -> writes only ``origem='vista'`` rows, never Vista
  action="status"             GET  .../importar-vista/{execucao_id} (counts + per-code rows; ``resultados`` filter, ``limit``/``offset``)
                              or, without an id, the latest runs. Poll until status is concluida / abortada / falhou / ignorada.

``codigos`` (list) scopes a run to those codes; ``limite`` cuts it. ``org_id`` targets another org (default: the token's org).
Rules + counts: products/social-wiring/backend/app/services/imovel_videos_vista_import_service.py (Destaque wins, else the lowest
VideoCodigo; a Short / non-YouTube is skipped; a julia/manual row is never overwritten).

Config (env, repo-root ``.env``): ``NOCTUS_SW_URL`` + ``NOCTUS_SW_TOKEN`` — a PLATFORM ADMIN's bearer session token (the routes are
``platform`` tier); https only (http only to loopback); the token is never logged or returned.
"""
from __future__ import annotations

import os
import uuid
from typing import Any
from urllib.parse import urlsplit

import httpx

from tools.noctus.dev._http import bounded_client

ACOES = ("dry_run", "run", "status")
_BASE = "/api/imoveis/videos-youtube/importar-vista"
_LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})


def _error(codigo: str, mensagem: str, **extra: Any) -> dict[str, Any]:
    return {"error": {"codigo": codigo, "mensagem": mensagem, **extra}}


def _url_segura(url: str) -> bool:
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


def _uuid_valido(valor: str) -> bool:
    try:
        return str(uuid.UUID(valor)) == valor.lower()
    except ValueError:
        return False


def imovel_videos_vista_import(
    action: str = "dry_run", confirm: bool = False, codigos: list[str] | None = None, limite: int | None = None, org_id: str = "",
    execucao_id: str = "", resultados: str = "", limit: int = 200, offset: int = 0,
    *, _transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    if action not in ACOES:
        return _error("acao_invalida", f"action deve ser um de {ACOES}.")
    if action == "run" and not confirm:
        return _error("confirmacao_obrigatoria", "run grava no campo do vídeo: rode antes um dry_run, revise o relatório e reenvie com confirm=True.")
    if execucao_id and not _uuid_valido(execucao_id):
        return _error("execucao_id_invalido", "execucao_id precisa ser um UUID.")
    if org_id and not _uuid_valido(org_id):
        return _error("org_id_invalido", "org_id precisa ser um UUID.")
    if limite is not None and limite < 1:
        return _error("parametro_invalido", "limite precisa ser >= 1.")
    cfg = _config()
    if isinstance(cfg, dict):
        return cfg
    base, token = cfg
    if action == "status":
        caminho = f"{_BASE}/{execucao_id}" if execucao_id else _BASE
        params = {"limit": limit, "offset": offset, **({"resultados": resultados} if resultados else {})} if execucao_id else None
        metodo, corpo = "GET", None
    else:
        corpo = {"dry_run": action == "dry_run"}
        if codigos:
            corpo["codigos"] = list(codigos)
        if limite:
            corpo["limite"] = limite
        if org_id:
            corpo["org_id"] = org_id
        metodo, caminho, params = "POST", _BASE, None
    try:
        with bounded_client(base_url=base, headers={"Authorization": f"Bearer {token}"}, transport=_transport, deadline_s=60.0,
                            why="queues / reads a Vista videos import run", call_site="sw.imovel_videos_vista_import") as c:
            resp = c.request(metodo, caminho, params=params, json=corpo)
    except httpx.HTTPError as exc:
        return _error("erro_de_rede", type(exc).__name__)  # never the request (it carries the bearer)
    try:
        dados = resp.json()
    except ValueError:
        dados = {}
    if resp.status_code >= 400:
        dados = dados if isinstance(dados, dict) else {}
        err = dados.get("error") if isinstance(dados.get("error"), dict) else {}
        detalhe = dados.get("detail") if isinstance(dados.get("detail"), str) else None
        return _error(str(err.get("code") or f"http_{resp.status_code}"), str(err.get("message") or detalhe or "Falha na chamada ao social-wiring.")[:300],
                      http_status=resp.status_code)
    resultado = dados.get("data") if isinstance(dados, dict) and "data" in dados else dados
    status = {"dry_run": "queued_dry_run", "run": "queued", "status": "ok"}[action]
    return {"status": status, "http_status": resp.status_code, "resultado": resultado}


def register(server) -> None:
    @server.tool(
        name="noctus.sw.imovel_videos_vista_import",
        description=("Fill social-wiring's imóvel YouTube field from the videos already in Vista (the `Video` relation). "
                     "action=dry_run (default) queues a ZERO-write simulation; action=run needs confirm=True (writes origem=vista rows "
                     "only, never Vista, never over a julia/manual row); action=status execucao_id= returns counts + per-code rows "
                     "(resultados=a,b|todos, limit, offset), no id = latest runs. codigos=[...] / limite / org_id scope a run. "
                     "Needs NOCTUS_SW_URL + NOCTUS_SW_TOKEN (platform admin bearer)."),
    )
    def _imovel_videos_vista_import(action: str = "dry_run", confirm: bool = False, codigos: list[str] | None = None,
                                    limite: int | None = None, org_id: str = "", execucao_id: str = "", resultados: str = "",
                                    limit: int = 200, offset: int = 0) -> dict:
        return imovel_videos_vista_import(action=action, confirm=confirm, codigos=codigos, limite=limite, org_id=org_id,
                                          execucao_id=execucao_id, resultados=resultados, limit=limit, offset=offset)


__all__ = ["imovel_videos_vista_import", "register"]
