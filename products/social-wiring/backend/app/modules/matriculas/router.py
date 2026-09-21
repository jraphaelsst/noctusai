"""`/api/matriculas/*` — transcribe a matrícula, split it into acts, and let a
contract quote them literally.

Ported from `erp-imobiliario`'s `app/routers/matriculas.py` (2026-09-02).
The legacy route shapes, status codes and Portuguese are identical; three
things changed in the port, and each one is a decision rather than a
translation:

1. 🔴 ORG COMES FROM THE DB, NOT THE JWT — and now not from this file
   either. ERP had to read `noctus_users` by hand (`resolve_org_id_db`)
   because its `get_current_user` returned no org; a stale JWT claim
   yielded a NULL org, the app omitted the NOT NULL column, and the insert
   500'd for a freshly-provisioned user (erp incident 2026-07-07, migration
   038). This product's canonical dep `get_current_user_org` already
   resolves org from `public.noctus_users` FIRST and 403s when there is
   none, so the hand-rolled lookup and its 400 branch are gone — the
   incident is closed one layer down instead of re-litigated here.
   Migration 092 additionally stamps `org_id DEFAULT public.current_org_id()`,
   so the upload INSERT deliberately does NOT send an org: the DB derives it
   from the same table RLS trusts, and the app cannot get it wrong.

2. 🔴 NO `log_action`. ERP audited upload + delete through
   `app.dependencies.log_action`; this product has no audit-log table and
   no such helper. The calls are dropped rather than shimmed — inventing a
   product-local audit trail to keep two call sites company is a fork, not
   a port.

3. 🔴 THE LEGACY ROUTES USE THE CALLER'S TOKEN; THE BACKGROUND TASK DOES
   NOT. RLS decides which org's rows those requests reach — application
   `.eq("org_id", ...)` filters are a second lock, not the first one. But a
   background task outlives the request that spawned it, so it cannot hold
   that token (a long vision pass can outlive its expiry, and the write
   would then fail with nobody left to tell). It writes service-role, which
   is exactly why every write in `service.py` carries an explicit `org_id`
   predicate.

MIGRATION 109 — THE STRUCTURED HALF
-----------------------------------
The contract ("Promessa de Venda e Compra") describes the property with the
LITERAL matrícula text, typos included, as a sequence of acts the operator
selects. The routes added for that (`/extracoes/de-documento`,
`/extracoes/{id}/atos`, `/extracoes/{id}/fontes`, `/contratos/{id}/atos`)
touch `imovel_dados`, `imovel_documentos` and `atendimento_contratos`, whose
RLS grants `authenticated` SELECT only — so they go through the
service-role `get_matriculas_client`, and every query in
`estrutura_service.py` carries an explicit org predicate.

A matrícula uploaded WITH a `codigo` is kept: its PDF becomes the imóvel's
`imovel_documentos` row (one storage home for an imóvel's matrícula, LGPD-
logged since 109), and the imóvel's número-de-matrícula read is queued
exactly as an upload on the imóvel page would queue it.

MIGRATION 115 — WHAT THE ACTS SAY
---------------------------------
`GET .../atos` now carries each act's typed `detalhes` (seed
`extrair_detalhes_ato`, stored as a suggestion). `PUT /atos/{ato_id}/detalhes`
is the operator's confirmation. Three imóvel-level reads build on the acts
the operator chose in 109 — `/imoveis/{codigo}/titulo-aquisitivo`,
`/imoveis/{codigo}/onus-credor` (each with a PUT that confirms the wording)
and `/imoveis/{codigo}/antigos-proprietarios` (the office's 5-year certidões
rule). They live HERE, not in `imovel_hub`, because every answer is a reading
of a matrícula; `titulo_service.py` holds the logic.

Route ordering: every path is under the literal `/api/matriculas` prefix.
`POST /extracoes/de-documento` is a literal sibling of the dynamic
`/extracoes/{extracao_id}`, which declares no POST — nothing can shadow it.
"""
from __future__ import annotations

