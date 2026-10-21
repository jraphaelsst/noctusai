"""
Clients router — CRUD for orbity.clients (the agency's customers).

Auth: every endpoint requires Depends(get_current_user_org).
Unauth'd requests → 401 (strict, not 404/422).

Endpoints:
  GET    /api/clients          list (page, page_size, active_only)
  POST   /api/clients          create → 201
  GET    /api/clients/{id}     detail
  PATCH  /api/clients/{id}     update
  PATCH  /api/clients/{id}     update (``active=false`` is refused: inactivating goes through /archive)
  GET    /api/clients/cnpj/{cnpj}              Razão Social from the public CNPJ registry
  GET    /api/clients/{id}/offboarding-preview open charges + live contracts the inactivation touches  [admin]
  DELETE /api/clients/{id}                     soft-delete (refused 409 with a live contract / open charge) [admin]
  POST   /api/clients/{id}/archive             inactivate: cancel or keep each open charge, terminate the contracts [admin]
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from noctusai_lib.domain.finance.entries import normalize_doc
from noctusai_lib.domain.finance.errors import FinanceError
from noctusai_lib.integrations.cnpj_registry.errors import CnpjNotFoundError, CnpjRegistryError
from noctusai_lib.integrations.cnpj_registry.types import CnpjRegistryLookup
from noctusai_lib.primitives.identificador import validar_cnpj
from noctusai_seed.organ_auth import make_organ_auth

from app import billing
from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_core_client,
    get_current_user_org,
    get_user_client,
)
from app.schemas.clients import ArchiveRequest, ClientCreate, ClientOut, ClientUpdate, CnpjLookupOut
from app.services import offboarding
from app.services.billing_charges import BillingError
from app.services.clients_service import ClientsService
from app.services.automation_triggers import adisparar

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/clients", tags=["Clients"])

# Inactivating a client moves money (cancels charges, ends contracts): an ORG ADMIN of the SELECTED org, never plain staff.
_organ_auth = make_organ_auth(get_current_user_org, get_core_client, context="Clientes")
admin_dependency = _organ_auth.admin


def _normalized_document(raw: Optional[str]) -> Optional[str]:
    """CPF / CNPJ digits with valid check digits; blank -> None; 422 otherwise."""
    try:
        return normalize_doc(raw)
    except FinanceError:
        raise HTTPException(status_code=422, detail="CPF ou CNPJ inválido.")


@router.get("", status_code=status.HTTP_200_OK)
def list_clients(
    active_only: bool = Query(default=True),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    svc = ClientsService(get_user_client(token), org_id=org_id)
    try:
        result = svc.list(active_only=active_only, page=page, page_size=page_size)
    except Exception:
        logger.exception("clients.list failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar clientes")
    return result


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
async def create_client(
    payload: ClientCreate,
    auth: tuple = Depends(get_current_user_org),
) -> ClientOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    svc = ClientsService(get_user_client(token), org_id=org_id)
    data = payload.model_dump(mode="json", exclude_none=True)
    if "document" in data:
        data["document"] = _normalized_document(data["document"])
        if data["document"] is None:
            del data["document"]
    try:
        row = svc.create(data)
    except Exception:
        logger.exception("clients.create failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao criar cliente")
    await adisparar("client_created", org_id, subject_type="client", subject_id=row.get("id"))
    return ClientOut(**row)


@router.get("/{client_id}", response_model=ClientOut, status_code=status.HTTP_200_OK)
def get_client(
    client_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> ClientOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    svc = ClientsService(get_user_client(token), org_id=org_id)
    try:
        row = svc.get(client_id)
    except Exception:
        logger.exception("clients.get failed org=%s id=%s", org_id, client_id)
        raise HTTPException(status_code=502, detail="Falha ao buscar cliente")
    if not row:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return ClientOut(**row)


@router.patch("/{client_id}", response_model=ClientOut, status_code=status.HTTP_200_OK)
def update_client(
    client_id: str,
    payload: ClientUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> ClientOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    data = payload.model_dump(mode="json", exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    if data.get("active") is False:
        raise HTTPException(
            status_code=409,
            detail="Para inativar o cliente use a inativação (POST /api/clients/{id}/archive): ela decide o destino das cobranças em aberto.",
        )
    if "document" in data:
        data["document"] = _normalized_document(data["document"])
        if data["document"] is None:
            del data["document"]
    svc = ClientsService(get_user_client(token), org_id=org_id)
    try:
        row = svc.update(client_id, data)
    except Exception:
        logger.exception("clients.update failed org=%s id=%s", org_id, client_id)
        raise HTTPException(status_code=502, detail="Falha ao atualizar cliente")
    if not row:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return ClientOut(**row)


def cnpj_lookup_dependency() -> CnpjRegistryLookup:
    """DI seam (tests swap it through ``app.dependency_overrides``): the public registry, Real unless the harness opted into fakes."""
    return billing.get_cnpj_lookup()


@router.get("/cnpj/{cnpj}", response_model=CnpjLookupOut, status_code=status.HTTP_200_OK)
async def lookup_cnpj(
    cnpj: str,
    auth: tuple = Depends(get_current_user_org),
    lookup: CnpjRegistryLookup = Depends(cnpj_lookup_dependency),
) -> CnpjLookupOut:
    """Razão Social for the client form's "Buscar CNPJ" (public BrasilAPI / ReceitaWS; nothing is stored)."""
    verdict = validar_cnpj(cnpj)
    if not verdict.valido or not verdict.canonico:
        raise HTTPException(status_code=422, detail="CNPJ inválido.")
    digits = "".join(ch for ch in verdict.canonico if ch.isalnum())
    try:
        found = await lookup.lookup(digits)
    except CnpjNotFoundError:
        raise HTTPException(status_code=404, detail="CNPJ não encontrado na Receita Federal.")
    except CnpjRegistryError:
        logger.warning("clients.cnpj lookup failed", exc_info=True)
        raise HTTPException(status_code=502, detail="Não foi possível consultar o CNPJ agora. Preencha a Razão Social manualmente.")
    return CnpjLookupOut(cnpj=digits, legal_name=found.razao_social, situacao_cadastral=found.situacao_cadastral)


