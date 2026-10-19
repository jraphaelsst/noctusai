"""Julia wave 12 -- Atualizacao de imoveis: the owners (proprietarios) contacted to refresh a listing
(contract 14 / 17).

An owner is contacted ONLY through a Cloud template of an `atualizacao_anuncios` disparo. LGPD (contract 17):
an owner who answers "parar" is opted out for good -- `opt_out` + `opt_out_at` on every row of that phone,
his pending targets are dropped, and the dispatch skips him. When an owner replies and the page confirms the
status / price, the confirmation is stored on the owner row (Julia-owned) and the target moves
`respondido -> enviado_sw`. The Vista mirror `imoveis` is NEVER written (the Vista sync owns those columns and
would overwrite it): readers overlay the confirmation through `julia_imovel_confirmado`.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.primitives.exceptions import AppException

logger = logging.getLogger(__name__)

TABLE = "julia_proprietarios_contatos"
T_ALVOS = "julia_disparo_alvos"
PRECO_TIPOS = ("venda", "locacao")
_PARAR = re.compile(r"^\s*(parar|pare|sair)[\s.!]*$", re.IGNORECASE)


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalizar_telefone(raw: str) -> str:
    """Digits only; a bare Brazilian 10/11-digit number gets the 55 prefix. 422 when not 10..15 digits."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) in (10, 11):
        digits = "55" + digits
    if not (10 <= len(digits) <= 15):
        raise AppException("telefone_invalido", "Telefone inválido.", status_code=422)
    return digits


def eh_parar(texto: Optional[str]) -> bool:
    return bool(texto and _PARAR.match(texto))


def _nao_encontrado() -> AppException:
    return AppException("proprietario_nao_encontrado", "Proprietário não encontrado.", status_code=404)


def obter(db: Any, org_id: UUID | str, pid: UUID | str) -> dict[str, Any]:
    rows = db.table(TABLE).select("*").eq("org_id", str(org_id)).eq("id", str(pid)).limit(1).execute().data or []
    if not rows:
        raise _nao_encontrado()
    return _com_ultimo_alvo(db, org_id, [rows[0]])[0]


def listar(
    db: Any, org_id: UUID | str, *, opt_out: Optional[bool] = None, busca: Optional[str] = None, status: Optional[str] = None,
) -> list[dict[str, Any]]:
    if status is not None and status not in STATUS_LINHA:
        raise AppException("status_invalido", "Status desconhecido.", status_code=422, details={"validos": list(STATUS_LINHA)})
    def page(start: int, end: int) -> Any:
        q = db.table(TABLE).select("*").eq("org_id", str(org_id))
        if opt_out is not None:
            q = q.eq("opt_out", opt_out)
        return q.order("id").range(start, end).execute().data

    rows = list(iter_paged_rows(page, id_key="id", label="julia proprietarios"))
    if busca:
        b = busca.strip().lower()
        rows = [r for r in rows if b in str(r.get("nome") or "").lower() or b in str(r["imovel_codigo"]).lower() or b in r["telefone"]]
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    rows = _com_ultimo_alvo(db, org_id, rows)
    return [r for r in rows if r["status"] == status] if status else rows


#: the page's status column: opt-out wins, else the latest target's status (enviado_sw reads "atualizado").
STATUS_LINHA = ("pendente", "enviado", "respondido", "atualizado", "erro", "parar")
_STATUS_ALVO = {"pendente": "pendente", "enviado": "enviado", "respondido": "respondido", "enviado_sw": "atualizado", "erro": "erro"}


def status_da_linha(row: dict[str, Any], alvo_status: Optional[str]) -> str:
    if row.get("opt_out"):
        return "parar"
    return _STATUS_ALVO.get(alvo_status or "", "pendente")