import asyncio
import logging
import unicodedata
from pathlib import Path
from typing import Optional
from urllib.parse import quote
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
)
from fastapi import Path as PathParam
from fastapi.responses import Response
from noctusai_lib.api.crud_safety import delete_or_404
from noctusai_lib.integrations.documents.abnt import UnsupportedGlyphError

from app.dependencies import coerce_org_uuid, get_current_user_org, get_user_client
from app.modules.imovel_hub import documentos_service as imovel_docs_svc
from app.modules.imovel_hub import matricula_extracao_service as imovel_matricula_svc
from app.modules.imovel_hub.deps import (
    MatriculaExtractorFactory,
    get_matricula_extractor_factory,
    get_storage_backend,
)
from app.modules.matriculas import arquivos_service as arquivos_svc
from app.modules.matriculas import estrutura_service as estrutura_svc
from app.modules.matriculas import qualificacao_service as qualificacao_svc
from app.modules.matriculas import titulo_service as titulo_svc
from app.modules.matriculas.deps import (
    TranscriberFactory,
    get_background_client,
    get_matriculas_client,
    get_notification_service,
    get_transcriber_factory,
)
from app.modules.matriculas.schemas import (
    DetalhesAtoBody,
    EnderecoRegistroBody,
    ExtracaoDeDocumentoBody,
    ExtracaoManualBody,
    FontesMatriculaBody,
    OnusCredorBody,
    SelecaoAtosBody,
    TituloAquisitivoTextoBody,
)
from app.modules.matriculas.service import (
    TABLE,
    check_required_credentials,
    processar_extracao,
    processar_extracao_de_documento,
    registrar_transcricao_manual,
    renderizar_extracao_pdf,
    texto_html_da_extracao,
)
from app.responses import (
    calculate_pagination,
    ok_response,
    paginated_response,
    success_response,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/matriculas", tags=["Matrículas"])

#: Ceiling for one upload. A matrícula is a handful of scanned pages; 20 MB
#: is generous for that and is the number ERP shipped.
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

#: 🔴 THE APP REFUSES TO BOOT WITHOUT THIS ENTRY IN `main.py`.
#: `noctusai_seed.upload_route_overrides` requires every mounted route that
#: declares an `UploadFile` to carry a `max_body_path_overrides` entry — the
#: platform-wide 1 MB default exists to DoS-guard inbound webhooks and would
#: silently 413 every realistic matrícula. `main.py`'s
#: `_MAX_BODY_PATH_OVERRIDES` carries the same number; declared here too, next
#: to the handler ceiling it mirrors, so a test can pin the two together.
MAX_BODY_PATH_OVERRIDES = {"/api/matriculas/extrair": MAX_FILE_SIZE}

#: Selected for the history list. `texto_extraido` is deliberately absent —
#: a full matrícula transcription is tens of KB, and a 50-row page of them
#: is megabytes nobody on that screen reads.
_COLUNAS_LISTA = (
    "id,nome_arquivo,tamanho_bytes,num_paginas,status,erro_mensagem,"
    "codigo,imovel_documento_id,arquivo_origem_id,substituida_por,"
    "possui_marcacao_bruta,created_at"
)


def _auth_parts(auth) -> tuple[object, str, str]:
    """`(user, token, org_id)` with the org normalised to a UUID string.

    `get_current_user_org` is `required=True`, so an unprovisioned caller is
    already a 403 before this runs — there is no org-less branch to handle.
    """
    user, token, raw_org = auth
    return user, token, str(coerce_org_uuid(raw_org))


def _content_disposition(filename: str) -> str:
    """An attachment header that survives an accented filename.

    Copied from `certidoes/routers/certidoes.py::_content_disposition`
    (identical bug, identical fix — an unescaped accented `filename=` raises
    inside Starlette and 500s the whole download) rather than imported: the
    two modules share no common parent this platform lets them both import
    from within THIS slice's scope. Flagged as `scoped-improvement:` in
    S3's delivery note — a third caller makes this N=3, the DRY recurrence
    rule's MUST-formalize threshold.
    """
    folded = (
        unicodedata.normalize("NFKD", filename)
        .encode("ascii", "ignore")
        .decode("ascii")
        .replace('"', "")
        .strip()
    )
    ascii_name = folded or "download"
    return (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )


def _exigir_credenciais(org_id: str) -> None:
    """422 up front: the transcription runs detached, so a missing key
    discovered there reaches the user as a row that failed 40 seconds later
    instead of as an answer to the request that caused it."""
    missing = check_required_credentials(org_id)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=" ".join(missing)
            + " Configure em Configurações → Chaves de API.",
        )


