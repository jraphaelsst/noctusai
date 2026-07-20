import { Link } from "react-router-dom";
import { useAuthStore } from '@noctusai/seed/infra';
import { resolveSSOContext } from "@noctusai/lib";
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
} from "lucide-react";

/**
 * Dashboard — the logged-in home screen.
 *
 * Honest overview + navigation shell: no fabricated KPIs. Real-metric
 * wiring (leads this week, tarefas atrasadas, receita do mês, etc.) is a
 * later slice once each module's aggregate endpoints exist — at that
 * point the module cards below should each grow a real-data summary
 * line fed by that module's own hook (`useCrm`, `useFinancial`, ...).
 */
export default function Dashboard() {
  const { user } = useAuthStore();
  const ssoCtx = resolveSSOContext(user?.user_metadata);
  const orgName = ssoCtx.org.name;

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
