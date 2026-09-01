/**
 * Dashboard — the agency's daily view.
 *
 * Replaces the seed's "Stack Status" scaffold, which reported which framework
 * pieces had booted. That is a useful thing for the reference product to say
 * and a useless thing for an agency to open every morning: it showed zero
 * business data on the first screen after login.
 *
 * Everything here reads a live endpoint. Where a number cannot be trusted yet
 * it says so rather than rendering a confident zero — a dashboard that shows
 * `R$ 0,00` for margin when nobody has entered an hourly rate is not reporting
 * a margin, it is hiding a missing input.
 */
import { Badge, TableSkeleton } from "@noctusai/lib/design-system";
import {
  AlertTriangle,
  BarChart3,
  Building2,
  KanbanSquare,
  Wallet,
} from "lucide-react";
import { Link } from "react-router-dom";

import { useClientes } from "@/hooks/useClientes";
import { useProfissionais } from "@/hooks/useCustos";
import { useDRE, useInadimplentes } from "@/hooks/useFinanceiro";
import { useQuadro } from "@/hooks/useEsteira";

const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

/** Stages still in flight — everything before "pronto para agendamento". */
const EM_PRODUCAO = new Set([
  "aguardando_roteiro",
  "roteiro_em_producao",
  "aguardando_design",
  "design_em_producao",
  "revisao_interna",
]);

export default function Dashboard() {
  const { clientes, loading: carregandoClientes } = useClientes();
  const { quadro, loading: carregandoQuadro } = useQuadro();
  const { profissionais } = useProfissionais();
  const { linhas: dre } = useDRE();
  const { atrasadas: inadimplentes } = useInadimplentes();

  const ativos = clientes.filter((c) => c.status === "ativo").length;
  const inadimplentesCount = clientes.filter((c) => c.status === "inadimplente").length;

  const colunas = quadro?.colunas ?? {};
  const emProducao = Object.entries(colunas)
    .filter(([etapa]) => EM_PRODUCAO.has(etapa))
    .reduce((n, [, tarefas]) => n + (tarefas as unknown[]).length, 0);
  const aguardandoCliente = (colunas["aprovacao_cliente"] as unknown[] | undefined)?.length ?? 0;

  // The margin is only meaningful once hours have a cost. Said out loud rather
  // than shown as a number, because "0%" and "unknown" look identical.
  const semCustoHora = profissionais.filter((p) => p.custo_hora_indefinido).length;
  const semProfissionais = profissionais.length === 0;
  const margemConfiavel = !semProfissionais && semCustoHora === 0;
  const receita = dre.reduce((s, d) => s + d.receita, 0);
  const margem = dre.reduce((s, d) => s + d.margem, 0);

  return (
    <div className="space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold text-foreground">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Visão geral da agência — carteira, produção e financeiro.
        </p>
      </header>

      {/* The one blocker worth interrupting for: without rates, three módulos
          report zero. Linked, not just described. */}
      {(semProfissionais || semCustoHora > 0) && (
        <Link
          to="/custos"
          className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive hover:bg-destructive/10"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            {semProfissionais
              ? "Nenhum profissional com custo/hora cadastrado — a calculadora de escopo, o BI de eficiência e o DRE não conseguem calcular custo real."
              : `${semCustoHora} profissional(is) sem custo/hora — as horas deles não entram no custo real e a margem fica superestimada.`}{" "}
            <span className="underline">Cadastrar em Custos</span>
          </span>
        </Link>
      )}

      {/* ── Indicadores ──────────────────────────────────────────── */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Indicador
          icone={<Building2 className="h-4 w-4" />}
          rotulo="Clientes ativos"
          valor={carregandoClientes ? "—" : String(ativos)}
          nota={inadimplentesCount > 0 ? `${inadimplentesCount} inadimplente(s)` : undefined}
          href="/clientes"
        />
        <Indicador
          icone={<KanbanSquare className="h-4 w-4" />}
          rotulo="Peças em produção"
          valor={carregandoQuadro ? "—" : String(emProducao)}
          nota={aguardandoCliente > 0 ? `${aguardandoCliente} aguardando cliente` : undefined}
          href="/esteira"
        />
        <Indicador
          icone={<Wallet className="h-4 w-4" />}
          rotulo="Receita no mês"
          valor={BRL.format(receita)}
          href="/financeiro"
        />
        <Indicador
          icone={<BarChart3 className="h-4 w-4" />}
          rotulo="Margem no mês"
          valor={margemConfiavel ? BRL.format(margem) : "indisponível"}
          nota={margemConfiavel ? undefined : "sem custo/hora"}
          href="/financeiro"
        />
      </div>

      {/* ── Aprovações pendentes + inadimplência ─────────────────── */}
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-border bg-card p-4">
          <h2 className="mb-3 text-sm font-semibold text-foreground">
            Aguardando aprovação do cliente
          </h2>
          {carregandoQuadro ? (
            <TableSkeleton rows={2} />
          ) : aguardandoCliente === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nada parado com o cliente no momento.
            </p>
          ) : (
            <ul className="space-y-2">
              {((colunas["aprovacao_cliente"] as { id: string; titulo: string; refacoes: number }[]) ?? []).map(
                (t) => (
                  <li key={t.id} className="flex items-center justify-between gap-3 text-sm">
                    <span className="min-w-0 truncate text-foreground">{t.titulo}</span>
                    {t.refacoes > 0 && (
                      <Badge variant="muted">{t.refacoes} refação(ões)</Badge>
                    )}
                  </li>
                ),
              )}
            </ul>
          )}
        </section>

        <section className="rounded-lg border border-border bg-card p-4">
          <h2 className="mb-3 text-sm font-semibold text-foreground">Inadimplência</h2>
          {inadimplentes.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhuma fatura vencida.</p>
          ) : (
            <ul className="space-y-2">
              {inadimplentes.map((i) => (
                <li key={i.fatura_id} className="flex items-center justify-between gap-3 text-sm">
                  <span className="text-foreground">{i.competencia}</span>
                  <span className="text-muted-foreground">
                    {BRL.format(i.valor_total)} · {i.dias_atraso}d
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

function Indicador({
  icone,
  rotulo,
  valor,
  nota,
  href,
}: {
  icone: React.ReactNode;
  rotulo: string;
  valor: string;
  nota?: string;
  href: string;
}) {
  return (
    <Link
      to={href}
      className="rounded-lg border border-border bg-card p-4 transition-colors hover:border-primary/40"
    >
      <p className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
        {icone}
        {rotulo}
      </p>
      <p className="mt-2 text-2xl font-semibold text-foreground">{valor}</p>
      {nota && <p className="mt-1 text-xs text-muted-foreground">{nota}</p>}
    </Link>
  );
}
