"""``noctus.sw.vista_clientes_sync`` — Vista clientes -> our lead people (fill-empty-only), from the toolkit.

  action="status"   GET  /api/leads/vista-clientes/resumo  -> links, pending notices, settings (rate budget, LGPD identity flag), last run
  action="sync"     POST /api/leads/vista-clientes/sync     -> ONE bounded batch (``limite`` clientes from ``cursor``), or ``max_lotes`` of
                    them. DRY-RUN by default (reads Vista paced by the org's budget, writes nothing, reports field NAMES only); a real run
                    needs ``dry_run=False`` AND ``confirm=True``. Resumable: pass back ``proximo_cursor`` as ``cursor``.

A full pass over the Vista client list (tens of thousands) is OWNER-TRIGGERED: this tool never loops past ``max_lotes`` (default 1, max 20).
CONTRACT: products/social-wiring/projects/ad-lead-intake-CONTRACT.md § 8. Same auth/config as ``noctus.sw.ad_lead_intake``
(``NOCTUS_SW_URL`` + ``NOCTUS_SW_TOKEN``, an org ADMIN's bearer token; never logged or returned).
"""
from __future__ import annotations

import os
from typing import Any

import httpx

MODOS = ("novos", "refazer")
MAX_LOTES = 20
_TIMEOUT = httpx.Timeout(600.0, connect=10.0)
_SOMAS = ("lote", "ja_vinculados", "casados", "campos_preenchidos", "divergencias", "ambiguos", "sem_match")


def _error(codigo: str, mensagem: str, **extra: Any) -> dict[str, Any]:
    return {"error": {"codigo": codigo, "mensagem": mensagem, **extra}}


def _config() -> tuple[str, str] | dict[str, Any]:
    url = os.environ.get("NOCTUS_SW_URL", "").strip().rstrip("/")
    token = os.environ.get("NOCTUS_SW_TOKEN", "").strip()
    if not url or not token:
        return _error("nao_configurado", "NOCTUS_SW_URL e NOCTUS_SW_TOKEN (token de sessão de um admin da org) precisam estar no .env da raiz.")
    return url, token


def _chamar(client: httpx.Client, metodo: str, caminho: str, params: dict | None = None) -> dict[str, Any]:
    try:
        resp = client.request(metodo, caminho, params=params)
    except httpx.HTTPError as exc:
        return _error("erro_de_rede", f"{type(exc).__name__}: {exc}")
    try:
        corpo = resp.json()
    except ValueError:
        corpo = {}
    if resp.status_code >= 400:
        err = corpo.get("error") if isinstance(corpo, dict) else None
        return _error((err or {}).get("code") or f"http_{resp.status_code}", (err or {}).get("message") or "Falha na chamada ao social-wiring.", http_status=resp.status_code)
    return {"ok": True, "dados": (corpo.get("data") if isinstance(corpo, dict) and "data" in corpo else corpo)}


def vista_clientes_sync(
    action: str = "status", org: str = "", dry_run: bool = True, confirm: bool = False, modo: str = "novos",
    limite: int = 50, cursor: str = "", max_lotes: int = 1, pausa_s: float = 0.0,
    *, _transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    if action not in ("status", "sync"):
        return _error("acao_invalida", "action deve ser status ou sync.")
    if modo not in MODOS or not (1 <= limite <= 500) or not (1 <= max_lotes <= MAX_LOTES):
        return _error("parametro_invalido", f"modo ∈ {MODOS}; 1 ≤ limite ≤ 500; 1 ≤ max_lotes ≤ {MAX_LOTES}.")
    cfg = _config()
    if isinstance(cfg, dict):
        return cfg
    base, token = cfg
    efetivo_dry = dry_run or not confirm
    with httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT, transport=_transport) as c:
        if action == "status":
            r = _chamar(c, "GET", "/api/leads/vista-clientes/resumo")
            return r if "error" in r else {"status": "ok", "org": org or None, "resumo": r["dados"]}
        total: dict[str, Any] = {k: 0 for k in _SOMAS} | {"sem_match_por_flag": {}, "amostra": None}
        atual = cursor or None
        lotes = 0
        for _ in range(max_lotes):
            params = {"dry_run": str(efetivo_dry).lower(), "limite": limite, "modo": modo, "pausa_s": pausa_s}
            if atual:
                params["cursor"] = atual
            r = _chamar(c, "POST", "/api/leads/vista-clientes/sync", params)
            if "error" in r:
                return {**r, "parcial": total, "proximo_cursor": atual, "lotes": lotes}
            d = r["dados"]
            lotes += 1
            for k in _SOMAS:
                total[k] += int(d.get(k) or 0)
            for k, v in (d.get("sem_match_por_flag") or {}).items():
                total["sem_match_por_flag"][k] = total["sem_match_por_flag"].get(k, 0) + v
            total["amostra"] = total["amostra"] or d.get("amostra")
            atual = d.get("proximo_cursor")
            if not atual or d.get("status") == "erro":
                break
    saida = {"status": "planned" if efetivo_dry else "done", "org": org or None, "dry_run": efetivo_dry, "modo": modo, "lotes": lotes, "total": total, "proximo_cursor": atual}
    if dry_run is False and not confirm:
        saida["mensagem"] = "dry_run=False sem confirm=True: rodou como DRY-RUN. Reenvie com confirm=True para gravar."
    return saida


def register(server) -> None:
    @server.tool(
        name="noctus.sw.vista_clientes_sync",
        description=("Vista clientes -> our lead people of a social-wiring org, FILL-EMPTY-ONLY (a Vista value fills an empty field; a different one is a "
                     "warning, never an overwrite; nothing is written to Vista). action=status = links/notices/settings/last run; action=sync = ONE bounded "
                     "batch (limite clientes from cursor; max_lotes batches, default 1), DRY-RUN unless dry_run=False AND confirm=True, resumable via "
                     "proximo_cursor, modo novos|refazer. A full pass is owner-triggered. Needs NOCTUS_SW_URL + NOCTUS_SW_TOKEN (org admin bearer)."),
    )
    def _vista_clientes_sync(
        action: str = "status", org: str = "", dry_run: bool = True, confirm: bool = False, modo: str = "novos",
        limite: int = 50, cursor: str = "", max_lotes: int = 1, pausa_s: float = 0.0,
    ) -> dict:
        return vista_clientes_sync(action=action, org=org, dry_run=dry_run, confirm=confirm, modo=modo, limite=limite, cursor=cursor, max_lotes=max_lotes, pausa_s=pausa_s)


__all__ = ["register", "vista_clientes_sync"]