# ─── transcription ────────────────────────────────────────────────────────


@router.post("/extrair")
async def extrair_matricula(
    file: UploadFile = File(...),
    codigo: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    auth=Depends(get_current_user_org),
    background_db=Depends(get_background_client),
    transcriber_factory: TranscriberFactory = Depends(get_transcriber_factory),
    matriculas_client=Depends(get_matriculas_client),
    storage=Depends(get_storage_backend),
    extractor_factory: MatriculaExtractorFactory = Depends(
        get_matricula_extractor_factory
    ),
):
    """Upload a matrícula PDF and start text extraction in the background.

    With `codigo`, the PDF is KEPT as that imóvel's `matricula` document and
    the extraction is linked to it. Without, the standalone shape — the PDF
    is STILL kept (migration 135, `arquivos_svc`), just not attached to any
    imóvel, so the transcription can be re-run and audited against its
    source the same way a linked one can.
    """
    user, token, org_id = _auth_parts(auth)
    db = get_user_client(token)

    _exigir_credenciais(org_id)

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos.")

    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Arquivo muito grande ({len(pdf_bytes) // (1024 * 1024)}MB). "
                f"Máximo: {MAX_FILE_SIZE // (1024 * 1024)}MB."
            ),
        )
    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    codigo_canonico = (codigo or "").strip().upper() or None
    documento: Optional[dict] = None
    vinculo: dict = {}
    if codigo_canonico:
        # 404 for an unknown imóvel happens HERE, before any extraction row
        # exists. The document store is the imóvel's — one home for the PDF.
        documento = await imovel_docs_svc.upload(
            matriculas_client,
            storage,
            UUID(org_id),
            codigo_canonico,
            filename=file.filename or "matricula.pdf",
            content_type="application/pdf",
            data=pdf_bytes,
            tipo_documento="matricula",
            enviado_por=getattr(user, "id", None),
        )
        vinculo = {
            "codigo": codigo_canonico,
            "imovel_documento_id": documento["id"],
        }
    else:
        # 🔴 Migration 135: the standalone shape used to discard `pdf_bytes`
        # right here — nothing downstream of this branch ever saw them
        # again. Retained through the SAME `DocumentoStore` mechanism the
        # linked branch above uses, just with no imóvel to own the row.
        arquivo = await arquivos_svc.guardar(
            matriculas_client,
            storage,
            UUID(org_id),
            filename=file.filename or "matricula.pdf",
            content_type="application/pdf",
            data=pdf_bytes,
            enviado_por=getattr(user, "id", None),
        )
        vinculo = {"arquivo_origem_id": arquivo["id"]}

    # 🔴 `org_id` is deliberately absent: migration 092 defaults the column
    # to `public.current_org_id()`, the same trusted source RLS reads. The
    # app never names the org on a write, so it can never name the wrong one.
    result = (
        db.table(TABLE)
        .insert(
            {
                "user_id": user.id,
                "nome_arquivo": file.filename or "matricula.pdf",
                "tamanho_bytes": len(pdf_bytes),
                "status": "pendente",
                **vinculo,
            }
        )
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar extração")
    extracao = result.data[0]

    # 🔴 The org the DETACHED half writes with comes from the ROW, not from
    # this request. The two agree — the dep resolved the org from
    # `noctus_users` and the column DEFAULT reads the same table — but
    # "agree" is a claim about two code paths, while `extracao["org_id"]` is
    # the org the row ACTUALLY landed in. A background UPDATE scoped to the
    # wrong org is not an error, it is a no-op: the row stays `processando`
    # forever and only the hourly sweep ever notices.
    org_da_linha = str(extracao.get("org_id") or org_id)

    background_tasks.add_task(
        _run_extraction,
        extracao["id"],
        pdf_bytes,
        org_da_linha,
        background_db,
        transcriber_factory,
    )
    if documento is not None:
        # The imóvel's número-de-matrícula read, queued exactly as the imóvel
        # page's own upload queues it — the same job, not a second copy.
        background_tasks.add_task(
            imovel_matricula_svc.extrair,
            matriculas_client,
            storage,
            UUID(org_id),
            codigo_canonico,
            UUID(documento["id"]),
            extractor=extractor_factory(org_id),
        )

    return success_response(extracao)


@router.post("/extracoes/de-documento")
async def extrair_de_documento(
    body: ExtracaoDeDocumentoBody,
    background_tasks: BackgroundTasks,
    auth=Depends(get_current_user_org),
    client=Depends(get_matriculas_client),
    background_db=Depends(get_background_client),
    storage=Depends(get_storage_backend),
    transcriber_factory: TranscriberFactory = Depends(get_transcriber_factory),
):
    """Transcribe a matrícula PDF the imóvel already holds (no re-upload)."""
    user, _token, org_id = _auth_parts(auth)
    _exigir_credenciais(org_id)

    extracao = estrutura_svc.criar_extracao_de_documento(
        client,
        UUID(org_id),
        codigo=body.codigo,
        imovel_documento_id=body.imovel_documento_id,
        usuario_id=getattr(user, "id", None),
    )
    storage_path = extracao.pop("storage_path")
    background_tasks.add_task(
        _run_extraction_de_documento,
        extracao["id"],
        storage_path,
        org_id,
        background_db,
        storage,
        transcriber_factory,
    )
    return success_response(extracao)


@router.post("/extracoes/manual")
async def criar_extracao_manual_route(
    body: ExtracaoManualBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_matriculas_client),
):
    """Create a matrícula transcription straight from typed/pasted text —
    no PDF, no vision AI (migration 147). Runs synchronously (no background
    task): unlike a PDF, there is no I/O-bound step here — it is a plain
    Python segmentation of the text the request already carries."""
    user, _token, org_id = _auth_parts(auth)
    extracao = estrutura_svc.criar_extracao_manual(
        client,
        UUID(org_id),
        codigo=body.codigo,
        texto=body.texto,
        usuario_id=getattr(user, "id", None),
    )
    registrar_transcricao_manual(client, extracao["id"], org_id, body.texto)
    return success_response(
        estrutura_svc.exigir_extracao(client, UUID(org_id), UUID(extracao["id"]))
    )


