"""Owner-confirmed status / price of a listing, overlaid on the Vista mirror at READ time.

`imoveis.status / valor_venda / valor_locacao` belong to the Vista sync (it overwrites them on every run), so an
owner's confirmation ("still available" / "new price") is never written there. It lives in the Lais-owned
`lais_proprietarios_contatos` row (`status_confirmado`, `preco_confirmado`, `preco_tipo_confirmado`,
`confirmado_at`; migration 275 + 283), and every reader that shows a listing's status or price (Julia's tools,
the Atualizacao page) asks this module whether a confirmation is newer than what Vista holds.

RULE (one place): a confirmation wins over the Vista value when it is NEWER than Vista's own last edit of the
listing (`imoveis.data_atualizacao`, a date -- a confirmation made the same day or earlier loses, so a Vista
edit is never shadowed by an older answer) or when Vista carries no edit date at all. The overlay is always
reported with its provenance ("confirmado pelo proprietario em <data>"), never silently merged.

Only status / price / date leave this module -- never the owner's name or phone (the select does not read them).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
TABLE = "lais_proprietarios_contatos"
_COLUNAS = "imovel_codigo, status_confirmado, preco_confirmado, preco_tipo_confirmado, confirmado_at"
_LOTE = 100


def _instante(v: Any) -> Optional[datetime]:
    if isinstance(v, datetime):
        d = v
    elif isinstance(v, str) and v:
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _data(v: Any) -> Optional[date]:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str) and v:
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def carregar(client: Any, org_id: UUID | str, codigos: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    """`{CODIGO: [confirmed rows, newest first]}` for the org (rows that were actually confirmed only)."""
    alvo = sorted({str(c).strip().upper() for c in codigos if c and str(c).strip()})
    out: dict[str, list[dict[str, Any]]] = {}
    for i in range(0, len(alvo), _LOTE):  # `.in_()` rides in the URL: batch it
        rows = (
            client.table(TABLE).select(_COLUNAS).eq("org_id", str(org_id)).in_("imovel_codigo", alvo[i:i + _LOTE])
            .limit(1000).execute().data or []
        )
        for r in rows:
            if _instante(r.get("confirmado_at")) is not None:
                out.setdefault(str(r["imovel_codigo"]).strip().upper(), []).append(r)
    for lista in out.values():
        lista.sort(key=lambda r: _instante(r["confirmado_at"]), reverse=True)
    return out


def _vigente(confirmado_at: Any, data_atualizacao: Any) -> bool:
    inst = _instante(confirmado_at)
    if inst is None:
        return False
    vista = _data(data_atualizacao)
    return vista is None or inst.astimezone(TZ).date() > vista


def provenance(em: datetime) -> str:
    return f"confirmado pelo proprietário em {em.astimezone(TZ):%d/%m/%Y}"


def aplicar(
    confirmacoes: list[dict[str, Any]], *, data_atualizacao: Any, preco_tipo: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """The confirmation to show for one listing, or None when Vista's value stands.

    `preco_tipo` (`venda` | `locacao`) says which price the caller shows; a confirmation whose kind is unknown
    (confirmed before migration 283) never overrides a price, only a status. Result:
    `{status?, preco?, preco_tipo?, em (ISO date), provenance}` -- keys absent when that field was not confirmed."""
    status = preco = None
    datas: list[datetime] = []
    for c in confirmacoes:
        if not _vigente(c.get("confirmado_at"), data_atualizacao):
            continue
        inst = _instante(c["confirmado_at"])
        if status is None and c.get("status_confirmado"):
            status = str(c["status_confirmado"])
            datas.append(inst)
        if (preco is None and preco_tipo and c.get("preco_confirmado") is not None
                and c.get("preco_tipo_confirmado") == preco_tipo):
            preco = float(c["preco_confirmado"])
            datas.append(inst)
    if status is None and preco is None:
        return None
    em = max(datas)
    out: dict[str, Any] = {"em": em.astimezone(TZ).date().isoformat(), "provenance": provenance(em)}
    if status is not None:
        out["status"] = status
    if preco is not None:
        out["preco"] = preco
        out["preco_tipo"] = preco_tipo
    return out


__all__ = ["aplicar", "carregar", "provenance"]
