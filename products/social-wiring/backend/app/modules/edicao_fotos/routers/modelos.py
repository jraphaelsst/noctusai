"""`/api/edicao-fotos/modelos` — contract §8, the model catalog (W8).

    GET  /modelos                                  member — enabled image models; metrics + notes for admins
    GET  /modelos/catalogo                         platform admin — every row (image/vision/chat), incl. disabled
    PUT  /modelos/catalogo/{modelo_id}             platform admin — save one row (versioned)
    GET  /modelos/catalogo/{modelo_id}/versoes     platform admin — the row's history
    GET  /modelos/etapas                           platform admin — model per engine step
    PUT  /modelos/etapas                           platform admin
    POST /modelos/notas/gerar                      platform admin — queue a note rewrite now (202)

The catalog is the seed's static `llm.models.MODELS` with the platform
admin's overrides applied (`llm.catalog_overrides`, migration 130): the
same overlay the pricing code, `capabilities_for_model` and submission read,
so what this page shows IS what the engine bills. A saved row refreshes this
process's overlay at once; other processes pick it up within
`EDICAO_FOTOS_CATALOG_REFRESH_SECONDS`.

Live metrics come from the `fotos_modelo_metricas` RPC on every read (never
cached); the note is the latest daily AI note. Both are admin-only — they
carry cost and AI-verdict aggregates (contract §1).
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, Query, status

from noctusai_lib.domain.photo_editing import (
    Actor,
    PhotoEditingPorts,
    Step,
    StepModelError,
    enqueue_model_notes,
    step_models_view,
    validate_step_model,
)
from noctusai_lib.domain.photo_editing.steps import STEP_SETTING
from noctusai_lib.integrations.llm import (
    ModelCatalogStore,
    ModelOverride,
    ModelOverrideConflict,
    base_models_for,
    get_model_override,
    get_model_overrides,
    models_for,
)

from app.modules.edicao_fotos.deps import (
    can_see_verdict,
    get_catalog_store,
    get_edicao_ports,
    get_worker_control,
    require_member,
    require_platform_admin,
)
from app.modules.edicao_fotos.errors import api_error
from app.modules.edicao_fotos.presenters import (
    etapas_out,
    modelo_admin_out,
    modelo_out,
    modelo_versao_out,
)
from app.modules.edicao_fotos.schemas import ModeloCatalogoBody, ModelosEtapasBody

router = APIRouter(prefix="/api/edicao-fotos/modelos", tags=["edicao-fotos"])

PROVIDER = "openai"
IMAGE_EDIT_PROVIDER = PROVIDER
ADMIN_KINDS = ("image_edit", "vision", "chat")
MODEL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,119}$")


@router.get("")
async def list_modelos_route(
    actor: Actor = Depends(require_member),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> list[dict]:
    entries = models_for(IMAGE_EDIT_PROVIDER, "image_edit")
    if not can_see_verdict(actor):
        return [modelo_out(e) for e in entries]
    ids = [e.id for e in entries]
    notes = await ports.repo.latest_model_notes(ids)
    return [
        modelo_out(e, metrics=await ports.repo.model_metrics(e.id), note=notes.get(e.id))
        for e in entries
    ]


def _admin_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for kind in ADMIN_KINDS:
        base = {m.id: m for m in base_models_for(PROVIDER, kind)}
        effective = {m.id: m for m in models_for(PROVIDER, kind)}
        ids = list(base)
        ids += sorted(i for i in effective if i not in base)
        ids += sorted(
            o.model_id
            for o in get_model_overrides()
            if o.provider == PROVIDER and o.kind == kind and o.model_id not in base and not o.enabled
        )
        for model_id in ids:
            rows.append(
                modelo_admin_out(
                    model_id=model_id,
                    kind=kind,
                    effective=effective.get(model_id),
                    base=base.get(model_id),
                    override=get_model_override(PROVIDER, kind, model_id),
                )
            )
    return rows


@router.get("/catalogo")
async def list_catalogo_route(_actor: Actor = Depends(require_platform_admin)) -> dict:
    return {"items": _admin_rows()}


def _in_use_by_step(platform: Any, config: Any, kind: str, model_id: str) -> list[str]:
    return [
        v.step.value
        for v in step_models_view(platform, config)
        if v.kind == kind and v.modelo == model_id
    ]


def _price(value: Any) -> float | None:
    return None if value is None else float(value)


@router.put("/catalogo/{modelo_id}")
async def put_catalogo_route(
    modelo_id: str,
    body: ModeloCatalogoBody,
    actor: Actor = Depends(require_platform_admin),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
    store: ModelCatalogStore = Depends(get_catalog_store),
    control: Any = Depends(get_worker_control),
) -> dict:
    if not MODEL_ID_RE.fullmatch(modelo_id):
        raise api_error(422, "modelo_id_invalido", "Identificador de modelo inválido.")
    if not body.habilitado:
        in_use = _in_use_by_step(await ports.repo.get_platform_settings(), ports.config, body.kind, modelo_id)
        if in_use:
            raise api_error(
                409,
                "modelo_em_uso",
                f"O modelo está configurado nas etapas: {', '.join(in_use)}. Troque-o antes de desativar.",
            )
    base = next((m for m in base_models_for(PROVIDER, body.kind) if m.id == modelo_id), None)
    override = ModelOverride(
        provider=PROVIDER,
        kind=body.kind,
        model_id=modelo_id,
        enabled=body.habilitado,
        label=(body.nome or "").strip() or (base.label if base else modelo_id),
        description=(body.descricao or "").strip() or None,
        snapshot=(body.snapshot or "").strip() or None,
        cost_per_1m_input_tokens=_price(body.preco_entrada_texto_1m),
        cost_per_1m_output_tokens=_price(body.preco_saida_texto_1m),
        cost_per_1m_image_input_tokens=_price(body.preco_entrada_imagem_1m),
        cost_per_1m_image_output_tokens=_price(body.preco_saida_imagem_1m),
        supports_batch=body.suporta_batch if body.kind == "image_edit" else False,
        tag_performance=body.tag_performance,
    )
    try:
        saved = await store.save_override(override, changed_by=actor.user_id)
    except ModelOverrideConflict as exc:
        raise api_error(409, exc.code, "Outra pessoa salvou este modelo agora — recarregue e tente de novo.") from exc
    # `recarregado=false` ⇒ saved, but this process still serves the previous
    # overlay until the refresher's next tick (the failure is on the panel).
    recarregado = await control.refresh_catalog(store) is not None
    row = modelo_admin_out(
        model_id=modelo_id,
        kind=body.kind,
        effective=saved.to_entry(base) if saved.enabled else None,
        base=base,
        override=saved,
    )
    return {**row, "recarregado": recarregado}


@router.get("/catalogo/{modelo_id}/versoes")
async def list_versoes_route(
    modelo_id: str,
    kind: str = Query("image_edit"),
    limit: int = Query(50, ge=1, le=200),
    _actor: Actor = Depends(require_platform_admin),
    store: ModelCatalogStore = Depends(get_catalog_store),
) -> dict:
    if kind not in ADMIN_KINDS:
        raise api_error(422, "tipo_invalido", "Tipo de modelo inválido.")
    versions = await store.list_versions(PROVIDER, kind, modelo_id, limit=limit)
    return {"items": [modelo_versao_out(v) for v in versions]}


@router.get("/etapas")
async def get_etapas_route(
    _actor: Actor = Depends(require_platform_admin),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    platform = await ports.repo.get_platform_settings()
    return etapas_out(step_models_view(platform, ports.config))


@router.put("/etapas")
async def put_etapas_route(
    body: ModelosEtapasBody,
    _actor: Actor = Depends(require_platform_admin),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    changes: dict[str, Any] = {}
    for step in Step:
        if step.value not in body.model_fields_set:
            continue
        value = (getattr(body, step.value) or "").strip() or None
        if value is not None:
            try:
                validate_step_model(ports.config, step, value)
            except StepModelError as exc:
                raise api_error(422, exc.code, f"Etapa {step.value}: {exc}") from exc
        changes[STEP_SETTING[step]] = value
    platform = (
        await ports.repo.update_platform_settings(**changes)
        if changes
        else await ports.repo.get_platform_settings()
    )
    return etapas_out(step_models_view(platform, ports.config))


@router.post("/notas/gerar", status_code=status.HTTP_202_ACCEPTED)
async def gerar_notas_route(
    _actor: Actor = Depends(require_platform_admin),
    ports: PhotoEditingPorts = Depends(get_edicao_ports),
) -> dict:
    job = await enqueue_model_notes(ports)
    return {"job_id": str(job.id), "status": job.status.value}


__all__ = ["router"]
