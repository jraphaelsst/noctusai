"""Certidões Negativas — HTTP surface.

    GET    /api/certidoes/tipos                          the catalogue
    GET    /api/certidoes/consultas                      list + per-consulta counts
    POST   /api/certidoes/consultas                      create + fan out + process
    POST   /api/certidoes/consultas/manual                create + fan out, no InfoSimples
    GET    /api/certidoes/consultas/{id}                 detail + resultados
    POST   /api/certidoes/consultas/{id}/reprocessar     retry the failed ones
    POST   /api/certidoes/consultas/{id}/cancelar        stop what is in flight
    DELETE /api/certidoes/consultas/{id}                 soft-delete (migration 161)
    POST   /api/certidoes/consultas/{id}/restaurar        undo a soft-delete
    GET    /api/certidoes/download                       one file, proxied
    GET    /api/certidoes/consultas/{id}/download-zip    all of them, zipped
    POST   /api/certidoes/resultados/{id}/upload         manual PDF, same pipeline (async extraction)
    GET    /api/certidoes/fila-tjsp                      queue + live cooldown
    POST   /api/certidoes/consultas/{id}/vincular-parte  attach to an atendimento_parte
    GET    /api/certidoes/partes/{id}/resultados          every certidão for one parte
    PATCH  /api/certidoes/resultados/{id}                 confirm/correct structured fields
    GET    /api/certidoes/resultados/{id}/url             LGPD-logged signed URL
    POST   /api/certidoes/consultas/{id}/vincular-cliente attach to a card's titular
    GET    /api/certidoes/clientes/{id}/resultados         every certidão for one cliente
    PATCH  /api/certidoes/consultas/{id}/situacao-cadastral  manual registration-status entry

Same paths as the ERP router this is ported from, because a live user's
frontend calls them. The middle four are migration 107's contract-automation
slice; the last three are migration 116's — the titular's own certidões
(the card's `atendimento_parte_id`-less party) plus the manual entry point
for a CNPJ/CPF's registration status.

Auth: `Depends(get_current_user_org)` → `(user, token, org_id)`, per
`KB § PATTERNS/backend/backend.md § Auth — canonical pattern`. The org is the
access boundary: migration 091 scopes reads to `current_org_id()` and routes
writes through service-role, so **every** query below carries an explicit
`.eq("org_id", ...)`. A consulta belonging to another org is a 404, not a 403 —
its existence is not this caller's business.

🔴 THE `arquivo_url` CONTRACT — read this before building against it
--------------------------------------------------------------------
`resultados[].arquivo_url` is an OPAQUE HANDLE, not a fetchable URL. It holds
EITHER a key in this product's private document bucket (the normal case, when
we persisted the file) OR an `https://` URL at the source system (the fallback,
when we could not). It diverges from the ERP, whose column held a permanent
PUBLIC url — this product's bucket is private with short-TTL signed URLs, so a
stored URL would be a dead link minutes after issuance (`service._persist_pdf`
has the full reasoning).

For a frontend that means:

- **Never `fetch()` / `<a href>` / `<img src>` an `arquivo_url` directly.** A
  bucket key is not a URL and will not resolve.
- **Treat it as truthy-or-not**: non-null ⇒ a file exists for this resultado
  ⇒ show the download control. That check is unchanged from the ERP.
- **Download through `GET /api/certidoes/download?url=<arquivo_url>`**, which
  resolves either kind server-side and streams the PDF back. It also
  authorizes the handle against the caller's org, so passing anything this API
  did not hand you is a 404 by design.
- The whole-consulta `GET /api/certidoes/consultas/{id}/download-zip` needs no
  handle at all.
"""
from __future__ import annotations

import asyncio
import io
import logging
import time
import unicodedata
import zipfile
from typing import Optional
from urllib.parse import quote
from uuid import UUID

