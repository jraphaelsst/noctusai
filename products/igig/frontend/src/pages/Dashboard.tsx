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
 *
 * TWO-SIGNAL LOADING (achado: live smoke finding). The red "Nenhum
 * profissional com custo/hora cadastrado" banner and the "R$ 0,00" receita
 * used to render WHILE `useProfissionais()`/`useDRE()` were still on their
 * first fetch — `profissionais.length === 0` is indistinguishable from "no
 * profissionais yet" and "haven't loaded any profissionais yet" unless the
 * loading flag is checked too. Every number/banner below is gated on its own
 * query's `showSkeleton`/`loading` (`isPending && !data`, never a bare
 * `isFetching` and never `isLoading`), per `KB § PATTERNS/frontend/
 * lying-loading-state.md`.
 */
import { Badge, TableSkeleton } from "@noctusai/lib/design-system";
import {
  AlertTriangle,
  BarChart3,
  Briefcase,
  Building2,
  KanbanSquare,
  Trophy,
  Wallet,
} from "lucide-react";
import { Link } from "react-router-dom";

import { useClientes } from "@/hooks/useClientes";
import { useProfissionais } from "@/hooks/useCustos";
import { useDRE, useInadimplentes } from "@/hooks/useFinanceiro";
import { esteiraPipeline } from "@/hooks/useEsteira";
import { PAPEL_APROVACAO_CLIENTE } from "@/components/esteira/moveRules";
import { describeError } from "@/lib/errors";
import { comercialPipeline } from "@/lib/pipelines";

const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

/** Current competência ('YYYY-MM') in the agency's own timezone — never the
 * browser's. `Financeiro.tsx` has its own `competenciaAtual()` using a bare
 * `new Date()` (not TZ-aware, and not exported); both should eventually
 * share one helper — flagged as scoped-improvement, out of this file's
 * ownership. */
function competenciaAtualSP(): string {
  const partes = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo",
    year: "numeric",
    month: "2-digit",
  }).formatToParts(new Date());
  const ano = partes.find((p) => p.type === "year")?.value ?? "0000";
  const mes = partes.find((p) => p.type === "month")?.value ?? "01";
  return `${ano}-${mes}`;
}

const COMPETENCIA_ATUAL = competenciaAtualSP();

export default function Dashboard() {
  // ── Carteira ────────────────────────────────────────────────────────
  // Server-side counts (`.total`), never the 50-capped `.itens` list — a
  // count derived from a paged page silently undercounts past the first
  // page (achado #7 / plat#5).
  const clientesAtivos = useClientes({ status: "ativo" });
  const clientesInadimplentes = useClientes({ status: "inadimplente" });

  // ── Produção ────────────────────────────────────────────────────────
  // Same query (and cache entry) as the Esteira page's unfiltered board.
  const { data: colunasEsteira, isPending: quadroPendente } = esteiraPipeline.useBoard();
  const carregandoQuadro = quadroPendente && !colunasEsteira;

  // ── Comercial (achado #21: the Dashboard showed nothing from the funil) ──
  const { data: colunasComercial, isPending: comercialPendente } = comercialPipeline.useBoard();
  const carregandoComercial = comercialPendente && !colunasComercial;
  const negociosDoBoard = (colunasComercial ?? []).flatMap((c) => c.cards);
  const negociosAbertos = negociosDoBoard.filter((n) => n.status === "aberto");
  const valorEmNegociacao = negociosAbertos.reduce((s, n) => s + (n.valor_estimado ?? 0), 0);
  const ganhosNoMes = negociosDoBoard.filter(
    (n) => n.status === "ganho" && (n.ganho_em ?? "").slice(0, 7) === COMPETENCIA_ATUAL,
  );

  // ── Custos / financeiro ─────────────────────────────────────────────
  const profissionaisQuery = useProfissionais();
  const { profissionais, loading: carregandoProfissionais } = profissionaisQuery;
  const { linhas: dre, loading: carregandoDRE } = useDRE(COMPETENCIA_ATUAL);
  const {
    atrasadas: inadimplentes,
    loading: carregandoInadimplentes,
    isError: erroInadimplentes,
    error: erroInadimplentesMsg,
  } = useInadimplentes();

  // Stages are the org's own editable rows, so "in production" is keyed on
  // ORDER and ROLE, never on slugs or labels: every column BEFORE the
  // approval-role stage is still being made.
  const colunas = colunasEsteira ?? [];
  const iAprovacao = colunas.findIndex((c) => c.stage?.papel === PAPEL_APROVACAO_CLIENTE);
  const emProducao = colunas
    .slice(0, iAprovacao === -1 ? colunas.length : iAprovacao)
    .reduce((n, c) => n + (c.total ?? c.cards.length), 0);
  const tarefasComCliente = iAprovacao === -1 ? [] : colunas[iAprovacao].cards;
  const aguardandoCliente =
    iAprovacao === -1 ? 0 : colunas[iAprovacao].total ?? tarefasComCliente.length;

  // The margin is only meaningful once hours have a cost. Said out loud
  // rather than shown as a number, because "0%" and "unknown" look
  // identical — but ONLY once profissionais has actually finished loading;
  // before that, both are simply unknown, not "zero profissionais".
  const semCustoHora = profissionais.filter((p) => p.custo_hora_indefinido).length;
  const semProfissionais = !carregandoProfissionais && profissionais.length === 0;
  const margemConfiavel = !carregandoProfissionais && !semProfissionais && semCustoHora === 0;
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
          report zero. Linked, not just described. Never shown mid-load. */}
      {!carregandoProfissionais && (semProfissionais || semCustoHora > 0) && (
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
          valor={clientesAtivos.loading ? "—" : String(clientesAtivos.total)}
          nota={clientesInadimplentes.total > 0 ? `${clientesInadimplentes.total} inadimplente(s)` : undefined}
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
          valor={carregandoDRE ? "—" : BRL.format(receita)}
          href="/financeiro"
        />
        <Indicador
          icone={<BarChart3 className="h-4 w-4" />}
          rotulo="Margem no mês"
          valor={carregandoDRE ? "—" : margemConfiavel ? BRL.format(margem) : "indisponível"}
          nota={!carregandoDRE && !margemConfiavel ? "sem custo/hora" : undefined}
          href="/financeiro"
        />
      </div>

      {/* ── Comercial (achado #21) ──────────────────────────────────── */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Indicador
          icone={<Briefcase className="h-4 w-4" />}
          rotulo="Negócios abertos"
          valor={carregandoComercial ? "—" : String(negociosAbertos.length)}
          href="/comercial"
        />
        <Indicador
          icone={<Wallet className="h-4 w-4" />}
          rotulo="Valor em negociação"
          valor={carregandoComercial ? "—" : BRL.format(valorEmNegociacao)}
          href="/comercial"
        />
        <Indicador
          icone={<Trophy className="h-4 w-4" />}
          rotulo="Ganhos no mês"
          valor={carregandoComercial ? "—" : String(ganhosNoMes.length)}
          href="/comercial"
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
              {tarefasComCliente.map(
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
          {erroInadimplentes ? (
            <p role="alert" className="text-sm text-destructive">
              {describeError(erroInadimplentesMsg, "Não foi possível carregar a inadimplência.")}
            </p>
          ) : carregandoInadimplentes ? (
            <TableSkeleton rows={2} />
          ) : inadimplentes.length === 0 ? (
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
