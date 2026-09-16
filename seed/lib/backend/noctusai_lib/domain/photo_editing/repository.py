"""Persistence seam for the photo-editing engine.

``PhotoEditingRepository`` Protocol + ``InMemoryPhotoEditingRepository``
(tests/dev) + ``SupabasePhotoEditingRepository`` (Postgres via the
Supabase client) + ``make_photo_editing_repository`` factory — the
canonical Protocol+Fake+Real+factory shape
(``KB § PATTERNS/backend/seed-fake-real-adapter.md``).

The Supabase implementation targets the reference tables of the first
consumer (social-wiring migrations 123-126 in the product schema, plus
Core 046's ``public.cost_ledger``). Table names are the defaults below;
the schema is a constructor argument, so a second consumer (Phase 2)
ships the same tables under its own schema without touching this file.

Every photo status change goes through ``transition_photo``: a
read-then-compare-and-set that refuses an illegal transition
(``types.IllegalTransitionError``), returns ``None`` when a concurrent
writer moved the row first, and appends the ``fotos_eventos`` row the
throughput charts read.
"""

from __future__ import annotations

import dataclasses
import itertools
from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from noctusai_lib.domain.photo_editing.types import (
    Batch,
    BatchStatus,
    CostLedgerRow,
    DatasetRecord,
    Decision,
    EditAttempt,
    EditType,
    EffectiveGuide,
    Evaluation,
    GuideStatus,
    IllegalTransitionError,
    LlmUsageRow,
    OrgRule,
    OrgSettings,
    Photo,
    PhotoEvent,
    PhotoStatus,
    PlatformSettings,
    ProposalCursor,
    ReferencePair,
    ReviewDecision,
    Room,
    RuleSet,
    RuleStatus,
    Speed,
    StyleGuide,
    can_transition,
)

_BATCH_MUTABLE = frozenset(
    {
        "status",
        "velocidade",
        "guia_efetivo_id",
        "guia_efetivo_sha256",
        "modelo_editor_id",
        "submetido_at",
        "pronto_at",
    }
)
# `status` is deliberately absent: photo status only moves via
# `transition_photo`.
_PHOTO_MUTABLE = frozenset(
    {
        "storage_path_original",
        "storage_path_editada",
        "largura_original",
        "altura_original",
        "falha_motivo",
    }
)
_EDIT_MUTABLE = frozenset(
    {"status", "erro", "llm_usage_id", "modelo_versao", "concluida_at"}
)


def _check_fields(kind: str, changes: dict[str, Any], allowed: frozenset[str]) -> None:
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"{kind}: fields not updatable: {sorted(unknown)}")


class RepositoryError(RuntimeError):
    """A write the engine relies on did not return the row it wrote."""


@runtime_checkable
class PhotoEditingRepository(Protocol):
    # --- settings -----------------------------------------------------
    async def get_org_settings(self, org_id: str) -> OrgSettings | None: ...
    async def get_platform_settings(self) -> PlatformSettings: ...

    # --- batches ------------------------------------------------------
    async def create_batch(
        self,
        *,
        org_id: str,
        nome: str,
        criado_por: str,
        origem: str,
        velocidade: Speed,
        imovel_org_id: str | None = None,
        imovel_codigo: str | None = None,
    ) -> Batch: ...
    async def get_batch(self, lote_id: str) -> Batch | None: ...
    async def update_batch(self, lote_id: str, **changes: Any) -> Batch: ...

    # --- photos -------------------------------------------------------
    async def add_photo(
        self,
        *,
        org_id: str,
        lote_id: str,
        ordem: int,
        storage_path_original: str,
        vista_codigo: str | None = None,
    ) -> Photo: ...
    async def get_photo(self, foto_id: str) -> Photo | None: ...
    async def list_photos(self, lote_id: str) -> list[Photo]: ...
    async def update_photo(self, foto_id: str, **changes: Any) -> Photo: ...
    async def transition_photo(
        self,
        foto_id: str,
        target: PhotoStatus,
        *,
        falha_motivo: str | None = None,
        increment_tentativas: bool = False,
        event_tipo: str = "transicao_estado",
        detalhe: dict[str, Any] | None = None,
    ) -> Photo | None: ...
    async def add_event(self, event: PhotoEvent) -> None: ...
    async def list_events(self, lote_id: str) -> list[PhotoEvent]: ...

    # --- edits / evaluations / decisions ------------------------------
    async def create_edit(
        self,
        *,
        org_id: str,
        lote_id: str,
        foto_id: str,
        tentativa: int,
        tipos_edicao: tuple[EditType, ...],
        modelo_id: str,
        velocidade: Speed,
    ) -> EditAttempt: ...
    async def update_edit(self, edicao_id: str, **changes: Any) -> EditAttempt: ...
    async def get_edit(self, edicao_id: str) -> EditAttempt | None: ...
    async def latest_edit(self, foto_id: str) -> EditAttempt | None: ...
    async def add_evaluation(
        self,
        *,
        org_id: str,
        lote_id: str,
        foto_id: str,
        edicao_id: str | None,
        recomendacao: Decision,
        score: Decimal,
        motivo: str | None,
        modelo_id: str,
        modelo_versao: str | None,
    ) -> Evaluation: ...
    async def latest_evaluation(self, foto_id: str) -> Evaluation | None: ...
    async def add_decision(
        self,
        *,
        org_id: str,
        lote_id: str,
        foto_id: str,
        decisao: Decision,
        comentario: str | None,
        decidido_por: str,
    ) -> ReviewDecision: ...
    async def latest_decisions(self, lote_id: str) -> dict[str, ReviewDecision]: ...
    async def list_rejections(
        self, org_id: str, *, after: datetime | None = None, limit: int = 200
    ) -> list[ReviewDecision]: ...
    async def add_dataset_record(self, record: DatasetRecord) -> None: ...

    # --- pool / guides / rules ----------------------------------------
    async def list_active_references(self, *, limit: int) -> list[ReferencePair]: ...
    async def last_pool_change_at(self) -> datetime | None: ...
    async def get_active_guide(self) -> StyleGuide | None: ...
    async def get_guide(self, versao: int) -> StyleGuide | None: ...
    async def latest_guide_version(self) -> int: ...
    async def create_guide(
        self,
        *,
        versao: int,
        texto: str,
        sha256: str,
        gerado_de_versao: int | None,
        criado_por: str | None,
    ) -> StyleGuide: ...
    async def activate_guide(
        self, versao: int, *, ativado_por: str, at: datetime
    ) -> StyleGuide: ...
    async def add_rule(
        self, *, org_id: str, texto: str, origem_comentarios: tuple[dict[str, Any], ...]
    ) -> OrgRule: ...
    async def get_rule(self, regra_id: str) -> OrgRule | None: ...
    async def list_rules(
        self, org_id: str, *, status: RuleStatus | None = None
    ) -> list[OrgRule]: ...
    async def update_rule(
        self,
        regra_id: str,
        *,
        status: RuleStatus,
        decidido_por: str,
        decidido_em: datetime,
        override_platform_admin: bool,
    ) -> OrgRule: ...
    async def latest_rule_set(self, org_id: str) -> RuleSet | None: ...
    async def create_rule_set(
        self, *, org_id: str, versao: int, regra_ids: tuple[str, ...], sha256: str
    ) -> RuleSet: ...
    async def get_or_create_effective_guide(
        self,
        *,
        org_id: str,
        guia_estilo_id: str,
        conjunto_regras_id: str | None,
        texto: str,
        sha256: str,
    ) -> EffectiveGuide: ...
    async def get_effective_guide(self, guia_efetivo_id: str) -> EffectiveGuide | None: ...
    async def get_cursor(self, org_id: str) -> ProposalCursor | None: ...
    async def save_cursor(self, cursor: ProposalCursor) -> None: ...

    # --- costs --------------------------------------------------------
    async def add_llm_usage(self, row: LlmUsageRow) -> int: ...
    async def add_cost(self, row: CostLedgerRow) -> int: ...
    async def list_fx_pending(self, *, limit: int = 200) -> list[CostLedgerRow]: ...
    async def resolve_fx(
        self, cost_id: int, *, fx_rate: Decimal, fx_quote_date: date, amount_brl: Decimal
    ) -> None: ...


