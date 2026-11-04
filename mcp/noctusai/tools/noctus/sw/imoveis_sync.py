"""``noctus.sw.imoveis_sync`` — the Vista imóveis refresh of a social-wiring org, from the toolkit.

  action="status"  GET  /api/imoveis/sync/ultimo   -> the last run (when, path, new/updated/unchanged/removed/failed, calls)
  action="run"     POST /api/imoveis/sync?modo=..  -> queues a refresh (202). DRY-RUN by default: without ``confirm=True`` it
                   returns the exact request it WOULD send and sends nothing.

The ORG is the token's org (the product never takes an org from a body); ``org`` here is a label echoed in the plan/result so a
transcript says which tenant was meant. ``modo``: auto (listar first, per-code refresh when Vista's listar is silent) | listar |
detalhes; ``escopo``: vitrine | resto | todos (per-code scope).

Auth/config convention (same as ``noctus.transcription.*``): ``NOCTUS_SW_URL`` + ``NOCTUS_SW_TOKEN`` in env (an org admin's bearer
token — the endpoint is org-admin only); never logged or returned. Missing config is a typed ``nao_configurado`` error, never a
silent stub.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

MODOS = ("auto", "listar", "detalhes")
ESCOPOS = ("vitrine", "resto", "todos")
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def _error(codigo: str, mensagem: str, **extra: Any) -> dict[str, Any]:
    return {"error": {"codigo": codigo, "mensagem": mensagem, **extra}}


def _config() -> tuple[str, str] | dict[str, Any]:
    url = os.environ.get("NOCTUS_SW_URL", "").strip().rstrip("/")
    token = os.environ.get("NOCTUS_SW_TOKEN", "").strip()
    if not url or not token:
        return _error("nao_configurado", "NOCTUS_SW_URL e NOCTUS_SW_TOKEN (token de sessão de um admin da org) precisam estar no .env da raiz.")
    return url, token


def imoveis_sync(
    action: str = "status", org: str = "", modo: str = "auto", escopo: str = "vitrine", confirm: bool = False,
    *, _transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    if action not in ("status", "run"):
        return _error("acao_invalida", "action deve ser status ou run.")
    if modo not in MODOS or escopo not in ESCOPOS:
        return _error("parametro_invalido", f"modo ∈ {MODOS}; escopo ∈ {ESCOPOS}.")
    cfg = _config()
    if isinstance(cfg, dict):
        return cfg
    base, token = cfg
    if action == "run":
        plano = {"method": "POST", "url": f"{base}/api/imoveis/sync", "params": {"modo": modo, "escopo": escopo}}
        if not confirm:
            return {"status": "planned", "org": org or None, "plano": plano,
                    "mensagem": "Dry-run: nada foi enviado. Reenvie com confirm=true para enfileirar a atualização."}
        metodo, caminho, params = "POST", "/api/imoveis/sync", plano["params"]
    else:
        metodo, caminho, params = "GET", "/api/imoveis/sync/ultimo", None
    try:
        with httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT, transport=_transport) as c:
            resp = c.request(metodo, caminho, params=params)
    except httpx.HTTPError as exc:
        return _error("erro_de_rede", f"{type(exc).__name__}: {exc}")  # str(exc) never carries the Authorization header
    try:
        corpo = resp.json()
    except ValueError:
        corpo = {}
    if resp.status_code >= 400:
        err = corpo.get("error") if isinstance(corpo, dict) else None
        return _error(
            (err or {}).get("code") or f"http_{resp.status_code}",
            (err or {}).get("message") or (corpo.get("detail") if isinstance(corpo, dict) and isinstance(corpo.get("detail"), str) else "Falha na chamada ao social-wiring."),
            http_status=resp.status_code,
        )
    return {"status": "queued" if action == "run" else "ok", "org": org or None, "http_status": resp.status_code, "resultado": corpo}


def register(server) -> None:
    @server.tool(
        name="noctus.sw.imoveis_sync",
        description=("Vista imóveis refresh of a social-wiring org. action=status reads the last run (when, path listar|detalhes, "
                     "new/updated/unchanged/removed/failed, call counts); action=run queues a refresh (modo auto|listar|detalhes, "
                     "escopo vitrine|resto|todos) and is a DRY-RUN unless confirm=True. Needs NOCTUS_SW_URL + NOCTUS_SW_TOKEN "
                     "(org admin bearer); the org is the token's."),
    )
    def _imoveis_sync(action: str = "status", org: str = "", modo: str = "auto", escopo: str = "vitrine", confirm: bool = False) -> dict:
        return imoveis_sync(action=action, org=org, modo=modo, escopo=escopo, confirm=confirm)


__all__ = ["imoveis_sync", "register"]
