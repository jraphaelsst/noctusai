"""Central da Marca — Módulo 2.

Two surfaces:

  MARCA          /api/marcas …            brand identity, tone of voice,
                                          editorial lines, personas, logo
  REPERTÓRIO     /api/marcas/repertorio/{cliente_id}
                                          the compact payload the persistent
                                          sidebar renders on task screens
  COFRE          /api/marcas/acessos …    encrypted client credentials

**The Cofre is the sensitive part** and is treated accordingly:
  * listing NEVER returns a password — not even ciphertext, which would hand
    an attacker an offline target. `AcessoOut` has no such field; `tem_senha`
    is a boolean.
  * revealing one password is a separate, explicit, ADMIN-ONLY endpoint that
    logs who did it.
  * storing a password with no configured key is REFUSED rather than silently
    downgraded to plaintext (enforced in the repository).
"""
# NOTE: no `from __future__ import annotations` — see esteira_router.py. This
# module is not rate-limited today, but the constraint travels with the file
# the moment someone adds a decorator, and the cost of eager annotations is nil.
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from noctusai_lib.integrations.persistence import RecordNotFound
from noctusai_lib.primitives.roles import ADMIN_ROLES

from app.config import settings
from app.dependencies import (
    coerce_org_uuid,
    get_current_user_org,
    get_user_role,
    resolve_platform_role,
)
from app.repositories import Repositorios
from app.schemas.marca import (
    AcessoCreate,
    AcessoOut,
    AcessoUpdate,
    AcessosOut,
    LogoOut,
    MarcaCreate,
    MarcaOut,
    MarcaUpdate,
    RepertorioOut,
    SenhaRevelada,
)
from app.storage import chave_da_peca, get_storage
from app.store import get_repositorios

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/marcas", tags=["marca"])

#: Logos are the only upload this router accepts. The spec asks for PNG/SVG;
#: an allowlist (not a denylist) keeps an SVG-borne script or a disguised
#: executable from being stored and later served back to a browser.
_LOGO_MIMES = {"image/png", "image/svg+xml", "image/jpeg", "image/webp"}
_LOGO_MAX_BYTES = 2 * 1024 * 1024


def _org(auth: tuple) -> str:
    _user, _token, raw_org = auth
    return str(coerce_org_uuid(raw_org))


def _exigir_admin(auth: tuple) -> None:
    """Gate for revealing a stored credential.

    Every member of the agency can SEE that a credential exists and use the
    account through the linked tool; only owners/admins can read the password
    back out. Without this, the vault is a plaintext store with extra steps
    for anyone who can log in.

    **Trust model matters more here than anywhere else in this product.**
    `resolve_sso_role` reads `user_metadata`, which Supabase lets ANY
    authenticated user rewrite via `auth.updateUser({data})` — using it here
    would let a member promote themselves and read every stored client
    password. This resolves through `make_resolve_platform_role`
    (trusted `public.noctus_users`, fail-closed) and falls back to the
    product's own `get_user_role`, which reads the same trusted row.
    → `role-cascade-trusted`, 2026-07-14.
    """
    user, _token, _raw_org = auth
    if resolve_platform_role(user) == "platform_admin":
        return
    papel = get_user_role(user)
    if papel not in ADMIN_ROLES:
        raise HTTPException(
            status_code=403, detail="Apenas administradores podem revelar senhas"
        )


def _chave_cofre() -> bytes:
    """The Fernet key, or a loud 409.

    A 409 rather than a 500: the request is well-formed, the SERVER is not
    configured. Saying so plainly is what stops someone concluding the vault
    is broken and pasting the password into `observacoes`.
    """
    if not settings.igig_cofre_key:
        raise HTTPException(
            status_code=409,
            detail=(
                "Cofre não configurado: defina IGIG_COFRE_KEY no ambiente. "
                "Nenhuma senha é gravada em texto puro."
            ),
        )
    return settings.igig_cofre_key.encode("utf-8")


def _acesso_out(row: dict) -> AcessoOut:
    """Project a vault row, dropping the ciphertext."""
    return AcessoOut(**row, tem_senha=bool(row.get("senha_cifrada")))


