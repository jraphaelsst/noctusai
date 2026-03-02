"""
Banco Service — Business logic for bank integration.

Handles bank statement import, reconciliation (manual and automatic),
and CNAB remittance file generation.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.dependencies import first_or_none

logger = logging.getLogger(__name__)


class BancoService:
    """Service for bank integration business logic."""

    def __init__(self, db_client, user_id: str):
        """
        Initialize the service.

        Args:
            db_client: Supabase client (user-authenticated)
            user_id: Current user's ID
        """
        self.db = db_client
        self.user_id = user_id

    def importar_extrato(
        self,
        banco: str,
        agencia: Optional[str],
        conta: Optional[str],
        movimentacoes: List[Dict],
        arquivo_nome: str,
    ) -> Dict[str, Any]:
        """
        Import a bank statement: creates extrato record and bulk inserts movimentacoes.

        Args:
            banco: Bank name or code
            agencia: Branch number (optional)
            conta: Account number (optional)
            movimentacoes: List of dicts with data, descricao, valor, tipo
            arquivo_nome: Name of the imported file

        Returns:
            Summary dict with extrato_id, total_registros, periodo_inicio, periodo_fim
        """
        # Determine period from movimentacoes dates
        datas = sorted([m["data"] for m in movimentacoes])
        periodo_inicio = datas[0] if datas else None
        periodo_fim = datas[-1] if datas else None

        # Create extrato record
        extrato_data = {
            "banco": banco,
            "arquivo_nome": arquivo_nome,
            "total_registros": len(movimentacoes),
            "periodo_inicio": periodo_inicio,
            "periodo_fim": periodo_fim,
        }
        if agencia:
            extrato_data["agencia"] = agencia
        if conta:
            extrato_data["conta"] = conta

        extrato_result = (
            self.db.table("extratos_bancarios")
            .insert(extrato_data)
            .execute()
        )
        extrato_row = first_or_none(extrato_result)
        if not extrato_row:
            raise RuntimeError("Falha ao criar registro de extrato bancario")

        extrato_id = extrato_row["id"]

        # Bulk insert movimentacoes
        movimentacoes_records = []
        for mov in movimentacoes:
            movimentacoes_records.append({
                "extrato_id": extrato_id,
                "data": mov["data"],
                "descricao": mov["descricao"],
                "valor": mov["valor"],
                "tipo": mov["tipo"],
                "conciliado": False,
            })

        if movimentacoes_records:
            self.db.table("movimentacoes_bancarias").insert(movimentacoes_records).execute()

        # Calculate totals
        total_creditos = sum(m["valor"] for m in movimentacoes if m["tipo"] == "credito")
        total_debitos = sum(m["valor"] for m in movimentacoes if m["tipo"] == "debito")

        return {
            "extrato_id": extrato_id,
            "banco": banco,
            "arquivo_nome": arquivo_nome,
            "total_registros": len(movimentacoes),
            "periodo_inicio": periodo_inicio,
            "periodo_fim": periodo_fim,
            "total_creditos": round(total_creditos, 2),
            "total_debitos": round(total_debitos, 2),
            "saldo_periodo": round(total_creditos - total_debitos, 2),
        }

    def get_pendentes_conciliacao(self) -> List[Dict]:
        """
        Return all unmatched movimentacoes (conciliado=false).

        Returns:
            List of movimentacao dicts pending reconciliation
        """
        result = (
            self.db.table("movimentacoes_bancarias")
            .select("*")
            .eq("conciliado", False)
            .order("data", desc=True)
            .execute()
        )
        return result.data or []

    def conciliar(self, movimentacao_id: str, lancamento_id: str) -> Dict[str, Any]:
        """
        Link a bank movimentacao to a lancamento financeiro and mark as reconciled.

        Args:
            movimentacao_id: ID of the bank movimentacao
            lancamento_id: ID of the corresponding lancamento

        Returns:
            Updated movimentacao record

        Raises:
            ValueError: If movimentacao or lancamento is not found
        """
        # Verify movimentacao exists
        mov_result = (
            self.db.table("movimentacoes_bancarias")
            .select("*")
            .eq("id", movimentacao_id)
            .single()
            .execute()
        )
        if not mov_result.data:
            raise ValueError("Movimentacao bancaria nao encontrada")

        # Verify lancamento exists
        lanc_result = (
            self.db.table("lancamentos")
            .select("id")
            .eq("id", lancamento_id)
            .single()
            .execute()
        )
        if not lanc_result.data:
            raise ValueError("Lancamento financeiro nao encontrado")

        # Update movimentacao with link and mark as reconciled
        update_result = (
            self.db.table("movimentacoes_bancarias")
            .update({
                "conciliado": True,
                "lancamento_id": lancamento_id,
            })
            .eq("id", movimentacao_id)
            .execute()
        )

        return first_or_none(update_result)

    def auto_conciliar(self, extrato_id: str) -> Dict[str, Any]:
        """
        Attempt automatic reconciliation by matching amount and date
        between movimentacoes of an extrato and lancamentos.

        Matches credito movimentacoes to receita lancamentos and
        debito movimentacoes to despesa lancamentos, using exact
        valor and data correspondence.

        Args:
            extrato_id: ID of the extrato to auto-reconcile

        Returns:
            Summary with total_conciliados and total_pendentes counts
        """
        # Fetch unreconciled movimentacoes for this extrato
        mov_result = (
            self.db.table("movimentacoes_bancarias")
            .select("*")
            .eq("extrato_id", extrato_id)
            .eq("conciliado", False)
            .execute()
        )
        movimentacoes = mov_result.data or []

        if not movimentacoes:
            return {"total_conciliados": 0, "total_pendentes": 0}

        # Fetch all pending lancamentos for matching
        lanc_result = (
            self.db.table("lancamentos")
            .select("id, tipo, valor, data_vencimento")
            .eq("status", "pendente")
            .execute()
        )
        lancamentos = lanc_result.data or []

        # Build lookup: (tipo_lanc, valor, data) -> list of lancamento IDs
        # Map: credito -> receita, debito -> despesa
        tipo_map = {"credito": "receita", "debito": "despesa"}
        lanc_lookup: Dict[tuple, List[str]] = {}
        for lanc in lancamentos:
            key = (lanc["tipo"], float(lanc["valor"]), lanc["data_vencimento"])
            if key not in lanc_lookup:
                lanc_lookup[key] = []
            lanc_lookup[key].append(lanc["id"])

        # Track used lancamento IDs to avoid double matching
        used_lancamento_ids: set = set()
        total_conciliados = 0

        for mov in movimentacoes:
            tipo_lanc = tipo_map.get(mov["tipo"])
            if not tipo_lanc:
                continue

            key = (tipo_lanc, float(mov["valor"]), mov["data"])
            candidates = lanc_lookup.get(key, [])

            # Find first unused candidate
            matched_id = None
            for cid in candidates:
                if cid not in used_lancamento_ids:
                    matched_id = cid
                    break

            if matched_id:
                try:
                    self.db.table("movimentacoes_bancarias").update({
                        "conciliado": True,
                        "lancamento_id": matched_id,
                    }).eq("id", mov["id"]).execute()

                    used_lancamento_ids.add(matched_id)
                    total_conciliados += 1
                except Exception as e:
                    logger.warning(
                        f"Falha ao auto-conciliar movimentacao {mov['id']}: {e}"
                    )

        total_pendentes = len(movimentacoes) - total_conciliados

        return {
            "total_conciliados": total_conciliados,
            "total_pendentes": total_pendentes,
        }

    def gerar_remessa(
        self,
        tipo: str,
        banco: str,
        titulos: List[Dict],
    ) -> Dict[str, Any]:
        """
        Create a remessa record with titulo data and return generated file info.

        Args:
            tipo: Remittance type ('cnab240' or 'cnab400')
            banco: Bank name or code
            titulos: List of dicts with valor, vencimento, sacado_nome, sacado_cpf

        Returns:
            Dict with remessa_id, arquivo_nome, total_titulos, valor_total, status
        """
        valor_total = sum(t["valor"] for t in titulos)
        total_titulos = len(titulos)

        # Generate file name
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        arquivo_nome = f"remessa_{tipo}_{banco}_{timestamp}.rem"

        # Create remessa record
        remessa_data = {
            "tipo": tipo,
            "banco": banco,
            "arquivo_nome": arquivo_nome,
            "total_titulos": total_titulos,
            "valor_total": round(valor_total, 2),
            "status": "gerado",
        }

        remessa_result = (
            self.db.table("remessas")
            .insert(remessa_data)
            .execute()
        )
        remessa_row = first_or_none(remessa_result)
        if not remessa_row:
            raise RuntimeError("Falha ao criar registro de remessa")

        remessa_id = remessa_row["id"]

        return {
            "remessa_id": remessa_id,
            "tipo": tipo,
            "banco": banco,
            "arquivo_nome": arquivo_nome,
            "total_titulos": total_titulos,
            "valor_total": round(valor_total, 2),
            "status": "gerado",
            "titulos": titulos,
        }
