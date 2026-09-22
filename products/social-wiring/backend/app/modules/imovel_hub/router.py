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
    HTTPException,
    Query,
    UploadFile,
    status,
)

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.modules.imovel_hub import busca_service
from app.modules.imovel_hub import dados_service as dados_svc
from app.modules.imovel_hub import documentos_service as docs_svc
from app.modules.imovel_hub import matricula_extracao_service as matricula_svc
from app.modules.imovel_hub.deps import (
    get_imovel_hub_client,
    get_matricula_extractor_factory,
    get_storage_backend,
)
from app.modules.imovel_hub.schemas import (
    EnderecoManualPatchBody,
    ImovelDadosPatchBody,
    ImovelDocumentoExtracaoPatchBody,
)

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


@router.put("/{codigo}/endereco-manual")
async def put_endereco_manual_route(
    codigo: str,
    body: EnderecoManualPatchBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    """Manual override for the 4 address fields `contrato_gerador.derivacao`
    reads (migration 149) — see `dados_service.gravar_endereco_manual`."""
    user, org_id = _auth_parts(auth)
    codigo_canonico = codigo.upper()
    valores = {
        f"endereco_manual_{k}": getattr(body, k) for k in body.model_fields_set
    }
    catalogo = (
        busca_service.enriquecer(client, org_id, [codigo_canonico]).get(
            busca_service.canonical(codigo_canonico)
        )
        or {}
    )
    return dados_svc.gravar_endereco_manual(
        client,
        org_id,
        codigo_canonico,
        valores=valores,
        mirror=catalogo,
        usuario_id=getattr(user, "id", None),
    )


@router.get("/{codigo}/endereco-manual/historico")
async def get_endereco_manual_historico_route(
    codigo: str,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    _user, org_id = _auth_parts(auth)
    itens = dados_svc.historico_endereco(client, org_id, codigo.upper())
    return {"items": itens, "total": len(itens)}


@router.post("/{codigo}/registrar")
async def registrar_imovel_route(
    codigo: str,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    """Give a brand-new código (never seen in the Vista mirror nor the
    registry) a registry identity, so it becomes pickable everywhere
    `imovel_registry` is the FK target — `ImovelCodigoPicker`'s "cadastrar
    novo imóvel" affordance for a property that has no anúncio at all
    (off-market, being tested manually). Idempotent — `registrar_imovel`
    itself already is."""
    _user, org_id = _auth_parts(auth)
    canonico = dados_svc.registrar_imovel(client, org_id, codigo, origem="manual")
    if not canonico:
        raise HTTPException(status_code=400, detail="Código do imóvel é obrigatório.")
    return {"codigo": canonico}


@router.get("/{codigo}/registro")
async def obter_registro_route(
    codigo: str,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    """Is this código known at all — even a manually registered property
    (or a lead-discovered one) `GET /api/imoveis/{codigo}` 404s, because
    that route only reads the Vista-synced mirror? The property page's
    "can this even open" check, before it tries to render cartório/
    endereço/inscrição fields that route can never carry for such a
    código. See `dados_service.registro_status` for the `origem` mapping.
    """
    _user, org_id = _auth_parts(auth)
    resultado = dados_svc.registro_status(client, org_id, codigo)
    if resultado is None:
        raise HTTPException(
            status_code=404, detail=f"Imóvel {codigo} não encontrado."
        )
    return resultado


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
    # Migration 118 — a SECOND, independent job: numero/emitida_em/
    # validade_ate/resultado/inscricao_imobiliaria. Runs alongside the
    # número-de-matrícula job above for `matricula` — two different
    # questions asked of the same PDF.
    if docs_svc.deve_extrair_estrutura(tipo_documento):
        background.add_task(
            docs_svc.extrair_estrutura,
            client,
            storage,
            org_id,
            codigo,
            UUID(documento["id"]),
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
    user, org_id = _auth_parts(auth)
    # The user is passed so the LGPD access log (migration 109) names WHO
    # opened the file — an unattributed content read is not an audit trail.
    return await docs_svc.url_do_documento(
        client,
        storage,
        org_id,
        codigo.upper(),
        documento_id,
        usuario_id=getattr(user, "id", None),
    )


@router.get("/{codigo}/documentos/{documento_id}/acessos")
async def list_documento_acessos_route(
    codigo: str,
    documento_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    """The LGPD access log for one imóvel document (migration 109/111)."""
    _user, org_id = _auth_parts(auth)
    return docs_svc.listar_acessos(client, org_id, codigo.upper(), documento_id)


@router.patch("/{codigo}/documentos/{documento_id}/extracao")
async def patch_documento_extracao_route(
    codigo: str,
    documento_id: UUID,
    body: ImovelDocumentoExtracaoPatchBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    """The operator confirms or corrects a document's structured extraction
    (migration 118). Same `model_fields_set` convention as `patch_dados_
    route`: an empty body is a valid confirmation, not a no-op."""
    user, org_id = _auth_parts(auth)
    valores = {k: getattr(body, k) for k in body.model_fields_set}
    return docs_svc.confirmar_extracao(
        client,
        org_id,
        codigo.upper(),
        documento_id,
        valores=valores,
        usuario_id=getattr(user, "id", None),
    )


@router.get("/{codigo}/certidoes")
async def list_certidoes_route(
    codigo: str,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
) -> dict:
    """The imóvel CND group — IPTU CND, condomínio, matrícula emissão date —
    latest per tipo (migration 118)."""
    _user, org_id = _auth_parts(auth)
    return docs_svc.certidoes(client, org_id, codigo.upper())


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
    user, org_id = _auth_parts(auth)
    docs_svc.remover(
        client,
        org_id,
        codigo.upper(),
        documento_id,
        motivo=motivo,
        usuario_id=getattr(user, "id", None),
    )


__all__ = ["router"]
