"""Admin API — `/api/admin/*`, gated by `require_store_admin` (owner only).

Contract §3 "Admin". Every route declares the gate as a router-level
dependency, so a new route cannot forget it: no/invalid token -> 401
(from `get_current_user`); signed in but not in `STORE_ADMIN_EMAILS` -> 403.

Uploads read the body in bounded chunks (`_read_capped`) so an oversize file
is refused without buffering it whole; each route also has a
`max_body_path_overrides` entry in `app/main.py` (the platform's 1 MB webhook
DoS default would otherwise 413 any real upload).
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.dependencies import require_store_admin
from app.schemas.store import KitInfoOut, SettingsUpdate
from app.services.assets import MAX_KIT_BYTES, MAX_PHOTO_BYTES, AssetRejected, AssetService
from app.services.delivery_service import DeliveryFailed, DeliveryService
from app.services.settings_service import SettingsService, SettingsVersionConflict
from app.store_deps import get_assets, get_delivery_service, get_pedido_store, get_settings_service
from app.stores import PedidoStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["store-admin"], dependencies=[Depends(require_store_admin)])

_VALID_STATUS = {"pendente", "pago", "reembolsado", "falhou"}
_CHUNK = 1024 * 1024


async def _read_capped(file: UploadFile, max_bytes: int) -> bytes:
    """Read at most `max_bytes`; one byte over => 413 without reading the rest."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail={"detail": f"Arquivo maior que {max_bytes // (1024 * 1024)} MB.", "code": "too_large"},
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _rejected(exc: AssetRejected) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"detail": exc.detail, "code": "invalid_file"})


def _mask_cpf(cpf: str) -> str:
    digits = "".join(ch for ch in (cpf or "") if ch.isdigit())
    return f"***.***.***-{digits[-2:]}" if len(digits) >= 2 else "***"


def _pedido_admin_out(row: dict) -> dict:
    # The buyer's `token` (their only handle) and the full CPF never leave the
    # server in the admin list.
    return {
        "id": str(row["id"]),
        "nome": row["nome"],
        "email": row["email"],
        "cpf_mascarado": _mask_cpf(str(row.get("cpf") or "")),
        "valor_cents": row["valor_cents"],
        "produto": row["produto"],
        "status": row["status"],
        "gateway": row.get("gateway"),
        "pago_em": row.get("pago_em"),
        "email_enviado_em": row.get("email_enviado_em"),
        "email_erro": row.get("email_erro"),
        "downloads": row.get("downloads", 0),
        "created_at": row["created_at"],
    }


@router.get("/settings")
async def get_admin_settings(service: SettingsService = Depends(get_settings_service)) -> dict:
    return await service.admin_view()


@router.put("/settings")
async def put_admin_settings(
    body: SettingsUpdate,
    user=Depends(require_store_admin),
    service: SettingsService = Depends(get_settings_service),
) -> dict:
    try:
        version = service.update(body.data, body.expected_version, created_by=str(getattr(user, "id", "") or "") or None)
    except SettingsVersionConflict as exc:
        raise HTTPException(
            status_code=409, detail={"detail": "A página foi alterada por outra sessão. Recarregue.", "code": "version_conflict"}
        ) from exc
    return {"version": version}


@router.post("/autor/foto")
async def upload_author_photo(
    file: UploadFile = File(...),
    assets: AssetService = Depends(get_assets),
) -> dict:
    data = await _read_capped(file, MAX_PHOTO_BYTES)
    try:
        await assets.put_photo(data, file.content_type or "")
    except AssetRejected as exc:
        raise _rejected(exc) from exc
    return {"ok": True}


@router.post("/produto/arquivo", response_model=KitInfoOut)
async def upload_kit(
    file: UploadFile = File(...),
    assets: AssetService = Depends(get_assets),
) -> dict:
    data = await _read_capped(file, MAX_KIT_BYTES)
    try:
        await assets.put_kit(data)
    except AssetRejected as exc:
        raise _rejected(exc) from exc
    return await assets.kit_info()


@router.get("/produto/arquivo", response_model=KitInfoOut)
async def get_kit_info(assets: AssetService = Depends(get_assets)) -> dict:
    return await assets.kit_info()


@router.get("/pedidos")
async def list_pedidos(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    pedidos: PedidoStore = Depends(get_pedido_store),
) -> dict:
    if status is not None and status not in _VALID_STATUS:
        raise HTTPException(status_code=422, detail={"detail": "Status inválido.", "code": "invalid", "field": "status"})
    return {"items": [_pedido_admin_out(r) for r in pedidos.list(status=status, limit=limit, offset=offset)]}


@router.post("/pedidos/{pedido_id}/reenviar")
async def resend_delivery(
    pedido_id: str,
    pedidos: PedidoStore = Depends(get_pedido_store),
    delivery: DeliveryService = Depends(get_delivery_service),
) -> dict:
    pedido = pedidos.get_by_id(pedido_id)
    if pedido is None:
        raise HTTPException(status_code=404, detail={"detail": "Pedido não encontrado.", "code": "not_found"})
    if pedido["status"] != "pago":
        raise HTTPException(
            status_code=409, detail={"detail": "Só é possível reenviar o e-mail de um pedido pago.", "code": "not_paid"}
        )
    try:
        await delivery.resend(pedido)
    except DeliveryFailed as exc:
        raise HTTPException(
            status_code=502, detail={"detail": "Não foi possível enviar o e-mail agora.", "code": "email_failed"}
        ) from exc
    return {"ok": True}


__all__ = ["router"]