@router.get("/extracoes")
async def listar_extracoes(
    busca: Optional[str] = Query(None),
    codigo: Optional[str] = Query(None, max_length=64),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    auth=Depends(get_current_user_org),
):
    """List extraction history — without `texto_extraido` (see `_COLUNAS_LISTA`).

    `codigo` narrows to one imóvel's matrículas.
    """
    _user, token, _org_id = _auth_parts(auth)
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(page, page_size)
    codigo_canonico = (codigo or "").strip().upper() or None

    def _filtrar(query):
        if busca:
            query = query.ilike("nome_arquivo", f"%{busca}%")
        if codigo_canonico:
            query = query.eq("codigo", codigo_canonico)
        return query

    count_result = _filtrar(db.table(TABLE).select("id", count="exact")).execute()
    total = count_result.count if count_result.count is not None else 0

    # Bounded by `page_size` (≤ 200), so this read cannot reach PostgREST's
    # 1 000-row cap — no pager needed.
    query = (
        _filtrar(db.table(TABLE).select(_COLUNAS_LISTA).order("created_at", desc=True))
        .range(offset, offset + validated_page_size - 1)
    )

    result = query.execute()
    return paginated_response(
        result.data or [], total, validated_page, validated_page_size
    )


@router.get("/extracoes/{extracao_id}")
async def obter_extracao(
    extracao_id: str,
    auth=Depends(get_current_user_org),
    matriculas_client=Depends(get_matriculas_client),
):
    """Get a single extraction WITH its full text.

    🔴 LGPD (migration 111): the row carries CPF-bearing text, so a
    successful read appends a `text_view` row to `imovel_documento_acessos`
    BEFORE the response goes out — a failed log write fails the request,
    same contract as `DocumentoStore.url`.

    Contract §4 (migration 113): `data` gains `texto_html` (Word-pasteable,
    `None` when there is no text yet) alongside the `formatacao` the raw
    `select("*")` already carries.
    """
    user, token, org_id = _auth_parts(auth)
    db = get_user_client(token)

    # `maybe_single`, not `single`: PostgREST's `single` raises on zero rows
    # (PGRST116) rather than returning empty, which surfaces as a 500 for
    # what is an ordinary 404.
    result = db.table(TABLE).select("*").eq("id", extracao_id).maybe_single().execute()
    if not result or not result.data:
        raise HTTPException(status_code=404, detail="Extração não encontrada")

    estrutura_svc.log_leitura_texto(
        matriculas_client, UUID(org_id), extracao_id, getattr(user, "id", None)
    )
    dados = dict(result.data)
    dados["texto_html"] = texto_html_da_extracao(
        dados.get("texto_extraido"), dados.get("formatacao")
    )
    return success_response(dados)


