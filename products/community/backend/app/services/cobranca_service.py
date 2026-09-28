"""Billing settings + the billing sweep — projects/ninho-vazio/CONTRACT.md
§Billing lifecycle (the two "sweep:" rows) and §Billing — slice BE-B.

The sweep runs hourly through the seed scheduler (`app/scheduler.py`,
gated on `NOCTUS_SCHEDULERS_ENABLED`) and on demand
(`POST /api/cobranca/executar-rotina`). It is three reports, in order:

1. `cancelamentos_pendentes_gateway` — retry every gateway cancel a past
   sweep could not complete (`gateway_cancelamento_pendente = true`).
   Runs first so a failure from THIS run is not retried seconds later.
2. `carencia_expirada` — `carencia` with `carencia_ate ≤ now` → `expirada`;
   the member goes to the free plan (`ativo`); the gateway subscription is
   cancelled (failure → flagged pending + reported).
3. `fim_do_periodo_pago` — `cancelada` with `pago_ate ≤ now` whose member is
   still on that plan → the member goes to the free plan.

`automacoes_ativas = false` → every report is `pulado` and nothing is
written. Every estado move goes through the seed state machine
(`ciclo_assinatura.validar_transicao`); an illegal one lands in `erros`,
never applied. A missing gateway key is an error, never a Fake success.

NOC-REMEDIATE[billing-sweep-seed-lift]: Core's `billing_automations` is N=1
of this grace/expiry sweep shape and this module is N=2; lift the shared
skeleton (report, guarded run, pending gateway cancel) into the seed at
N=3. — 2026-09-28
"""
from __future__ import annotations

import functools
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

from noctusai_lib.integrations.persistence.paging import iter_paged_rows

from app.services.ciclo_assinatura import (
    TransicaoIlegal,
    agora_utc,
    cancelar_no_gateway,
    gateway_estrito,
    iso,
    ler_configuracoes,
    ler_timestamp,
    marcar_cancelamento_pendente,
    plano_gratuito,
    validar_transicao,
)
from app.services.eventos_service import registrar_evento
from app.services.membros_service import MembrosService

logger = logging.getLogger(__name__)

_ASSINATURAS_TABLE = "assinaturas"
_MEMBROS_TABLE = "membros"
_CONFIG_TABLE = "configuracoes_cobranca"

ROTINA_CANCELAMENTOS_PENDENTES = "cancelamentos_pendentes_gateway"
ROTINA_CARENCIA_EXPIRADA = "carencia_expirada"
ROTINA_FIM_DO_PERIODO = "fim_do_periodo_pago"
ROTINAS = (ROTINA_CANCELAMENTOS_PENDENTES, ROTINA_CARENCIA_EXPIRADA, ROTINA_FIM_DO_PERIODO)

PLANO_GRATUITO_AUSENTE = "Plano gratuito não configurado."


@dataclass
class RelatorioRotina:
    nome: str
    pulado: bool = False
    examinadas: int = 0
    alteradas: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)

    def como_dict(self) -> dict[str, Any]:
        return {
            "nome": self.nome,
            "pulado": self.pulado,
            "examinadas": self.examinadas,
            "alteradas": list(self.alteradas),
            "erros": list(self.erros),
        }


