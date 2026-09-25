"""The ONE definition of "recover extractions that were started and never
finished" — the recurrence-rule formalization S2 contract
`sw-negociacao-extracao-contract.md` §E3.3 requires.

🔴 WHY THIS EXISTS NOW, AND NOT EARLIER
------------------------------------------
By the time this module lands, FOUR hand-rolled sweeps already existed —
`identidade_extracao_service.varrer_extracoes_pendentes`, `imovel_hub.
matricula_extracao_service`'s own sweep, `imovel_hub.documentos_service`'s
structured-read sweep, and `empresas.sweep_service.varrer_extracoes_
pendentes`. Every one of them is the SAME shape: find rows stuck in
`pendente`/`processando` past a stale cutoff, rows never even started, and
rows that failed with a retryable error under `extracao_retentativa`'s cap
— then re-run each one's own `extrair` function, never letting one bad row
stop the sweep. `negociacao_extracao_service`'s OWN sweep would have been a
FIFTH — the recurrence rule (`KB § PATTERNS/architect/project-execution.md`
§ N=3+ MUST formalize) forbids shipping that fourth-becomes-fifth copy. This
module is what the fourth one (`empresas.sweep_service`) is now built ON —
see that module's own docstring — and what `negociacao_extracao_service`'s
sweep uses from the start; `identidade_extracao_service` / `imovel_hub`'s
two are marked `NOC-REMEDIATE[dry-extracao-varredura]` for a later slice
that migrates them too (their candidate-selection SQL shape differs slightly
— matrícula's `documento_id`-vs-`id` naming — so a mechanical swap needs its
own review, not this commit's).

WHAT THIS OWNS
--------------
- `candidatos` — the THREE-way UNION (stale non-terminal, never-started,
  retryable-error) every sweep above independently re-derived, deduped by
  `id`, oldest-first.
- `varrer` — the recovery loop: exhausted rows are marked `erro` and left
  for a human; everything else is re-run through the CALLER's own
  `extrair_fn`, one bad row logged and skipped rather than stopping the
  whole sweep (the "audit every action" rule — every skip is logged, never
  silent).

WHAT THIS DOES **NOT** OWN
---------------------------
Which columns a surface's OWN `extracao_dados`/`extracao_erro` shape has
beyond the common five (`extracao_status`, `extracao_em`,
`extracao_tentativas`, `id`, `org_id`) — those are read generically via
`select(colunas)`. The scheduler wrapper (`never raise`, `no storage ->
skip`) stays `app.services.extraction_sweep.make_sweep_job`/`configure_
sweep` — a DIFFERENT layer (this module finds+retries rows; that one wraps
a callable in the guards a SCHEDULED job needs). Compose them:
`extraction_sweep.configure_sweep(sweep=lambda admin, storage: varrer(admin,
storage, MY_CONFIG))`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional
from uuid import UUID

from app.services import extracao_retentativa, table_reads

logger = logging.getLogger(__name__)

#: How long a document may sit in a non-terminal state before the sweep
#: treats it as abandoned — comfortably longer than a real extraction (tens
#: of seconds), so the sweep never races a job that is simply still working.
STALE_APOS = timedelta(minutes=20)

_ESTADOS_NAO_TERMINAIS = ("pendente", "processando")

#: `(client, storage, org_id, owner_id, documento_id, *, extractor, notification_service=None) -> Awaitable[dict]`
#: — every surface's own `extrair_<tipo>`/`extrair` function already has
#: exactly this shape (`empresas.extracao_service.extrair_cartao`,
#: `card_hub.negociacao_extracao_service.extrair`).
ExtrairFn = Callable[..., Awaitable[dict]]
#: `(org_id, tipo_documento) -> extractor` — the same `ExtractorFactory`
#: shape `card_hub.deps.get_identity_extractor_factory` already returns.
ExtractorFactory = Callable[[str, Optional[str]], Any]


@dataclass(frozen=True)
class SweepConfig:
    """One surface's sweep wiring — the four things that differ per table;
    everything else (`candidatos`'s three-way union, `varrer`'s recovery
    loop) is shared."""

    #: The documents table (`empresa_documentos`, `atendimento_documentos`, ...).
    table: str
    #: The owner-id column `extrair_fn` needs (`empresa_id`, `atendimento_id`).
    owner_col: str
    #: `select()` column list — must include `id, org_id, extracao_status,
    #: extracao_tentativas, extracao_em, created_at, tipo_documento` plus
    #: `owner_col`.
    colunas: str
    extrair_fn: ExtrairFn
    max_tentativas: int = extracao_retentativa.MAX_TENTATIVAS
    stale_apos: timedelta = STALE_APOS
    tipo_documento_col: str = "tipo_documento"
    #: Resolved once per candidate row (org-scoped, type-scoped) — `None`
    #: means every caller's `extrair_fn` builds its own default when handed
    #: `extractor=None` (mirrors `empresas.extracao_service.extrair_cartao`'s
    #: own fallback).
    extractor_factory: Optional[ExtractorFactory] = None


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _stale_cutoff(stale_apos: timedelta) -> str:
    return (datetime.now(timezone.utc) - stale_apos).isoformat()


def candidatos(client: Any, config: SweepConfig, limite: int) -> list[dict]:
    """The three-way union every sweep re-derives: stale non-terminal,
    never-started, retryable-error — deduped by `id`, oldest-claim-first."""
    cutoff = _stale_cutoff(config.stale_apos)

    def base():
        return _t(client, config.table).select(config.colunas).is_("deleted_at", "null")

    parados = (
        base()
        .in_("extracao_status", list(_ESTADOS_NAO_TERMINAIS))
        .lte("extracao_em", cutoff)
        .limit(limite)
        .execute()
    ).data or []
    nunca_iniciados = (
        base()
        .eq("extracao_status", "pendente")
        .is_("extracao_em", "null")
        .lte("created_at", cutoff)
        .limit(limite)
        .execute()
    ).data or []
    com_erro = (
        base()
        .eq("extracao_status", "erro")
        .lt("extracao_tentativas", config.max_tentativas)
        .lte("extracao_em", cutoff)
        .limit(limite)
        .execute()
    ).data or []

    vistos: set[str] = set()
    linhas: list[dict] = []
    for row in [*parados, *nunca_iniciados, *com_erro]:
        chave = str(row["id"])
        if chave in vistos:
            continue
        vistos.add(chave)
        linhas.append(row)
    linhas.sort(key=lambda r: r.get("extracao_em") or r.get("created_at") or "")
    return linhas[:limite]


async def varrer(
    client: Any,
    storage: Any,
    config: SweepConfig,
    *,
    notification_service: Optional[Any] = None,
    limite: int = 50,
) -> dict:
    """Recover every candidate: exhausted rows are marked `erro` for a
    human (never retried again); everything else is re-run through
    `config.extrair_fn`, one failing row logged and skipped rather than
    stopping the sweep."""
    rows = candidatos(client, config, limite)

    retomados = 0
    esgotados = 0
    falhas = 0

    for row in rows:
        documento_id = UUID(str(row["id"]))
        tentativas = int(row.get("extracao_tentativas") or 0)

        if tentativas >= config.max_tentativas:
            _t(client, config.table).update(
                {
                    "extracao_status": "erro",
                    "extracao_erro": (
                        f"extração abandonada após {tentativas} tentativas "
                        f"(limite {config.max_tentativas})"
                    ),
                    "extracao_em": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", str(documento_id)).execute()
            esgotados += 1
            continue

        try:
            org_id = UUID(str(row["org_id"]))
            owner_id = UUID(str(row[config.owner_col]))
            tipo_documento = str(row.get(config.tipo_documento_col) or "")
            extractor = (
                config.extractor_factory(str(org_id), tipo_documento)
                if config.extractor_factory
                else None
            )
            await config.extrair_fn(
                client, storage, org_id, owner_id, documento_id,
                extractor=extractor,
                notification_service=notification_service,
            )
            retomados += 1
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the sweep
            logger.warning(
                "%s sweep: documento %s failed: %s", config.table, documento_id, exc,
            )
            falhas += 1

    if rows:
        logger.info(
            "%s extracao sweep: %d candidate(s), %d retried, %d exhausted, %d failed",
            config.table, len(rows), retomados, esgotados, falhas,
        )
    return {
        "encontrados": len(rows),
        "retomados": retomados,
        "esgotados": esgotados,
        "falhas": falhas,
    }


__all__ = [
    "STALE_APOS",
    "ExtractorFactory",
    "ExtrairFn",
    "SweepConfig",
    "candidatos",
    "varrer",
]