@router.get("/extracoes/{extracao_id}/pdf")
async def baixar_extracao_pdf(
    extracao_id: str,
    auth=Depends(get_current_user_org),
    matriculas_client=Depends(get_matriculas_client),
):
    """ABNT-formatted PDF of the transcript — 'Baixar PDF' on the Matrículas
    page (contract §4). Route ordering: `{extracao_id}` matches exactly one
    path segment (Starlette), so this two-segment suffix can never be
    shadowed by, or shadow, the bare `GET /extracoes/{extracao_id}` above.

    🔴 LGPD (migration 111): the SAME `text_view` log `obter_extracao`
    writes — this route exposes the identical CPF-bearing text, as a PDF
    instead of JSON.
    """
    user, token, org_id = _auth_parts(auth)
    db = get_user_client(token)

    result = (
        db.table(TABLE)
        .select("nome_arquivo, status, texto_extraido, formatacao")
        .eq("id", extracao_id)
        .maybe_single()
        .execute()
    )
    if not result or not result.data:
        raise HTTPException(status_code=404, detail="Extração não encontrada")
    row = result.data
    texto = row.get("texto_extraido")
    if row.get("status") != "concluida" or not texto:
        raise HTTPException(
            status_code=409, detail="Transcrição ainda não concluída"
        )

    estrutura_svc.log_leitura_texto(
        matriculas_client, UUID(org_id), extracao_id, getattr(user, "id", None)
    )

    nome_arquivo = row.get("nome_arquivo") or "matricula.pdf"
    try:
        pdf_bytes = renderizar_extracao_pdf(nome_arquivo, texto, row.get("formatacao"))
    except UnsupportedGlyphError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    filename = f"{Path(nome_arquivo).stem}_transcricao.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@router.delete("/extracoes/{extracao_id}")
async def excluir_extracao(
    extracao_id: str,
    auth=Depends(get_current_user_org),
    matriculas_client=Depends(get_matriculas_client),
):
    """Delete an extraction — 409 while a contract or an imóvel quotes it."""
    _user, token, org_id = _auth_parts(auth)
    estrutura_svc.garantir_removivel(matriculas_client, UUID(org_id), extracao_id)

    db = get_user_client(token)
    delete_or_404(db, TABLE, ("id", extracao_id), message="Extração não encontrada")

    return ok_response("Extração excluída com sucesso")


