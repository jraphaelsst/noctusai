"""Response shapes. Enum values are the pt-BR literals the tables store.

🔴 No presenter here ever reads an evaluation: the AI verdict is added by
the review router ONLY for callers allowed to see it (contract §1)."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Optional

from noctusai_lib.domain.photo_editing import Batch, Photo
from noctusai_lib.domain.photo_editing.types import (
    Evaluation,
    OrgSettings,
    PlatformSettings,
    ReviewDecision,
)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _v(value: Any) -> Any:
    return getattr(value, "value", value)


def batch_out(batch: Batch, photos: Optional[list[Photo]] = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": str(batch.id),
        "nome": batch.nome,
        "status": _v(batch.status),
        "velocidade": _v(batch.velocidade),
        "origem": batch.origem,
        "criado_por": str(batch.criado_por),
        "imovel": (
            {"org_id": str(batch.imovel_org_id), "codigo": batch.imovel_codigo}
            if batch.imovel_codigo
            else None
        ),
        "modelo_editor_id": batch.modelo_editor_id,
        "created_at": _iso(batch.created_at),
        "submetido_at": _iso(batch.submetido_at),
        "pronto_at": _iso(batch.pronto_at),
    }
    if photos is not None:
        out["total_fotos"] = len(photos)
        out["por_status"] = dict(Counter(_v(p.status) for p in photos))
    return out


def photo_out(photo: Photo) -> dict[str, Any]:
    return {
        "id": str(photo.id),
        "ordem": photo.ordem,
        "status": _v(photo.status),
        "tentativas": photo.tentativas,
        "falha_motivo": photo.falha_motivo,
        "vista_codigo": photo.vista_codigo,
        "largura": photo.largura_original,
        "altura": photo.altura_original,
        "editada": bool(photo.storage_path_editada),
    }


def decision_out(decision: Optional[ReviewDecision]) -> Optional[dict[str, Any]]:
    if decision is None:
        return None
    return {
        "id": str(decision.id),
        "decisao": _v(decision.decisao),
        "comentario": decision.comentario,
        "decidido_por": str(decision.decidido_por),
        "created_at": _iso(decision.created_at),
    }


def evaluation_out(evaluation: Optional[Evaluation]) -> Optional[dict[str, Any]]:
    if evaluation is None:
        return None
    return {
        "recomendacao": _v(evaluation.recomendacao),
        "score": float(evaluation.score),
        "motivo": evaluation.motivo,
        "modelo_id": evaluation.modelo_id,
        "modelo_versao": evaluation.modelo_versao,
    }


def org_settings_out(settings: OrgSettings) -> dict[str, Any]:
    return {
        "org_id": str(settings.org_id),
        "tipos_edicao_ativos": [_v(t) for t in settings.tipos_edicao_ativos],
        "modelo_editor_id": settings.modelo_editor_id,
        "velocidade_override": _v(settings.velocidade_override),
        "notificacoes_ativas": settings.notificacoes_ativas,
        "limites": {
            "fotos_por_lote": settings.limite_fotos_por_lote,
            "bytes_por_foto": settings.limite_bytes_por_foto,
        },
    }


def platform_settings_out(settings: PlatformSettings) -> dict[str, Any]:
    price = settings.preco_storage_gb_mes_usd
    return {
        "velocidade_default": _v(settings.velocidade_default),
        "notificacoes_globais_ativas": settings.notificacoes_globais_ativas,
        "preco_storage_gb_mes_usd": str(price) if price is not None else None,
    }


def page_out(items: list[Any], *, page: int, page_size: int, total: int) -> dict[str, Any]:
    return {"items": items, "page": page, "page_size": page_size, "total": total}
