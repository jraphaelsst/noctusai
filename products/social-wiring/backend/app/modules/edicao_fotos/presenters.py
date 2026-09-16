"""Response shapes — the SAME shapes the seed FE hook factory is typed
against (`seed/lib/frontend/src/photo-editing/hooks.ts`), pinned by
`seed/lib/frontend/src/photo-editing/contract.fixture.json` and replayed by
`tests/modules/edicao_fotos/test_edicao_fotos_contract_fixture.py`.

Enum values are the pt-BR literals the tables store.

🔴 The AI verdict (`avaliacao`) is added by `foto_revisao_out` ONLY when the
caller passes an evaluation — the routers fetch one only for callers allowed
to see it (contract §1). Absent key, never `null`, for everyone else."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional

from noctusai_lib.domain.photo_editing import Batch, Photo, PhotoStatus
from noctusai_lib.domain.photo_editing.types import (
    BatchStatus,
    Evaluation,
    OrgSettings,
    PlatformSettings,
    ReferencePair,
    ReviewDecision,
    StyleGuide,
)

_DECIDED = {PhotoStatus.APROVADA, PhotoStatus.REJEITADA}

def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _v(value: Any) -> Any:
    return getattr(value, "value", value)


def estado_agregado(batch: Batch, states: Iterable[PhotoStatus]) -> str:
    """One badge for the list view, derived from batch + photo states.

    rascunho            the batch was not submitted yet
    processando         submitted, photos still in the pipeline
    aguardando_revisao  processed; at least one photo awaits a decision
    com_falhas          everything decided, but some photos failed
    concluido           everything decided, no failures
    """
    status = BatchStatus(batch.status)
    if status is BatchStatus.RASCUNHO:
        return "rascunho"
    if status is not BatchStatus.PRONTO:
        return "processando"
    states = [PhotoStatus(s) for s in states]
    if any(s is PhotoStatus.AGUARDANDO_DECISAO for s in states):
        return "aguardando_revisao"
    if any(s is PhotoStatus.FALHOU for s in states):
        return "com_falhas"
    return "concluido"


def _imovel(batch: Batch) -> Optional[dict[str, Any]]:
    if not batch.imovel_codigo:
        return None
    return {"org_id": str(batch.imovel_org_id), "codigo": batch.imovel_codigo}


def lote_resumo_out(batch: Batch, states: list[PhotoStatus]) -> dict[str, Any]:
    """FE `LoteResumo` (+ `status`, the raw batch state)."""
    return {
        "id": str(batch.id),
        "nome": batch.nome,
        "criado_em": _iso(batch.created_at),
        "imovel": _imovel(batch),
        "velocidade": _v(batch.velocidade),
        "estado_agregado": estado_agregado(batch, states),
        "total_fotos": len(states),
        "fotos_decididas": sum(1 for s in states if PhotoStatus(s) in _DECIDED),
        "status": _v(batch.status),
    }


def lote_detalhe_out(batch: Batch, photos: list[Photo], fotos: list[dict[str, Any]]) -> dict[str, Any]:
    """FE `LoteDetalhe` (+ the `LoteResumo` aggregates and timestamps)."""
    return {
        **lote_resumo_out(batch, [PhotoStatus(p.status) for p in photos]),
        "submetido_em": _iso(batch.submetido_at),
        "pronto_em": _iso(batch.pronto_at),
        "fotos": fotos,
    }


def foto_revisao_out(
    photo: Photo,
    *,
    url_antes: Optional[str],
    url_depois: Optional[str],
    decision: Optional[ReviewDecision],
    evaluation: Optional[Evaluation] = None,
    include_verdict: bool = False,
) -> dict[str, Any]:
    """FE `FotoRevisao` (+ `ordem`, `tentativas`, `vista_codigo`)."""
    out: dict[str, Any] = {
        "id": str(photo.id),
        "ordem": photo.ordem,
        "url_antes": url_antes,
        "url_depois": url_depois,
        "comodo": None,
        "estado": _v(photo.status),
        "falha_motivo": photo.falha_motivo,
        "decisao": _v(decision.decisao) if decision else None,
        "comentario": decision.comentario if decision else None,
        "tentativas": photo.tentativas,
        "vista_codigo": photo.vista_codigo,
    }
    if include_verdict:
        out["avaliacao"] = (
            {
                "veredito": _v(evaluation.recomendacao),
                "score": float(evaluation.score),
                "motivo": evaluation.motivo or "",
            }
            if evaluation is not None
            else None
        )
    return out


def org_configuracoes_out(settings: OrgSettings, platform: PlatformSettings) -> dict[str, Any]:
    """FE `OrgConfiguracoes` (+ org_id, the raw override, notificacoes, limites).

    `velocidade_padrao` is the EFFECTIVE speed: the org override when set,
    else the platform default."""
    effective = settings.velocidade_override or platform.velocidade_default
    return {
        "tipos_edicao_ativos": [_v(t) for t in settings.tipos_edicao_ativos],
        "modelo_editor_imagem": settings.modelo_editor_id,
        "velocidade_padrao": _v(effective),
        "org_id": str(settings.org_id),
        "segue_padrao_plataforma": settings.velocidade_override is None,
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
        "limite_pares_referencia": settings.limite_pares_referencia or None,
    }


def referencia_out(
    pair: ReferencePair, *, antes_url: Optional[str], depois_url: Optional[str]
) -> dict[str, Any]:
    """FE `ReferenciaPar` (+ `criado_em`, `criado_por`). The stored
    `antes_url`/`depois_url` are PRIVATE bucket keys; the wire carries
    short-lived signed URLs in their place, never the key."""
    return {
        "id": str(pair.id),
        "antes_url": antes_url,
        "depois_url": depois_url,
        "comodo": _v(pair.comodo),
        "tipos_edicao": [_v(t) for t in pair.tipos_edicao],
        "nota": pair.nota,
        "arquivada_em": _iso(pair.arquivado_em),
        "criado_em": _iso(pair.created_at),
        "criado_por": str(pair.criado_por) if pair.criado_por else None,
    }


def guia_origem(guide: StyleGuide) -> str:
    """How a version came to be — derived from the immutable row:
    `ia` (builder: no author) · `restaurada` (an author cloned an older
    version) · `manual` (an author wrote it)."""
    if not guide.criado_por:
        return "ia"
    return "restaurada" if guide.gerado_de_versao is not None else "manual"


def guia_out(guide: StyleGuide) -> dict[str, Any]:
    """FE `GuiaEstiloVersao`."""
    return {
        "id": str(guide.id),
        "versao": guide.versao,
        "status": _v(guide.status),
        "texto": guide.texto,
        "sha256": guide.sha256,
        "gerado_de_versao": guide.gerado_de_versao,
        "origem": guia_origem(guide),
        "criado_por": str(guide.criado_por) if guide.criado_por else None,
        "criado_em": _iso(guide.created_at),
        "ativado_por": str(guide.ativado_por) if guide.ativado_por else None,
        "ativado_em": _iso(guide.ativado_em),
    }


def modelo_out(entry: Any) -> dict[str, Any]:
    """FE `ModeloCatalogoItem`. Live metrics and the AI-written notes are
    the model-notes slice (W8) — `null` until then, which the FE type
    already allows."""
    return {
        "id": entry.id,
        "nome": entry.label,
        "versao": f"{entry.id}{entry.snapshot}" if entry.snapshot else entry.id,
        "tag_performance": None,
        "suporta_batch": bool(entry.supports_batch),
        "nota_recomendacao": None,
        "metricas": None,
    }


def page_out(items: list[Any], *, page: int, page_size: int, total: int) -> dict[str, Any]:
    return {"items": items, "page": page, "page_size": page_size, "total": total}