import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import Response, StreamingResponse
from noctusai_lib.integrations.documents.abnt import UnsupportedGlyphError
from noctusai_lib.integrations.storage import StorageBackend

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.modules.certidoes import service
from app.modules.certidoes.deps import (
    CertidoesService,
    get_certidoes_client,
    get_certidoes_service,
    get_storage_backend,
)
from app.modules.certidoes.registry import (
    CERTIDOES_CONFIG,
    TJSP_TIPO,
    aplicavel_a_tipo_documento,
    get_certidoes_tipos,
    get_manual_tipos,
)
from app.modules.certidoes.schemas import (
    ConsultaCreate,
    ConsultaManualCreate,
    ResultadoPatch,
    SituacaoCadastralPatch,
    VincularClienteRequest,
    VincularEmpresaRequest,
    VincularParteRequest,
)
from app.responses import (
    calculate_pagination,
    ok_response,
    paginated_response,
    success_response,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/certidoes", tags=["Certidões"])

CONSULTAS = service.CONSULTAS
RESULTADOS = service.RESULTADOS

#: PostgREST-safe ceiling for `page_size`. This product's settings carry no
#: `max_page_size`, so the bound is declared here rather than borrowed from a
#: field that does not exist.
MAX_PAGE_SIZE = 200

# Throttle the stranded-work recovery — at most once per 60 seconds, so the
# frontend's 3-second poll does not add a DB round-trip per tick.
_last_stale_check: float = 0.0
_STALE_CHECK_INTERVAL = 60.0


def _maybe_recover(
    db, storage: StorageBackend, org_id: UUID, svc: "CertidoesService"
) -> None:
    """Throttled recovery of work stranded by a dead process.

    Two legs, both on the same throttle:

    - `recover_stale_processando` — the ERP behaviour: a resultado stuck in
      `processando` for over 15 minutes goes to `erro` so the spinner stops and
      the user gets a reprocess button instead of an infinite wait. `storage`
      is what lets it tell a stalled MANUAL upload apart from that (D3): one
      whose file already made it to the bucket gets its AI/vision extraction
      retried instead, bounded by `service.MAX_ESTRUTURA_TENTATIVAS`.
    - `schedule_tjsp_for_org` — NOT in the ERP, which resumed the TJSP queue
      only from its lifespan hook. `app/lifespan.py` is not this slice's to
      edit, and the seed scheduler refuses to run at all without
      `NOCTUS_SCHEDULERS_ENABLED` (deployed containers only). Re-arming here
      means the queue resumes the moment a human opens the page — which is both
      the environment-independent path and the moment it matters. Idempotent:
      it returns immediately when a task is already in flight for this org.
    """
    global _last_stale_check
    now = time.monotonic()
    if now - _last_stale_check < _STALE_CHECK_INTERVAL:
        return
    _last_stale_check = now
    svc.recover_stale_processando(db, storage)
    svc.schedule_tjsp_for_org(str(org_id), db, storage)


def _content_disposition(filename: str) -> str:
    """An attachment header that survives an accented filename.

    🔴 NOT COSMETIC, AND NOT HYPOTHETICAL. HTTP header values are latin-1 on
    the wire, so returning `filename="certidoes_João_da_Silva_...zip"` raises
    inside Starlette and the whole response 500s. The download therefore failed
    for anyone whose name carries an accent — which in a Brazilian real-estate
    product is most people. The ERP original built the header the same way and
    had the same latent defect; it is fixed here rather than ported.

    RFC 6266: an ASCII-folded `filename=` that any client understands, PLUS a
    percent-encoded UTF-8 `filename*=` that every current browser prefers — so
    the accented name is what the user actually sees, and nothing breaks if it
    is not understood.
    """
    folded = (
        unicodedata.normalize("NFKD", filename)
        .encode("ascii", "ignore")
        .decode("ascii")
        .replace('"', "")
        .strip()
    )
    # An all-non-ASCII name folds to "" — a header with an empty filename is
    # worse than a generic one, because some clients save it as the URL path.
    ascii_name = folded or "download"
    return (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )


def _get_consulta_or_404(db, consulta_id: str, org_id: UUID, select: str = "*") -> dict:
    """One consulta belonging to this org, or a 404.

    `.execute()` on a filtered select rather than `.single()`: `single()` raises
    on zero rows, and the raised shape differs across supabase-py versions —
    this returns the honest 404 the same way regardless.

    `.is_("excluida_em", "null")`: a soft-deleted consulta (migration 161) is
    a 404 here — the same shape a hard-deleted one always was. Every route
    that resolves a consulta through this helper (detail, reprocess, cancel,
    download-zip, upload, vincular-parte/cliente, situação cadastral) is
    therefore excluded-aware for free. `POST .../restaurar` is the one
    caller that deliberately does NOT go through this helper, because
    finding an excluded consulta is its entire job.
    """
    rows = (
        db.table(CONSULTAS)
        .select(select)
        .eq("id", consulta_id)
        .eq("org_id", str(org_id))
        .is_("excluida_em", "null")
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Consulta não encontrada")
    return rows[0]


def _fan_out_tipos_manuais(
    db, consulta_id: str, org_id, *, tipo_documento: Optional[str] = None
) -> None:
    """Idempotently add a `pendente` placeholder resultado for each
    manual-only type (Serasa, TJSP e-SAJ, TJSP e-PROC —
    `registry.get_manual_tipos`) this consulta does not already carry.

    Shared by `vincular_parte`, `vincular_cliente` and `vincular_empresa`
    (migration 116/167): each attaches a consulta to a person/empresa and
    each needs the same manual-upload targets to exist afterwards — the ten
    automated types get theirs from `criar_consulta`'s own fan-out; these
    three have no API call to make one from, so the upload endpoint always
    needs a resultado_id to target before a human can use it.

    🔴 EACH MANUAL TYPE IS SKIPPED WHEN INAPPLICABLE TO `tipo_documento`
    (P0c contract §E5/§H14's `serasa`-vs-cnpj fix, generalized by the
    Certidões matriz tab: `serasa` is a PF credit report, `fgts_
    regularidade` is a company-only obligation — see `registry.
    aplicavel_a_tipo_documento`). `tipo_documento=None` (an existing caller
    that has not been updated) keeps the old behaviour — always fan out
    every manual type — so this stays additive.
    """
    manuais = get_manual_tipos()
    if tipo_documento is not None:
        manuais = [
            tipo for tipo in manuais
            if aplicavel_a_tipo_documento(tipo["tipo"], tipo_documento)
        ]
    # postgrest-unbounded-ok: at most ~13 resultados per consulta (10
    # automated + 3 manual), the same bound every other resultados read in
    # this router relies on.
    existentes = (
        db.table(RESULTADOS)
        .select("tipo")
        .eq("consulta_id", consulta_id)
        .eq("org_id", str(org_id))
        .execute()
    ).data or []
    tipos_existentes = {r["tipo"] for r in existentes}
    novos = [
        {
            "consulta_id": consulta_id,
            "org_id": str(org_id),
            "tipo": tipo["tipo"],
            "nome_display": tipo["nome"],
            "ordem": tipo["ordem"],
            "status": "pendente",
        }
        for tipo in manuais
        if tipo["tipo"] not in tipos_existentes
    ]
    if novos:
        db.table(RESULTADOS).insert(novos).execute()


def _resolve_parte_cliente_id(db, org_id, atendimento_parte_id: str) -> Optional[str]:
    """The `cliente_id` behind one `atendimento_partes` row of THIS org, or a
    404 — never trust a caller-supplied `cliente_id` for a party, so a
    caller cannot link a consulta to a person who is not actually party to
    this atendimento. Shared by `vincular_parte` and `criar_consulta_manual`.
    """
    parte_rows = (
        db.table("atendimento_partes")
        .select("id, cliente_id")
        .eq("id", atendimento_parte_id)
        .eq("org_id", str(org_id))
        .execute()
    ).data or []
    if not parte_rows:
        raise HTTPException(status_code=404, detail="Parte não encontrada")
    return parte_rows[0]["cliente_id"]


def _validar_cliente_id(db, org_id, cliente_id: str) -> None:
    """404 unless `cliente_id` names a `clientes` row of THIS org. Shared by
    `vincular_cliente` and `criar_consulta_manual`."""
    cliente_rows = (
        db.table("clientes")
        .select("id")
        .eq("id", cliente_id)
        .eq("org_id", str(org_id))
        .execute()
    ).data or []
    if not cliente_rows:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")


# --------------- Endpoints ---------------


@router.get("/tipos")
async def listar_tipos_certidoes(_auth=Depends(get_current_user_org)):
    """List available certificate types."""
    return success_response(get_certidoes_tipos())


@router.get("/consultas")
async def listar_consultas(
    busca: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    storage: StorageBackend = Depends(get_storage_backend),
    svc: CertidoesService = Depends(get_certidoes_service),
):
    """List certificate consultation requests, newest first."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    _maybe_recover(db, storage, org_id, svc)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, MAX_PAGE_SIZE
    )

    def _scoped(query):
        # Migration 161: a soft-deleted consulta never appears in the list.
        query = query.eq("org_id", str(org_id)).is_("excluida_em", "null")
        if status:
            query = query.eq("status", status)
        if busca:
            query = query.or_(f"nome.ilike.%{busca}%,documento.ilike.%{busca}%")
        return query

    count_result = _scoped(
        db.table(CONSULTAS).select("id", count="exact")
    ).execute()
    total = count_result.count if count_result.count is not None else 0

    result = (
        _scoped(db.table(CONSULTAS).select("*"))
        .order("created_at", desc=True)
        .range(offset, offset + validated_page_size - 1)
        .execute()
    )
    consultas = result.data or []

    # Success/error counts per consulta. Both the URL-length and the row-cap
    # hazards live on this read — see `service.status_counts_por_consulta`,
    # which owns both.
    if consultas:
        success_counts, erro_counts = svc.status_counts_por_consulta(
            [c["id"] for c in consultas], org_id, db
        )
        for c in consultas:
            c["concluidas"] = success_counts.get(c["id"], 0)
            c["erros"] = erro_counts.get(c["id"], 0)

    return paginated_response(consultas, total, validated_page, validated_page_size)


@router.post("/consultas")
async def criar_consulta(
    body: ConsultaCreate,
    background_tasks: BackgroundTasks,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    storage: StorageBackend = Depends(get_storage_backend),
    svc: CertidoesService = Depends(get_certidoes_service),
):
    """Create a consultation, fan out one resultado per type, start processing."""
    user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    # Pre-flight the credentials BEFORE writing anything. Without this the
    # consulta is created, ten resultados fan out, and every one of them fails
    # a minute later with the same message — a row the user now has to delete
    # to learn something we knew before we started.
    missing = svc.check_required_credentials(str(org_id))
    if missing:
        # Wording is VERBATIM the sentence `matriculas/router.py` and
        # `settings_router.py` already use — the Settings page it names is one
        # page, so three workflows telling the operator to visit it in three
        # different phrasings reads as three different places.
        raise HTTPException(
            status_code=422,
            detail=" ".join(missing)
            + " Configure em Configurações → Chaves de API.",
        )

    # `incluir_tjsp` is a request switch, not a consulta column.
    configs = [
        config
        for config in CERTIDOES_CONFIG
        if body.incluir_tjsp or config["tipo"] != TJSP_TIPO
    ]

    consulta_data = {
        **body.model_dump(exclude_none=True, exclude={"incluir_tjsp"}),
        "org_id": str(org_id),
        "created_by": str(user.id),
        "status": "pendente",
        "total_certidoes": len(configs),
        "concluidas": 0,
    }

    consulta_result = db.table(CONSULTAS).insert(consulta_data).execute()
    if not consulta_result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar consulta")
    consulta = consulta_result.data[0]

    resultados_data = [
        {
            "consulta_id": consulta["id"],
            "org_id": str(org_id),
            "tipo": config["tipo"],
            "nome_display": config["nome"],
            "ordem": config["ordem"],
            "status": "pendente",
        }
        for config in configs
    ]
    db.table(RESULTADOS).insert(resultados_data).execute()

    # Background processing. Passed as an async coroutine function so it runs
    # in the MAIN event loop — required for the TJSP on-demand scheduling,
    # which needs a running loop to create its task on.
    background_tasks.add_task(svc.processar_consulta, consulta["id"], db, storage)

    # One resultado per registry type per consulta: the fan-out in
    # `criar_consulta` inserts exactly `len(CERTIDOES_CONFIG)` of them and the
    # FK cascades with the consulta.
    # postgrest-unbounded-ok: bounded at 10 rows by that fan-out, not 1 000.
    resultados = (
        db.table(RESULTADOS)
        .select(service.RESULTADO_COLUNAS_SEM_TEXTO)
        .eq("consulta_id", consulta["id"])
        .eq("org_id", str(org_id))
        .order("ordem")
        .execute()
    )
    consulta["resultados"] = resultados.data or []
    return success_response(consulta)


@router.post("/consultas/manual")
async def criar_consulta_manual(
    body: ConsultaManualCreate,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
):
    """Create a consultation the SAME shape `criar_consulta` produces — one
    `pendente` placeholder resultado per type the office checklist names,
    thirteen total for a CPF (`CERTIDOES_CONFIG`'s ten PLUS `get_manual_
    tipos()`'s three) — but NEVER calls InfoSimples and never requires its
    token. A CNPJ consulta gets twelve: Serasa is a PF credit report and is
    never fanned out for one (P0c contract §E5/§H14).

    🔴 CARD-ONLY, BY OWNER DECISION. This is reached from a party's/titular's
    own certidões panel on the card (`CertidoesPartePanel`'s "Registrar
    certidões manualmente"), for certidões the office already holds on paper
    — old processes, cards that will never go through InfoSimples. It is
    deliberately NOT offered as a chooser next to `criar_consulta` in the
    Nova Consulta modal: `ConsultaManualCreate`'s own docstring records why.

    Every resultado this creates is filled by hand through the EXISTING
    `PATCH /resultados/{id}` confirm/correct flow — nothing new there.

    🔴 NO `background_tasks.add_task(svc.processar_consulta, ...)` — the one
    line that fires InfoSimples calls and lands a `cost_ledger` row (via
    `_process_single_certidao` → `cost_ledger.book_infosimples_cost`) is
    simply never reached, by construction, not by a runtime flag a bug could
    flip. Also no `svc.check_required_credentials` pre-flight: this path has
    no credential to be missing.

    Optionally links the new consulta to a party or a card's titular in the
    SAME request — `atendimento_parte_id` resolved via `_resolve_parte_
    cliente_id` (never a caller-supplied `cliente_id` for a party, exactly
    like `vincular_parte`), `cliente_id` validated via `_validar_cliente_id`
    (exactly like `vincular_cliente`). Sending both is refused: an ambiguous
    link the caller could not have meant is worse than picking one silently.
    """
    user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    if body.atendimento_parte_id and body.cliente_id:
        raise HTTPException(
            status_code=422,
            detail="Envie apenas um vínculo: atendimento_parte_id OU cliente_id, não os dois.",
        )

    resolved_cliente_id: Optional[str] = None
    if body.atendimento_parte_id:
        resolved_cliente_id = _resolve_parte_cliente_id(
            db, org_id, str(body.atendimento_parte_id)
        )
    elif body.cliente_id:
        _validar_cliente_id(db, org_id, str(body.cliente_id))
        resolved_cliente_id = str(body.cliente_id)

    # P0c contract §E5/§H14 (generalized by the Certidões matriz tab): each
    # manual type only fans out onto a `tipo_documento` it applies to
    # (`serasa` is CPF-only, `fgts_regularidade` is CNPJ-only) — the SAME
    # `registry.aplicavel_a_tipo_documento` predicate `_fan_out_tipos_
    # manuais` uses, kept in sync rather than restated inline (this route
    # builds its own fan-out up front instead of calling that helper).
    manuais = [
        tipo for tipo in get_manual_tipos()
        if aplicavel_a_tipo_documento(tipo["tipo"], body.tipo_documento)
    ]

    consulta_data = {
        **body.model_dump(
            exclude_none=True,
            exclude={"atendimento_parte_id", "cliente_id", "incluir_tjsp"},
        ),
        "org_id": str(org_id),
        "created_by": str(user.id),
        "status": "pendente",
        "origem": "manual",
        "total_certidoes": len(CERTIDOES_CONFIG) + len(manuais),
        "concluidas": 0,
    }
    if body.atendimento_parte_id:
        consulta_data["atendimento_parte_id"] = str(body.atendimento_parte_id)
    if resolved_cliente_id:
        consulta_data["cliente_id"] = resolved_cliente_id

    consulta_result = db.table(CONSULTAS).insert(consulta_data).execute()
    if not consulta_result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar consulta")
    consulta = consulta_result.data[0]

    # Same thirteen types `criar_consulta`'s ten plus a `vincular_parte`/
    # `vincular_cliente`-linked consulta's three end up carrying — see this
    # function's own docstring. Unlike `criar_consulta`, TJSP is always
    # included: there is no InfoSimples call to gate here either way.
    resultados_data = [
        {
            "consulta_id": consulta["id"],
            "org_id": str(org_id),
            "tipo": config["tipo"],
            "nome_display": config["nome"],
            "ordem": config["ordem"],
            "status": "pendente",
        }
        for config in CERTIDOES_CONFIG
    ] + [
        {
            "consulta_id": consulta["id"],
            "org_id": str(org_id),
            "tipo": tipo["tipo"],
            "nome_display": tipo["nome"],
            "ordem": tipo["ordem"],
            "status": "pendente",
        }
        for tipo in manuais
    ]
    db.table(RESULTADOS).insert(resultados_data).execute()

    # postgrest-unbounded-ok: bounded at 13 rows by the fan-out above.
    resultados = (
        db.table(RESULTADOS)
        .select(service.RESULTADO_COLUNAS_SEM_TEXTO)
        .eq("consulta_id", consulta["id"])
        .eq("org_id", str(org_id))
        .order("ordem")
        .execute()
    )
    consulta["resultados"] = resultados.data or []
    return success_response(consulta)


@router.get("/consultas/{consulta_id}")
async def obter_consulta(
    consulta_id: str,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
):
    """Get a consultation with all its certificate results.

    THE endpoint the certidão detail screen polls. Each `resultados[]` entry's
    `arquivo_url` is an opaque handle to be round-tripped through
    `GET /api/certidoes/download`, never fetched directly — see this module's
    docstring for the contract.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    data = _get_consulta_or_404(db, consulta_id, org_id)

    # One resultado per registry type per consulta: the fan-out in
    # `criar_consulta` inserts exactly `len(CERTIDOES_CONFIG)` of them and the
    # FK cascades with the consulta.
    # postgrest-unbounded-ok: bounded at 10 rows by that fan-out, not 1 000.
    # Migration 113: THIS is the endpoint the certidão detail screen polls —
    # never select("*") here, or the certidão text rides along on every poll.
    resultados = (
        db.table(RESULTADOS)
        .select(service.RESULTADO_COLUNAS_SEM_TEXTO)
        .eq("consulta_id", consulta_id)
        .eq("org_id", str(org_id))
        .order("ordem")
        .execute()
    )
    res_list = resultados.data or []
    data["resultados"] = res_list
    data["concluidas"] = sum(1 for r in res_list if r.get("status") == "sucesso")
    data["erros"] = sum(1 for r in res_list if r.get("status") == "erro")
    return success_response(data)


@router.post("/consultas/{consulta_id}/reprocessar")
async def reprocessar_consulta(
    consulta_id: str,
    background_tasks: BackgroundTasks,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    storage: StorageBackend = Depends(get_storage_backend),
    svc: CertidoesService = Depends(get_certidoes_service),
):
    """Retry the failed certificates in a consultation."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    _get_consulta_or_404(db, consulta_id, org_id, select="id")

    # Failed non-TJSP resultados → pendente (they run in parallel immediately).
    db.table(RESULTADOS).update({
        "status": "pendente",
        "erro_mensagem": None,
    }).eq("consulta_id", consulta_id).eq("org_id", str(org_id)).eq(
        "status", "erro"
    ).neq("tipo", TJSP_TIPO).execute()

    # Failed TJSP resultados → na_fila directly, NOT pendente. `pendente` would
    # make `processar_consulta` fire the request now, and a premature TJSP call
    # RESETS their 30-minute counter — the retry would push the real attempt
    # further away rather than closer.
    db.table(RESULTADOS).update({
        "status": "na_fila",
        "erro_mensagem": None,
    }).eq("consulta_id", consulta_id).eq("org_id", str(org_id)).eq(
        "status", "erro"
    ).eq("tipo", TJSP_TIPO).execute()

    db.table(CONSULTAS).update({
        "status": "processando",
    }).eq("id", consulta_id).eq("org_id", str(org_id)).execute()

    background_tasks.add_task(svc.processar_consulta, consulta_id, db, storage)

    # `processar_consulta` only picks up "pendente" rows, so the TJSP items we
    # just moved to "na_fila" need their own scheduling pass.
    svc.schedule_tjsp_for_org(str(org_id), db, storage)

    return ok_response("Reprocessamento iniciado")


@router.post("/consultas/{consulta_id}/cancelar")
async def cancelar_consulta_processamento(
    consulta_id: str,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    svc: CertidoesService = Depends(get_certidoes_service),
):
    """Cancel in-progress certificate processing for one consulta."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    _get_consulta_or_404(db, consulta_id, org_id, select="id")

    result = svc.cancelar_processamento(consulta_id, str(org_id), db)
    return success_response(result)


@router.delete("/consultas/{consulta_id}")
async def excluir_consulta(
    consulta_id: str,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    svc: CertidoesService = Depends(get_certidoes_service),
):
    """Soft-delete a consultation and its results (migration 161).

    🔴 THIS USED TO HARD-DELETE. A prod consulta of 12 results + blobs was
    removed this way and nobody could tell WHO did it — the row that would
    have named the actor was the row that got deleted. Blobs are now KEPT
    (a soft-delete never touches storage): `excluida_em`/`excluida_por` are
    stamped on the consulta AND every one of its resultados instead, every
    reader filters `excluida_em is null` (see migration 161's header for the
    full grep), `POST .../restaurar` reverses it, and `certidoes.scheduler`'s
    purge job hard-deletes blobs + rows only after 30 days.

    The structured INFO line below is a BRIDGE, not the audit trail itself:
    a parallel slice is landing the seed audit middleware that will persist
    every action (not only deletes); until it does, this is the only durable
    trace of who excluded what. No PII — org/user/consulta ids and a count.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    # Verify existence up front — a 404 must not stamp an audit line for an
    # action that never happened.
    _get_consulta_or_404(db, consulta_id, org_id, select="id")

    n_resultados = svc.soft_delete_consulta(db, org_id, consulta_id, _user.id)
    if n_resultados is None:
        # Excluded between the check above and here (a race) — same 404 the
        # existence check would have raised.
        raise HTTPException(status_code=404, detail="Consulta não encontrada")

    logger.info(
        "certidoes: consulta excluida (soft) user_id=%s org_id=%s "
        "consulta_id=%s n_resultados=%d",
        _user.id, org_id, consulta_id, n_resultados,
    )

    return ok_response("Consulta excluída com sucesso")


@router.post("/consultas/{consulta_id}/restaurar")
async def restaurar_consulta(
    consulta_id: str,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    svc: CertidoesService = Depends(get_certidoes_service),
):
    """Undo a soft-delete (migration 161): clears `excluida_em`/
    `excluida_por` on the consulta and every one of its resultados. Blobs
    were never touched by the delete, so nothing is re-fetched here.

    404 for a consulta absent from this org OR one that was never excluded
    — `svc.restaurar_consulta`'s own docstring has the reasoning for the
    second case. Same authz as every other route: `get_current_user_org`,
    org-scoped.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    restored = svc.restaurar_consulta(db, org_id, consulta_id)
    if restored is None:
        raise HTTPException(status_code=404, detail="Consulta não encontrada")

    logger.info(
        "certidoes: consulta restaurada user_id=%s org_id=%s consulta_id=%s",
        _user.id, org_id, consulta_id,
    )

    return success_response(restored)


@router.get("/download")
async def download_certidao(
    url: str = Query(..., description="URL ou chave do arquivo para download"),
    filename: str = Query("certidao.pdf", description="Nome do arquivo"),
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    storage: StorageBackend = Depends(get_storage_backend),
    svc: CertidoesService = Depends(get_certidoes_service),
):
    """Download one certificate — from our bucket, or proxied from the source.

    🔴 `url` IS AUTHORIZED BEFORE IT IS FETCHED. The ERP original fetched
    whatever it was handed, which is both an SSRF vector (the server will GET
    any host a caller names) and a cross-org read (any bucket key, any org).
    Requiring the value to actually appear as an `arquivo_url` on a resultado in
    THIS caller's org closes both with one indexed lookup, and costs a legitimate
    caller nothing — the frontend only ever passes back a value this API gave it.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    owned = (
        db.table(RESULTADOS)
        .select("id")
        .eq("org_id", str(org_id))
        .eq("arquivo_url", url)
        .is_("excluida_em", "null")
        .limit(1)
        .execute()
    ).data or []
    if not owned:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    async with httpx.AsyncClient() as client:
        content = await svc.read_certidao_bytes(url, storage, client)

    if content is None:
        raise HTTPException(
            status_code=502, detail="Não foi possível baixar o arquivo"
        )

    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@router.get("/consultas/{consulta_id}/download-zip")
async def download_consulta_zip(
    consulta_id: str,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    storage: StorageBackend = Depends(get_storage_backend),
    svc: CertidoesService = Depends(get_certidoes_service),
):
    """Download every successful certificate of a consultation as one ZIP."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    consulta = _get_consulta_or_404(
        db, consulta_id, org_id, select="id, nome, documento"
    )

    # One resultado per registry type per consulta: the fan-out in
    # `criar_consulta` inserts exactly `len(CERTIDOES_CONFIG)` of them and the
    # FK cascades with the consulta.
    # postgrest-unbounded-ok: bounded at 10 rows by that fan-out, not 1 000.
    resultados = (
        db.table(RESULTADOS)
        .select("arquivo_url, arquivo_nome, nome_display")
        .eq("consulta_id", consulta_id)
        .eq("org_id", str(org_id))
        .eq("status", "sucesso")
        .order("ordem")
        .execute()
    )
    items = [r for r in (resultados.data or []) if r.get("arquivo_url")]

    if not items:
        raise HTTPException(
            status_code=404,
            detail="Nenhuma certidão disponível para download",
        )

    async def _fetch(client: httpx.AsyncClient, item: dict) -> Optional[tuple]:
        content = await svc.read_certidao_bytes(
            item["arquivo_url"], storage, client
        )
        if content is None:
            # Named, not swallowed: one unreachable file must not sink the ZIP
            # of the nine that ARE there, but it does get a log line.
            logger.warning(
                "certidoes: %s unavailable for consulta %s; omitted from the ZIP",
                item.get("nome_display"), consulta_id,
            )
            return None
        filename = item.get("arquivo_nome") or f"{item['nome_display']}.pdf"
        return (filename, content)

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[_fetch(client, it) for it in items])

    files = [r for r in results if r is not None]
    if not files:
        raise HTTPException(
            status_code=502,
            detail="Não foi possível baixar os arquivos das certidões",
        )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        seen: dict[str, int] = {}
        for filename, content in files:
            # Deduplicate filenames — a zip with two identical entries opens to
            # one file in most extractors, silently losing the other.
            if filename in seen:
                seen[filename] += 1
                name, ext = (
                    filename.rsplit(".", 1) if "." in filename else (filename, "")
                )
                filename = (
                    f"{name} ({seen[filename]}).{ext}"
                    if ext
                    else f"{name} ({seen[filename]})"
                )
            else:
                seen[filename] = 0
            zf.writestr(filename, content)
    buf.seek(0)

    nome_safe = consulta["nome"].replace(" ", "_")[:50]
    doc = consulta["documento"]
    zip_filename = f"certidoes_{nome_safe}_{doc}.zip"

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition(zip_filename)},
    )


@router.post("/resultados/{resultado_id}/upload")
async def upload_certidao_manual(
    resultado_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    storage: StorageBackend = Depends(get_storage_backend),
    svc: CertidoesService = Depends(get_certidoes_service),
):
    """Upload a certificate PDF by hand for a resultado the automation failed.

    Storage happens here, synchronously — a single bucket `PUT`. The AI/vision
    read that follows (text extraction, analysis, structured-field
    determination — bounded vision, `service.CERTIDAO_MANUAL_MAX_VISION_
    PAGES`, for a scanned PDF) is scheduled as a `BackgroundTasks` job instead
    of awaited here, the same split `card_hub.router.upload_documento_route`
    already uses for identity documents: a vision call is a per-page network
    round trip, and this response would otherwise hang on it. The response
    below reflects the resultado as `processando`; the existing consulta-detail
    poll picks up `sucesso` once the background job finishes — same as the
    automated flow already works.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=422,
            detail="Apenas arquivos PDF são aceitos.",
        )

    resultado_rows = (
        db.table(RESULTADOS)
        .select(
            "id, consulta_id, tipo, nome_display, resultado_origem, confirmado_por"
        )
        .eq("id", resultado_id)
        .eq("org_id", str(org_id))
        .execute()
    ).data or []
    if not resultado_rows:
        raise HTTPException(status_code=404, detail="Resultado não encontrado")
    resultado = resultado_rows[0]

    consulta = _get_consulta_or_404(db, resultado["consulta_id"], org_id)

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=422, detail="Arquivo vazio.")

    update_data = await svc.process_manual_upload(
        pdf_bytes=pdf_bytes,
        resultado_id=resultado_id,
        consulta=consulta,
        tipo=resultado["tipo"],
        nome_display=resultado["nome_display"],
        org_id=str(org_id),
        db=db,
        storage=storage,
    )
    background_tasks.add_task(
        svc.process_manual_extraction,
        pdf_bytes=pdf_bytes,
        resultado_id=resultado_id,
        consulta_id=resultado["consulta_id"],
        nome_display=resultado["nome_display"],
        org_id=str(org_id),
        db=db,
        resultado_origem_atual=resultado.get("resultado_origem"),
        confirmado_por_atual=resultado.get("confirmado_por"),
    )

    return success_response({**resultado, **update_data})


@router.get("/fila-tjsp")
async def status_fila_tjsp(
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    svc: CertidoesService = Depends(get_certidoes_service),
):
    """The TJSP queue for this org — who is waiting, and for how much longer."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    queued_items = svc.queued_tjsp_for_org(org_id, db)

    # Enrich with consulta info in batched queries (URL-length safety on
    # `.in_()`), so the queue reads as names rather than as ids.
    items = []
    consulta_cache: dict = {}
    if queued_items:
        unique_cids = list({item["consulta_id"] for item in queued_items})
        for batch in service.in_batches(unique_cids):
            # `id` is the primary key, so this returns exactly one row per
            # id, and `in_batches` already caps a batch at 200 ids.
            # postgrest-unbounded-ok: at most 200 rows, well under the cap.
            consultas_result = (
                db.table(CONSULTAS)
                .select("id, nome, documento, tipo_documento")
                .eq("org_id", str(org_id))
                .in_("id", batch)
                .execute()
            )
            for c in (consultas_result.data or []):
                consulta_cache[c["id"]] = c

    for i, item in enumerate(queued_items):
        consulta_info = consulta_cache.get(item["consulta_id"], {})
        items.append({
            "id": item["id"],
            "consulta_id": item["consulta_id"],
            "posicao": i + 1,
            "nome": consulta_info.get("nome", ""),
            "documento": consulta_info.get("documento", ""),
            "tipo_documento": consulta_info.get("tipo_documento", ""),
            "created_at": item["created_at"],
        })

    return success_response({
        "items": items,
        "total_na_fila": len(items),
        "cooldown": svc.tjsp_cooldown_status(org_id, db),
    })


# ---------------------------------------------------------------------------
# Contract-automation slice (migration 107): per-parte linkage, structured
# fields, LGPD-logged URL.
# ---------------------------------------------------------------------------


@router.post("/consultas/{consulta_id}/vincular-parte")
async def vincular_parte(
    consulta_id: str,
    body: VincularParteRequest,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
):
    """Attach a consulta to one party (`atendimento_partes` row) of an
    atendimento — the contract-automation slice's entry point for "which
    certidões exist for THIS person on THIS deal".

    `cliente_id` is resolved off the `atendimento_partes` row rather than
    trusted from the request body, so a caller cannot link a consulta to a
    person who is not actually party to this atendimento.

    Also fans out a `pendente` placeholder resultado for each manual-only
    type (Serasa, TJSP e-SAJ, TJSP e-PROC — `registry.get_manual_tipos`) this
    consulta does not already carry, idempotently: the ten automated types
    get theirs from `criar_consulta`'s own fan-out; these three have no API
    call to make one from, so the upload endpoint always needs a resultado_id
    to target before a human can use it.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    resolved_cliente_id = _resolve_parte_cliente_id(
        db, org_id, str(body.atendimento_parte_id)
    )

    _get_consulta_or_404(db, consulta_id, org_id, select="id")

    updated = (
        db.table(CONSULTAS)
        .update({
            "atendimento_parte_id": str(body.atendimento_parte_id),
            "cliente_id": resolved_cliente_id,
        })
        .eq("id", consulta_id)
        .eq("org_id", str(org_id))
        .execute()
    ).data or []
    consulta = updated[0] if updated else _get_consulta_or_404(db, consulta_id, org_id)

    _fan_out_tipos_manuais(db, consulta_id, org_id, tipo_documento=consulta.get("tipo_documento"))

    return success_response(consulta)


@router.get("/partes/{atendimento_parte_id}/resultados")
async def listar_resultados_por_parte(
    atendimento_parte_id: str,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    svc: CertidoesService = Depends(get_certidoes_service),
):
    """Every certidão result across every consulta linked to one party —
    the contract-automation screen's per-parte certidões panel."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    return success_response(
        svc.certidoes_por_parte(db, org_id, atendimento_parte_id)
    )


@router.post("/consultas/{consulta_id}/vincular-cliente")
async def vincular_cliente(
    consulta_id: str,
    body: VincularClienteRequest,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
):
    """Attach a consulta to a card's TITULAR — `atendimentos.cliente_id` —
    `vincular_parte`'s sibling for the one party it cannot reach: the
    titular has no `atendimento_partes` row at all (migration 073's
    header), so there is no party to resolve a `cliente_id` off; the
    caller names it directly, and it is validated against THIS org's
    `clientes` before it is written.

    Also fans out the three manual-only placeholder types, exactly like
    `vincular_parte` — see `_fan_out_tipos_manuais`.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    _validar_cliente_id(db, org_id, str(body.cliente_id))

    _get_consulta_or_404(db, consulta_id, org_id, select="id")

    updated = (
        db.table(CONSULTAS)
        .update({"cliente_id": str(body.cliente_id)})
        .eq("id", consulta_id)
        .eq("org_id", str(org_id))
        .execute()
    ).data or []
    consulta = updated[0] if updated else _get_consulta_or_404(db, consulta_id, org_id)

    _fan_out_tipos_manuais(db, consulta_id, org_id, tipo_documento=consulta.get("tipo_documento"))

    return success_response(consulta)


def _validar_empresa_id(db, org_id, empresa_id: str) -> dict:
    """The `empresas` row this org owns, or a 404 — never trust a caller-
    supplied `empresa_id` for a link. Mirrors `_validar_cliente_id`."""
    rows = (
        db.table("empresas")
        .select("id, cnpj")
        .eq("id", empresa_id)
        .eq("org_id", str(org_id))
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return rows[0]


@router.post("/consultas/{consulta_id}/vincular-empresa")
async def vincular_empresa(
    consulta_id: str,
    body: VincularEmpresaRequest,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
):
    """Attach a `tipo_documento='cnpj'` consulta to an `empresas` row (P0c
    contract §D5) — `vincular_cliente`'s sibling for a company rather than a
    person. 404 when the empresa does not exist in this org; 422 unless the
    consulta is `tipo_documento='cnpj'` AND its normalized `documento`
    equals the empresa's `cnpj` — emission needs only the CNPJ + razão
    social, both of which already live on `empresas` (owner rule,
    2026-09-24); this route only records the link, never re-derives them.

    Also fans out the manual-only placeholder types (TJSP e-SAJ/e-PROC —
    NOT Serasa, a CNPJ consulta's fan-out never carries it — see
    `_fan_out_tipos_manuais`).
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    empresa = _validar_empresa_id(db, org_id, str(body.empresa_id))
    consulta = _get_consulta_or_404(db, consulta_id, org_id)
    if consulta.get("tipo_documento") != "cnpj":
        raise HTTPException(
            status_code=422,
            detail="Apenas consultas de CNPJ podem ser vinculadas a uma empresa.",
        )
    from noctusai_lib.integrations.documents.cnpj import normalize as _normalize_cnpj

    if _normalize_cnpj(consulta.get("documento")) != empresa["cnpj"]:
        raise HTTPException(
            status_code=422,
            detail="O CNPJ da consulta não corresponde ao CNPJ da empresa.",
        )

    updated = (
        db.table(CONSULTAS)
        .update({"empresa_id": str(body.empresa_id)})
        .eq("id", consulta_id)
        .eq("org_id", str(org_id))
        .execute()
    ).data or []
    consulta = updated[0] if updated else _get_consulta_or_404(db, consulta_id, org_id)

    _fan_out_tipos_manuais(db, consulta_id, org_id, tipo_documento="cnpj")
    service.aplicar_crednet_pendente(db, org_id, consulta)

    return success_response(consulta)


@router.get("/empresas/{empresa_id}/resultados")
async def listar_resultados_por_empresa(
    empresa_id: str,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    svc: CertidoesService = Depends(get_certidoes_service),
):
    """Every certidão result across every consulta linked to an empresa —
    the empresas panel's certidões summary (contract §D5)."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    return success_response(svc.certidoes_por_empresa(db, org_id, empresa_id))


@router.get("/clientes/{cliente_id}/resultados")
async def listar_resultados_por_cliente(
    cliente_id: str,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    svc: CertidoesService = Depends(get_certidoes_service),
):
    """Every certidão result across every consulta linked to one cliente —
    `listar_resultados_por_parte`'s sibling for a card's titular, who has
    no `atendimento_parte_id` to look up by."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    return success_response(
        svc.certidoes_por_cliente(db, org_id, cliente_id)
    )


@router.patch("/consultas/{consulta_id}/situacao-cadastral")
async def atualizar_situacao_cadastral_route(
    consulta_id: str,
    body: SituacaoCadastralPatch,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    svc: CertidoesService = Depends(get_certidoes_service),
):
    """A human's manual entry of the CNPJ/CPF's registration status
    (migration 116) — `situacao_cadastral` / `data_situacao`, on the
    CONSULTA, not any one resultado. Requires at least one field: an empty
    body has nothing to confirm (unlike `confirmar_ou_corrigir_resultado`,
    there is no automated writer for this field to lock out today)."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    campos = body.model_dump(exclude_unset=True, mode="json")
    if not campos:
        raise HTTPException(
            status_code=422,
            detail="Informe situacao_cadastral e/ou data_situacao.",
        )
    updated = svc.atualizar_situacao_cadastral(db, org_id, consulta_id, campos)
    if updated is None:
        raise HTTPException(status_code=404, detail="Consulta não encontrada")
    return success_response(updated)


@router.get("/resultados/{resultado_id}/transcricao")
async def obter_transcricao(
    resultado_id: str,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    svc: CertidoesService = Depends(get_certidoes_service),
):
    """The certidão's transcript — text, Word-pasteable HTML, and inline
    formatting (migration 113) — the per-parte panel's `[Copiar]` source.
    LGPD-logged (`view`) before the response goes out.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    result = svc.obter_transcricao_resultado(
        db, org_id, resultado_id, usuario_id=_user.id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Resultado não encontrado")
    if not result["disponivel"]:
        raise HTTPException(
            status_code=404,
            detail="Transcrição indisponível para esta certidão",
        )
    return success_response({
        "texto": result["texto"],
        "texto_html": result["texto_html"],
        "formatacao": result["formatacao"],
    })


@router.get("/resultados/{resultado_id}/transcricao/pdf")
async def obter_transcricao_pdf(
    resultado_id: str,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    svc: CertidoesService = Depends(get_certidoes_service),
):
    """ABNT-formatted PDF of the certidão's transcript (migration 113).
    Route ordering: a two-segment suffix of `{resultado_id}` — cannot shadow,
    or be shadowed by, `GET /resultados/{resultado_id}/url` or the JSON
    `.../transcricao` route above (distinct static suffixes).
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    result = svc.obter_transcricao_resultado(
        db, org_id, resultado_id, usuario_id=_user.id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Resultado não encontrado")
    if not result["disponivel"]:
        raise HTTPException(
            status_code=404,
            detail="Transcrição indisponível para esta certidão",
        )

    try:
        pdf_bytes = svc.renderizar_transcricao_pdf(
            result["nome_display"], result["texto"], result["formatacao"]
        )
    except UnsupportedGlyphError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    filename = f"{result['tipo']}_transcricao.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@router.patch("/resultados/{resultado_id}")
async def confirmar_ou_corrigir_resultado(
    resultado_id: str,
    body: ResultadoPatch,
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    svc: CertidoesService = Depends(get_certidoes_service),
):
    """A human reviews (and optionally corrects) a resultado's structured
    fields. ALWAYS stamps `resultado_origem='manual'` plus who confirmed it
    and when — even an empty body, which means "I reviewed the API/IA-
    suggested values and they are right". From this point on, the automated
    pipeline (`service._derive_estrutura`) will never touch this resultado's
    structured fields again.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    campos = body.model_dump(exclude_unset=True, mode="json")
    updated = svc.confirmar_resultado(db, org_id, resultado_id, campos, _user.id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Resultado não encontrado")
    return success_response(updated)


@router.get("/resultados/{resultado_id}/url")
async def obter_url_resultado(
    resultado_id: str,
    intent: str = Query("view", pattern="^(view|download)$"),
    auth=Depends(get_current_user_org),
    db=Depends(get_certidoes_client),
    storage: StorageBackend = Depends(get_storage_backend),
    svc: CertidoesService = Depends(get_certidoes_service),
):
    """A short-TTL signed URL to one resultado's stored file, LGPD-logged to
    `certidao_resultado_acessos` — the resultado_id-scoped sibling of
    `GET /download`, for a caller that already holds the id (the per-parte
    certidões panel) rather than the opaque `arquivo_url` handle."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    result = await svc.mint_resultado_url(
        db, storage, org_id, resultado_id, usuario_id=_user.id, intent=intent
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Resultado não encontrado")
    if result.get("error") == "sem_arquivo":
        raise HTTPException(
            status_code=404, detail="Nenhum arquivo para este resultado"
        )
    return success_response(result)


__all__ = ["router"]
