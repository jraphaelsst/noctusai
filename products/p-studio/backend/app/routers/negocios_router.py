"""CRM comercial — o funil (spec § 2)."""
from fastapi import APIRouter, Depends

from app.dependencies import CurrentUser, get_current_user
from app.schemas.negocios import (
    ETAPA_LABELS,
    ETAPAS,
    NegocioCreate,
    NegocioEtapaUpdate,
    NegocioOut,
    NegocioUpdate,
)
from app.services.base import somente_preenchidos
from app.services.negocios_service import NegociosService

router = APIRouter(prefix="/api/negocios", tags=["negocios"])


def _service(user: CurrentUser) -> NegociosService:
    return NegociosService(user.db, user.org_id)


@router.get("/etapas")
def listar_etapas():
    """Colunas do kanban, na ordem canônica do funil."""
    return [{"id": e, "label": ETAPA_LABELS[e]} for e in ETAPAS]


@router.get("", response_model=list[NegocioOut])
def listar(user: CurrentUser = Depends(get_current_user)):
    return _service(user).listar_completo()


@router.post("", response_model=NegocioOut, status_code=201)
def criar(payload: NegocioCreate, user: CurrentUser = Depends(get_current_user)):
    dados = payload.model_dump(mode="json")
    servico_ids = dados.pop("servico_ids", [])
    return _service(user).criar_com_servicos(dados, servico_ids)


@router.get("/{negocio_id}", response_model=NegocioOut)
def obter(negocio_id: str, user: CurrentUser = Depends(get_current_user)):
    return _service(user).obter_completo(negocio_id)


@router.patch("/{negocio_id}", response_model=NegocioOut)
def atualizar(
    negocio_id: str,
    payload: NegocioUpdate,
    user: CurrentUser = Depends(get_current_user),
):
    changes = somente_preenchidos(payload)
    servico_ids = changes.pop("servico_ids", None)
    return _service(user).atualizar_com_servicos(negocio_id, changes, servico_ids)


@router.patch("/{negocio_id}/etapa", response_model=NegocioOut)
def mudar_etapa(
    negocio_id: str,
    payload: NegocioEtapaUpdate,
    user: CurrentUser = Depends(get_current_user),
):
    """Move o card no kanban.

    Rota própria — e não um campo do PATCH geral — porque a mudança de etapa
    tem efeito colateral: abre a produção, registra a entrega, dá baixa no
    financeiro. Ver `NegociosService.mudar_etapa`.
    """
    return _service(user).mudar_etapa(negocio_id, payload.etapa)


@router.delete("/{negocio_id}", status_code=204)
def excluir(negocio_id: str, user: CurrentUser = Depends(get_current_user)):
    _service(user).excluir(negocio_id)
    return None
