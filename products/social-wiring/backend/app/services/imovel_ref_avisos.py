"""Ref-divergence notices: the Vista sync NEVER erases our data -- it WARNS (owner 2026-11-09, migration 333).

  ref_sumiu_no_vista  a ref we have that Vista no longer has (per-code `DETALHE_SUMIU`, or a listar sweep that delisted it).
                      Every datum is KEPT. The imóvel is PAUSED: `imoveis.exibir_no_site=false`, the one flag the site, Julia's
                      catalog/offers and the campaign cards already honour. The pause is STICKY: while a notice is `pendente` or
                      `confirmada_sumiu` the sync cannot flip it back (`codigos_pausados` + `ImovelSyncService._aplicar_pausa`),
                      so a code that reappears in Vista is NEVER silently restored -- the notice gets a note (and a confirmed-gone one
                      reopens) and a human decides. Resolutions: `restaurar` (unpause + clear) | `confirmar_sumiu` (stays paused).
  ref_nova_no_vista   a ref Vista has that we did not: created on our side as before, recorded here (informational, `ciente` closes it).

One OPEN (`pendente`) notice per (imóvel, tipo) -- a partial unique index backs it. ONE in-app warning per sync run per tipo
(owners + admins, `notify_org_admins`), never per code. The owner's WhatsApp leg ("warn me" = WhatsApp, owner 2026-11-09) is
NOT sent here: the codes these functions return land on the run's `SyncReport` and `imoveis_atualizacao_service._avisar_dono`
sends ONE catalog-gated message per run (`imoveis_delistados` names the paused codes, `imoveis_novos_vista` the new ones). The sync's `_marcar_removidos` circuit breaker still refuses a mass
removal BEFORE any of this runs (a Vista fault is not a hundred disappearances).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Optional
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

TABLE = "imovel_ref_avisos"
TIPO_SUMIU = "ref_sumiu_no_vista"
TIPO_NOVA = "ref_nova_no_vista"
ST_PENDENTE = "pendente"
ST_RESTAURADA = "restaurada"
ST_CONFIRMADA = "confirmada_sumiu"
ST_CIENTE = "ciente"
#: Statuses under which a ref stays paused.
ST_PAUSA = (ST_PENDENTE, ST_CONFIRMADA)
ACOES = ("restaurar", "confirmar_sumiu", "ciente")
LINK = "/imoveis"
PRODUTO = "social-wiring"
MAX_CODIGOS_NA_MENSAGEM = 8


class AcaoInvalida(ValueError):
    """The resolution does not fit the notice (e.g. `restaurar` on a `ref_nova_no_vista`)."""


def _t(db: Any):
    return db.table(TABLE)


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canon(codigo: str) -> str:
    return codigo.strip().upper()


def _linhas(db: Any, org_id: Any, tipo: Optional[str] = None, status: Optional[Iterable[str]] = None) -> list[dict]:
    saida, inicio = [], 0
    while True:
        q = _t(db).select("*").eq("org_id", str(org_id))
        if tipo:
            q = q.eq("tipo", tipo)
        rows = q.order("id").range(inicio, inicio + 999).execute().data or []
        saida.extend(rows)
        if len(rows) < 1000:
            break
        inicio += 1000
    return [r for r in saida if status is None or r.get("status") in set(status)]


def codigos_pausados(db: Any, org_id: Any) -> set[str]:
    """Canonical codes the sync must keep paused (open or confirmed-gone `ref_sumiu_no_vista`). An unreadable table RAISES: a silent
    empty set would let the sync un-pause everything."""
    return {str(r["codigo_canonical"]) for r in _linhas(db, org_id, TIPO_SUMIU, ST_PAUSA)}


def _imoveis(db: Any):
    return db.table("imoveis")


def _pausar(db: Any, org_id: Any, codigo: str) -> Optional[bool]:
    """Set `exibir_no_site=false` on the mirror row; returns the value it had (`exibir_antes`, None = was NULL/shown or no row)."""
    rows = _imoveis(db).select("codigo, exibir_no_site").eq("org_id", str(org_id)).eq("codigo_norm", codigo).limit(1).execute().data or []
    if not rows:
        return None
    antes = rows[0].get("exibir_no_site")  # read BEFORE the update (the row object may be live)
    _imoveis(db).update({"exibir_no_site": False}).eq("org_id", str(org_id)).eq("codigo", rows[0]["codigo"]).execute()
    return antes


def registrar_sumiram(db: Any, org_id: Any, codigos: Iterable[str], *, origem: str) -> list[str]:
    """Pause + open a `ref_sumiu_no_vista` notice for each code (idempotent: one open notice per code). NEVER deletes anything.
    Returns the codes newly opened; sends ONE in-app warning for the batch."""
    # already noticed (open) OR already confirmed gone: nothing new to say, it is paused and a human has decided
    abertos = {str(r["codigo_canonical"]) for r in _linhas(db, org_id, TIPO_SUMIU, ST_PAUSA)}
    novos: list[str] = []
    for bruto in sorted({_canon(c) for c in codigos if c and c.strip()}):
        if bruto in abertos:
            continue
        antes = _pausar(db, org_id, bruto)
        _t(db).insert({
            "id": str(uuid4()), "org_id": str(org_id), "codigo_canonical": bruto, "tipo": TIPO_SUMIU, "status": ST_PENDENTE,
            "exibir_antes": antes, "notas": [{"em": _agora(), "texto": f"sumiu do Vista ({origem}); imóvel pausado, dados mantidos"}],
            "created_at": _agora(),
        }).execute()
        novos.append(bruto)
    if novos:
        _notificar(db, org_id, TIPO_SUMIU, novos)
    return novos


def registrar_novas(db: Any, org_id: Any, codigos: Iterable[str]) -> list[str]:
    """Record `ref_nova_no_vista` (informational) for codes Vista has and we did not; one open notice per code; ONE in-app warning."""
    abertos = {str(r["codigo_canonical"]) for r in _linhas(db, org_id, TIPO_NOVA, (ST_PENDENTE,))}
    novos: list[str] = []
    for c in sorted({_canon(c) for c in codigos if c and c.strip()}):
        if c in abertos:
            continue
        _t(db).insert({
            "id": str(uuid4()), "org_id": str(org_id), "codigo_canonical": c, "tipo": TIPO_NOVA, "status": ST_PENDENTE, "notas": [],
            "created_at": _agora(),
        }).execute()
        novos.append(c)
    if novos:
        _notificar(db, org_id, TIPO_NOVA, novos)
    return novos


def anotar_reaparecimentos(db: Any, org_id: Any, codigos_vistos: Iterable[str]) -> list[str]:
    """Vista answered for a code that has a pause notice: ADD A NOTE and keep it paused. A confirmed-gone notice reopens (new fact,
    a human must look). Never restores visibility. Returns the codes noted."""
    vistos = {_canon(c) for c in codigos_vistos if c}
    anotados: list[str] = []
    for r in _linhas(db, org_id, TIPO_SUMIU, ST_PAUSA):
        if str(r["codigo_canonical"]) not in vistos:
            continue
        notas = list(r.get("notas") or [])
        hoje = _agora()[:10]
        if any(n.get("tipo") == "reapareceu" and str(n.get("em", ""))[:10] == hoje for n in notas):
            continue
        notas.append({"em": _agora(), "tipo": "reapareceu", "texto": "reapareceu no Vista; o imóvel continua pausado até um humano decidir"})
        patch: dict[str, Any] = {"notas": notas}
        if r["status"] == ST_CONFIRMADA:
            patch.update({"status": ST_PENDENTE, "resolvido_em": None, "resolvido_por": None})
        _t(db).update(patch).eq("org_id", str(org_id)).eq("id", str(r["id"])).execute()
        anotados.append(str(r["codigo_canonical"]))
    return anotados


def _notificar(db: Any, org_id: Any, tipo: str, codigos: list[str]) -> int:
    """ONE in-app warning for a run's batch (owners + admins). Never raises; stamps `notificado_em` on the rows it covered."""
    try:
        from noctusai_lib.domain.notifications import notify_org_admins

        from app.database import get_core_client

        lista = ", ".join(codigos[:MAX_CODIGOS_NA_MENSAGEM]) + (f" e mais {len(codigos) - MAX_CODIGOS_NA_MENSAGEM}" if len(codigos) > MAX_CODIGOS_NA_MENSAGEM else "")
        if tipo == TIPO_SUMIU:
            titulo, msg = f"{len(codigos)} imóvel(is) sumiram do Vista", f"Pausados (dados mantidos): {lista}. Confira: restaurar ou confirmar que saíram."
        else:
            titulo, msg = f"{len(codigos)} imóvel(is) novos no Vista", f"Criados no nosso lado: {lista}."
        n = notify_org_admins(get_core_client(), org_id=org_id, kind=tipo, title=titulo, message=msg, produto=PRODUTO, link=LINK, entidade=None)
        if n:
            for r in _linhas(db, org_id, tipo, (ST_PENDENTE,)):
                if r["codigo_canonical"] in codigos and not r.get("notificado_em"):
                    _t(db).update({"notificado_em": _agora()}).eq("org_id", str(org_id)).eq("id", str(r["id"])).execute()
        return n
    except Exception:  # noqa: BLE001 -- the notice row is the record; the warning is a nudge
        logger.exception("imovel_ref_avisos: in-app warning (%s, %d codes) failed for org=%s", tipo, len(codigos), org_id)
        return 0


