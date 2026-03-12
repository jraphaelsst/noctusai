"""
Recorrência Service — Automated recurring financial transactions.

Generates monthly rent charges, contract installments, and recurring
financial entries based on active contracts and configurations.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RecorrenciaService:
    """Service for recurring transaction automation."""

    def __init__(self, db_client, org_id: str):
        self.db = db_client
        self.org_id = org_id

    def gerar_alugueis_mes(self, referencia: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate monthly rent charges for all active lease contracts.

        Args:
            referencia: Month reference in YYYY-MM format. Defaults to current month.

        Returns:
            Dict with gerados (count), existentes (skipped), and erros.
        """
        if not referencia:
            referencia = datetime.now(timezone.utc).strftime("%Y-%m")

        ano, mes = referencia.split("-")

        # Fetch active lease contracts
        result = self.db.table("contratos_locacao").select("*").eq(
            "status", "ativo"
        ).execute()
        contratos = result.data or []

        if not contratos:
            return {
                "referencia": referencia,
                "gerados": 0,
                "existentes": 0,
                "erros": 0,
                "total_contratos": 0,
            }

        # Batch-fetch all existing lancamentos for this reference month
        existing_result = self.db.table("lancamentos").select(
            "contrato_id"
        ).eq("referencia", referencia).execute()
        existing_contrato_ids = {
            r["contrato_id"] for r in (existing_result.data or [])
        }

        # Build list of new lancamentos to insert
        novos = []
        existentes = 0
        erros = 0

        for contrato in contratos:
            try:
                contrato_id = contrato["id"]

                if contrato_id in existing_contrato_ids:
                    existentes += 1
                    continue

                valor_aluguel = float(contrato.get("valor_aluguel", 0))
                dia_vencimento = int(contrato.get("dia_vencimento", 10))

                # Calculate due date
                try:
                    vencimento = datetime(int(ano), int(mes), min(dia_vencimento, 28))
                except ValueError:
                    vencimento = datetime(int(ano), int(mes), 28)

                novos.append({
                    "org_id": self.org_id,
                    "tipo": "receita",
                    "categoria": "aluguel",
                    "descricao": f"Aluguel {referencia} — Contrato {contrato_id[:8]}",
                    "valor": valor_aluguel,
                    "data_vencimento": vencimento.strftime("%Y-%m-%d"),
                    "status": "pendente",
                    "contrato_id": contrato_id,
                    "cliente_id": contrato.get("cliente_id"),
                    "imovel_id": contrato.get("imovel_id"),
                    "referencia": referencia,
                    "recorrente": True,
                })

            except Exception as e:
                logger.error(f"[RECORRENCIA] Erro ao gerar aluguel: {e}")
                erros += 1

        # Batch-insert all new lancamentos in a single call
        gerados = 0
        if novos:
            try:
                self.db.table("lancamentos").insert(novos).execute()
                gerados = len(novos)
            except Exception as e:
                logger.error(f"[RECORRENCIA] Erro ao inserir aluguéis em lote: {e}")
                erros += len(novos)

        logger.info(
            f"[RECORRENCIA] Aluguéis {referencia}: {gerados} gerados, "
            f"{existentes} existentes, {erros} erros"
        )

        return {
            "referencia": referencia,
            "gerados": gerados,
            "existentes": existentes,
            "erros": erros,
            "total_contratos": len(contratos),
        }

    def gerar_lancamentos_recorrentes(self) -> Dict[str, Any]:
        """
        Process all recurring financial entries and generate next occurrence.

        Looks for lancamentos with recorrente=true that need a new entry
        for the current month.
        """
        hoje = datetime.now(timezone.utc)
        referencia_atual = hoje.strftime("%Y-%m")

        # Fetch recurring lancamentos
        result = self.db.table("lancamentos").select("*").eq(
            "recorrente", True
        ).eq("status", "pago").execute()
        recorrentes = result.data or []

        if not recorrentes:
            return {"gerados": 0, "referencia": referencia_atual}

        # Batch-fetch existing lancamentos for current reference month
        existing_result = self.db.table("lancamentos").select(
            "categoria, descricao"
        ).eq("referencia", referencia_atual).execute()
        existing_keys = {
            (r.get("categoria"), r.get("descricao"))
            for r in (existing_result.data or [])
        }

        # Build list of new lancamentos to batch-insert
        novos = []
        for lanc in recorrentes:
            try:
                key = (lanc.get("categoria"), lanc.get("descricao", ""))
                if key in existing_keys:
                    continue

                # Calculate next due date (same day next month)
                venc_orig = lanc.get("data_vencimento", "")
                if venc_orig:
                    try:
                        dt = datetime.fromisoformat(venc_orig)
                        next_venc = dt.replace(month=hoje.month, year=hoje.year)
                    except (ValueError, TypeError):
                        next_venc = hoje.replace(day=min(hoje.day, 28))
                else:
                    next_venc = hoje.replace(day=min(hoje.day, 28))

                novos.append({
                    "org_id": self.org_id,
                    "tipo": lanc.get("tipo"),
                    "categoria": lanc.get("categoria"),
                    "descricao": lanc.get("descricao"),
                    "valor": lanc.get("valor"),
                    "data_vencimento": next_venc.strftime("%Y-%m-%d"),
                    "status": "pendente",
                    "contrato_id": lanc.get("contrato_id"),
                    "cliente_id": lanc.get("cliente_id"),
                    "imovel_id": lanc.get("imovel_id"),
                    "referencia": referencia_atual,
                    "recorrente": True,
                })

            except Exception as e:
                logger.error(f"[RECORRENCIA] Erro: {e}")

        # Single batch insert for all new lancamentos
        gerados = 0
        if novos:
            try:
                self.db.table("lancamentos").insert(novos).execute()
                gerados = len(novos)
            except Exception as e:
                logger.error(f"[RECORRENCIA] Erro ao inserir recorrentes em lote: {e}")

        return {"gerados": gerados, "referencia": referencia_atual}

    def verificar_inadimplencia(self) -> Dict[str, Any]:
        """
        Check for overdue payments and update their status.

        Returns count of newly marked overdue entries.
        """
        hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Bulk update all pending lancamentos past due date
        lanc_result = self.db.table("lancamentos").update(
            {"status": "atrasado"}
        ).eq("status", "pendente").lt("data_vencimento", hoje).execute()
        lancamentos_atrasados = len(lanc_result.data) if lanc_result.data else 0

        # Bulk update all pending parcelas past due date
        parcelas_result = self.db.table("parcelas_contrato").update(
            {"status": "atrasada"}
        ).eq("status", "pendente").lt("data_vencimento", hoje).execute()
        parcelas_atrasadas = len(parcelas_result.data) if parcelas_result.data else 0

        return {
            "lancamentos_atrasados": lancamentos_atrasados,
            "parcelas_atrasadas": parcelas_atrasadas,
            "total_atualizados": lancamentos_atrasados + parcelas_atrasadas,
        }
