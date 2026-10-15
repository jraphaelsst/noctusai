import { Link } from "react-router-dom";
import { useAuthStore } from '@noctusai/seed/infra';
import { resolveSSOContext } from "@noctusai/lib";
import { StatTile, StatTileRow } from "@noctusai/lib/design-system";
import { useDashboardKpis } from "@/hooks/useDashboard";
import { pipelineSummary, taskSummary, upcomingCount } from "@/lib/dashboardKpis";
import {
  LayoutDashboard,
  UserCheck,
  Kanban,
  ClipboardList,
  CalendarDays,
  DollarSign,
  Target,
  Zap,
  Megaphone,
  FileBarChart2,
  ArrowRight,
  RefreshCw,
  Users,
  TrendingUp,
  CheckSquare,
  Wallet,
} from "lucide-react";

/**
 * Dashboard — the logged-in home screen.
 *
 * KPI row = real data from the modules' existing endpoints (clientes, funil,
 * tarefas, fluxo de caixa do mês, agenda dos próximos 7 dias). Each KPI is its
 * own query: it shows a skeleton only while it has NO data (isPending && !data),
 * and a failing KPI shows "—" + a retry — never a fabricated zero.
 */
const brl = (v: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(v);
export default function Dashboard() {
  const { user } = useAuthStore();
  const ssoCtx = resolveSSOContext(user?.user_metadata);
  const orgName = ssoCtx.org.name;
  const k = useDashboardKpis();

  const showSkeleton = (q: { isPending: boolean; data?: unknown }) => q.isPending && !q.data;
  const anyError = [k.clients, k.funil, k.tasks, k.cashFlow, k.agenda].some((q) => q.isError && !q.data);
  const retryAll = () => {
    for (const q of [k.clients, k.funil, k.tasks, k.cashFlow, k.agenda]) if (q.isError) void q.refetch();
  };
  const pipe = k.funil.data ? pipelineSummary(k.funil.data) : null;
  const tasks = k.tasks.data ? taskSummary(k.tasks.data.items) : null;
  const upcoming = k.agenda.data ? upcomingCount(k.agenda.data.items) : null;
  const dash = "—";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <LayoutDashboard className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            {orgName
              ? `Bem-vindo(a) de volta, ${orgName}`
              : "Bem-vindo(a) ao Orbity"}
          </p>
        </div>
      </div>

      {/* KPI row — real data */}
      <section aria-label="Indicadores" className="space-y-2">
        <StatTileRow>
          <StatTile
            icon={Users}
            label="Clientes ativos"
            loading={showSkeleton(k.clients)}
            value={k.clients.data ?? dash}
            hint={k.clients.isError && !k.clients.data ? "Falha ao carregar" : undefined}
          />
          <StatTile
            icon={TrendingUp}
            label="Leads em aberto"
            loading={showSkeleton(k.funil)}
            value={pipe ? pipe.openLeads : dash}
            hint={pipe ? `Pipeline: ${brl(pipe.pipelineValue)}` : k.funil.isError ? "Falha ao carregar" : undefined}
          />
          <StatTile
            icon={CheckSquare}
            label="Tarefas abertas"
            loading={showSkeleton(k.tasks)}
            value={tasks ? tasks.todo + tasks.doing : dash}
            hint={
              tasks
                ? `${tasks.todo} a fazer · ${tasks.doing} em andamento · ${tasks.overdue} atrasadas`
                : k.tasks.isError
                  ? "Falha ao carregar"
                  : undefined
            }
          />
          <StatTile
            icon={Wallet}
            label={`Caixa do mês (${k.month})`}
            loading={showSkeleton(k.cashFlow)}
            value={k.cashFlow.data ? brl(k.cashFlow.data.net) : dash}
            hint={k.cashFlow.isError && !k.cashFlow.data ? "Falha ao carregar" : "Receitas pagas − despesas pagas"}
          />
          <StatTile
            icon={CalendarDays}
            label="Agenda · próximos 7 dias"
            loading={showSkeleton(k.agenda)}
            value={upcoming ?? dash}
            hint={k.agenda.isError && !k.agenda.data ? "Falha ao carregar" : undefined}
          />
        </StatTileRow>
        {anyError && (
          <button
            type="button"
            onClick={retryAll}
            className="inline-flex items-center gap-1 text-xs text-destructive underline"
          >
            <RefreshCw className="h-3 w-3" /> Alguns indicadores falharam — tentar novamente
          </button>
        )}
      </section>

      {/* Module navigation */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
        {MODULES.map((mod) => (
          <Link
            key={mod.href}
            to={mod.href}
            className="group rounded-lg border border-border bg-card p-5 flex items-start gap-4 hover:border-primary/40 hover:bg-accent/40 transition-colors"
          >
            <div className="h-10 w-10 shrink-0 rounded-md bg-primary/10 text-primary flex items-center justify-center">
              <mod.icon className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <h2 className="font-semibold text-foreground">{mod.title}</h2>
                <ArrowRight className="h-3.5 w-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
              <p className="text-sm text-muted-foreground">
                {mod.description}
              </p>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

const MODULES = [
  {
    href: "/clientes",
    title: "Clientes",
    description: "Cadastro e histórico dos clientes da agência.",
    icon: UserCheck,
  },
  {
    href: "/funil",
    title: "Funil",
    description: "Leads em kanban, do primeiro contato ao fechamento.",
    icon: Kanban,
  },
  {
    href: "/tarefas",
    title: "Tarefas",
    description: "Entregas e pendências da equipe.",
    icon: ClipboardList,
  },
  {
    href: "/agenda",
    title: "Agenda",
    description: "Compromissos e reuniões.",
    icon: CalendarDays,
  },
  {
    href: "/financeiro",
    title: "Financeiro",
    description: "Contratos, despesas, receitas e fluxo de caixa.",
    icon: DollarSign,
  },
  {
    href: "/rotinas",
    title: "Rotinas",
    description: "Tarefas recorrentes geradas automaticamente.",
    icon: RefreshCw,
  },
  {
    href: "/trafego",
    title: "Tráfego",
    description: "Contas de anúncio e métricas de campanhas (Meta Ads).",
    icon: Target,
  },
  {
    href: "/automacao",
    title: "Automação",
    description: "Fluxos automáticos de mensagens no WhatsApp.",
    icon: Zap,
  },
  {
    href: "/conteudo",
    title: "Conteúdo",
    description: "Campanhas, posts e aprovação com o cliente.",
    icon: Megaphone,
  },
  {
    href: "/relatorios",
    title: "Relatórios",
    description: "Relatórios compartilháveis por link público.",
    icon: FileBarChart2,
  },
];
