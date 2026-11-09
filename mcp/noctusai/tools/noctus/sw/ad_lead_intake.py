"""``noctus.sw.ad_lead_intake`` — the ad-lead intake backfill/retry of a social-wiring org, from the toolkit.

  action="status"    GET  /api/leads/ad-intake/resumo         -> intake outcomes by status + pending corretor divergences
  action="backfill"  POST /api/leads/ad-intake/backfill       -> a BATCH (or ``max_lotes`` batches) of the intake over existing
                     Meta leads. DRY-RUN by default (``dry_run`` true, nothing written, Vista never called); a real run needs
                     ``dry_run=False`` AND ``confirm=True`` (it calls Vista, paced by the product's shared rate limit).
                     Resumable: pass back ``proximo_cursor`` as ``cursor``; ``modo`` novos|pendentes|refazer.

CONTRACT: products/social-wiring/projects/ad-lead-intake-CONTRACT.md § 5. Same auth/config convention as
``noctus.sw.imoveis_sync``: ``NOCTUS_SW_URL`` + ``NOCTUS_SW_TOKEN`` (an org ADMIN's bearer token) in env, never logged or
returned; missing config is a typed ``nao_configurado`` error, never a silent stub. The org is the token's.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

MODOS = ("novos", "pendentes", "refazer")
_TIMEOUT = httpx.Timeout(900.0, connect=10.0)  # a real batch walks Vista code by code
_SOMAS = ("lote", "sem_lead", "ja_feitos", "a_processar", "processados")


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
        return _error("erro_de_rede", f"{type(exc).__name__}: {exc}")  # str(exc) never carries the Authorization header
    try:
        corpo = resp.json()
    except ValueError:
        corpo = {}
    if resp.status_code >= 400:
        err = corpo.get("error") if isinstance(corpo, dict) else None
        return _error((err or {}).get("code") or f"http_{resp.status_code}", (err or {}).get("message") or "Falha na chamada ao social-wiring.", http_status=resp.status_code)
    return {"ok": True, "dados": (corpo.get("data") if isinstance(corpo, dict) and "data" in corpo else corpo)}


def ad_lead_intake(
    action: str = "status", org: str = "", dry_run: bool = True, confirm: bool = False, modo: str = "novos",
    limite: int = 25, cursor: str = "", max_lotes: int = 1, pausa_s: float = 0.0,
    *, _transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    if action not in ("status", "backfill"):
        return _error("acao_invalida", "action deve ser status ou backfill.")
    if modo not in MODOS or not (1 <= limite <= 100) or not (1 <= max_lotes <= 200):
        return _error("parametro_invalido", f"modo ∈ {MODOS}; 1 ≤ limite ≤ 100; 1 ≤ max_lotes ≤ 200.")
    cfg = _config()
    if isinstance(cfg, dict):
        return cfg
    base, token = cfg
    efetivo_dry = dry_run or not confirm
    with httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT, transport=_transport) as c:
        if action == "status":
            r = _chamar(c, "GET", "/api/leads/ad-intake/resumo")
            return r if "error" in r else {"status": "ok", "org": org or None, "resumo": r["dados"]}
        total: dict[str, Any] = {k: 0 for k in _SOMAS} | {"por_status": {}, "falhas": []}
        atual = cursor or None
        lotes = 0
        for _ in range(max_lotes):
            params = {"dry_run": str(efetivo_dry).lower(), "limite": limite, "modo": modo, "pausa_s": pausa_s}
            if atual:
                params["cursor"] = atual
            r = _chamar(c, "POST", "/api/leads/ad-intake/backfill", params)
            if "error" in r:
                return {**r, "parcial": total, "proximo_cursor": atual, "lotes": lotes}
            d = r["dados"]
            lotes += 1
            for k in _SOMAS:
                total[k] += int(d.get(k) or 0)
            for k, v in (d.get("por_status") or {}).items():
                total["por_status"][k] = total["por_status"].get(k, 0) + v
            total["falhas"].extend(d.get("falhas") or [])
            atual = d.get("proximo_cursor")
            if not atual:
                break
    saida = {"status": "planned" if efetivo_dry else "done", "org": org or None, "dry_run": efetivo_dry, "modo": modo, "lotes": lotes, "total": total, "proximo_cursor": atual}
    if dry_run is False and not confirm:
        saida["mensagem"] = "dry_run=False sem confirm=True: rodou como DRY-RUN. Reenvie com confirm=True para gravar."
    return saida


def register(server) -> None:
    @server.tool(
        name="noctus.sw.ad_lead_intake",
        description=("Ad-lead intake of a social-wiring org (Meta form lead -> property refreshed from Vista -> links + corretor). "
                     "action=status = intake outcomes by status + pending corretor divergences; action=backfill = batch(es) over "
                     "existing Meta leads, DRY-RUN unless dry_run=False AND confirm=True (calls Vista), resumable via "
                     "proximo_cursor, modo novos|pendentes|refazer. Needs NOCTUS_SW_URL + NOCTUS_SW_TOKEN (org admin bearer)."),
    )
    def _ad_lead_intake(
        action: str = "status", org: str = "", dry_run: bool = True, confirm: bool = False, modo: str = "novos",
        limite: int = 25, cursor: str = "", max_lotes: int = 1, pausa_s: float = 0.0,
    ) -> dict:
        return ad_lead_intake(action=action, org=org, dry_run=dry_run, confirm=confirm, modo=modo, limite=limite, cursor=cursor, max_lotes=max_lotes, pausa_s=pausa_s)


__all__ = ["ad_lead_intake", "register"]
