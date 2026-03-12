"""
BI Service — Business Intelligence aggregation and analytics.

Pure computation on lists of dicts fetched from existing tables.
No direct database access — all data is passed in by the router.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BIService:
    """Service for BI dashboard analytics and aggregation."""

    def __init__(self, db_client, user_id: str):
        self.db = db_client
        self.user_id = user_id

    def get_vendas_analytics(
        self,
        propostas: List[Dict],
        lancamentos: List[Dict],
        periodo_inicio: Optional[str] = None,
        periodo_fim: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calculate sales analytics from proposals and financial transactions.

        Returns dict with total_vendas, ticket_medio, taxa_conversao,
        tempo_medio_fechamento, and vendas_por_mes breakdown.
        """
        # Filter proposals within the period
        propostas_periodo = self._filter_by_periodo(propostas, periodo_inicio, periodo_fim, date_field="created_at")

        total_propostas = len(propostas_periodo)
        vendas_aceitas = [p for p in propostas_periodo if p.get("status") == "aceita"]
        total_vendas = len(vendas_aceitas)

        # Ticket medio from accepted proposals
        valores_venda = [float(p.get("valor_proposta", 0)) for p in vendas_aceitas]
        ticket_medio = sum(valores_venda) / len(valores_venda) if valores_venda else 0.0

        # Conversion rate
        taxa_conversao = (total_vendas / total_propostas * 100) if total_propostas > 0 else 0.0

        # Average time to close (days between created_at and updated_at for accepted)
        tempos = []
        for p in vendas_aceitas:
            created = p.get("created_at", "")
            updated = p.get("updated_at", "")
            if created and updated:
                try:
                    dt_created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    dt_updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    dias = (dt_updated - dt_created).days
                    if dias >= 0:
                        tempos.append(dias)
                except (ValueError, TypeError):
                    continue
        tempo_medio_fechamento = sum(tempos) / len(tempos) if tempos else 0.0

        # Sales by month from accepted proposals
        vendas_por_mes: Dict[str, Dict[str, Any]] = {}
        for p in vendas_aceitas:
            date_str = p.get("created_at", "")
            if not date_str:
                continue
            mes = date_str[:7]
            if mes not in vendas_por_mes:
                vendas_por_mes[mes] = {"mes": mes, "quantidade": 0, "valor_total": 0.0}
            vendas_por_mes[mes]["quantidade"] += 1
            vendas_por_mes[mes]["valor_total"] += float(p.get("valor_proposta", 0))

        vendas_por_mes_list = sorted(vendas_por_mes.values(), key=lambda x: x["mes"])

        return {
            "total_vendas": total_vendas,
            "valor_total": sum(valores_venda),
            "ticket_medio": round(ticket_medio, 2),
            "taxa_conversao": round(taxa_conversao, 2),
            "tempo_medio_fechamento": round(tempo_medio_fechamento, 1),
            "total_propostas": total_propostas,
            "vendas_por_mes": vendas_por_mes_list,
        }

    def get_captacao_analytics(self, clientes: List[Dict]) -> Dict[str, Any]:
        """
        Aggregate lead acquisition metrics from client data.

        Returns dict with total_leads, leads_por_origem, custo_por_lead,
        leads_por_mes, and taxa_conversao_por_origem.
        """
        total_leads = len(clientes)

        # Leads by origin
        origens: Dict[str, int] = {}
        for c in clientes:
            origem = c.get("origem") or "Desconhecida"
            origens[origem] = origens.get(origem, 0) + 1

        leads_por_origem = [
            {"origem": k, "quantidade": v}
            for k, v in sorted(origens.items(), key=lambda x: x[1], reverse=True)
        ]

        # Leads by month (based on created_at)
        leads_mensal: Dict[str, int] = {}
        for c in clientes:
            date_str = c.get("created_at", "")
            if not date_str:
                continue
            mes = date_str[:7]
            leads_mensal[mes] = leads_mensal.get(mes, 0) + 1

        leads_por_mes = [
            {"mes": k, "quantidade": v}
            for k, v in sorted(leads_mensal.items())
        ]

        # Conversion rate by origin
        # Consider clients with etapa_atual == "fechamento" or "venda" as converted
        etapas_conversao = {"fechamento", "venda", "contrato", "concluido"}
        conversoes_por_origem: Dict[str, Dict[str, int]] = {}
        for c in clientes:
            origem = c.get("origem") or "Desconhecida"
            if origem not in conversoes_por_origem:
                conversoes_por_origem[origem] = {"total": 0, "convertidos": 0}
            conversoes_por_origem[origem]["total"] += 1
            etapa = (c.get("etapa_atual") or "").lower()
            if etapa in etapas_conversao:
                conversoes_por_origem[origem]["convertidos"] += 1

        taxa_conversao_por_origem = [
            {
                "origem": k,
                "total": v["total"],
                "convertidos": v["convertidos"],
                "taxa_conversao": round(v["convertidos"] / v["total"] * 100, 2) if v["total"] > 0 else 0.0,
            }
            for k, v in sorted(conversoes_por_origem.items(), key=lambda x: x[1]["total"], reverse=True)
        ]

        # Cost per lead placeholder (requires marketing spend data not yet tracked)
        custo_por_lead = 0.0

        return {
            "total_leads": total_leads,
            "leads_por_origem": leads_por_origem,
            "custo_por_lead": custo_por_lead,
            "leads_por_mes": leads_por_mes,
            "taxa_conversao_por_origem": taxa_conversao_por_origem,
        }

    def get_corretores_analytics(
        self,
        propostas: List[Dict],
        comissoes: List[Dict],
    ) -> List[Dict[str, Any]]:
        """
        Rank brokers by performance metrics.

        Returns list of dicts, each with corretor_id, nome, vendas,
        valor_total, comissao_total, atendimentos, taxa_conversao.
        """
        corretores: Dict[str, Dict[str, Any]] = {}

        # Aggregate proposals per broker
        for p in propostas:
            cid = p.get("corretor_id")
            if not cid:
                continue
            if cid not in corretores:
                corretores[cid] = {
                    "corretor_id": cid,
                    "nome": "",
                    "vendas": 0,
                    "valor_total": 0.0,
                    "comissao_total": 0.0,
                    "atendimentos": 0,
                }
            corretores[cid]["atendimentos"] += 1
            if p.get("status") == "aceita":
                corretores[cid]["vendas"] += 1
                corretores[cid]["valor_total"] += float(p.get("valor_proposta", 0))

        # Add commission data from splits
        for c in comissoes:
            splits = c.get("splits") or []
            if isinstance(splits, list):
                for s in splits:
                    cid = s.get("corretor_id")
                    if cid and cid in corretores:
                        corretores[cid]["comissao_total"] += float(s.get("valor", 0))
                        if not corretores[cid]["nome"]:
                            corretores[cid]["nome"] = s.get("corretor_nome", "")

            # Also check top-level commission if no splits
            if not splits:
                # Commission without splits — try to attribute via venda linkage
                pass

        # Calculate conversion rate per broker
        result = []
        for data in corretores.values():
            atendimentos = data["atendimentos"]
            vendas = data["vendas"]
            data["taxa_conversao"] = round(vendas / atendimentos * 100, 2) if atendimentos > 0 else 0.0
            result.append(data)

        # Sort by valor_total descending
        result.sort(key=lambda x: x["valor_total"], reverse=True)

        return result

    def get_imoveis_analytics(self, ativos: List[Dict]) -> Dict[str, Any]:
        """
        Property portfolio analytics.

        Returns dict with total_ativos, media_dias_mercado, preco_m2_medio,
        distribuicao_tipo, distribuicao_status, imoveis_por_bairro.
        """
        total_ativos = len(ativos)

        # Average days on market (from created_at to now for active properties)
        now = datetime.utcnow()
        dias_mercado = []
        for a in ativos:
            if a.get("status") == "ativo":
                created = a.get("created_at", "")
                if created:
                    try:
                        dt_created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        dias = (now - dt_created.replace(tzinfo=None)).days
                        if dias >= 0:
                            dias_mercado.append(dias)
                    except (ValueError, TypeError):
                        continue
        media_dias_mercado = round(sum(dias_mercado) / len(dias_mercado), 1) if dias_mercado else 0.0

        # Price per sqm average
        precos_m2 = []
        for a in ativos:
            valor = float(a.get("valor", 0))
            area = float(a.get("area_total", 0) or a.get("area_privativa", 0) or 0)
            if valor > 0 and area > 0:
                precos_m2.append(valor / area)
        preco_m2_medio = round(sum(precos_m2) / len(precos_m2), 2) if precos_m2 else 0.0

        # Distribution by property type
        tipos: Dict[str, int] = {}
        for a in ativos:
            tipo = a.get("tipo_imovel") or a.get("natureza") or "Outro"
            tipos[tipo] = tipos.get(tipo, 0) + 1

        distribuicao_tipo = [
            {"tipo": k, "quantidade": v}
            for k, v in sorted(tipos.items(), key=lambda x: x[1], reverse=True)
        ]

        # Distribution by status
        statuses: Dict[str, int] = {}
        for a in ativos:
            status = a.get("status") or "indefinido"
            statuses[status] = statuses.get(status, 0) + 1

        distribuicao_status = [
            {"status": k, "quantidade": v}
            for k, v in sorted(statuses.items(), key=lambda x: x[1], reverse=True)
        ]

        # Properties by neighborhood
        bairros: Dict[str, int] = {}
        for a in ativos:
            bairro = a.get("bairro") or "Sem bairro"
            bairros[bairro] = bairros.get(bairro, 0) + 1

        imoveis_por_bairro = [
            {"bairro": k, "quantidade": v}
            for k, v in sorted(bairros.items(), key=lambda x: x[1], reverse=True)
        ]

        return {
            "total_ativos": total_ativos,
            "media_dias_mercado": media_dias_mercado,
            "preco_m2_medio": preco_m2_medio,
            "distribuicao_tipo": distribuicao_tipo,
            "distribuicao_status": distribuicao_status,
            "imoveis_por_bairro": imoveis_por_bairro,
        }

    def get_financeiro_analytics(
        self,
        lancamentos: List[Dict],
        periodo_inicio: Optional[str] = None,
        periodo_fim: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Financial overview analytics.

        Returns dict with receita_total, despesa_total, saldo,
        previsao_receita, despesas_por_categoria, receitas_por_mes.
        """
        # Filter by period
        filtered = self._filter_by_periodo(lancamentos, periodo_inicio, periodo_fim, date_field="data_vencimento")

        receita_total = 0.0
        despesa_total = 0.0
        despesas_cat: Dict[str, float] = {}
        receitas_mensal: Dict[str, float] = {}

        for l in filtered:
            valor = float(l.get("valor", 0))
            tipo = l.get("tipo")

            if tipo == "receita":
                if l.get("status") == "pago":
                    receita_total += valor
                # Receitas by month
                date_str = l.get("data_pagamento") or l.get("data_vencimento", "")
                if date_str:
                    mes = date_str[:7]
                    receitas_mensal[mes] = receitas_mensal.get(mes, 0) + valor

            elif tipo == "despesa":
                if l.get("status") == "pago":
                    despesa_total += valor
                # Expenses by category
                cat = l.get("categoria") or "Outros"
                despesas_cat[cat] = despesas_cat.get(cat, 0) + valor

        saldo = receita_total - despesa_total

        # Revenue forecast: sum of pending receitas
        previsao_receita = sum(
            float(l.get("valor", 0))
            for l in filtered
            if l.get("tipo") == "receita" and l.get("status") == "pendente"
        )

        despesas_por_categoria = [
            {"categoria": k, "valor": round(v, 2)}
            for k, v in sorted(despesas_cat.items(), key=lambda x: x[1], reverse=True)
        ]

        receitas_por_mes = [
            {"mes": k, "valor": round(v, 2)}
            for k, v in sorted(receitas_mensal.items())
        ]

        return {
            "receita_total": round(receita_total, 2),
            "despesa_total": round(despesa_total, 2),
            "saldo": round(saldo, 2),
            "previsao_receita": round(previsao_receita, 2),
            "despesas_por_categoria": despesas_por_categoria,
            "receitas_por_mes": receitas_por_mes,
        }

    def get_dashboard_resumo(
        self,
        clientes: List[Dict],
        ativos: List[Dict],
        propostas: List[Dict],
        lancamentos: List[Dict],
        contratos: List[Dict],
        eventos: List[Dict],
        negociacoes: List[Dict],
    ) -> Dict[str, Any]:
        """
        Comprehensive dashboard summary — aggregates key metrics from all modules.

        Returns a single payload with: sales KPIs, funnel stats, financial summary,
        property portfolio counts, pending tasks, and recent activity.
        """
        from datetime import timezone

        now = datetime.now(timezone.utc)
        hoje = now.strftime("%Y-%m-%d")
        mes_atual = now.strftime("%Y-%m")

        # -- KPIs --
        total_clientes = len(clientes)
        clientes_novos_mes = sum(
            1 for c in clientes
            if (c.get("created_at") or "")[:7] == mes_atual
        )

        imoveis_ativos = sum(1 for a in ativos if a.get("natureza") == "imovel" and a.get("status") == "ativo")
        total_imoveis = sum(1 for a in ativos if a.get("natureza") == "imovel")

        propostas_abertas = sum(1 for p in propostas if p.get("status") in ("rascunho", "enviada"))
        propostas_aceitas = sum(1 for p in propostas if p.get("status") == "aceita")
        valor_vendas = sum(float(p.get("valor_proposta", 0)) for p in propostas if p.get("status") == "aceita")

        # -- Funil --
        etapas_funil: Dict[str, int] = {}
        for c in clientes:
            etapa = c.get("etapa_atual") or "sem_etapa"
            etapas_funil[etapa] = etapas_funil.get(etapa, 0) + 1

        # -- Financeiro --
        receitas_mes = sum(
            float(l.get("valor", 0)) for l in lancamentos
            if l.get("tipo") == "receita" and l.get("status") == "pago"
            and (l.get("data_vencimento") or "")[:7] == mes_atual
        )
        despesas_mes = sum(
            float(l.get("valor", 0)) for l in lancamentos
            if l.get("tipo") == "despesa" and l.get("status") == "pago"
            and (l.get("data_vencimento") or "")[:7] == mes_atual
        )
        vencidos = sum(
            1 for l in lancamentos
            if l.get("status") == "pendente" and (l.get("data_vencimento") or "") < hoje
        )
        a_receber = sum(
            float(l.get("valor", 0)) for l in lancamentos
            if l.get("tipo") == "receita" and l.get("status") == "pendente"
        )

        # -- Contratos --
        contratos_ativos = sum(1 for c in contratos if c.get("status") == "ativo")

        # -- Agenda --
        eventos_hoje = sum(
            1 for e in eventos
            if (e.get("data_inicio") or "")[:10] == hoje and e.get("status") == "agendado"
        )

        # -- Negociacoes --
        negociacoes_abertas = sum(
            1 for n in negociacoes
            if n.get("status_etapa") in ("qualificacao", "visitas", "proposta", "negociacao")
        )

        return {
            "kpis": {
                "total_clientes": total_clientes,
                "clientes_novos_mes": clientes_novos_mes,
                "imoveis_ativos": imoveis_ativos,
                "total_imoveis": total_imoveis,
                "propostas_abertas": propostas_abertas,
                "propostas_aceitas": propostas_aceitas,
                "valor_vendas": round(valor_vendas, 2),
                "contratos_ativos": contratos_ativos,
                "negociacoes_abertas": negociacoes_abertas,
                "eventos_hoje": eventos_hoje,
            },
            "funil": etapas_funil,
            "financeiro": {
                "receitas_mes": round(receitas_mes, 2),
                "despesas_mes": round(despesas_mes, 2),
                "saldo_mes": round(receitas_mes - despesas_mes, 2),
                "a_receber": round(a_receber, 2),
                "vencidos": vencidos,
            },
        }

    # --- Private helpers ---

    def _filter_by_periodo(
        self,
        items: List[Dict],
        periodo_inicio: Optional[str],
        periodo_fim: Optional[str],
        date_field: str = "created_at",
    ) -> List[Dict]:
        """
        Filter a list of dicts by a date range on the given field.

        Date strings are compared lexicographically (works for ISO 8601 format).
        """
        if not periodo_inicio and not periodo_fim:
            return items

        filtered = []
        for item in items:
            date_str = item.get(date_field, "")
            if not date_str:
                continue
            # Normalize: use only the date portion for comparison
            date_val = date_str[:10]
            if periodo_inicio and date_val < periodo_inicio:
                continue
            if periodo_fim and date_val > periodo_fim:
                continue
            filtered.append(item)

        return filtered