async def _com_logo(linha: dict) -> dict:
    """Return the row with a FRESHLY-SIGNED `logo_url` minted from `logo_key`.

    🔴 A signed URL must never be persisted. `storage.signed_url` defaults to a
    one-hour TTL, and `enviar_logo` used to write that value straight into
    `marca.logo_url` — so every logo rendered for an hour and then 404'd
    forever (observed in prod 2026-09-01: `naturalWidth: 0` on a logo uploaded
    90 minutes earlier). The key is the durable thing; the URL is a credential
    minted per response. Same shape `peca.storage_key` already used.

    Rows with no `logo_key` (created before `015`, or never given a logo) pass
    through untouched rather than erroring — a brand without a logo is normal.
    """
    chave = linha.get("logo_key")
    if not chave:
        return linha
    armazenamento = get_storage()
    return {
        **linha,
        "logo_url": await armazenamento.signed_url(
            bucket=settings.igig_storage_bucket, key=str(chave)
        ),
    }


# ── Marca ───────────────────────────────────────────────────────────
@router.get("", response_model=list[MarcaOut])
async def listar_marcas(
    cliente_id: str | None = None,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> list[MarcaOut]:
    org_id = _org(auth)
    linhas = (
        repos.marca.do_cliente(org_id, cliente_id) if cliente_id else repos.marca.listar(org_id)
    )
    return [MarcaOut(**await _com_logo(m)) for m in linhas]


@router.post("", response_model=MarcaOut, status_code=status.HTTP_201_CREATED)
async def criar_marca(
    payload: MarcaCreate,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> MarcaOut:
    org_id = _org(auth)
    try:
        repos.cliente.buscar(org_id, payload.cliente_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return MarcaOut(**repos.marca.criar(org_id, payload.model_dump(mode="json")))


@router.get("/repertorio/{cliente_id}", response_model=RepertorioOut)
async def obter_repertorio(
    cliente_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> RepertorioOut:
    """The persistent-sidebar payload for a client.

    Returns an EMPTY repertório (200) rather than 404 when the client has no
    brand yet — the sidebar is ambient chrome on a task screen, and a 404
    there would surface as an error banner over someone's work.
    """
    org_id = _org(auth)
    try:
        cliente = repos.cliente.buscar(org_id, cliente_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    marca = repos.marca.repertorio(org_id, cliente_id)
    if marca is None:
        return RepertorioOut(cliente_nome=cliente.get("nome"))
    marca = await _com_logo(marca)
    return RepertorioOut(
        cliente_nome=cliente.get("nome"),
        marca_nome=marca.get("nome"),
        logo_url=marca.get("logo_url"),
        paleta=marca.get("paleta") or [],
        tom_de_voz=marca.get("tom_de_voz"),
        termos_proibidos=marca.get("termos_proibidos"),
        nivel_formalidade=marca.get("nivel_formalidade"),
        linhas_editoriais=marca.get("linhas_editoriais") or [],
    )


@router.get("/{marca_id}", response_model=MarcaOut)
async def obter_marca(
    marca_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> MarcaOut:
    try:
        return MarcaOut(**await _com_logo(repos.marca.buscar(_org(auth), marca_id)))
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Marca não encontrada")


@router.patch("/{marca_id}", response_model=MarcaOut)
async def atualizar_marca(
    marca_id: str,
    payload: MarcaUpdate,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> MarcaOut:
    dados = payload.model_dump(mode="json", exclude_none=True)
    if not dados:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        return MarcaOut(**repos.marca.atualizar(_org(auth), marca_id, dados))
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Marca não encontrada")


@router.post("/{marca_id}/logo", response_model=LogoOut, status_code=status.HTTP_201_CREATED)
async def enviar_logo(
    marca_id: str,
    arquivo: UploadFile = File(...),
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> LogoOut:
    """Upload a brand logo through the seed storage seam.

    The bytes go to storage; the DB keeps only the resulting URL, so this
    endpoint is identical whether the backend is Supabase Storage or the local
    filesystem.
    """
    org_id = _org(auth)
    try:
        repos.marca.buscar(org_id, marca_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Marca não encontrada")

    if arquivo.content_type not in _LOGO_MIMES:
        raise HTTPException(
            status_code=422,
            detail=f"Formato não suportado: {arquivo.content_type}. Envie PNG, SVG, JPEG ou WebP.",
        )
    conteudo = await arquivo.read()
    if len(conteudo) > _LOGO_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Logo excede 2 MB")

    chave = chave_da_peca(org_id, f"marcas/{marca_id}", arquivo.filename or "logo")
    armazenamento = get_storage()
    await armazenamento.put(
        bucket=settings.igig_storage_bucket,
        key=chave,
        data=conteudo,
        content_type=arquivo.content_type,
    )
    url = await armazenamento.signed_url(bucket=settings.igig_storage_bucket, key=chave)
    # Persist the KEY. `logo_url` is written too so a consumer reading the row
    # directly still sees something, but it is authoritative for exactly as
    # long as the TTL — every READ path re-signs from `logo_key` via
    # `_com_logo`.
    repos.marca.atualizar(org_id, marca_id, {"logo_key": chave, "logo_url": url})
    logger.info("logo enviado org=%s marca=%s key=%s", org_id, marca_id, chave)
    return LogoOut(storage_key=chave, url=url)


# ── Cofre de Acessos ────────────────────────────────────────────────
@router.get("/acessos/{cliente_id}", response_model=AcessosOut)
async def listar_acessos(
    cliente_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> AcessosOut:
    """Vault entries for a client, plus whether the vault is configured.

    Passwords are NOT included. `cofre_configurado` lets the setup screen
    say so BEFORE someone types a password and hits a 409 — including for a
    client with zero entries, where a per-item flag would have nothing to
    attach to.
    """
    return AcessosOut(
        cofre_configurado=bool(settings.igig_cofre_key),
        itens=[_acesso_out(a) for a in repos.acesso.do_cliente(_org(auth), cliente_id)],
    )


@router.post("/acessos", response_model=AcessoOut, status_code=status.HTTP_201_CREATED)
async def criar_acesso(
    payload: AcessoCreate,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> AcessoOut:
    org_id = _org(auth)
    try:
        repos.cliente.buscar(org_id, payload.cliente_id)
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    campos = payload.model_dump(exclude_none=True)
    campos.pop("cliente_id", None)
    rotulo = campos.pop("rotulo")
    senha = campos.pop("senha", None)
    chave = _chave_cofre() if senha else None

    registro = repos.acesso.guardar(
        org_id, payload.cliente_id, rotulo=rotulo, senha=senha, chave=chave, **campos
    )
    return _acesso_out(registro)


@router.patch("/acessos/{acesso_id}", response_model=AcessoOut)
async def atualizar_acesso(
    acesso_id: str,
    payload: AcessoUpdate,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> AcessoOut:
    org_id = _org(auth)
    dados = payload.model_dump(exclude_none=True)
    senha = dados.pop("senha", None)
    if senha:
        from noctusai_lib.security.encrypted_tokens import encrypt

        dados["senha_cifrada"] = encrypt(senha, _chave_cofre())
    if not dados:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        return _acesso_out(repos.acesso.atualizar(org_id, acesso_id, dados))
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Acesso não encontrado")


@router.post("/acessos/{acesso_id}/revelar", response_model=SenhaRevelada)
async def revelar_senha(
    acesso_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> SenhaRevelada:
    """Decrypt ONE stored password. Admin/owner only, and logged.

    A POST rather than a GET on purpose: this is an auditable action with a
    side effect (the log entry), and GETs land in browser history, proxy logs
    and prefetchers.
    """
    _exigir_admin(auth)
    org_id = _org(auth)
    user, _token, _raw = auth
    try:
        senha = repos.acesso.revelar_senha(org_id, acesso_id, _chave_cofre())
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Acesso não encontrado")
    if senha is None:
        raise HTTPException(status_code=404, detail="Este acesso não possui senha armazenada")
    logger.info(
        "cofre: senha revelada org=%s acesso=%s por=%s",
        org_id, acesso_id, getattr(user, "id", None) or getattr(user, "email", "?"),
    )
    return SenhaRevelada(senha=senha)


@router.delete("/acessos/{acesso_id}", status_code=status.HTTP_200_OK)
async def remover_acesso(
    acesso_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> dict:
    if not repos.acesso.remover(_org(auth), acesso_id):
        raise HTTPException(status_code=404, detail="Acesso não encontrado")
    return {"ok": True}