def _com_ultimo_alvo(db: Any, org_id: UUID | str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach each owner's most recent target status (what the page's conversation column shows)."""
    if not rows:
        return rows
    ids = [str(r["id"]) for r in rows]
    alvos: list[dict[str, Any]] = []
    for i in range(0, len(ids), 200):  # `.in_()` rides in the URL: batch it
        alvos += db.table(T_ALVOS).select("proprietario_id, status, enviado_at, created_at").eq("org_id", str(org_id)).in_(
            "proprietario_id", ids[i:i + 200]).limit(1000).execute().data or []
    ultimo: dict[str, dict[str, Any]] = {}
    for a in sorted(alvos, key=lambda r: str(r.get("enviado_at") or r.get("created_at") or "")):
        ultimo[str(a["proprietario_id"])] = a
    out = []
    for r in rows:
        alvo_status = (ultimo.get(str(r["id"])) or {}).get("status")
        out.append({**r, "ultimo_alvo_status": alvo_status, "status": status_da_linha(r, alvo_status)})
    return out


def criar(db: Any, org_id: UUID | str, *, telefone: str, imovel_codigo: str, nome: Optional[str] = None) -> dict[str, Any]:
    tel = normalizar_telefone(telefone)
    codigo = imovel_codigo.strip().upper()
    if not codigo:
        raise AppException("codigo_invalido", "Informe o código do imóvel.", status_code=422)
    ja = db.table(TABLE).select("id").eq("org_id", str(org_id)).eq("telefone", tel).eq("imovel_codigo", codigo).limit(1).execute().data
    if ja:
        raise AppException("proprietario_duplicado", "Este proprietário já está cadastrado para o imóvel.", status_code=409)
    # a phone that already opted out stays opted out on every new row (LGPD)
    optou = db.table(TABLE).select("opt_out_at").eq("org_id", str(org_id)).eq("telefone", tel).eq("opt_out", True).limit(1).execute().data
    row = {
        "id": str(uuid4()), "org_id": str(org_id), "nome": (nome or "").strip() or None, "telefone": tel,
        "imovel_codigo": codigo, "opt_out": bool(optou), "opt_out_at": optou[0]["opt_out_at"] if optou else None,
    }
    created = db.table(TABLE).insert(row).execute().data or []
    if not created:
        raise RuntimeError("julia: proprietario insert returned no row")
    return _com_ultimo_alvo(db, org_id, [created[0]])[0]


def apagar(db: Any, org_id: UUID | str, pid: UUID | str) -> None:
    obter(db, org_id, pid)
    db.table(TABLE).delete().eq("org_id", str(org_id)).eq("id", str(pid)).execute()


def registrar_opt_out(db: Any, org_id: UUID | str, telefone: str) -> int:
    """"parar": opt the phone out on every row, drop his pending targets. Returns the rows opted out."""
    tel = normalizar_telefone(telefone)
    agora = _agora()
    rows = db.table(TABLE).select("id").eq("org_id", str(org_id)).eq("telefone", tel).limit(1000).execute().data or []
    for r in rows:
        db.table(TABLE).update({"opt_out": True, "opt_out_at": agora, "updated_at": agora}).eq("org_id", str(org_id)).eq(
            "id", r["id"]).execute()
    db.table(T_ALVOS).update({"status": "erro", "erro": "opt_out"}).eq("org_id", str(org_id)).eq("telefone", tel).eq(
        "status", "pendente").execute()
    return len(rows)


def reverter_opt_out(db: Any, org_id: UUID | str, pid: UUID | str) -> dict[str, Any]:
    """Only the OWNER's own act can lift it (he writes back); the page exposes this for that case."""
    p = obter(db, org_id, pid)
    db.table(TABLE).update({"opt_out": False, "opt_out_at": None, "updated_at": _agora()}).eq("org_id", str(org_id)).eq(
        "telefone", p["telefone"]).execute()
    return obter(db, org_id, pid)


def registrar_resposta(db: Any, org_id: UUID | str, telefone: str, texto: Optional[str]) -> str:
    """An inbound from an owner phone. Returns `opt_out` | `respondido` | `ignorado` (not an owner / no target)."""
    try:
        tel = normalizar_telefone(telefone)
    except AppException:
        return "ignorado"
    dono = db.table(TABLE).select("id").eq("org_id", str(org_id)).eq("telefone", tel).limit(1).execute().data
    if not dono:
        return "ignorado"
    if eh_parar(texto):
        registrar_opt_out(db, org_id, tel)
        return "opt_out"
    from app.services import julia_disparos_service

    return "respondido" if julia_disparos_service.registrar_resposta(db, org_id, tel) else "ignorado"


def confirmar(
    db: Any, org_id: UUID | str, pid: UUID | str, imoveis: Any, *,
    status: Optional[str] = None, preco: Optional[float] = None, preco_tipo: str = "venda",
) -> dict[str, Any]:
    """The owner confirmed status and/or price: store it on his row (Julia-owned storage, read back by
    `julia_imovel_confirmado` with provenance) and close his target `respondido -> enviado_sw`. 409 when he has
    not answered a Cloud template yet; 404 when the listing is not in the base. `imoveis` is read-only here."""
    if status is None and preco is None:
        raise AppException("nada_a_confirmar", "Informe o status e/ou o preço confirmado.", status_code=422)
    if preco_tipo not in PRECO_TIPOS:
        raise AppException("preco_tipo_invalido", "preco_tipo deve ser venda ou locacao.", status_code=422)
    if preco is not None and preco <= 0:
        raise AppException("preco_invalido", "O preço deve ser positivo.", status_code=422)
    p = obter(db, org_id, pid)
    if p.get("opt_out"):
        raise AppException("proprietario_opt_out", "O proprietário pediu para não ser contatado.", status_code=409)
    alvos = db.table(T_ALVOS).select("id, status").eq("org_id", str(org_id)).eq("proprietario_id", str(pid)).eq(
        "status", "respondido").limit(50).execute().data or []
    if not alvos:
        raise AppException(
            "sem_resposta_do_proprietario", "O proprietário ainda não respondeu a um modelo enviado pela API oficial.",
            status_code=409,
        )
    if imoveis.get(UUID(str(org_id)), p["imovel_codigo"]) is None:
        raise AppException("imovel_nao_encontrado", "Imóvel não encontrado na base.", status_code=404)
    agora = _agora()
    db.table(TABLE).update({
        "status_confirmado": status, "preco_confirmado": preco,
        "preco_tipo_confirmado": preco_tipo if preco is not None else None, "confirmado_at": agora, "updated_at": agora,
    }).eq("org_id", str(org_id)).eq("id", str(pid)).execute()
    for a in alvos:
        db.table(T_ALVOS).update({"status": "enviado_sw"}).eq("org_id", str(org_id)).eq("id", a["id"]).execute()
    return obter(db, org_id, pid)


__all__ = [
    "apagar", "confirmar", "criar", "eh_parar", "listar", "normalizar_telefone", "obter", "registrar_opt_out",
    "registrar_resposta", "reverter_opt_out",
]
