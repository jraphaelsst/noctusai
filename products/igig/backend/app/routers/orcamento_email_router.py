"""Orçamento by e-mail (slice B, roadmap R7).

  POST /api/orcamentos/{id}/enviar {para?, cc?, assunto?, mensagem?}
       → {data: {orcamento, message_id}}
  GET  /api/orcamentos/{id}/emails → {data: OrcamentoEmail[]}

The send needs the PDF slice A generates (``pdf_key`` → 409 ``pdf_nao_gerado``)
and a recipient (the lead's e-mail by default → 422
``email_destinatario_ausente``). Business logic lives in
``app/services/orcamento_email.py``.

`enviar_orcamento` answers the FULL `Orcamento` shape — slice A's serializer
(`app/services/orcamentos.py::obter`), the same one every other orçamento
endpoint answers — not the raw stored row `orcamento_email.enviar_orcamento`
returns (no `itens`/`lead`/`negocio`/`limites_escopo`). Building `repos` from
the SAME PostgREST client `get_db` injects (rather than the independently
resolved `Depends(get_repositorios)`) keeps the write and the re-read on one
store, as production already does — `SupabaseRecordStore` over ``db`` IS
`get_repositorios`'s production path (`app/store.py::make_store`).
"""
# NOTE: no `from __future__ import annotations` — consistent with the other
# IgIg routers.
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from noctusai_lib.integrations.persistence import RecordNotFound, get_record_store
from noctusai_lib.integrations.storage import StorageBackend

from app.config import settings
from app.dependencies import coerce_org_uuid, get_current_user_org
from app.email_deps import (
    EmailSenderFactory,
    get_email_sender_factory,
    get_email_settings,
    get_pdf_storage,
)
from app.pipelines import get_db
from app.repositories import Repositorios
from app.repositories.email import repositorios_email
from app.schemas.email import EnviarOrcamentoIn
from app.services import orcamento_email
from app.services import orcamentos as orcamentos_svc
from app.services.email_config import EmailSettings
from app.services.regras import RegraViolada, http_de
from app.store import get_repositorios

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orcamentos", tags=["orcamentos"])

_CAMPOS_EMAIL = (
    "id", "orcamento_id", "direction", "message_id", "thread_id",
    "from_addr", "subject", "snippet", "occurred_at",
)


def _org(auth: tuple) -> str:
    _user, _token, raw_org = auth
    return str(coerce_org_uuid(raw_org))


def _nao_encontrado() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"detail": "Orçamento não encontrado.", "code": "orcamento_nao_encontrado"},
    )


@router.post("/{orcamento_id}/enviar")
async def enviar_orcamento(
    orcamento_id: str,
    payload: EnviarOrcamentoIn,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
    sender_factory: EmailSenderFactory = Depends(get_email_sender_factory),
    cfg: EmailSettings = Depends(get_email_settings),
    storage: StorageBackend = Depends(get_pdf_storage),
) -> dict:
    org_id = _org(auth)
    repos = Repositorios(get_record_store(supabase_client=db))
    try:
        _atualizado, message_id = await orcamento_email.enviar_orcamento(
            repos, repositorios_email(repos.store), org_id, orcamento_id,
            para=payload.para, cc=payload.cc,  # type: ignore[arg-type] — normalized to lists
            assunto=payload.assunto, mensagem=payload.mensagem,
            sender_factory=sender_factory,
            storage=storage, bucket=settings.igig_storage_bucket, settings=cfg,
        )
    except RecordNotFound as erro:
        raise _nao_encontrado() from erro
    except RegraViolada as erro:
        raise http_de(erro) from erro
    orcamento = orcamentos_svc.obter(db, org_id, orcamento_id)
    return {"data": {"orcamento": orcamento, "message_id": message_id}}


@router.get("/{orcamento_id}/emails")
async def listar_emails(
    orcamento_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> dict:
    org_id = _org(auth)
    try:
        repos.orcamento.buscar(org_id, orcamento_id)
    except RecordNotFound as erro:
        raise _nao_encontrado() from erro
    linhas = repositorios_email(repos.store).emails.do_orcamento(org_id, orcamento_id)
    return {"data": [{campo: linha.get(campo) for campo in _CAMPOS_EMAIL} for linha in linhas]}
