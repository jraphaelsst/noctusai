"""Vista CRM showcase router — admin-only proxy onto external CRM.

This router never touches Vista directly; it goes through
`app.services.vista_showcase_service`, which funnels every outbound call
through one audit-log path.

LGPD posture: see `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/vista.md` § 5.4
(audit-log contract) and § 5.6 (admin-gating). Admin-only is the v1
mitigation, not an exemption — every call writes an audit-log row to
`erp.user_actions_log`.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.config import settings
from app.dependencies import require_role
from noctusai_lib.integrations.vista import (
    VistaClient,
    VistaConfigError,
    VistaFieldNotAvailable,
    VistaNotFound,
    VistaPermissionDenied,
    VistaTimeout,
    VistaUpstreamError,
)
from app.services import vista_showcase_service as svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/vista-showcase", tags=["Vista Showcase (admin)"])

ALLOWED_ADMIN_ROLES = ("platform_admin", "admin", "owner")


# ---------------------------------------------------------------------------
# Admin-only dependency
# ---------------------------------------------------------------------------
# Phase 3 (erp-wiring 2026-05-11) — bespoke `require_admin` body retired in
# favor of the seed `make_require_role` composition (Pattern F continuation,
# PROJECT.md §11). The ERP-specific resolution order (SSO short-circuit →
# `erp_role` → `noctus_role`) lives in `app.dependencies.get_erp_user_role`;
# `require_role` is the bound `make_require_role` factory.
#
# `require_admin` is kept as a thin adapter so each endpoint's signature
# binds to a single dep and unwraps `(user, _token, _role) → user` without
# repeating the slice at every callsite.


async def require_admin(auth_role = Depends(require_role(*ALLOWED_ADMIN_ROLES))):
    """Allow only platform/erp admins. Returns the resolved user object."""
    user, _token, _role = auth_role
    return user


def _client() -> VistaClient:
    return VistaClient(settings.vista_base_url, settings.vista_api_key)


# ---------------------------------------------------------------------------
# Tabs catalog — drives frontend sub-tab nav
# ---------------------------------------------------------------------------


@router.get("/tabs")
async def list_tabs(user=Depends(require_admin)):
    tabs = svc.list_tabs(_client())
    return {"tabs": [t.model_dump() for t in tabs]}


# ---------------------------------------------------------------------------
# Imóveis tab
# ---------------------------------------------------------------------------


@router.get("/imoveis")
async def imoveis(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=50),
    status: Optional[str] = None,
    categoria: Optional[str] = None,
    cidade: Optional[str] = None,
    bairro: Optional[str] = None,
    finalidade: Optional[str] = None,
    user=Depends(require_admin),
):
    try:
        env = await svc.fetch_imoveis(
            _client(),
            user_id=str(user.id),
            page=page,
            page_size=page_size,
            status=status,
            categoria=categoria,
            cidade=cidade,
            bairro=bairro,
            finalidade=finalidade,
        )
        return env.model_dump()
    except VistaConfigError:
        raise HTTPException(503, "Vista não configurada (VISTA_BASE_URL / VISTA_API_KEY ausentes).")
    except VistaPermissionDenied:
        raise HTTPException(403, "Permissão pendente — solicite expansão de chave junto à Vista.")
    except VistaNotFound:
        raise HTTPException(404, "Endpoint Vista não disponível neste tenant.")
    except VistaFieldNotAvailable as e:
        # Match VistaUpstreamError ordering: subclass must come BEFORE the
        # parent so the field-error path wins.
        raise HTTPException(422, f"Campo Vista '{e.field}' indisponível para este tenant — atualize IMOVEL_LIST_FIELDS.")
    except VistaTimeout:
        raise HTTPException(504, "Vista demorou mais que 15s para responder.")
    except VistaUpstreamError as e:
        raise HTTPException(502, f"Vista respondeu erro {e.status}.")


@router.get("/imoveis/{codigo}")
async def imovel_detalhes(codigo: str, user=Depends(require_admin)):
    try:
        env = await svc.fetch_imovel_detalhes(_client(), user_id=str(user.id), codigo=codigo)
        return env.model_dump()
    except VistaConfigError:
        raise HTTPException(503, "Vista não configurada.")
    except VistaPermissionDenied:
        raise HTTPException(403, "Permissão pendente para acessar detalhes deste imóvel.")
    except VistaNotFound:
        raise HTTPException(404, "Imóvel não encontrado em Vista.")
    except VistaFieldNotAvailable as e:
        raise HTTPException(422, f"Campo '{e.field}' não disponível para este tenant.")
    except VistaTimeout:
        raise HTTPException(504, "Vista demorou mais que 15s para responder.")
    except VistaUpstreamError as e:
        raise HTTPException(502, f"Vista respondeu erro {e.status}.")


@router.get("/imoveis-conteudo")
async def imoveis_conteudo(user=Depends(require_admin)):
    """Filter dropdown content (Status, Categoria, Cidade, Bairro enums)."""
    try:
        env = await svc.fetch_imoveis_conteudo(_client(), user_id=str(user.id))
        return env.model_dump()
    except VistaConfigError:
        raise HTTPException(503, "Vista não configurada.")
    except VistaPermissionDenied:
        raise HTTPException(403, "Permissão pendente.")
    except VistaNotFound:
        raise HTTPException(404, "Endpoint não disponível.")
    except VistaTimeout:
        raise HTTPException(504, "Vista timeout.")
    except VistaUpstreamError as e:
        raise HTTPException(502, f"Vista erro {e.status}.")


# ---------------------------------------------------------------------------
# Clientes tab
# ---------------------------------------------------------------------------
#
# LGPD: two endpoints, not one, and the split is the mitigation. `/clientes`
# serves the minimised list projection; `/clientes/{codigo}` is the only route
# that returns DataNascimento / Sexo / EstadoCivil / Profissao, for one named
# record, with its own audit row. Merging them would silently widen bulk
# exposure by four categories — see the field-set comment in the service.


@router.get("/clientes")
async def clientes(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=50),
    nome: Optional[str] = None,
    status: Optional[str] = None,
    user=Depends(require_admin),
):
    try:
        env = await svc.fetch_clientes(
            _client(),
            user_id=str(user.id),
            page=page,
            page_size=page_size,
            nome=nome,
            status=status,
        )
        return env.model_dump()
    except VistaConfigError:
        raise HTTPException(503, "Vista não configurada (VISTA_BASE_URL / VISTA_API_KEY ausentes).")
    except VistaPermissionDenied:
        # Reachable again only if the 2026-08-21 grant is rolled back, or on a
        # tenant that never had it. Kept, not deleted — see vista.md § 4.2.
        raise HTTPException(403, "Permissão pendente — solicite expansão de chave junto à Vista.")
    except VistaNotFound:
        raise HTTPException(404, "Endpoint /clientes/listar não disponível neste tenant.")
    except VistaFieldNotAvailable as e:
        raise HTTPException(422, f"Campo Vista '{e.field}' indisponível para este tenant — atualize CLIENTE_LIST_FIELDS.")
    except VistaTimeout:
        raise HTTPException(504, "Vista demorou mais que 15s para responder.")
    except VistaUpstreamError as e:
        raise HTTPException(502, f"Vista respondeu erro {e.status}.")


@router.get("/clientes/{codigo}")
async def cliente_detalhes(codigo: str, user=Depends(require_admin)):
    try:
        env = await svc.fetch_cliente_detalhes(_client(), user_id=str(user.id), codigo=codigo)
        return env.model_dump()
    except VistaConfigError:
        raise HTTPException(503, "Vista não configurada.")
    except VistaPermissionDenied:
        raise HTTPException(403, "Permissão pendente para acessar detalhes deste cliente.")
    except VistaNotFound:
        raise HTTPException(404, "Cliente não encontrado em Vista.")
    except VistaFieldNotAvailable as e:
        raise HTTPException(422, f"Campo '{e.field}' não disponível para este tenant — atualize CLIENTE_DETAIL_FIELDS.")
    except VistaTimeout:
        raise HTTPException(504, "Vista demorou mais que 15s para responder.")
    except VistaUpstreamError as e:
        raise HTTPException(502, f"Vista respondeu erro {e.status}.")


# ---------------------------------------------------------------------------
# Usuários + Agência tabs
# ---------------------------------------------------------------------------


@router.get("/usuarios")
async def usuarios(user=Depends(require_admin)):
    try:
        env = await svc.fetch_usuarios(_client(), user_id=str(user.id))
        return env.model_dump()
    except VistaConfigError:
        raise HTTPException(503, "Vista não configurada.")
    except VistaPermissionDenied:
        raise HTTPException(403, "Permissão pendente.")
    except VistaNotFound:
        raise HTTPException(404, "Endpoint /usuarios/listar não disponível.")
    except VistaTimeout:
        raise HTTPException(504, "Vista timeout.")
    except VistaUpstreamError as e:
        raise HTTPException(502, f"Vista erro {e.status}.")


@router.get("/agencias")
async def agencias(user=Depends(require_admin)):
    try:
        env = await svc.fetch_agencias(_client(), user_id=str(user.id))
        return env.model_dump()
    except VistaConfigError:
        raise HTTPException(503, "Vista não configurada.")
    except VistaPermissionDenied:
        raise HTTPException(403, "Permissão pendente.")
    except VistaNotFound:
        raise HTTPException(404, "Endpoint /agencias/listar não disponível.")
    except VistaTimeout:
        raise HTTPException(504, "Vista timeout.")
    except VistaUpstreamError as e:
        raise HTTPException(502, f"Vista erro {e.status}.")


# ---------------------------------------------------------------------------
# Diagnóstico tab — admin-only health probe
# ---------------------------------------------------------------------------


@router.get("/diagnostico")
async def diagnostico(user=Depends(require_admin)):
    diag = await svc.diagnose(_client(), user_id=str(user.id))
    return diag.model_dump()
