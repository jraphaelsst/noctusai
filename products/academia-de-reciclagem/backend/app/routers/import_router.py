"""Knowledge-bundle import route — contract §B.6.

`POST /api/import` is admin-only (`academia:import`, contract §B.0 —
"never granted to an agent") and accepts either a raw JSONL body
(`application/x-ndjson`) or a multipart upload under the field
`bundle`. Parses via A2's `app/importer/bundle.py` (size cap + path
denylist + the shared content secret scan,
`noctusai_lib.security.secrets_scan`), then runs the whole thing
through A2's transactional `app.importer.run.run_import` against A1b's
`get_store` seam. Returns `200` (contract §B.6 gap closed by this
slice — see the contract's own note on `POST /api/import`'s status:
a verification REPORT, not a single created resource, so `200` rather
than `201`).

**Auth is stricter than `require_scopes` alone.** `academia:import`
is admin-only by contract — but the contract also says the scope must
"never [be] granted to an agent" in the first place, i.e. no
`caller_kind == "product"` token should ever legitimately reach this
route. `_require_import_no_agents` enforces that as an UNCONDITIONAL
refusal (`403 product_forbidden`) BEFORE the scope/role check, rather
than relying on the scope simply never being minted — belt-and-braces
against a future minting mistake. Every other case still goes through
`app.dependencies.require_import_admin` (built from `require_scopes`,
same as every other write dependency in this module) for the real
ADMIN-role check.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel

from noctusai_lib.api.auth.session.types import AuthContext

from app.dependencies import get_auth_context, get_store, require_import_admin
from app.importer.bundle import BundleInvalid, BundleTooLarge, SecretDetected, parse_bundle_lines
from app.importer.run import run_import
from app.knowledge import KnowledgeStore

router = APIRouter(prefix="/api/import", tags=["import"])


class ImportVerificacaoOut(BaseModel):
    revisoes_git: int
    revisoes_importadas: int
    entidades: dict[str, int]
    hashes_head_ok: bool
    codigos: dict[str, int]


class ImportReportOut(BaseModel):
    verificacao: ImportVerificacaoOut
    avisos: list[str]


async def _require_import_no_agents(
    ctx: AuthContext = Depends(get_auth_context),
) -> AuthContext:
    """`academia:import` is admin-only and must NEVER be reachable by a
    product/agent token — contract §B.0's "never granted to an agent",
    enforced unconditionally here rather than left as an implicit
    consequence of the scope simply never being minted (see module
    docstring). Falls through to `require_import_admin`'s real ADMIN
    role check for every `caller_kind == "user"` caller.
    """
    if ctx.caller_kind == "product":
        raise HTTPException(
            status_code=403,
            detail={
                "detail": "Tokens de produto não podem importar — apenas administradores humanos.",
                "code": "product_forbidden",
            },
        )
    return await require_import_admin(ctx)


@router.post("", response_model=ImportReportOut, status_code=status.HTTP_200_OK)
async def import_bundle(
    request: Request,
    bundle: UploadFile | None = File(default=None),
    ctx: AuthContext = Depends(_require_import_no_agents),
    store: KnowledgeStore = Depends(get_store),
) -> ImportReportOut:
    if bundle is not None:
        raw = await bundle.read()
    else:
        raw = await request.body()

    try:
        lines = parse_bundle_lines(raw)
    except BundleTooLarge as exc:
        raise HTTPException(
            status_code=422,
            detail={"detail": str(exc), "code": "bundle_too_large"},
        ) from exc
    except SecretDetected as exc:
        # §B.6: name the PATH only, never the value.
        raise HTTPException(
            status_code=422,
            detail={
                "detail": f"Segredo detectado em: {exc.path}",
                "code": "secret_detected",
            },
        ) from exc
    except BundleInvalid as exc:
        raise HTTPException(
            status_code=422,
            detail={"detail": str(exc), "code": "bundle_invalid"},
        ) from exc

    # `ctx.user_id` is non-None here: `_require_import_no_agents` already
    # refused every `caller_kind == "product"` caller above, so only an
    # SSO admin (`caller_kind == "user"`) can reach this line.
    report = await run_import(store, ctx.org_id, lines, ctx.user_id)
    return ImportReportOut(**report)
