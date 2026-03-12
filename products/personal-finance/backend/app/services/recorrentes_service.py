"""Recurring transactions service — schedule execution and backfill."""
import logging
from datetime import date
from typing import Dict, List, Optional
from dateutil.relativedelta import relativedelta
from app.dependencies import first_or_none

logger = logging.getLogger(__name__)

MAX_EXECUCOES_POR_CHAMADA = 100
MAX_BACKFILL_POR_RECORRENTE = 6

FREQUENCIA_DELTA = {
    "semanal": relativedelta(weeks=1),
    "quinzenal": relativedelta(weeks=2),
    "mensal": relativedelta(months=1),
    "bimestral": relativedelta(months=2),
    "trimestral": relativedelta(months=3),
    "semestral": relativedelta(months=6),
    "anual": relativedelta(years=1),
}


def calcular_proxima_data(data_atual: date, frequencia: str) -> date:
    """Advance a date by the frequency delta. Pure function, no side effects."""
    delta = FREQUENCIA_DELTA.get(frequencia)
    if not delta:
        raise ValueError(f"Frequencia desconhecida: {frequencia}")
    return data_atual + delta


class RecorrentesService:
    def __init__(self, db_client, org_id: str):
        self.db = db_client
        self.org_id = org_id

    async def executar_pendentes(self) -> Dict:
        """Execute all pending automatic recurring entries up to today.

        Returns summary with counts of executed/skipped/errors.
        """
        hoje = date.today()
        result = self.db.table("recorrentes").select("*").eq(
            "org_id", self.org_id
        ).eq("ativo", True).eq("is_automatico", True).lte(
            "proxima_data", hoje.isoformat()
        ).execute()

        pendentes = result.data or []
        total_executadas = 0
        erros = 0

        for rec in pendentes:
            if total_executadas >= MAX_EXECUCOES_POR_CHAMADA:
                break
            executadas, erro = await self._executar_recorrente(rec, hoje, MAX_EXECUCOES_POR_CHAMADA - total_executadas)
            total_executadas += executadas
            erros += erro

        return {
            "executadas": total_executadas,
            "pendentes_processadas": len(pendentes),
            "erros": erros,
        }

    async def executar_unico(self, recorrente_id: str) -> Optional[Dict]:
        """Execute a single recurring entry once (manual trigger).

        Returns the created transaction, or None if the entry doesn't exist.
        """
        result = self.db.table("recorrentes").select("*").eq(
            "id", recorrente_id
        ).eq("org_id", self.org_id).single().execute()

        if not result.data:
            return None

        rec = result.data
        hoje = date.today()
        proxima = date.fromisoformat(rec["proxima_data"]) if rec.get("proxima_data") else hoje

        transacao = await self._criar_transacao(rec, proxima)
        if not transacao:
            return None

        nova_data = calcular_proxima_data(proxima, rec["frequencia"])
        self.db.table("recorrentes").update(
            {"proxima_data": nova_data.isoformat()}
        ).eq("id", recorrente_id).execute()

        return transacao

    async def _executar_recorrente(self, rec: Dict, hoje: date, limite: int) -> tuple:
        """Execute a single recurring entry, backfilling missed dates.

        Returns (count_executed, count_errors).
        """
        if not rec.get("conta_id"):
            logger.warning(f"Recorrente {rec['id']} sem conta_id, pulando")
            return 0, 0

        proxima_str = rec.get("proxima_data")
        if not proxima_str:
            return 0, 0

        proxima = date.fromisoformat(proxima_str)
        executadas = 0
        erros = 0

        backfill_limit = min(limite, MAX_BACKFILL_POR_RECORRENTE)

        while proxima <= hoje and executadas < backfill_limit:
            try:
                transacao = await self._criar_transacao(rec, proxima)
                if not transacao:
                    erros += 1
                    break
                proxima = calcular_proxima_data(proxima, rec["frequencia"])
                executadas += 1
            except Exception as e:
                logger.error(f"Erro ao executar recorrente {rec['id']}: {e}")
                erros += 1
                break

        # Update proxima_data
        if executadas > 0:
            self.db.table("recorrentes").update(
                {"proxima_data": proxima.isoformat()}
            ).eq("id", rec["id"]).execute()

        return executadas, erros

    async def _criar_transacao(self, rec: Dict, data_transacao: date) -> Optional[Dict]:
        """Create a transaction from a recurring entry."""
        from app.services.transacoes_service import TransacoesService

        tx_data = {
            "descricao": rec.get("nome", "Transacao recorrente"),
            "valor": rec["valor"],
            "tipo": rec["tipo"],
            "conta_id": rec["conta_id"],
            "categoria_id": rec.get("categoria_id"),
            "data": data_transacao.isoformat(),
            "comerciante": rec.get("comerciante"),
            "recorrente_id": rec["id"],
        }

        svc = TransacoesService(self.db, self.org_id)
        return await svc.criar(tx_data)
