"""Photo-editing engine — vocabulary, state machines, records, dedupe keys.

Pure domain: no IO, no clock read, no product import. Every enum value
here is the exact literal the consumer's SQL ``CHECK`` constraints carry
(social-wiring migrations 123-126 are the reference shape — see
``KB § PATTERNS/backend/photo-editing-seed.md``), so a record built from
these types round-trips through a Postgres row without translation.

Identifiers are English; values are the pt-BR literals the product
stores and shows (the contract's convention: "All pt-BR in UI copy; all
identifiers English").
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


class PhotoStatus(str, Enum):
    """Per-photo pipeline state (contract §3 state machine)."""

    RECEBIDA = "recebida"
    NORMALIZANDO = "normalizando"
    PRONTA = "pronta"
    EDITANDO = "editando"
    # Econômico-only (Batch API). Present because the SQL CHECK carries it;
    # no engine path enters it in R1 — see NOC-REMEDIATE[image-edit-batch-c8]
    # in `noctusai_lib.integrations.image_edit`.
    EM_LOTE_OPENAI = "em_lote_openai"
    EDITADA = "editada"
    AVALIANDO = "avaliando"
    AGUARDANDO_DECISAO = "aguardando_decisao"
    APROVADA = "aprovada"
    REJEITADA = "rejeitada"
    FALHOU = "falhou"


class BatchStatus(str, Enum):
    """Per-batch (lote) state."""

    RASCUNHO = "rascunho"
    SUBMETIDO = "submetido"
    PROCESSANDO = "processando"
    PRONTO = "pronto"


class EditType(str, Enum):
    """The fixed edit-type vocabulary the owner defined."""

    COR_LUZ = "cor_luz"
    CEU = "ceu"
    DECLUTTER = "declutter"
    STAGING_VIRTUAL = "staging_virtual"


class Speed(str, Enum):
    URGENTE = "urgente"
    ECONOMICO = "economico"


class Decision(str, Enum):
    APROVAR = "aprovar"
    REJEITAR = "rejeitar"


class RuleStatus(str, Enum):
    PROPOSTA = "proposta"
    APROVADA = "aprovada"
    REJEITADA = "rejeitada"


class GuideStatus(str, Enum):
    RASCUNHO = "rascunho"
    ATIVA = "ativa"
    SUBSTITUIDA = "substituida"


class Room(str, Enum):
    """Fixed room/area tag list for reference pairs."""

    SALA = "sala"
    QUARTO = "quarto"
    COZINHA = "cozinha"
    BANHEIRO = "banheiro"
    AREA_EXTERNA = "area_externa"
    FACHADA = "fachada"
    VARANDA = "varanda"
    ESCRITORIO = "escritorio"
    OUTRO = "outro"


class JobType:
    """Job-type names the engine registers on `domain.jobs.Worker`.

    `fotos.poll_openai_batch` (Econômico) is deliberately absent — C8.
    """

    INGEST = "fotos.ingest"
    SUBMIT_LOTE = "fotos.submit_lote"
    EDIT = "fotos.edit"
    AVALIAR = "fotos.avaliar"
    LOTE_PRONTO = "fotos.lote_pronto"
    REGEN_GUIA = "fotos.regen_guia"
    PROPOR_REGRAS = "fotos.propor_regras"
    FX_BACKFILL = "fotos.fx_backfill"

    ALL: tuple[str, ...] = (
        INGEST,
        SUBMIT_LOTE,
        EDIT,
        AVALIAR,
        LOTE_PRONTO,
        REGEN_GUIA,
        PROPOR_REGRAS,
        FX_BACKFILL,
    )


# Role vocabulary (contract §1). Server-side only — never read from SSO
# metadata.
AGENCY_ADMIN_ROLES: frozenset[str] = frozenset({"owner", "admin", "manager"})
CORRETOR_ROLES: frozenset[str] = frozenset({"member", "corretor"})
# The named grant in Core `public.user_permission_grants` (Core 046),
# checked through `noctusai_lib.domain.permissions`.
PHOTO_CURATOR_PERMISSION = "photo_curator"

# Owner limits (plan §1): 100 photos per batch, 25 MB per file.
MAX_PHOTOS_PER_BATCH = 100
MAX_BYTES_PER_PHOTO = 25 * 1024 * 1024


# ---------------------------------------------------------------------------
# Photo state machine
# ---------------------------------------------------------------------------

#: Photo states the batch-readiness check treats as "processing finished".
PROCESSING_DONE_STATES: frozenset[PhotoStatus] = frozenset(
    {
        PhotoStatus.AGUARDANDO_DECISAO,
        PhotoStatus.APROVADA,
        PhotoStatus.REJEITADA,
        PhotoStatus.FALHOU,
    }
)

#: States a review decision may be recorded from — decisions are always
#: changeable, including after download (plan §1).
DECIDABLE_STATES: frozenset[PhotoStatus] = frozenset(
    {PhotoStatus.AGUARDANDO_DECISAO, PhotoStatus.APROVADA, PhotoStatus.REJEITADA}
)

_P = PhotoStatus
_LEGAL_PHOTO_TRANSITIONS: frozenset[tuple[PhotoStatus, PhotoStatus]] = frozenset(
    {
        (_P.RECEBIDA, _P.NORMALIZANDO),
        (_P.NORMALIZANDO, _P.PRONTA),
        (_P.PRONTA, _P.EDITANDO),
        (_P.PRONTA, _P.EM_LOTE_OPENAI),
        (_P.EDITANDO, _P.EDITADA),
        (_P.EM_LOTE_OPENAI, _P.EDITADA),
        (_P.EDITADA, _P.AVALIANDO),
        (_P.AVALIANDO, _P.AGUARDANDO_DECISAO),
        (_P.AGUARDANDO_DECISAO, _P.APROVADA),
        (_P.AGUARDANDO_DECISAO, _P.REJEITADA),
        # Decisions are always changeable.
        (_P.APROVADA, _P.REJEITADA),
        (_P.REJEITADA, _P.APROVADA),
        # Manual retry of a failed photo: back to where its work resumes.
        (_P.FALHOU, _P.RECEBIDA),
        (_P.FALHOU, _P.PRONTA),
    }
    # Any in-flight state may fail (after the one automatic retry).
    | {
        (s, _P.FALHOU)
        for s in (
            _P.RECEBIDA,
            _P.NORMALIZANDO,
            _P.PRONTA,
            _P.EDITANDO,
            _P.EM_LOTE_OPENAI,
            _P.EDITADA,
            _P.AVALIANDO,
        )
    }
)


def can_transition(current: PhotoStatus, target: PhotoStatus) -> bool:
    """True iff ``current -> target`` is a legal photo transition."""
    return (PhotoStatus(current), PhotoStatus(target)) in _LEGAL_PHOTO_TRANSITIONS


def sources_for(target: PhotoStatus) -> frozenset[PhotoStatus]:
    """Every state a photo may legally enter ``target`` from.

    Repositories use this as the compare-and-set guard of
    ``transition_photo`` so an illegal transition is refused at write time.
    """
    target = PhotoStatus(target)
    return frozenset(s for (s, t) in _LEGAL_PHOTO_TRANSITIONS if t is target)


class IllegalTransitionError(ValueError):
    """A photo transition not in the legal set was requested."""


class PoolFullError(RuntimeError):
    """The reference pool already holds ``limite_pares_referencia`` active
    pairs — uploads are blocked until one is archived or the limit raised.

    Raised by the pool entry point (``pool.add_reference_pair``) and by a
    repository whose storage enforces the limit at write time (the
    Supabase implementation maps the migration-129 trigger's error here)."""

    code = "pool_cheio"


# ---------------------------------------------------------------------------
# Records (one per consumer table; field names == column names)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrgSettings:
    org_id: str
    tipos_edicao_ativos: tuple[EditType, ...] = ()
    modelo_editor_id: str | None = None
    velocidade_override: Speed | None = None
    limite_fotos_por_lote: int = MAX_PHOTOS_PER_BATCH
    limite_bytes_por_foto: int = MAX_BYTES_PER_PHOTO
    notificacoes_ativas: bool = True


@dataclass(frozen=True)
class PlatformSettings:
    velocidade_default: Speed = Speed.URGENTE
    notificacoes_globais_ativas: bool = True
    preco_storage_gb_mes_usd: Decimal | None = None
    #: Reference-pool size limit, counted in PAIRS. ``None`` or ``0`` =
    #: unlimited; archived pairs never count (contract §5).
    limite_pares_referencia: int | None = None


@dataclass(frozen=True)
class Batch:
    id: str
    org_id: str
    nome: str
    criado_por: str
    origem: str  # 'upload' | 'vista'
    velocidade: Speed
    status: BatchStatus = BatchStatus.RASCUNHO
    imovel_org_id: str | None = None
    imovel_codigo: str | None = None
    guia_efetivo_id: str | None = None
    guia_efetivo_sha256: str | None = None
    modelo_editor_id: str | None = None
    submetido_at: datetime | None = None
    pronto_at: datetime | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class Photo:
    id: str
    org_id: str
    lote_id: str
    ordem: int
    storage_path_original: str
    status: PhotoStatus = PhotoStatus.RECEBIDA
    storage_path_editada: str | None = None
    vista_codigo: str | None = None
    largura_original: int | None = None
    altura_original: int | None = None
    tentativas: int = 0
    falha_motivo: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class PhotoEvent:
    org_id: str
    lote_id: str
    tipo: str
    foto_id: str | None = None
    estado_de: str | None = None
    estado_para: str | None = None
    detalhe: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass(frozen=True)
class EditAttempt:
    id: str
    org_id: str
    lote_id: str
    foto_id: str
    tentativa: int
    tipos_edicao: tuple[EditType, ...]
    modelo_id: str
    velocidade: Speed
    status: str = "pendente"  # 'pendente' | 'concluida' | 'falhou'
    modelo_versao: str | None = None
    erro: str | None = None
    llm_usage_id: int | None = None
    created_at: datetime | None = None
    concluida_at: datetime | None = None


@dataclass(frozen=True)
class Evaluation:
    id: str
    org_id: str
    lote_id: str
    foto_id: str
    recomendacao: Decision
    score: Decimal
    modelo_id: str
    edicao_id: str | None = None
    motivo: str | None = None
    modelo_versao: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class ReviewDecision:
    id: str
    org_id: str
    lote_id: str
    foto_id: str
    decisao: Decision
    decidido_por: str
    comentario: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class DatasetRecord:
    """One append-only training-ready row (``fotos_dataset``)."""

    org_id: str
    lote_id: str
    foto_id: str
    decisao_id: str
    tipos_edicao: tuple[EditType, ...]
    guia_efetivo_sha256: str
    decisao_final: Decision
    storage_path_original: str
    storage_path_editada: str | None = None
    avaliacao_score: Decimal | None = None
    avaliacao_recomendacao: Decision | None = None
    comentario: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class ReferencePair:
    id: str
    antes_url: str
    depois_url: str
    comodo: Room
    criado_por: str
    tipos_edicao: tuple[EditType, ...] = ()
    nota: str | None = None
    arquivado_em: datetime | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class StyleGuide:
    id: str
    versao: int
    texto: str
    sha256: str
    status: GuideStatus = GuideStatus.RASCUNHO
    gerado_de_versao: int | None = None
    criado_por: str | None = None
    ativado_por: str | None = None
    ativado_em: datetime | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class OrgRule:
    id: str
    org_id: str
    texto: str
    status: RuleStatus = RuleStatus.PROPOSTA
    origem_comentarios: tuple[dict[str, Any], ...] = ()
    decidido_por: str | None = None
    decidido_em: datetime | None = None
    override_platform_admin: bool = False
    created_at: datetime | None = None


@dataclass(frozen=True)
class RuleSet:
    """Versioned snapshot of an org's approved rules (``fotos_conjuntos_regras``)."""

    id: str
    org_id: str
    versao: int
    regra_ids: tuple[str, ...]
    sha256: str
    created_at: datetime | None = None


@dataclass(frozen=True)
class EffectiveGuide:
    """Company guide + org rules, frozen (``fotos_guias_efetivos``)."""

    id: str
    org_id: str
    guia_estilo_id: str
    texto: str
    sha256: str
    conjunto_regras_id: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class ProposalCursor:
    org_id: str
    ultima_decisao_id: str | None = None
    ultima_execucao_em: datetime | None = None
    rejeicoes_desde_ultima: int = 0


@dataclass(frozen=True)
class LlmUsageRow:
    """One ``llm_usage`` row (the 122 shape, incl. image tokens)."""

    provider: str
    model: str
    operation: str
    cost_estimate_usd: Decimal
    org_id: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    image_input_tokens: int | None = None
    image_output_tokens: int | None = None
    model_version: str | None = None
    batch: bool = False
    at: datetime | None = None


@dataclass(frozen=True)
class CostLedgerRow:
    """One Core ``public.cost_ledger`` row (Core 046).

    The three legal shapes mirror the table's CHECK exactly — see
    ``costs.build_cost_row``, the only constructor the engine uses.
    """

    org_id: str
    category: str
    amount_native: Decimal
    currency: str
    fx_pending: bool
    step: str | None = None
    reference_type: str | None = None
    reference_id: str | None = None
    fx_rate: Decimal | None = None
    fx_quote_date: Any | None = None  # datetime.date
    amount_brl: Decimal | None = None
    id: int | None = None
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# Dedupe keys — one pure function per job type
# ---------------------------------------------------------------------------


def dedupe_ingest(foto_id: str, tentativas: int = 0) -> str:
    return f"{JobType.INGEST}:{foto_id}:{tentativas}"


def dedupe_submit(lote_id: str) -> str:
    return f"{JobType.SUBMIT_LOTE}:{lote_id}"


def dedupe_edit(foto_id: str, tentativas: int) -> str:
    """One edit job per (photo, attempt round).

    ``tentativas`` is the photo's counter at enqueue time: the automatic
    retry re-runs the SAME job (same key), a manual retry happens after the
    counter moved, so it gets a fresh key.
    """
    return f"{JobType.EDIT}:{foto_id}:{tentativas}"


def dedupe_avaliar(foto_id: str, edicao_id: str) -> str:
    return f"{JobType.AVALIAR}:{foto_id}:{edicao_id}"


def batch_state_signature(photos: list[Photo]) -> str:
    """Stable digest of every photo's (id, status, tentativas).

    Each photo completion changes it, so the LAST completion of a round
    always produces a fresh `fotos.lote_pronto` key, while a duplicate
    enqueue from the same state is a no-op.
    """
    parts = sorted(f"{p.id}={PhotoStatus(p.status).value}/{p.tentativas}" for p in photos)
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def dedupe_lote_pronto(lote_id: str, signature: str) -> str:
    return f"{JobType.LOTE_PRONTO}:{lote_id}:{signature}"


def debounce_bucket(at: datetime, window_seconds: int) -> int:
    """Integer window index for a trailing debounce."""
    if window_seconds <= 0:
        raise ValueError(f"window_seconds must be > 0, got {window_seconds}")
    return int(at.timestamp()) // window_seconds


def dedupe_regen_guia(bucket: int) -> str:
    return f"{JobType.REGEN_GUIA}:{bucket}"


def dedupe_regen_guia_manual(bucket: int) -> str:
    """Manual "regenerate" button: one job per short window, so a double
    click never enqueues two builder calls."""
    return f"{JobType.REGEN_GUIA}:manual:{bucket}"


def dedupe_propor_regras(org_id: str, bucket: int) -> str:
    return f"{JobType.PROPOR_REGRAS}:{org_id}:{bucket}"


def dedupe_fx_backfill(day_iso: str) -> str:
    return f"{JobType.FX_BACKFILL}:{day_iso}"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = [
    "AGENCY_ADMIN_ROLES",
    "Batch",
    "BatchStatus",
    "CORRETOR_ROLES",
    "CostLedgerRow",
    "DECIDABLE_STATES",
    "DatasetRecord",
    "Decision",
    "EditAttempt",
    "EditType",
    "EffectiveGuide",
    "Evaluation",
    "GuideStatus",
    "IllegalTransitionError",
    "JobType",
    "LlmUsageRow",
    "MAX_BYTES_PER_PHOTO",
    "MAX_PHOTOS_PER_BATCH",
    "OrgRule",
    "OrgSettings",
    "PHOTO_CURATOR_PERMISSION",
    "PROCESSING_DONE_STATES",
    "Photo",
    "PhotoEvent",
    "PhotoStatus",
    "PlatformSettings",
    "PoolFullError",
    "ProposalCursor",
    "ReferencePair",
    "ReviewDecision",
    "Room",
    "RuleSet",
    "RuleStatus",
    "Speed",
    "StyleGuide",
    "batch_state_signature",
    "can_transition",
    "debounce_bucket",
    "dedupe_avaliar",
    "dedupe_edit",
    "dedupe_fx_backfill",
    "dedupe_ingest",
    "dedupe_lote_pronto",
    "dedupe_propor_regras",
    "dedupe_regen_guia",
    "dedupe_regen_guia_manual",
    "dedupe_submit",
    "sha256_text",
    "sources_for",
]