class CobrancaService:
    def __init__(
        self,
        client: Any,
        *,
        org_id: Any,
        gateway_factory: Optional[Callable[[str], Any]] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._client = client
        self._org_id = str(org_id)
        self._gateway_factory = gateway_factory or functools.partial(
            gateway_estrito, org_id=self._org_id
        )
        self._clock = clock or agora_utc

    # ── settings ─────────────────────────────────────────────────────

    def obter_configuracoes(self) -> dict:
        row = ler_configuracoes(self._client, self._org_id)
        return {
            "dias_carencia": int(row.get("dias_carencia")),
            "automacoes_ativas": bool(row.get("automacoes_ativas")),
        }

    def salvar_configuracoes(self, *, dias_carencia: int, automacoes_ativas: bool) -> dict:
        ler_configuracoes(self._client, self._org_id)  # ensures the row exists
        written = (
            self._client.table(_CONFIG_TABLE)
            .update({"dias_carencia": dias_carencia, "automacoes_ativas": automacoes_ativas})
            .eq("org_id", self._org_id)
            .execute()
            .data
            or []
        )
        if not written:
            raise RuntimeError(
                f"configuracoes_cobranca update returned no row (org={self._org_id})"
            )
        return {
            "dias_carencia": int(written[0]["dias_carencia"]),
            "automacoes_ativas": bool(written[0]["automacoes_ativas"]),
        }

    # ── the sweep ────────────────────────────────────────────────────

    async def executar_rotina(self) -> list[RelatorioRotina]:
        config = ler_configuracoes(self._client, self._org_id)
        if not config.get("automacoes_ativas"):
            logger.info("cobranca: rotina pulada — automações desligadas (org=%s)", self._org_id)
            return [RelatorioRotina(nome, pulado=True) for nome in ROTINAS]
        now = self._clock()
        gratuito = plano_gratuito(self._client, self._org_id)
        relatorios = [
            self._cancelamentos_pendentes(),
            await self._expirar_carencias(now, gratuito),
            await self._encerrar_periodos_pagos(now, gratuito),
        ]
        for r in relatorios:
            if r.alteradas or r.erros:
                logger.info(
                    "cobranca: %s examinadas=%d alteradas=%d erros=%d",
                    r.nome, r.examinadas, len(r.alteradas), len(r.erros),
                )
        return relatorios

    def _assinaturas(self, filtrar: Callable[[Any], Any], label: str) -> list[dict]:
        return list(
            iter_paged_rows(
                lambda start, end: filtrar(
                    self._client.table(_ASSINATURAS_TABLE)
                    .select("*")
                    .eq("org_id", self._org_id)
                )
                .order("id")
                .range(start, end)
                .execute()
                .data,
                label=label,
            )
        )

    def _cancelar_no_gateway(self, assinatura: dict) -> Optional[str]:
        """Stop future charges at the gateway. Returns an error text, or
        None on success / nothing to cancel."""
        return cancelar_no_gateway(assinatura, self._gateway_factory)

    def _marcar_pendente(self, assinatura_id: Any, pendente: bool) -> None:
        marcar_cancelamento_pendente(self._client, self._org_id, assinatura_id, pendente)

    async def _mover_para_gratuito(self, assinatura: dict, gratuito: dict) -> bool:
        """Put the subscription's member on the free plan, `ativo`.

        Only when the member is still on THIS subscription's plan — a
        member who already moved to another plan (a newer subscription,
        a manager edit) is left alone — and never a soft-deleted
        (`cancelado`) member. Returns True when the member was moved.
        """
        membro = (
            self._client.table(_MEMBROS_TABLE)
            .select("*")
            .eq("org_id", self._org_id)
            .eq("id", str(assinatura["membro_id"]))
            .maybe_single()
            .execute()
        ).data
        if not membro:
            logger.error(
                "cobranca: assinatura_id=%s references a missing membro_id=%s",
                assinatura["id"], assinatura["membro_id"],
            )
            return False
        if str(membro.get("plano_id")) != str(assinatura.get("plano_id")):
            return False
        if membro.get("status") == "cancelado":
            return False
        self._client.table(_MEMBROS_TABLE).update({"plano_id": gratuito["id"]}).eq(
            "org_id", self._org_id
        ).eq("id", membro["id"]).execute()
        await MembrosService(self._client, org_id=self._org_id).set_status(
            membro_id=membro["id"], novo_status="ativo",
        )
        return True

    def _cancelamentos_pendentes(self) -> RelatorioRotina:
        relatorio = RelatorioRotina(ROTINA_CANCELAMENTOS_PENDENTES)
        linhas = self._assinaturas(
            lambda q: q.eq("gateway_cancelamento_pendente", True),
            label="assinaturas com cancelamento pendente no gateway",
        )
        for assinatura in linhas:
            relatorio.examinadas += 1
            erro = self._cancelar_no_gateway(assinatura)
            if erro:
                relatorio.erros.append(erro)
                continue
            self._marcar_pendente(assinatura["id"], False)
            relatorio.alteradas.append(f"{assinatura['id']}: cancelamento no gateway concluído")
        return relatorio

    async def _expirar_carencias(self, now: datetime, gratuito: Optional[dict]) -> RelatorioRotina:
        relatorio = RelatorioRotina(ROTINA_CARENCIA_EXPIRADA)
        linhas = self._assinaturas(
            lambda q: q.eq("estado", "carencia").lte("carencia_ate", iso(now)),
            label="assinaturas em carência vencida",
        )
        for assinatura in linhas:
            carencia_ate = ler_timestamp(assinatura.get("carencia_ate"))
            if carencia_ate is None or carencia_ate > now:
                continue
            relatorio.examinadas += 1
            try:
                validar_transicao(assinatura, "expirada", now=now)
            except TransicaoIlegal as exc:
                logger.error("cobranca: %s", exc)
                relatorio.erros.append(f"{assinatura['id']}: {exc}")
                continue
            if gratuito is None:
                relatorio.erros.append(f"{assinatura['id']}: {PLANO_GRATUITO_AUSENTE}")
                continue
            # Optimistic guard: a payment that re-activated the row since
            # it was read wins — nothing is written over it.
            escritas = (
                self._client.table(_ASSINATURAS_TABLE)
                .update({"estado": "expirada", "expirada_em": iso(now)})
                .eq("org_id", self._org_id)
                .eq("id", str(assinatura["id"]))
                .eq("estado", "carencia")
                .execute()
                .data
                or []
            )
            if not escritas:
                continue
            erro_gateway = self._cancelar_no_gateway(assinatura)
            if erro_gateway:
                relatorio.erros.append(erro_gateway)
                self._marcar_pendente(assinatura["id"], True)
            movido = await self._mover_para_gratuito(assinatura, gratuito)
            registrar_evento(
                self._client, org_id=self._org_id, membro_id=assinatura["membro_id"],
                tipo="assinatura",
                descricao=(
                    "Carência encerrada sem pagamento — assinatura expirada."
                    + (f" Membro movido para o plano {gratuito.get('nome')}." if movido else "")
                ),
                dados={
                    "assinatura_id": str(assinatura["id"]),
                    "estado_anterior": "carencia",
                    "carencia_ate": assinatura.get("carencia_ate"),
                    "plano_gratuito_id": str(gratuito["id"]) if movido else None,
                    "gateway_cancelamento_pendente": bool(erro_gateway),
                },
            )
            relatorio.alteradas.append(f"{assinatura['id']}: carencia → expirada")
        return relatorio

    async def _encerrar_periodos_pagos(
        self, now: datetime, gratuito: Optional[dict]
    ) -> RelatorioRotina:
        relatorio = RelatorioRotina(ROTINA_FIM_DO_PERIODO)
        linhas = self._assinaturas(
            lambda q: q.eq("estado", "cancelada").lte("pago_ate", iso(now)),
            label="assinaturas canceladas com período pago encerrado",
        )
        for assinatura in linhas:
            pago_ate = ler_timestamp(assinatura.get("pago_ate"))
            if pago_ate is None or pago_ate > now:
                continue
            relatorio.examinadas += 1
            if gratuito is None:
                relatorio.erros.append(f"{assinatura['id']}: {PLANO_GRATUITO_AUSENTE}")
                continue
            if str(assinatura.get("plano_id")) == str(gratuito["id"]):
                continue
            if not await self._mover_para_gratuito(assinatura, gratuito):
                continue
            registrar_evento(
                self._client, org_id=self._org_id, membro_id=assinatura["membro_id"],
                tipo="plano",
                descricao=(
                    "Fim do período pago da assinatura cancelada — membro movido "
                    f"para o plano {gratuito.get('nome')}."
                ),
                dados={
                    "assinatura_id": str(assinatura["id"]),
                    "plano_anterior_id": str(assinatura.get("plano_id")),
                    "plano_id": str(gratuito["id"]),
                    "pago_ate": assinatura.get("pago_ate"),
                },
            )
            relatorio.alteradas.append(f"{assinatura['id']}: membro → plano gratuito")
        return relatorio


__all__ = [
    "CobrancaService",
    "PLANO_GRATUITO_AUSENTE",
    "ROTINAS",
    "ROTINA_CANCELAMENTOS_PENDENTES",
    "ROTINA_CARENCIA_EXPIRADA",
    "ROTINA_FIM_DO_PERIODO",
    "RelatorioRotina",
]
