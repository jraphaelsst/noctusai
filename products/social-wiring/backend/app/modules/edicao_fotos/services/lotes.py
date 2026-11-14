"""Batch (lote) creation shared by `POST /api/edicao-fotos/lotes` and `POST /api/imobshotai/lotes` (contract §1/§2).

One place for the rules: editor model + edit types configured, speed resolution, imóvel org match and imóvel
EXISTENCE (`422 imovel_inexistente` — the root fix: a lote can no longer point at a code that is not in the registry
or the mirror)."""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional

from noctusai_lib.domain.photo_editing import Actor, Batch, OrgSettings, PhotoEditingPorts, Speed

from app.modules.edicao_fotos.errors import api_error
from app.modules.edicao_fotos.schemas import ImovelRef

#: `(org_id, [codigo]) -> {codigo: imóvel}` (`imovel_hub.busca_service.enriquecer` in production).
ImovelLookup = Callable[[str, list[str]], dict[str, dict]]


def canonical(codigo: str) -> str:
    return codigo.strip().upper()


async def imovel_existe(lookup: ImovelLookup, org_id: str, codigo: str) -> bool:
    key = canonical(codigo)
    found = (await asyncio.to_thread(lookup, org_id, [key])).get(key)
    # `fonte == "nenhuma"` (or no entry) = in neither the registry nor the mirror.
    return bool(found) and found.get("fonte") != "nenhuma"


async def org_settings(ports: PhotoEditingPorts, org_id: str) -> OrgSettings:
    return await ports.repo.get_org_settings(org_id) or OrgSettings(org_id=org_id)


async def criar_lote(
    *,
    ports: PhotoEditingPorts,
    actor: Actor,
    nome: str,
    imovel: Optional[ImovelRef],
    velocidade: Optional[str],
    imovel_lookup: ImovelLookup,
    antes_de_criar: Optional[Callable[[], Awaitable[Any]]] = None,
) -> Batch:
    """Validate, then create the batch. `antes_de_criar` runs after every validation passed and before the row is
    written (ImobShotAI creates the card there, so a refused request never leaves a card behind)."""
    settings = await org_settings(ports, actor.org_id)
    if not settings.modelo_editor_id:
        raise api_error(
            422, "modelo_nao_configurado", "Nenhum modelo de edição configurado para a organização."
        )
    if not settings.tipos_edicao_ativos:
        raise api_error(422, "sem_tipos_edicao", "Nenhum tipo de edição ativo.")
    platform = await ports.repo.get_platform_settings()
    # An explicit per-batch choice wins; otherwise the org override, then the
    # platform default. Econômico is gated by the engine's capability port
    # alone — never silently downgraded to Urgente.
    speed = Speed(velocidade or settings.velocidade_override or platform.velocidade_default)
    if speed is Speed.ECONOMICO and not ports.capabilities(settings.modelo_editor_id).supports_batch:
        raise api_error(422, "economico_indisponivel", "Modo Econômico indisponível.")
    if imovel is not None:
        if str(imovel.org_id) != actor.org_id:
            raise api_error(
                422, "imovel_outra_organizacao", "O imóvel precisa pertencer à sua organização."
            )
        if not await imovel_existe(imovel_lookup, actor.org_id, imovel.codigo):
            raise api_error(422, "imovel_inexistente", "Nenhum imóvel com esse código.")
    if antes_de_criar is not None:
        await antes_de_criar()
    return await ports.repo.create_batch(
        org_id=actor.org_id,
        nome=nome.strip(),
        criado_por=actor.user_id,
        # The imóvel link is what enables a Vista pull; each photo also
        # records its own provenance in `vista_codigo`.
        origem="vista" if imovel is not None else "upload",
        velocidade=speed,
        imovel_org_id=str(imovel.org_id) if imovel else None,
        imovel_codigo=imovel.codigo.strip() if imovel else None,
    )


__all__ = ["ImovelLookup", "canonical", "criar_lote", "imovel_existe", "org_settings"]
