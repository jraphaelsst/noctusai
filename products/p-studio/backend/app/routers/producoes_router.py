"""Pipeline de produção (spec § 4)."""
from fastapi import APIRouter, Depends

from app.dependencies import CurrentUser, get_current_user
from app.schemas.producoes import (
    ETAPA_LABELS,
    ETAPAS,
    ProducaoCreate,
    ProducaoEtapaUpdate,
    ProducaoEventoCreate,
    ProducaoOut,
    ProducaoUpdate,
)
from app.services.base import somente_preenchidos
from app.services.producoes_service import ProducoesService

router = APIRouter(prefix="/api/producoes", tags=["producoes"])


def _service(user: CurrentUser) -> ProducoesService:
    return ProducoesService(user.db, user.org_id)


@router.get("/etapas")
def listar_etapas():
    return [{"id": e, "label": ETAPA_LABELS[e]} for e in ETAPAS]


@router.get("", response_model=list[ProducaoOut])
def listar(user: CurrentUser = Depends(get_current_user)):
    return _service(user).listar_completo()


@router.post("", response_model=ProducaoOut, status_code=201)
def criar(payload: ProducaoCreate, user: CurrentUser = Depends(get_current_user)):
    """Cria uma produção avulsa.

    O caminho normal é o funil abrir a produção sozinho quando o negócio entra
    em `producao`. Esta rota existe para o trabalho que não passou pelo CRM.
    """
    producao = _service(user).criar(payload.model_dump(mode="json"))
    return _service(user).obter_completo(producao["id"])


@router.get("/{producao_id}", response_model=ProducaoOut)
def obter(producao_id: str, user: CurrentUser = Depends(get_current_user)):
    return _service(user).obter_completo(producao_id)


@router.patch("/{producao_id}", response_model=ProducaoOut)
def atualizar(
    producao_id: str,
    payload: ProducaoUpdate,
    user: CurrentUser = Depends(get_current_user),
):
    service = _service(user)
    service.atualizar(producao_id, somente_preenchidos(payload))
    return service.obter_completo(producao_id)


@router.patch("/{producao_id}/etapa", response_model=ProducaoOut)
def mudar_etapa(
    producao_id: str,
    payload: ProducaoEtapaUpdate,
    user: CurrentUser = Depends(get_current_user),
):
    """Avança (ou volta) a etapa, registrando um evento no histórico."""
    return _service(user).mudar_etapa(
        producao_id, payload.etapa, payload.responsavel, payload.comentario
    )


@router.post("/{producao_id}/eventos", response_model=ProducaoOut, status_code=201)
def comentar(
    producao_id: str,
    payload: ProducaoEventoCreate,
    user: CurrentUser = Depends(get_current_user),
):
    return _service(user).comentar(producao_id, payload.comentario, payload.responsavel)


@router.delete("/{producao_id}", status_code=204)
def excluir(producao_id: str, user: CurrentUser = Depends(get_current_user)):
    _service(user).excluir(producao_id)
    return None