@router.post("/extracoes/{extracao_id}/retranscrever")
async def retranscrever_extracao(
    extracao_id: str,
    background_tasks: BackgroundTasks,
    auth=Depends(get_current_user_org),
    client=Depends(get_matriculas_client),
    background_db=Depends(get_background_client),
    storage=Depends(get_storage_backend),
    transcriber_factory: TranscriberFactory = Depends(get_transcriber_factory),
):
    """Re-run transcription of a concluded extraction from its RETAINED
    source (migration 135) — linked or standalone. SUPERSEDES: a new row is
    created and the caller's history keeps the old one, marked
    `substituida_por`. 409 (via `estrutura_svc.criar_retranscricao`) when the
    extraction is not concluded, was already superseded, or kept no source
    to re-run from (a pre-135 row — it still needs a fresh upload).
    """
    user, _token, org_id = _auth_parts(auth)
    _exigir_credenciais(org_id)

    nova = estrutura_svc.criar_retranscricao(
        client, UUID(org_id), extracao_id, usuario_id=getattr(user, "id", None)
    )
    storage_path = nova.pop("storage_path")
    background_tasks.add_task(
        _run_extraction_de_documento,
        nova["id"], storage_path, org_id, background_db, storage, transcriber_factory,
    )
    return success_response(nova)


@router.get("/extracoes/{extracao_id}/arquivo-original")
async def arquivo_original_route(
    extracao_id: str,
    auth=Depends(get_current_user_org),
    matriculas_client=Depends(get_matriculas_client),
    storage=Depends(get_storage_backend),
):
    """A short-TTL signed URL for the SOURCE PDF this extraction was
    transcribed from — so 'Visualizar' can show text next to source (the
    audit this whole slice exists for). 409 when nothing was retained (a
    pre-135 row — see `estrutura_svc.obter_url_arquivo_original`)."""
    user, _token, org_id = _auth_parts(auth)
    resultado = await estrutura_svc.obter_url_arquivo_original(
        matriculas_client,
        storage,
        UUID(org_id),
        extracao_id,
        usuario_id=getattr(user, "id", None),
    )
    return success_response(resultado)


# ─── the structured half (migration 109) ──────────────────────────────────


@router.get("/extracoes/{extracao_id}/atos")
async def listar_atos_route(
    extracao_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_matriculas_client),
):
    """The matrícula's acts, each with its literal text slice."""
    user, _token, org_id = _auth_parts(auth)
    return success_response(
        estrutura_svc.listar_atos(
            client, UUID(org_id), extracao_id, usuario_id=getattr(user, "id", None)
        )
    )


@router.get("/extracoes/{extracao_id}/fontes")
async def obter_fontes_route(
    extracao_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_matriculas_client),
):
    """Heuristic título/ônus suggestions + the imóvel's confirmed pointers."""
    _user, _token, org_id = _auth_parts(auth)
    return success_response(
        estrutura_svc.obter_fontes(client, UUID(org_id), extracao_id)
    )


@router.put("/extracoes/{extracao_id}/fontes")
async def definir_fontes_route(
    extracao_id: UUID,
    body: FontesMatriculaBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_matriculas_client),
):
    """Record the operator's título aquisitivo / ônus source acts."""
    user, _token, org_id = _auth_parts(auth)
    # `model_fields_set`: `null` is a real value (clear the pointer), so
    # absence is the only thing that can mean "leave alone".
    valores = {k: getattr(body, k) for k in body.model_fields_set}
    return success_response(
        estrutura_svc.definir_fontes(
            client,
            UUID(org_id),
            extracao_id,
            valores=valores,
            usuario_id=getattr(user, "id", None),
        )
    )


