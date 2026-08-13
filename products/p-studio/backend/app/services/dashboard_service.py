"""Dashboard executivo — os nove indicadores da spec § 1.

Tudo aqui é agregação sobre as outras tabelas; o dashboard não tem tabela
própria. No protótipo esses nove números eram literais num arquivo TypeScript,
o que é precisamente o que um backend existe para resolver.

Volume: um estúdio faz dezenas de captações por mês, não milhões. Carregar as
tabelas e agregar em Python é mais simples e mais legível do que espalhar a
lógica por views SQL — e mantém os testes sem banco. Se o volume mudar de
ordem de grandeza, o lugar de trocar por SQL agregado é este arquivo.
"""
from collections import Counter
from datetime import date, timedelta

from app.database import execute
from app.schemas.negocios import ETAPA_LABELS, ETAPAS
from app.services.base import CrudService
from app.services.financeiro_service import status_exibido

MESES_PT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
            "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

# Um serviço está "em andamento" quando saiu da captação e ainda não foi
# entregue — é o que o estúdio precisa produzir agora.
ETAPAS_EM_ANDAMENTO = ("captado", "backup", "selecao", "edicao", "revisao")


def _para_data(valor) -> date | None:
    if not valor:
        return None
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


class DashboardService(CrudService):
    table = "negocios"  # não usado diretamente; o service agrega várias

    def montar(self, hoje: date | None = None) -> dict:
        hoje = hoje or date.today()
        inicio_mes = hoje.replace(day=1)

        negocios = execute(self.db.table("negocios").select("*")).data or []
        captacoes = execute(self.db.table("captacoes").select("*")).data or []
        producoes = execute(self.db.table("producoes").select("*")).data or []
        lancamentos = execute(self.db.table("lancamentos").select("*")).data or []

        return {
            "captacoes_mes": self._captacoes_mes(captacoes, inicio_mes, hoje),
            "entregas_mes": self._entregas_mes(producoes, inicio_mes, hoje),
            "servicos_andamento": sum(
                1 for p in producoes if p.get("etapa") in ETAPAS_EM_ANDAMENTO
            ),
            "faturamento_mes": self._faturamento_mes(lancamentos, inicio_mes, hoje),
            "a_receber": self._a_receber(lancamentos, hoje),
            "ticket_medio": self._ticket_medio(negocios),
            "clientes_ativos": self._clientes_ativos(negocios, hoje),
            "prazo_medio_dias": self._prazo_medio(producoes, captacoes),
            "taxa_recorrencia": self._taxa_recorrencia(negocios),
            "receita_por_mes": self._receita_por_mes(lancamentos, hoje),
            "captacoes_por_semana": self._captacoes_por_semana(captacoes, hoje),
            "funil": self._funil(negocios),
        }

    # ── indicadores ──────────────────────────────────────────────────────
    @staticmethod
    def _captacoes_mes(captacoes: list[dict], inicio: date, hoje: date) -> int:
        return sum(
            1
            for c in captacoes
            if (d := _para_data(c.get("data")))
            and inicio <= d <= hoje
            and c.get("status") != "cancelado"
        )

    @staticmethod
    def _entregas_mes(producoes: list[dict], inicio: date, hoje: date) -> int:
        return sum(
            1
            for p in producoes
            if (d := _para_data(p.get("entregue_em"))) and inicio <= d <= hoje
        )

    @staticmethod
    def _faturamento_mes(lancamentos: list[dict], inicio: date, hoje: date) -> float:
        total = sum(
            float(l.get("valor") or 0)
            for l in lancamentos
            if l.get("status") == "recebido"
            and (d := _para_data(l.get("pago_em")))
            and inicio <= d <= hoje
        )
        return round(total, 2)

    @staticmethod
    def _a_receber(lancamentos: list[dict], hoje: date) -> float:
        total = sum(
            float(l.get("valor") or 0)
            for l in lancamentos
            if status_exibido(l, hoje) in ("a_faturar", "faturado", "atrasado")
        )
        return round(total, 2)

    @staticmethod
    def _ticket_medio(negocios: list[dict]) -> float:
        # Só negócios ganhos: incluir leads e orçamentos perdidos puxaria o
        # ticket para baixo e o número deixaria de significar o que o estúdio
        # cobra de fato.
        ganhos = [
            float(n.get("valor") or 0)
            for n in negocios
            if n.get("etapa") in ("aprovado", "agendamento", "producao",
                                  "entregue", "recebido", "arquivado")
        ]
        return round(sum(ganhos) / len(ganhos), 2) if ganhos else 0.0

    @staticmethod
    def _clientes_ativos(negocios: list[dict], hoje: date) -> int:
        """Clientes com negócio nos últimos 90 dias.

        Janela em vez de flag: um cadastro marcado `ativo` que não compra há
        um ano não é um cliente ativo do ponto de vista da operação.
        """
        corte = hoje - timedelta(days=90)
        return len(
            {
                n["cliente_id"]
                for n in negocios
                if n.get("cliente_id")
                and (d := _para_data(n.get("created_at")))
                and d >= corte
            }
        )

    @staticmethod
    def _prazo_medio(producoes: list[dict], captacoes: list[dict]) -> float | None:
        """Dias entre a captação e a entrega, na média.

        Precisa das duas pontas: produções entregues sem captação vinculada
        não têm marco inicial e ficam de fora em vez de entrar como zero.
        """
        por_id = {c["id"]: c for c in captacoes}
        dias: list[int] = []
        for p in producoes:
            entrega = _para_data(p.get("entregue_em"))
            captacao = por_id.get(p.get("captacao_id"))
            inicio = _para_data(captacao.get("data")) if captacao else None
            if entrega and inicio and entrega >= inicio:
                dias.append((entrega - inicio).days)
        return round(sum(dias) / len(dias), 1) if dias else None

    @staticmethod
    def _taxa_recorrencia(negocios: list[dict]) -> float:
        """Fração de clientes que contrataram mais de uma vez (spec § 1)."""
        contagem = Counter(n["cliente_id"] for n in negocios if n.get("cliente_id"))
        if not contagem:
            return 0.0
        recorrentes = sum(1 for qtd in contagem.values() if qtd > 1)
        return round(recorrentes / len(contagem), 4)

    # ── séries ───────────────────────────────────────────────────────────
    @staticmethod
    def _receita_por_mes(lancamentos: list[dict], hoje: date, meses: int = 6) -> list[dict]:
        chaves: list[tuple[int, int]] = []
        ano, mes = hoje.year, hoje.month
        for _ in range(meses):
            chaves.append((ano, mes))
            mes -= 1
            if mes == 0:
                ano, mes = ano - 1, 12
        chaves.reverse()

        acumulado: dict[tuple[int, int], float] = {k: 0.0 for k in chaves}
        for l in lancamentos:
            if l.get("status") != "recebido":
                continue
            d = _para_data(l.get("pago_em"))
            if d and (d.year, d.month) in acumulado:
                acumulado[(d.year, d.month)] += float(l.get("valor") or 0)

        return [
            {
                "mes": f"{a:04d}-{m:02d}",
                "label": MESES_PT[m - 1],
                "valor": round(acumulado[(a, m)], 2),
            }
            for a, m in chaves
        ]

    @staticmethod
    def _captacoes_por_semana(captacoes: list[dict], hoje: date) -> list[dict]:
        """Quatro semanas corridas terminando hoje (S1 = a mais antiga)."""
        inicio = hoje - timedelta(days=27)
        baldes = [0, 0, 0, 0]
        for c in captacoes:
            d = _para_data(c.get("data"))
            if d and inicio <= d <= hoje and c.get("status") != "cancelado":
                baldes[min((d - inicio).days // 7, 3)] += 1
        return [{"semana": f"S{i + 1}", "captacoes": n} for i, n in enumerate(baldes)]

    @staticmethod
    def _funil(negocios: list[dict]) -> list[dict]:
        resumo = {e: {"quantidade": 0, "valor": 0.0} for e in ETAPAS}
        for n in negocios:
            etapa = n.get("etapa")
            if etapa in resumo:
                resumo[etapa]["quantidade"] += 1
                resumo[etapa]["valor"] += float(n.get("valor") or 0)
        return [
            {
                "etapa": e,
                "label": ETAPA_LABELS[e],
                "quantidade": resumo[e]["quantidade"],
                "valor": round(resumo[e]["valor"], 2),
            }
            for e in ETAPAS
        ]


class ClienteMetricasService(CrudService):
    """Histórico consolidado por cliente (spec § 8).

    O protótipo mostrava esses números vindos de `mock-data.ts` ao lado de
    clientes reais — a tela misturava cadastro verdadeiro com métrica
    fictícia. Aqui saem dos dados.
    """

    table = "clientes"
    order_by = "nome"
    order_desc = False

    def metricas(self, hoje: date | None = None) -> list[dict]:
        hoje = hoje or date.today()
        clientes = self.listar(incluir_inativos=True)
        negocios = execute(self.db.table("negocios").select("*")).data or []
        imoveis = execute(self.db.table("imoveis").select("id,cliente_id")).data or []
        lancamentos = execute(self.db.table("lancamentos").select("*")).data or []

        resultado = []
        for cliente in clientes:
            cid = cliente["id"]
            meus_negocios = [n for n in negocios if n.get("cliente_id") == cid]
            recebido = sum(
                float(l.get("valor") or 0)
                for l in lancamentos
                if l.get("cliente_id") == cid and l.get("status") == "recebido"
            )
            datas = sorted(
                d for n in meus_negocios if (d := _para_data(n.get("created_at")))
            )

            resultado.append(
                {
                    "cliente_id": cid,
                    "nome": cliente["nome"],
                    "empresa": cliente.get("empresa"),
                    "faturamento_total": round(recebido, 2),
                    "total_servicos": len(meus_negocios),
                    "total_imoveis": sum(1 for i in imoveis if i.get("cliente_id") == cid),
                    "ticket_medio": round(recebido / len(meus_negocios), 2)
                    if meus_negocios
                    else 0.0,
                    "ultimo_servico": datas[-1].isoformat() if datas else None,
                    "frequencia_mensal": self._frequencia(datas, hoje),
                }
            )
        return resultado

    @staticmethod
    def _frequencia(datas: list[date], hoje: date) -> float:
        """Negócios por mês desde o primeiro contrato.

        Mede ritmo, não volume: dois clientes com dez negócios cada são
        diferentes se um os fez em seis meses e o outro em três anos.
        """
        if not datas:
            return 0.0
        meses = max((hoje - datas[0]).days / 30.0, 1.0)
        return round(len(datas) / meses, 2)