# ─── the human side ──────────────────────────────────────────────────────


def listar(db: Any, org_id: Any, *, tipo: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
    rows = _linhas(db, org_id, tipo, (status,) if status else None)
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return rows


def resolver(db: Any, org_id: Any, aviso_id: Any, acao: str, user_id: Any = None, nota: Optional[str] = None) -> dict:
    """`restaurar` (sumiu only: put `exibir_no_site` back to what it was, clear) | `confirmar_sumiu` (sumiu only: stays paused,
    resolved) | `ciente` (nova only). Never auto-invoked. Raises `LookupError` (unknown notice) / `AcaoInvalida`."""
    if acao not in ACOES:
        raise AcaoInvalida(f"acao must be one of {ACOES}")
    rows = _t(db).select("*").eq("org_id", str(org_id)).eq("id", str(aviso_id)).limit(1).execute().data or []
    if not rows:
        raise LookupError(f"aviso {aviso_id} not found")
    r = rows[0]
    if (acao == "ciente") != (r["tipo"] == TIPO_NOVA):
        raise AcaoInvalida(f"{acao!r} does not apply to {r['tipo']!r}")
    novo_status = {"restaurar": ST_RESTAURADA, "confirmar_sumiu": ST_CONFIRMADA, "ciente": ST_CIENTE}[acao]
    if acao == "restaurar":
        _imoveis(db).update({"exibir_no_site": r.get("exibir_antes")}).eq("org_id", str(org_id)).eq("codigo_norm", r["codigo_canonical"]).execute()
    notas = list(r.get("notas") or [])
    notas.append({"em": _agora(), "tipo": acao, "por": str(user_id) if user_id else None, "texto": nota or acao})
    patch = {"status": novo_status, "notas": notas, "resolvido_em": _agora(), "resolvido_por": str(user_id) if user_id else None}
    _t(db).update(patch).eq("org_id", str(org_id)).eq("id", str(aviso_id)).execute()
    return {**r, **patch}


__all__ = [
    "ACOES", "AcaoInvalida", "TIPO_NOVA", "TIPO_SUMIU", "anotar_reaparecimentos", "codigos_pausados", "listar", "registrar_novas",
    "registrar_sumiram", "resolver",
]