@router.get("/contratos/{contrato_id}/atos")
async def obter_selecao_route(
    contrato_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_matriculas_client),
):
    """The acts a contract quotes, as literal slices, in contract order."""
    user, _token, org_id = _auth_parts(auth)
    return success_response(
        estrutura_svc.obter_selecao(
            client, UUID(org_id), contrato_id, usuario_id=getattr(user, "id", None)
        )
    )


@router.put("/contratos/{contrato_id}/atos")
async def definir_selecao_route(
    contrato_id: UUID,
    body: SelecaoAtosBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_matriculas_client),
):
    """Replace the acts a contract quotes."""
    user, _token, org_id = _auth_parts(auth)
    return success_response(
        estrutura_svc.definir_selecao(
            client,
            UUID(org_id),
            contrato_id,
            extracao_id=body.extracao_id,
            ato_ids=body.ato_ids,
            usuario_id=getattr(user, "id", None),
            permutas=[p.model_dump() for p in body.permutas],
        )
    )


# ─── act details · título · ônus creditor · previous owners (115) ─────────


_CODIGO = PathParam(..., min_length=1, max_length=64)


@router.put("/atos/{ato_id}/detalhes")
async def confirmar_detalhes_route(
    ato_id: UUID,
    body: DetalhesAtoBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_matriculas_client),
):
    """Confirm an act's details, editing any subset. Absent keys keep the
    suggestion; `null` clears. The request IS the confirmation."""
    user, _token, org_id = _auth_parts(auth)
    return success_response(
        titulo_svc.confirmar_detalhes_ato(
            client,
            UUID(org_id),
            ato_id,
            valores=body.model_dump(include=body.model_fields_set),
            usuario_id=getattr(user, "id", None),
        )
    )


# ─── party qualification (137) ─────────────────────────────────────────────


@router.put("/qualificacoes/{qualificacao_id}/confirmar")
async def confirmar_qualificacao_route(
    qualificacao_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_matriculas_client),
    notification_service=Depends(get_notification_service),
):
    """Confirm a matrícula party's qualification. Applies every field it
    carries onto the matched cliente, when `vinculo_status == 'vinculado'`.
    A field that disagrees with an existing value opens an admin conflict
    (migration 138) and is announced via `notification_service` instead of
    being applied."""
    user, _token, org_id = _auth_parts(auth)
    return success_response(
        await qualificacao_svc.confirmar(
            client,
            UUID(org_id),
            qualificacao_id,
            usuario_id=getattr(user, "id", None),
            notification_service=notification_service,
        )
    )


@router.put("/qualificacoes/{qualificacao_id}/descartar")
async def descartar_qualificacao_route(
    qualificacao_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_matriculas_client),
):
    """Turn down a matrícula party's qualification. The reading is kept."""
    user, _token, org_id = _auth_parts(auth)
    return success_response(
        qualificacao_svc.descartar(
            client, UUID(org_id), qualificacao_id, usuario_id=getattr(user, "id", None)
        )
    )


@router.get("/imoveis/{codigo}/titulo-aquisitivo")
async def obter_titulo_route(
    codigo: str = _CODIGO,
    auth=Depends(get_current_user_org),
    client=Depends(get_matriculas_client),
):
    """Suggested título aquisitivo phrase + the confirmed wording."""
    user, _token, org_id = _auth_parts(auth)
    return success_response(
        titulo_svc.obter_titulo(client, UUID(org_id), codigo, usuario_id=getattr(user, "id", None))
    )


@router.put("/imoveis/{codigo}/titulo-aquisitivo")
async def confirmar_titulo_route(
    body: TituloAquisitivoTextoBody,
    codigo: str = _CODIGO,
    auth=Depends(get_current_user_org),
    client=Depends(get_matriculas_client),
):
    """Confirm the título aquisitivo wording (`texto: null` clears it)."""
    user, _token, org_id = _auth_parts(auth)
    return success_response(
        titulo_svc.confirmar_titulo(
            client, UUID(org_id), codigo, texto=body.texto, usuario_id=getattr(user, "id", None)
        )
    )


