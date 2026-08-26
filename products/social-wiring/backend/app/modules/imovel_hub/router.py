"""`/api/imoveis/{codigo}/...` — the cartório data + documents we author.

Deliberately a SEPARATE router from `app/routers/imoveis_router.py`, which
is the read surface over the Vista sync mirror. The split mirrors the one
migration 075 makes in the schema, for the same reason: what the CRM tells
us and what we author about a property are different things with different
write rules, and one router owning both invites a "just send the whole row"
refactor that nulls a matrícula number.

🔴 ROUTE-ORDERING: `imoveis_router` declares its catch-all `GET /{codigo}`
LAST, precisely so literal siblings (`/filtros`, `/sync`) are not shadowed.
Every path here is TWO segments deep (`/{codigo}/dados`,
`/{codigo}/documentos`, ...), so it cannot collide with that one-segment
shape regardless of which router mounts first. No ordering constraint
applies between the two files.

Envelope conventions (house): list responses are `{"items": [...],
"total": n}`; errors go through `AppException` → `{"error": {...}}`. Every
route is org-scoped and auth-required.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    UploadFile,
    status,
)

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.modules.imovel_hub import dados_service as dados_svc
from app.modules.imovel_hub import documentos_service as docs_svc
from app.modules.imovel_hub import matricula_extracao_service as matricula_svc
from app.modules.imovel_hub.deps import (
    get_imovel_hub_client,
    get_matricula_extractor_factory,
    get_storage_backend,
)
from app.modules.imovel_hub.schemas import ImovelDadosPatchBody

router = APIRouter(prefix="/api/imoveis", tags=["imoveis-dados"])


def _auth_parts(auth):
    user, _token, raw_org = auth
    return user, coerce_org_uuid(raw_org)


# ─── Cartório data ────────────────────────────────────────────────────────


@router.get("/{codigo}/dados")
async def get_dados_route(
    codigo: str,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return dados_svc.obter(client, org_id, codigo.upper())


@router.patch("/{codigo}/dados")
async def patch_dados_route(
    codigo: str,
    body: ImovelDadosPatchBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    user, org_id = _auth_parts(auth)
    # `model_fields_set`, NOT `model_dump(exclude_none=True)`: `None` is a
    # real value here (clearing a wrongly-typed matrícula number), so absence
    # is the only thing that can mean "leave alone".
    valores = {k: getattr(body, k) for k in body.model_fields_set}
    return dados_svc.atualizar(
        client,
        org_id,
        codigo.upper(),
        valores=valores,
        usuario_id=getattr(user, "id", None),
    )


# ─── Documents ────────────────────────────────────────────────────────────


@router.get("/{codigo}/documentos")
async def list_documentos_route(
    codigo: str,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return docs_svc.listar(client, org_id, codigo.upper())


@router.post("/{codigo}/documentos")
async def upload_documento_route(
    codigo: str,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    tipo_documento: str = Form(...),
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
    storage=Depends(get_storage_backend),
    extractor_factory=Depends(get_matricula_extractor_factory),
) -> dict:
    user, org_id = _auth_parts(auth)
    codigo = codigo.upper()
    data = await file.read()
    documento = await docs_svc.upload(
        client,
        storage,
        org_id,
        codigo,
        filename=file.filename or "arquivo",
        content_type=file.content_type or "application/octet-stream",
        data=data,
        tipo_documento=tipo_documento,
        enviado_por=getattr(user, "id", None),
    )

    # The matrícula gets read AFTER the response. The ladder's vision rung
    # takes seconds to tens of seconds on a 30-page scan, so doing it inline
    # would make a successful upload feel broken and would couple it to an
    # LLM provider being reachable. The upload is already committed and
    # stamped `extracao_status='pendente'`; the job only moves that forward,
    # and `varrer_pendentes` recovers it if the job never runs.
    if docs_svc.deve_extrair(tipo_documento):
        background.add_task(
            matricula_svc.extrair,
            client,
            storage,
            org_id,
            codigo,
            UUID(documento["id"]),
            extractor=extractor_factory(str(org_id)),
        )
    return documento


@router.get("/{codigo}/documentos/{documento_id}/url")
async def get_documento_url_route(
    codigo: str,
    documento_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
    storage=Depends(get_storage_backend),
) -> dict:
    _user, org_id = _auth_parts(auth)
    return await docs_svc.url_do_documento(
        client, storage, org_id, codigo.upper(), documento_id
    )


@router.delete(
    "/{codigo}/documentos/{documento_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_documento_route(
    codigo: str,
    documento_id: UUID,
    # A required QUERY param, not a body — same call the sibling
    # `card_hub` route makes, and for the same mechanical reason: the seed
    # `ApiClient.delete()` has no body parameter, and DELETE-with-body is
    # poorly supported across the stack (Starlette's own TestClient refuses
    # to send one). Required rather than defaulted because "wrong file
    # uploaded" and "superseded by a newer certidão" are different facts,
    # and a reason nobody had to supply always says the same thing.
    motivo: str = Query(..., min_length=1, max_length=500),
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
):
    # No `-> None` annotation: FastAPI would build a response model for it
    # and then assert that a 204 carries no body, which fails at import.
    _user, org_id = _auth_parts(auth)
    docs_svc.remover(client, org_id, codigo.upper(), documento_id, motivo=motivo)


__all__ = ["router"]
