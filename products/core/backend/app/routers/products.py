"""
Products Router — Product catalog for the NoctusAI marketplace.

GET    /api/products                      — List all products (public catalog)
GET    /api/products/{id}                 — Product details
POST   /api/products                      — Create product (platform admin only)
PATCH  /api/products/{id}                 — Update presentation fields (admin only)
POST   /api/products/{id}/activation      — Activate / deactivate (admin only)
POST   /api/products/{id}/deploy-scope    — Move between live / dev scope (admin only)
DELETE /api/products/{id}                 — Deactivate product (platform admin only)

TWO AXES, TWO ENDPOINTS
-----------------------
`ativo` (status) and `deploy_scope` (working scope) together form the team's
working guide — which products we touch, and in which environment:

    ativo + live → work it in PROD (dev-validate, then promote)
    ativo + dev  → work it in DEV only; never reaches prod
    inativo      → do not touch the product at all

They are separate endpoints rather than PATCH fields because each carries a
transition rule that a generic field write cannot express. See
`app/schemas/products.py` and migration 042 for the invariants.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException

from app.database import get_admin_client
from app.dependencies import get_current_user, get_current_admin
from app.schemas.products import (
    ProductActivation,
    ProductCreate,
    ProductDeployScope,
    ProductUpdate,
)
from app.services.deployment_status import (
    FleetProber,
    get_deployment_status,
    house_port_from_url_base,
    probe_fleet,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/products", tags=["Products"])


def get_fleet_prober() -> FleetProber:
    """DI seam for the deployment prober — overridden in tests (no network)."""
    return probe_fleet


@router.get("")
async def listar_products(
    authorization: Optional[str] = Header(None),
    include_inactive: bool = False,
):
    """List products from the marketplace catalog (`public.products`).

    Default (marketplace): only ACTIVE products. `include_inactive=true`
    (platform-admin only) returns ALL rows — same table, same data the
    marketplace reads — so the admin panel can see *and reactivate*
    deactivated products instead of them vanishing after a soft-delete.
    """
    if include_inactive:
        user, token = await get_current_admin(authorization)
    else:
        user, token = await get_current_user(authorization)
    db = get_admin_client()

    query = db.table("products").select("*")
    if not include_inactive:
        query = query.eq("ativo", True)
    result = query.order("nome").execute()
    return {"data": result.data or []}


@router.get("/deployment-status")
async def deployment_status(
    authorization: Optional[str] = Header(None),
    prober: FleetProber = Depends(get_fleet_prober),
):
    """Report which catalog products are deployed (container reachable) RIGHT NOW.

    "Deployed" = the product's single container answers /api/health on the
    shared noctus-net (internal port 8000). Environment-accurate by
    construction — core probes whatever fleet it runs alongside (dev OR prod),
    so a product can be deployed in dev but not prod with one catalog. Drives
    the launcher's "dev" badge. Never raises because a product is down.

    NOTE: declared BEFORE GET /{product_id} so "deployment-status" isn't
    captured as a product id.
    """
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    result = db.table("products").select("slug, url_base").eq("ativo", True).execute()
    # Probe each container on its HOUSE port (parsed from url_base) — every
    # product serves on uvicorn `--port <house>`, NOT a uniform 8000.
    targets = {
        row["slug"]: house_port_from_url_base(row.get("url_base"))
        for row in (result.data or []) if row.get("slug")
    }
    deployed = await get_deployment_status(targets, prober=prober)
    return {"deployed": deployed}


@router.get("/{product_id}")
async def get_product(product_id: str, authorization: Optional[str] = Header(None)):
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    result = db.table("products").select("*").eq("id", product_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return {"data": result.data}


@router.post("")
async def criar_product(body: ProductCreate, authorization: Optional[str] = Header(None)):
    """Create a new product (platform admin only)."""
    user, token = await get_current_admin(authorization)
    db = get_admin_client()

    # Check for duplicate slug
    existing = db.table("products").select("id").eq("slug", body.slug).execute()
    if existing.data:
        raise HTTPException(status_code=409, detail="Já existe um produto com este slug")

    data = body.model_dump(exclude_none=True)
    data["ativo"] = True

    result = db.table("products").insert(data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar produto")

    logger.info(f"Product created: {body.nome}")
    return {"data": result.data[0]}


@router.patch("/{product_id}")
async def atualizar_product(
    product_id: str, body: ProductUpdate, authorization: Optional[str] = Header(None)
):
    """Update a product (platform admin only). Slug is immutable."""
    user, token = await get_current_admin(authorization)
    db = get_admin_client()

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = db.table("products").update(data).eq("id", product_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    logger.info(f"Product updated: {product_id}")
    return {"data": result.data[0]}


def _apply_activation(db, product_id: str, ativo: bool) -> dict:
    """THE single place the status transition is expressed.

    Both `POST /{id}/activation` and the legacy `DELETE /{id}` funnel through
    here so the rules cannot diverge between two call sites.

    Deactivating writes `ativo=false` AND `deploy_scope='dev'` in ONE update.
    That is not a convenience — the DB CHECK (`products_inactive_never_live`)
    forbids the inactive+live combination, so a two-step "demote then
    deactivate" would leave a window where a crash between the writes strands
    the row. One statement means the forbidden state is never reachable.

    Reactivating also forces 'dev': a product returning from inactive has not
    been re-validated in prod, so it must not silently resume shipping there.
    """
    patch = {"ativo": ativo, "deploy_scope": "dev"}
    result = db.table("products").update(patch).eq("id", product_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return result.data[0]


@router.post("/{product_id}/activation")
async def definir_activation(
    product_id: str,
    body: ProductActivation,
    authorization: Optional[str] = Header(None),
):
    """Activate / deactivate a product (platform admin only) — the STATUS axis.

    Deactivation demotes the product to `dev` scope in the same write; a
    reactivated product always comes back in `dev` and must be promoted to
    `live` explicitly.
    """
    user, token = await get_current_admin(authorization)
    db = get_admin_client()

    row = _apply_activation(db, product_id, body.ativo)
    logger.info(
        "Product %s: %s (deploy_scope forced to dev)",
        product_id, "activated" if body.ativo else "deactivated",
    )
    return {"data": row}


@router.post("/{product_id}/deploy-scope")
async def definir_deploy_scope(
    product_id: str,
    body: ProductDeployScope,
    authorization: Optional[str] = Header(None),
):
    """Move a product between `live` and `dev` working scope (admin only).

    Refuses with 409 when the product is inactive — an inactive product is one
    we have agreed not to touch at all, so giving it a working scope is
    meaningless. Returning a typed refusal here (rather than letting the DB
    CHECK fire) is what turns the invariant into an explainable error.
    """
    user, token = await get_current_admin(authorization)
    db = get_admin_client()

    current = db.table("products").select("ativo").eq("id", product_id).execute()
    if not current.data:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    if body.deploy_scope == "live" and current.data[0].get("ativo") is not True:
        raise HTTPException(
            status_code=409,
            detail=(
                "Produto inativo não pode ser LIVE. Ative o produto primeiro; "
                "ele volta em DEV e pode então ser promovido."
            ),
        )

    result = (
        db.table("products")
        .update({"deploy_scope": body.deploy_scope})
        .eq("id", product_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    logger.info("Product %s deploy_scope -> %s", product_id, body.deploy_scope)
    return {"data": result.data[0]}


@router.delete("/{product_id}")
async def desativar_product(product_id: str, authorization: Optional[str] = Header(None)):
    """Soft-delete a product by setting ativo = false (platform admin only).

    Retained for existing callers; delegates to the same transition helper as
    `POST /{id}/activation` so it cannot drift into leaving a deactivated
    product marked `live`.
    """
    user, token = await get_current_admin(authorization)
    db = get_admin_client()

    row = _apply_activation(db, product_id, False)
    logger.info(f"Product deactivated: {product_id}")
    return {"data": row}