@router.get("/imoveis/{codigo}/endereco-registro")
async def obter_endereco_registro_route(
    codigo: str = _CODIGO,
    auth=Depends(get_current_user_org),
    client=Depends(get_matriculas_client),
):
    """The operator's confirmed short address (migration 139) — never a
    recomputed suggestion."""
    _user, _token, org_id = _auth_parts(auth)
    return success_response(titulo_svc.obter_endereco_registro(client, UUID(org_id), codigo))


@router.put("/imoveis/{codigo}/endereco-registro")
async def confirmar_endereco_registro_route(
    body: EnderecoRegistroBody,
    codigo: str = _CODIGO,
    auth=Depends(get_current_user_org),
    client=Depends(get_matriculas_client),
):
    """Confirm the short address the posse clauses print (`texto: null`
    clears it)."""
    user, _token, org_id = _auth_parts(auth)
    return success_response(
        titulo_svc.confirmar_endereco_registro(
            client, UUID(org_id), codigo, texto=body.texto, usuario_id=getattr(user, "id", None)
        )
    )


@router.get("/imoveis/{codigo}/onus-credor")
async def obter_onus_credor_route(
    codigo: str = _CODIGO,
    auth=Depends(get_current_user_org),
    client=Depends(get_matriculas_client),
):
    """Creditor(s) read from the confirmed ônus acts + the confirmed value."""
    user, _token, org_id = _auth_parts(auth)
    return success_response(
        titulo_svc.obter_onus_credor(
            client, UUID(org_id), codigo, usuario_id=getattr(user, "id", None)
        )
    )


@router.put("/imoveis/{codigo}/onus-credor")
async def confirmar_onus_credor_route(
    body: OnusCredorBody,
    codigo: str = _CODIGO,
    auth=Depends(get_current_user_org),
    client=Depends(get_matriculas_client),
):
    """Confirm the ônus creditor (`credor: null` clears it)."""
    user, _token, org_id = _auth_parts(auth)
    return success_response(
        titulo_svc.confirmar_onus_credor(
            client, UUID(org_id), codigo, credor=body.credor, usuario_id=getattr(user, "id", None)
        )
    )


@router.get("/imoveis/{codigo}/antigos-proprietarios")
async def antigos_proprietarios_route(
    codigo: str = _CODIGO,
    auth=Depends(get_current_user_org),
    client=Depends(get_matriculas_client),
):
    """The last registered compra e venda's sellers, its date, and whether
    their certidões are required (sale less than 5 years old)."""
    user, _token, org_id = _auth_parts(auth)
    return success_response(
        titulo_svc.antigos_proprietarios(
            client, UUID(org_id), codigo, usuario_id=getattr(user, "id", None)
        )
    )


# ─── background bridges ───────────────────────────────────────────────────


def _run_extraction(
    extracao_id: str,
    pdf_bytes: bytes,
    org_id: str,
    db,
    transcriber_factory: TranscriberFactory,
) -> None:
    """Bridge the async pipeline into FastAPI's sync background-task slot.

    A sync task runs in the threadpool, so `asyncio.run` here spins its own
    loop without touching the request loop. `processar_extracao` never
    raises, so this cannot leave a thread dying silently.
    """
    asyncio.run(
        processar_extracao(
            extracao_id,
            pdf_bytes,
            org_id,
            db,
            transcriber_factory=transcriber_factory,
        )
    )


def _run_extraction_de_documento(
    extracao_id: str,
    storage_path: str,
    org_id: str,
    db,
    storage,
    transcriber_factory: TranscriberFactory,
) -> None:
    """Same bridge, reading the kept PDF back out of storage first."""
    asyncio.run(
        processar_extracao_de_documento(
            extracao_id,
            storage_path,
            org_id,
            db,
            storage,
            transcriber_factory=transcriber_factory,
        )
    )


__all__ = ["MAX_BODY_PATH_OVERRIDES", "MAX_FILE_SIZE", "router"]