@router.get("/{client_id}/offboarding-preview", status_code=status.HTTP_200_OK)
async def offboarding_preview(client_id: str, auth: tuple = Depends(admin_dependency)) -> dict:
    org_id = str(coerce_org_uuid(auth[2]))
    try:
        return await asyncio.to_thread(lambda: offboarding.preview(get_admin_client(), org_id, client_id))
    except BillingError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)
    except Exception:
        logger.exception("clients.offboarding_preview failed org=%s id=%s", org_id, client_id)
        raise HTTPException(status_code=502, detail="Falha ao consultar as cobranças do cliente")


@router.post("/{client_id}/archive", status_code=status.HTTP_200_OK)
async def archive_client(
    client_id: str,
    payload: Optional[ArchiveRequest] = None,
    auth: tuple = Depends(admin_dependency),
) -> dict:
    """Inactivate the client: each open charge is cancelled or kept (``charges``), then its contracts end.

    The charge decisions + the client row are ONE transaction; the contract terminations and gateway cancels follow and
    are reported back (``contracts_failed`` / ``gateway_pending`` non-empty => the same call finishes them).
    Reversible via PATCH ``active=true`` (contracts that ended stay ended).
    """
    user, _token, raw_org = auth
    org_id = str(coerce_org_uuid(raw_org))
    decisions = {c.entry_id: c.action for c in (payload.charges if payload else [])}
    try:
        summary = await asyncio.to_thread(lambda: offboarding.offboard(
            get_admin_client(), billing.get_gateway(), org_id, client_id, decisions, user_id=str(getattr(user, "id", "") or "") or None))
    except BillingError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)
    except Exception:
        logger.exception("clients.archive failed org=%s id=%s", org_id, client_id)
        raise HTTPException(status_code=502, detail="Falha ao inativar cliente")
    if summary["contracts_failed"]:
        raise HTTPException(
            status_code=502,
            detail={"message": "Cliente inativado, mas nem todos os contratos foram encerrados. Repita a operação para concluir.",
                    **summary},
        )
    return {"ok": True, "id": client_id, **summary}


@router.delete("/{client_id}", status_code=status.HTTP_200_OK)
async def delete_client(client_id: str, auth: tuple = Depends(admin_dependency)) -> dict:
    """Soft-delete the client (``deleted_at``/``deleted_by``): hidden from every list/picker, rows kept.

    Refused 409 ``cliente_com_pendencias`` while the client has an ACTIVE/suspended contract or an open
    (pending/overdue) charge: terminate/cancel those first (or inactivate through /archive).
    """
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        # The live-client check is the 404 authority: preview() below would still find an already-deleted row.
        if ClientsService(get_user_client(token), org_id=org_id).get(client_id) is None:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        blockers = await asyncio.to_thread(lambda: offboarding.deletion_blockers(get_admin_client(), str(org_id), client_id))
        if blockers["contracts"] or blockers["charges"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "cliente_com_pendencias",
                    "detail": "Este cliente tem contrato ativo ou cobranças em aberto. Encerre o contrato e cancele ou receba as cobranças antes de excluir.",
                    "contracts": len(blockers["contracts"]),
                    "charges": len(blockers["charges"]),
                },
            )
        deleted = ClientsService(get_user_client(token), org_id=org_id).soft_delete(
            client_id, deleted_by=str(getattr(user, "id", "") or "") or None)
    except HTTPException:
        raise
    except BillingError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)
    except Exception:
        logger.exception("clients.delete failed org=%s id=%s", org_id, client_id)
        raise HTTPException(status_code=502, detail="Falha ao excluir cliente")
    if not deleted:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return {"ok": True, "id": client_id}