# ---------------------------------------------------------------------------
# In-memory implementation
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryPhotoEditingRepository:
    """Deterministic in-memory repository for dev + tests.

    Ids are ``"<kind>-<n>"`` (stable across runs); ``now`` is injectable.
    Seed settings / pool / guides with the ``seed_*`` helpers — they are
    test-arrangement conveniences, not Protocol methods.
    """

    def __init__(self, *, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or _utcnow
        self._seq = itertools.count(1)
        self.org_settings: dict[str, OrgSettings] = {}
        self.platform_settings = PlatformSettings()
        self.batches: dict[str, Batch] = {}
        self.photos: dict[str, Photo] = {}
        self.events: list[PhotoEvent] = []
        self.edits: dict[str, EditAttempt] = {}
        self.evaluations: list[Evaluation] = []
        self.decisions: list[ReviewDecision] = []
        self.dataset: list[DatasetRecord] = []
        self.references: dict[str, ReferencePair] = {}
        self.guides: dict[int, StyleGuide] = {}
        self.rules: dict[str, OrgRule] = {}
        self.rule_sets: list[RuleSet] = []
        self.effective_guides: dict[str, EffectiveGuide] = {}
        self.cursors: dict[str, ProposalCursor] = {}
        self.llm_usage: dict[int, LlmUsageRow] = {}
        self.costs: dict[int, CostLedgerRow] = {}

    def _id(self, kind: str) -> str:
        return f"{kind}-{next(self._seq)}"

    # --- arrangement helpers ------------------------------------------
    def seed_org_settings(self, settings: OrgSettings) -> None:
        self.org_settings[settings.org_id] = settings

    def seed_reference(self, pair: ReferencePair) -> None:
        if pair.created_at is None:
            pair = dataclasses.replace(pair, created_at=self._now())
        self.references[pair.id] = pair

    # --- settings -----------------------------------------------------
    async def get_org_settings(self, org_id: str) -> OrgSettings | None:
        return self.org_settings.get(org_id)

    async def get_platform_settings(self) -> PlatformSettings:
        return self.platform_settings

    # --- batches ------------------------------------------------------
    async def create_batch(
        self,
        *,
        org_id: str,
        nome: str,
        criado_por: str,
        origem: str,
        velocidade: Speed,
        imovel_org_id: str | None = None,
        imovel_codigo: str | None = None,
    ) -> Batch:
        batch = Batch(
            id=self._id("lote"),
            org_id=org_id,
            nome=nome,
            criado_por=criado_por,
            origem=origem,
            velocidade=Speed(velocidade),
            imovel_org_id=imovel_org_id,
            imovel_codigo=imovel_codigo,
            created_at=self._now(),
        )
        self.batches[batch.id] = batch
        return batch

    async def get_batch(self, lote_id: str) -> Batch | None:
        return self.batches.get(lote_id)

    async def update_batch(self, lote_id: str, **changes: Any) -> Batch:
        _check_fields("update_batch", changes, _BATCH_MUTABLE)
        updated = dataclasses.replace(self.batches[lote_id], **changes)
        self.batches[lote_id] = updated
        return updated

    # --- photos -------------------------------------------------------
    async def add_photo(
        self,
        *,
        org_id: str,
        lote_id: str,
        ordem: int,
        storage_path_original: str,
        vista_codigo: str | None = None,
    ) -> Photo:
        if any(p.lote_id == lote_id and p.ordem == ordem for p in self.photos.values()):
            raise ValueError(f"duplicate ordem {ordem} in lote {lote_id}")
        photo = Photo(
            id=self._id("foto"),
            org_id=org_id,
            lote_id=lote_id,
            ordem=ordem,
            storage_path_original=storage_path_original,
            vista_codigo=vista_codigo,
            created_at=self._now(),
        )
        self.photos[photo.id] = photo
        return photo

    async def get_photo(self, foto_id: str) -> Photo | None:
        return self.photos.get(foto_id)

    async def list_photos(self, lote_id: str) -> list[Photo]:
        return sorted(
            (p for p in self.photos.values() if p.lote_id == lote_id),
            key=lambda p: p.ordem,
        )

    async def update_photo(self, foto_id: str, **changes: Any) -> Photo:
        _check_fields("update_photo", changes, _PHOTO_MUTABLE)
        updated = dataclasses.replace(self.photos[foto_id], **changes)
        self.photos[foto_id] = updated
        return updated

    async def transition_photo(
        self,
        foto_id: str,
        target: PhotoStatus,
        *,
        falha_motivo: str | None = None,
        increment_tentativas: bool = False,
        event_tipo: str = "transicao_estado",
        detalhe: dict[str, Any] | None = None,
    ) -> Photo | None:
        current = self.photos.get(foto_id)
        if current is None:
            raise KeyError(f"photo not found: {foto_id}")
        target = PhotoStatus(target)
        if not can_transition(current.status, target):
            raise IllegalTransitionError(
                f"photo {foto_id}: {current.status.value} -> {target.value}"
            )
        updated = dataclasses.replace(
            current,
            status=target,
            falha_motivo=falha_motivo,
            tentativas=current.tentativas + (1 if increment_tentativas else 0),
        )
        self.photos[foto_id] = updated
        await self.add_event(
            PhotoEvent(
                org_id=current.org_id,
                lote_id=current.lote_id,
                foto_id=foto_id,
                tipo=event_tipo,
                estado_de=current.status.value,
                estado_para=target.value,
                detalhe=dict(detalhe or {}),
            )
        )
        return updated

    async def add_event(self, event: PhotoEvent) -> None:
        if event.created_at is None:
            event = dataclasses.replace(event, created_at=self._now())
        self.events.append(event)

    async def list_events(self, lote_id: str) -> list[PhotoEvent]:
        return [e for e in self.events if e.lote_id == lote_id]

    # --- edits / evaluations / decisions ------------------------------
    async def create_edit(
        self,
        *,
        org_id: str,
        lote_id: str,
        foto_id: str,
        tentativa: int,
        tipos_edicao: tuple[EditType, ...],
        modelo_id: str,
        velocidade: Speed,
    ) -> EditAttempt:
        edit = EditAttempt(
            id=self._id("edicao"),
            org_id=org_id,
            lote_id=lote_id,
            foto_id=foto_id,
            tentativa=tentativa,
            tipos_edicao=tuple(EditType(t) for t in tipos_edicao),
            modelo_id=modelo_id,
            velocidade=Speed(velocidade),
            created_at=self._now(),
        )
        self.edits[edit.id] = edit
        return edit

    async def update_edit(self, edicao_id: str, **changes: Any) -> EditAttempt:
        _check_fields("update_edit", changes, _EDIT_MUTABLE)
        updated = dataclasses.replace(self.edits[edicao_id], **changes)
        self.edits[edicao_id] = updated
        return updated

    async def get_edit(self, edicao_id: str) -> EditAttempt | None:
        return self.edits.get(edicao_id)

    async def latest_edit(self, foto_id: str) -> EditAttempt | None:
        mine = [e for e in self.edits.values() if e.foto_id == foto_id]
        return mine[-1] if mine else None

    async def add_evaluation(
        self,
        *,
        org_id: str,
        lote_id: str,
        foto_id: str,
        edicao_id: str | None,
        recomendacao: Decision,
        score: Decimal,
        motivo: str | None,
        modelo_id: str,
        modelo_versao: str | None,
    ) -> Evaluation:
        ev = Evaluation(
            id=self._id("avaliacao"),
            org_id=org_id,
            lote_id=lote_id,
            foto_id=foto_id,
            edicao_id=edicao_id,
            recomendacao=Decision(recomendacao),
            score=score,
            motivo=motivo,
            modelo_id=modelo_id,
            modelo_versao=modelo_versao,
            created_at=self._now(),
        )
        self.evaluations.append(ev)
        return ev

    async def latest_evaluation(self, foto_id: str) -> Evaluation | None:
        mine = [e for e in self.evaluations if e.foto_id == foto_id]
        return mine[-1] if mine else None

    async def add_decision(
        self,
        *,
        org_id: str,
        lote_id: str,
        foto_id: str,
        decisao: Decision,
        comentario: str | None,
        decidido_por: str,
    ) -> ReviewDecision:
        d = ReviewDecision(
            id=self._id("decisao"),
            org_id=org_id,
            lote_id=lote_id,
            foto_id=foto_id,
            decisao=Decision(decisao),
            comentario=comentario,
            decidido_por=decidido_por,
            created_at=self._now(),
        )
        self.decisions.append(d)
        return d

    async def latest_decisions(self, lote_id: str) -> dict[str, ReviewDecision]:
        out: dict[str, ReviewDecision] = {}
        for d in self.decisions:  # insertion order == created order
            if d.lote_id == lote_id:
                out[d.foto_id] = d
        return out

    async def list_rejections(
        self, org_id: str, *, after: datetime | None = None, limit: int = 200
    ) -> list[ReviewDecision]:
        rows = [
            d
            for d in self.decisions
            if d.org_id == org_id
            and d.decisao is Decision.REJEITAR
            and d.comentario
            and (after is None or (d.created_at is not None and d.created_at > after))
        ]
        return rows[:limit]

    async def add_dataset_record(self, record: DatasetRecord) -> None:
        if record.created_at is None:
            record = dataclasses.replace(record, created_at=self._now())
        self.dataset.append(record)

    # --- pool / guides / rules ----------------------------------------
    async def list_active_references(self, *, limit: int) -> list[ReferencePair]:
        active = [r for r in self.references.values() if r.arquivado_em is None]
        active.sort(key=lambda r: (r.created_at or datetime.min, r.id), reverse=True)
        return active[:limit]

    async def last_pool_change_at(self) -> datetime | None:
        stamps = [
            s
            for r in self.references.values()
            for s in (r.created_at, r.arquivado_em)
            if s is not None
        ]
        return max(stamps) if stamps else None

    async def get_active_guide(self) -> StyleGuide | None:
        for g in self.guides.values():
            if g.status is GuideStatus.ATIVA:
                return g
        return None

    async def get_guide(self, versao: int) -> StyleGuide | None:
        return self.guides.get(versao)

    async def latest_guide_version(self) -> int:
        return max(self.guides, default=0)

    async def create_guide(
        self,
        *,
        versao: int,
        texto: str,
        sha256: str,
        gerado_de_versao: int | None,
        criado_por: str | None,
    ) -> StyleGuide:
        if versao in self.guides:
            raise ValueError(f"guide version {versao} already exists (versions are immutable)")
        guide = StyleGuide(
            id=self._id("guia"),
            versao=versao,
            texto=texto,
            sha256=sha256,
            gerado_de_versao=gerado_de_versao,
            criado_por=criado_por,
            created_at=self._now(),
        )
        self.guides[versao] = guide
        return guide

    async def activate_guide(
        self, versao: int, *, ativado_por: str, at: datetime
    ) -> StyleGuide:
        target = self.guides[versao]
        for v, g in list(self.guides.items()):
            if g.status is GuideStatus.ATIVA and v != versao:
                self.guides[v] = dataclasses.replace(g, status=GuideStatus.SUBSTITUIDA)
        activated = dataclasses.replace(
            target, status=GuideStatus.ATIVA, ativado_por=ativado_por, ativado_em=at
        )
        self.guides[versao] = activated
        return activated

    async def add_rule(
        self, *, org_id: str, texto: str, origem_comentarios: tuple[dict[str, Any], ...]
    ) -> OrgRule:
        rule = OrgRule(
            id=self._id("regra"),
            org_id=org_id,
            texto=texto,
            origem_comentarios=tuple(origem_comentarios),
            created_at=self._now(),
        )
        self.rules[rule.id] = rule
        return rule

    async def get_rule(self, regra_id: str) -> OrgRule | None:
        return self.rules.get(regra_id)

    async def list_rules(
        self, org_id: str, *, status: RuleStatus | None = None
    ) -> list[OrgRule]:
        return [
            r
            for r in self.rules.values()
            if r.org_id == org_id and (status is None or r.status is RuleStatus(status))
        ]

    async def update_rule(
        self,
        regra_id: str,
        *,
        status: RuleStatus,
        decidido_por: str,
        decidido_em: datetime,
        override_platform_admin: bool,
    ) -> OrgRule:
        updated = dataclasses.replace(
            self.rules[regra_id],
            status=RuleStatus(status),
            decidido_por=decidido_por,
            decidido_em=decidido_em,
            override_platform_admin=override_platform_admin,
        )
        self.rules[regra_id] = updated
        return updated

    async def latest_rule_set(self, org_id: str) -> RuleSet | None:
        mine = [s for s in self.rule_sets if s.org_id == org_id]
        return max(mine, key=lambda s: s.versao) if mine else None

    async def create_rule_set(
        self, *, org_id: str, versao: int, regra_ids: tuple[str, ...], sha256: str
    ) -> RuleSet:
        if any(s.org_id == org_id and s.versao == versao for s in self.rule_sets):
            raise ValueError(f"rule set v{versao} already exists for {org_id}")
        rs = RuleSet(
            id=self._id("conjunto"),
            org_id=org_id,
            versao=versao,
            regra_ids=tuple(regra_ids),
            sha256=sha256,
            created_at=self._now(),
        )
        self.rule_sets.append(rs)
        return rs

    async def get_or_create_effective_guide(
        self,
        *,
        org_id: str,
        guia_estilo_id: str,
        conjunto_regras_id: str | None,
        texto: str,
        sha256: str,
    ) -> EffectiveGuide:
        for g in self.effective_guides.values():
            if g.org_id == org_id and g.sha256 == sha256:
                return g
        eg = EffectiveGuide(
            id=self._id("guia-efetivo"),
            org_id=org_id,
            guia_estilo_id=guia_estilo_id,
            conjunto_regras_id=conjunto_regras_id,
            texto=texto,
            sha256=sha256,
            created_at=self._now(),
        )
        self.effective_guides[eg.id] = eg
        return eg

    async def get_effective_guide(self, guia_efetivo_id: str) -> EffectiveGuide | None:
        return self.effective_guides.get(guia_efetivo_id)

    async def get_cursor(self, org_id: str) -> ProposalCursor | None:
        return self.cursors.get(org_id)

    async def save_cursor(self, cursor: ProposalCursor) -> None:
        self.cursors[cursor.org_id] = cursor

    # --- costs --------------------------------------------------------
    async def add_llm_usage(self, row: LlmUsageRow) -> int:
        new_id = next(self._seq)
        if row.at is None:
            row = dataclasses.replace(row, at=self._now())
        self.llm_usage[new_id] = row
        return new_id

    async def add_cost(self, row: CostLedgerRow) -> int:
        new_id = next(self._seq)
        self.costs[new_id] = dataclasses.replace(
            row, id=new_id, created_at=row.created_at or self._now()
        )
        return new_id

    async def list_fx_pending(self, *, limit: int = 200) -> list[CostLedgerRow]:
        return [c for c in self.costs.values() if c.fx_pending][:limit]

    async def resolve_fx(
        self, cost_id: int, *, fx_rate: Decimal, fx_quote_date: date, amount_brl: Decimal
    ) -> None:
        row = self.costs[cost_id]
        if not row.fx_pending:
            return  # idempotent: already resolved
        self.costs[cost_id] = dataclasses.replace(
            row,
            fx_pending=False,
            fx_rate=fx_rate,
            fx_quote_date=fx_quote_date,
            amount_brl=amount_brl,
        )


# ---------------------------------------------------------------------------
# Row codec (dataclass <-> PostgREST JSON)
# ---------------------------------------------------------------------------


def _encode(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_encode(v) for v in value]
    if isinstance(value, dict):
        return {k: _encode(v) for k, v in value.items()}
    return value


def _parse_dt(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _parse_date(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _parse_dec(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _decode(
    cls: type,
    row: dict[str, Any],
    *,
    enums: dict[str, type[Enum]] | None = None,
    enum_tuples: dict[str, type[Enum]] | None = None,
    decimals: tuple[str, ...] = (),
    datetimes: tuple[str, ...] = (),
    dates: tuple[str, ...] = (),
    tuples: tuple[str, ...] = (),
) -> Any:
    names = {f.name for f in dataclasses.fields(cls)}
    kwargs: dict[str, Any] = {}
    for key, value in row.items():
        if key not in names:
            continue
        if enums and key in enums and value is not None:
            value = enums[key](value)
        elif enum_tuples and key in enum_tuples:
            value = tuple(enum_tuples[key](v) for v in (value or ()))
        elif key in decimals:
            value = _parse_dec(value)
        elif key in datetimes:
            value = _parse_dt(value)
        elif key in dates:
            value = _parse_date(value)
        elif key in tuples:
            value = tuple(value or ())
        if key in ("id", "org_id", "lote_id", "foto_id") and value is not None and not isinstance(value, int):
            value = str(value)
        kwargs[key] = value
    return cls(**kwargs)


def _batch(row: dict[str, Any]) -> Batch:
    return _decode(
        Batch,
        row,
        enums={"velocidade": Speed, "status": BatchStatus},
        datetimes=("submetido_at", "pronto_at", "created_at"),
    )


def _photo(row: dict[str, Any]) -> Photo:
    return _decode(Photo, row, enums={"status": PhotoStatus}, datetimes=("created_at",))


def _edit(row: dict[str, Any]) -> EditAttempt:
    return _decode(
        EditAttempt,
        row,
        enums={"velocidade": Speed},
        enum_tuples={"tipos_edicao": EditType},
        datetimes=("created_at", "concluida_at"),
    )


def _evaluation(row: dict[str, Any]) -> Evaluation:
    return _decode(
        Evaluation,
        row,
        enums={"recomendacao": Decision},
        decimals=("score",),
        datetimes=("created_at",),
    )


def _decision(row: dict[str, Any]) -> ReviewDecision:
    return _decode(ReviewDecision, row, enums={"decisao": Decision}, datetimes=("created_at",))


def _reference(row: dict[str, Any]) -> ReferencePair:
    return _decode(
        ReferencePair,
        row,
        enums={"comodo": Room},
        enum_tuples={"tipos_edicao": EditType},
        datetimes=("arquivado_em", "created_at"),
    )


def _guide(row: dict[str, Any]) -> StyleGuide:
    return _decode(
        StyleGuide, row, enums={"status": GuideStatus}, datetimes=("ativado_em", "created_at")
    )


def _rule(row: dict[str, Any]) -> OrgRule:
    return _decode(
        OrgRule,
        row,
        enums={"status": RuleStatus},
        datetimes=("decidido_em", "created_at"),
        tuples=("origem_comentarios",),
    )


def _rule_set(row: dict[str, Any]) -> RuleSet:
    return _decode(RuleSet, row, datetimes=("created_at",), tuples=("regra_ids",))


def _effective(row: dict[str, Any]) -> EffectiveGuide:
    return _decode(EffectiveGuide, row, datetimes=("created_at",))


def _cost(row: dict[str, Any]) -> CostLedgerRow:
    return _decode(
        CostLedgerRow,
        row,
        decimals=("amount_native", "fx_rate", "amount_brl"),
        dates=("fx_quote_date",),
        datetimes=("created_at",),
    )


def _row_of(record: Any, *, drop: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        f.name: _encode(getattr(record, f.name))
        for f in dataclasses.fields(record)
        if f.name not in drop and not (f.name in ("created_at", "at") and getattr(record, f.name) is None)
    }


def _is_unique_violation(exc: Exception) -> bool:
    text = f"{getattr(exc, 'code', '')} {exc}"
    return "23505" in text or "duplicate key" in text.lower()


# ---------------------------------------------------------------------------
# Supabase implementation
# ---------------------------------------------------------------------------


class SupabasePhotoEditingRepository:
    """Supabase-client backed repository.

    ``schema`` hosts the pipeline tables (``social_wiring`` for the first
    consumer); ``cost_schema`` hosts ``cost_ledger`` (Core 046 ⇒ ``public``).
    Uses a service-role client: the engine runs in workers, and RLS on
    these tables is for the product's user-facing reads.
    """

    def __init__(
        self,
        client: Any,
        *,
        schema: str = "social_wiring",
        cost_schema: str = "public",
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._client = client
        self._schema = schema
        self._cost_schema = cost_schema
        self._now = now or _utcnow

    # --- plumbing -----------------------------------------------------
    def _t(self, table: str, *, schema: str | None = None) -> Any:
        schema = schema or self._schema
        if schema == "public":
            return self._client.table(table)
        return self._client.schema(schema).from_(table)

    async def _execute(self, builder: Any) -> list[dict[str, Any]]:
        result = builder.execute()
        if hasattr(result, "__await__"):
            result = await result
        data = getattr(result, "data", None)
        if data is None:
            return []
        return data if isinstance(data, list) else [data]

    async def _one(self, builder: Any) -> dict[str, Any] | None:
        rows = await self._execute(builder)
        return rows[0] if rows else None

    async def _insert(self, table: str, row: dict[str, Any], *, schema: str | None = None) -> dict[str, Any]:
        rows = await self._execute(self._t(table, schema=schema).insert(row))
        if not rows:
            raise RepositoryError(f"insert into {table} returned no row")
        return rows[0]

    async def _update(
        self, table: str, key: Any, changes: dict[str, Any], *, schema: str | None = None
    ) -> dict[str, Any]:
        rows = await self._execute(
            self._t(table, schema=schema).update(_encode(changes)).eq("id", key)
        )
        if not rows:
            raise RepositoryError(f"update {table} id={key} matched no row")
        return rows[0]

    # --- settings -----------------------------------------------------
    async def get_org_settings(self, org_id: str) -> OrgSettings | None:
        row = await self._one(self._t("fotos_org_settings").select("*").eq("org_id", org_id).limit(1))
        if row is None:
            return None
        return _decode(
            OrgSettings,
            row,
            enums={"velocidade_override": Speed},
            enum_tuples={"tipos_edicao_ativos": EditType},
        )

    async def get_platform_settings(self) -> PlatformSettings:
        row = await self._one(self._t("fotos_platform_settings").select("*").eq("id", 1).limit(1))
        if row is None:
            raise RepositoryError("fotos_platform_settings singleton row is missing")
        return _decode(
            PlatformSettings,
            row,
            enums={"velocidade_default": Speed},
            decimals=("preco_storage_gb_mes_usd",),
        )

    # --- batches ------------------------------------------------------
    async def create_batch(
        self,
        *,
        org_id: str,
        nome: str,
        criado_por: str,
        origem: str,
        velocidade: Speed,
        imovel_org_id: str | None = None,
        imovel_codigo: str | None = None,
    ) -> Batch:
        row = await self._insert(
            "fotos_lotes",
            _encode(
                {
                    "org_id": org_id,
                    "nome": nome,
                    "criado_por": criado_por,
                    "origem": origem,
                    "velocidade": Speed(velocidade),
                    "imovel_org_id": imovel_org_id,
                    "imovel_codigo": imovel_codigo,
                }
            ),
        )
        return _batch(row)

    async def get_batch(self, lote_id: str) -> Batch | None:
        row = await self._one(self._t("fotos_lotes").select("*").eq("id", lote_id).limit(1))
        return _batch(row) if row else None

    async def update_batch(self, lote_id: str, **changes: Any) -> Batch:
        _check_fields("update_batch", changes, _BATCH_MUTABLE)
        changes["updated_at"] = self._now()
        return _batch(await self._update("fotos_lotes", lote_id, changes))

    # --- photos -------------------------------------------------------
    async def add_photo(
        self,
        *,
        org_id: str,
        lote_id: str,
        ordem: int,
        storage_path_original: str,
        vista_codigo: str | None = None,
    ) -> Photo:
        row = await self._insert(
            "fotos_fotos",
            {
                "org_id": org_id,
                "lote_id": lote_id,
                "ordem": ordem,
                "storage_path_original": storage_path_original,
                "vista_codigo": vista_codigo,
            },
        )
        return _photo(row)

    async def get_photo(self, foto_id: str) -> Photo | None:
        row = await self._one(self._t("fotos_fotos").select("*").eq("id", foto_id).limit(1))
        return _photo(row) if row else None

    async def list_photos(self, lote_id: str) -> list[Photo]:
        rows = await self._execute(
            self._t("fotos_fotos").select("*").eq("lote_id", lote_id).order("ordem")
        )
        return [_photo(r) for r in rows]

    async def update_photo(self, foto_id: str, **changes: Any) -> Photo:
        _check_fields("update_photo", changes, _PHOTO_MUTABLE)
        changes["updated_at"] = self._now()
        return _photo(await self._update("fotos_fotos", foto_id, changes))

    async def transition_photo(
        self,
        foto_id: str,
        target: PhotoStatus,
        *,
        falha_motivo: str | None = None,
        increment_tentativas: bool = False,
        event_tipo: str = "transicao_estado",
        detalhe: dict[str, Any] | None = None,
    ) -> Photo | None:
        current = await self.get_photo(foto_id)
        if current is None:
            raise KeyError(f"photo not found: {foto_id}")
        target = PhotoStatus(target)
        if not can_transition(current.status, target):
            raise IllegalTransitionError(
                f"photo {foto_id}: {current.status.value} -> {target.value}"
            )
        changes: dict[str, Any] = {
            "status": target.value,
            "falha_motivo": falha_motivo,
            "updated_at": self._now().isoformat(),
        }
        if increment_tentativas:
            changes["tentativas"] = current.tentativas + 1
        # Compare-and-set on the status we read: a concurrent writer that
        # moved the row first makes this match zero rows.
        rows = await self._execute(
            self._t("fotos_fotos")
            .update(changes)
            .eq("id", foto_id)
            .eq("status", current.status.value)
        )
        if not rows:
            return None
        await self.add_event(
            PhotoEvent(
                org_id=current.org_id,
                lote_id=current.lote_id,
                foto_id=foto_id,
                tipo=event_tipo,
                estado_de=current.status.value,
                estado_para=target.value,
                detalhe=dict(detalhe or {}),
            )
        )
        return _photo(rows[0])

    async def add_event(self, event: PhotoEvent) -> None:
        await self._insert("fotos_eventos", _row_of(event))

    async def list_events(self, lote_id: str) -> list[PhotoEvent]:
        rows = await self._execute(
            self._t("fotos_eventos").select("*").eq("lote_id", lote_id).order("created_at")
        )
        return [_decode(PhotoEvent, r, datetimes=("created_at",)) for r in rows]

    # --- edits / evaluations / decisions ------------------------------
    async def create_edit(
        self,
        *,
        org_id: str,
        lote_id: str,
        foto_id: str,
        tentativa: int,
        tipos_edicao: tuple[EditType, ...],
        modelo_id: str,
        velocidade: Speed,
    ) -> EditAttempt:
        row = await self._insert(
            "fotos_edicoes",
            _encode(
                {
                    "org_id": org_id,
                    "lote_id": lote_id,
                    "foto_id": foto_id,
                    "tentativa": tentativa,
                    "tipos_edicao": tuple(EditType(t) for t in tipos_edicao),
                    "modelo_id": modelo_id,
                    "velocidade": Speed(velocidade),
                }
            ),
        )
        return _edit(row)

    async def update_edit(self, edicao_id: str, **changes: Any) -> EditAttempt:
        _check_fields("update_edit", changes, _EDIT_MUTABLE)
        return _edit(await self._update("fotos_edicoes", edicao_id, changes))

    async def get_edit(self, edicao_id: str) -> EditAttempt | None:
        row = await self._one(self._t("fotos_edicoes").select("*").eq("id", edicao_id).limit(1))
        return _edit(row) if row else None

    async def latest_edit(self, foto_id: str) -> EditAttempt | None:
        row = await self._one(
            self._t("fotos_edicoes")
            .select("*")
            .eq("foto_id", foto_id)
            .order("created_at", desc=True)
            .limit(1)
        )
        return _edit(row) if row else None

    async def add_evaluation(
        self,
        *,
        org_id: str,
        lote_id: str,
        foto_id: str,
        edicao_id: str | None,
        recomendacao: Decision,
        score: Decimal,
        motivo: str | None,
        modelo_id: str,
        modelo_versao: str | None,
    ) -> Evaluation:
        row = await self._insert(
            "fotos_avaliacoes",
            _encode(
                {
                    "org_id": org_id,
                    "lote_id": lote_id,
                    "foto_id": foto_id,
                    "edicao_id": edicao_id,
                    "recomendacao": Decision(recomendacao),
                    "score": score,
                    "motivo": motivo,
                    "modelo_id": modelo_id,
                    "modelo_versao": modelo_versao,
                }
            ),
        )
        return _evaluation(row)

    async def latest_evaluation(self, foto_id: str) -> Evaluation | None:
        row = await self._one(
            self._t("fotos_avaliacoes")
            .select("*")
            .eq("foto_id", foto_id)
            .order("created_at", desc=True)
            .limit(1)
        )
        return _evaluation(row) if row else None

    async def add_decision(
        self,
        *,
        org_id: str,
        lote_id: str,
        foto_id: str,
        decisao: Decision,
        comentario: str | None,
        decidido_por: str,
    ) -> ReviewDecision:
        row = await self._insert(
            "fotos_decisoes",
            _encode(
                {
                    "org_id": org_id,
                    "lote_id": lote_id,
                    "foto_id": foto_id,
                    "decisao": Decision(decisao),
                    "comentario": comentario,
                    "decidido_por": decidido_por,
                }
            ),
        )
        return _decision(row)

    async def latest_decisions(self, lote_id: str) -> dict[str, ReviewDecision]:
        rows = await self._execute(
            self._t("fotos_decisoes").select("*").eq("lote_id", lote_id).order("created_at")
        )
        out: dict[str, ReviewDecision] = {}
        for r in rows:
            d = _decision(r)
            out[d.foto_id] = d
        return out

    async def list_rejections(
        self, org_id: str, *, after: datetime | None = None, limit: int = 200
    ) -> list[ReviewDecision]:
        q = (
            self._t("fotos_decisoes")
            .select("*")
            .eq("org_id", org_id)
            .eq("decisao", Decision.REJEITAR.value)
        )
        if after is not None:
            q = q.gt("created_at", after.isoformat())
        rows = await self._execute(q.order("created_at").limit(limit))
        return [_decision(r) for r in rows if r.get("comentario")]

    async def add_dataset_record(self, record: DatasetRecord) -> None:
        await self._insert("fotos_dataset", _row_of(record))

    # --- pool / guides / rules ----------------------------------------
    async def list_active_references(self, *, limit: int) -> list[ReferencePair]:
        rows = await self._execute(
            self._t("fotos_referencias")
            .select("*")
            .is_("arquivado_em", "null")
            .order("created_at", desc=True)
            .limit(limit)
        )
        return [_reference(r) for r in rows]

    async def last_pool_change_at(self) -> datetime | None:
        created = await self._one(
            self._t("fotos_referencias").select("created_at").order("created_at", desc=True).limit(1)
        )
        archived = await self._one(
            self._t("fotos_referencias")
            .select("arquivado_em")
            .not_.is_("arquivado_em", "null")
            .order("arquivado_em", desc=True)
            .limit(1)
        )
        stamps = [
            _parse_dt(r.get(k))
            for r, k in ((created, "created_at"), (archived, "arquivado_em"))
            if r and r.get(k)
        ]
        return max(stamps) if stamps else None

    async def get_active_guide(self) -> StyleGuide | None:
        row = await self._one(
            self._t("fotos_guias_estilo").select("*").eq("status", GuideStatus.ATIVA.value).limit(1)
        )
        return _guide(row) if row else None

    async def get_guide(self, versao: int) -> StyleGuide | None:
        row = await self._one(self._t("fotos_guias_estilo").select("*").eq("versao", versao).limit(1))
        return _guide(row) if row else None

    async def latest_guide_version(self) -> int:
        row = await self._one(
            self._t("fotos_guias_estilo").select("versao").order("versao", desc=True).limit(1)
        )
        return int(row["versao"]) if row else 0

    async def create_guide(
        self,
        *,
        versao: int,
        texto: str,
        sha256: str,
        gerado_de_versao: int | None,
        criado_por: str | None,
    ) -> StyleGuide:
        row = await self._insert(
            "fotos_guias_estilo",
            {
                "versao": versao,
                "texto": texto,
                "sha256": sha256,
                "gerado_de_versao": gerado_de_versao,
                "criado_por": criado_por,
            },
        )
        return _guide(row)

    async def activate_guide(
        self, versao: int, *, ativado_por: str, at: datetime
    ) -> StyleGuide:
        # Two statements: demote, then promote. The table's partial UNIQUE
        # index (at most one 'ativa') makes the promote fail loudly if the
        # demote did not land; a crash between them leaves NO active guide,
        # which blocks submission with GuideNotActiveError (loud) rather
        # than running on a stale one.
        await self._execute(
            self._t("fotos_guias_estilo")
            .update({"status": GuideStatus.SUBSTITUIDA.value})
            .eq("status", GuideStatus.ATIVA.value)
            .neq("versao", versao)
        )
        rows = await self._execute(
            self._t("fotos_guias_estilo")
            .update(
                {
                    "status": GuideStatus.ATIVA.value,
                    "ativado_por": ativado_por,
                    "ativado_em": at.isoformat(),
                }
            )
            .eq("versao", versao)
        )
        if not rows:
            raise RepositoryError(f"activate_guide: version {versao} not found")
        return _guide(rows[0])

    async def add_rule(
        self, *, org_id: str, texto: str, origem_comentarios: tuple[dict[str, Any], ...]
    ) -> OrgRule:
        row = await self._insert(
            "fotos_regras_org",
            {
                "org_id": org_id,
                "texto": texto,
                "origem_comentarios": _encode(tuple(origem_comentarios)),
            },
        )
        return _rule(row)

    async def get_rule(self, regra_id: str) -> OrgRule | None:
        row = await self._one(self._t("fotos_regras_org").select("*").eq("id", regra_id).limit(1))
        return _rule(row) if row else None

    async def list_rules(
        self, org_id: str, *, status: RuleStatus | None = None
    ) -> list[OrgRule]:
        q = self._t("fotos_regras_org").select("*").eq("org_id", org_id)
        if status is not None:
            q = q.eq("status", RuleStatus(status).value)
        return [_rule(r) for r in await self._execute(q.order("created_at"))]

    async def update_rule(
        self,
        regra_id: str,
        *,
        status: RuleStatus,
        decidido_por: str,
        decidido_em: datetime,
        override_platform_admin: bool,
    ) -> OrgRule:
        # `override_platform_admin` is ALSO forced true by the table's
        # BEFORE UPDATE trigger on a decided->decided flip; sending it keeps
        # the in-memory and Postgres implementations observably identical.
        return _rule(
            await self._update(
                "fotos_regras_org",
                regra_id,
                {
                    "status": RuleStatus(status),
                    "decidido_por": decidido_por,
                    "decidido_em": decidido_em,
                    "override_platform_admin": override_platform_admin,
                },
            )
        )

    async def latest_rule_set(self, org_id: str) -> RuleSet | None:
        row = await self._one(
            self._t("fotos_conjuntos_regras")
            .select("*")
            .eq("org_id", org_id)
            .order("versao", desc=True)
            .limit(1)
        )
        return _rule_set(row) if row else None

    async def create_rule_set(
        self, *, org_id: str, versao: int, regra_ids: tuple[str, ...], sha256: str
    ) -> RuleSet:
        row = await self._insert(
            "fotos_conjuntos_regras",
            {"org_id": org_id, "versao": versao, "regra_ids": list(regra_ids), "sha256": sha256},
        )
        return _rule_set(row)

    async def _find_effective(self, org_id: str, sha256: str) -> EffectiveGuide | None:
        row = await self._one(
            self._t("fotos_guias_efetivos")
            .select("*")
            .eq("org_id", org_id)
            .eq("sha256", sha256)
            .limit(1)
        )
        return _effective(row) if row else None

    async def get_or_create_effective_guide(
        self,
        *,
        org_id: str,
        guia_estilo_id: str,
        conjunto_regras_id: str | None,
        texto: str,
        sha256: str,
    ) -> EffectiveGuide:
        existing = await self._find_effective(org_id, sha256)
        if existing is not None:
            return existing
        try:
            row = await self._insert(
                "fotos_guias_efetivos",
                {
                    "org_id": org_id,
                    "guia_estilo_id": guia_estilo_id,
                    "conjunto_regras_id": conjunto_regras_id,
                    "texto": texto,
                    "sha256": sha256,
                },
            )
        except Exception as exc:
            if not _is_unique_violation(exc):
                raise
            # UNIQUE (org_id, sha256): a concurrent submit won the insert.
            raced = await self._find_effective(org_id, sha256)
            if raced is None:
                raise
            return raced
        return _effective(row)

    async def get_effective_guide(self, guia_efetivo_id: str) -> EffectiveGuide | None:
        row = await self._one(
            self._t("fotos_guias_efetivos").select("*").eq("id", guia_efetivo_id).limit(1)
        )
        return _effective(row) if row else None

    async def get_cursor(self, org_id: str) -> ProposalCursor | None:
        row = await self._one(
            self._t("fotos_propostas_cursor").select("*").eq("org_id", org_id).limit(1)
        )
        return _decode(ProposalCursor, row, datetimes=("ultima_execucao_em",)) if row else None

    async def save_cursor(self, cursor: ProposalCursor) -> None:
        row = _row_of(cursor)
        row["updated_at"] = self._now().isoformat()
        await self._execute(
            self._t("fotos_propostas_cursor").upsert(row, on_conflict="org_id")
        )

    # --- costs --------------------------------------------------------
    async def add_llm_usage(self, row: LlmUsageRow) -> int:
        inserted = await self._insert("llm_usage", _row_of(row))
        return int(inserted["id"])

    async def add_cost(self, row: CostLedgerRow) -> int:
        inserted = await self._insert(
            "cost_ledger", _row_of(row, drop=("id",)), schema=self._cost_schema
        )
        return int(inserted["id"])

    async def list_fx_pending(self, *, limit: int = 200) -> list[CostLedgerRow]:
        rows = await self._execute(
            self._t("cost_ledger", schema=self._cost_schema)
            .select("*")
            .eq("fx_pending", True)
            .order("created_at")
            .limit(limit)
        )
        return [_cost(r) for r in rows]

    async def resolve_fx(
        self, cost_id: int, *, fx_rate: Decimal, fx_quote_date: date, amount_brl: Decimal
    ) -> None:
        # Guarded on fx_pending so a second backfill run is a no-op.
        await self._execute(
            self._t("cost_ledger", schema=self._cost_schema)
            .update(
                _encode(
                    {
                        "fx_pending": False,
                        "fx_rate": fx_rate,
                        "fx_quote_date": fx_quote_date,
                        "amount_brl": amount_brl,
                    }
                )
            )
            .eq("id", cost_id)
            .eq("fx_pending", True)
        )


def make_photo_editing_repository(
    *,
    use_fake: bool = False,
    supabase_client: Any | None = None,
    schema: str = "social_wiring",
    cost_schema: str = "public",
) -> PhotoEditingRepository:
    """Construct a repository. ``use_fake=True`` ⇒ in-memory; otherwise a
    Supabase client is REQUIRED (no silent fallback to in-memory)."""
    if use_fake:
        return InMemoryPhotoEditingRepository()
    if supabase_client is None:
        raise RuntimeError(
            "make_photo_editing_repository: supabase_client is required when use_fake=False"
        )
    return SupabasePhotoEditingRepository(
        supabase_client, schema=schema, cost_schema=cost_schema
    )


__all__ = [
    "InMemoryPhotoEditingRepository",
    "PhotoEditingRepository",
    "RepositoryError",
    "SupabasePhotoEditingRepository",
    "make_photo_editing_repository",
]
