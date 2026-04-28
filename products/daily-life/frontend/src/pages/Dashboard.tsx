import {
  useDashboardTaskStats,
  useDashboardMetrics,
  useDashboardTodayEvents,
} from "@/hooks/useDashboard";
import { useAuthStore } from '@noctusai/seed/infra';
import { resolveSSOContext } from "@noctusai/lib";
import { WeeklyReviewCard } from "@/components/WeeklyReviewCard";
import {
  CalendarCheck, ListTodo, Target, Calendar, StickyNote,
  Loader2, TrendingUp, Flame, CheckCircle2,
} from "lucide-react";

export default function Dashboard() {
  const { user } = useAuthStore();
  const ssoCtx = resolveSSOContext(user?.user_metadata);

  const userName = user?.user_metadata?.full_name
    || user?.user_metadata?.name
    || user?.email?.split("@")[0]
    || "Usuario";

  const { data: taskStats } = useDashboardTaskStats();
  const { data: metricsRes } = useDashboardMetrics();
  const { data: todayEventsRes } = useDashboardTodayEvents();

  const stats = taskStats?.data;
  const metrics = metricsRes?.data;
  const todayEvents = todayEventsRes?.data ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <CalendarCheck className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Ola, {userName}</h1>
          <p className="text-sm text-muted-foreground">Aqui esta o resumo do seu dia</p>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={ListTodo}
          label="Tarefas pendentes"
          value={stats ? stats.pendente + stats.em_progresso : "-"}
          sub={stats ? `${stats.concluida} concluidas` : undefined}
        />
        <StatCard
          icon={CheckCircle2}
          label="Concluidas (7d)"
          value={metrics?.total_tarefas_concluidas ?? "-"}
          sub={metrics?.total_checkins ? `${metrics.total_checkins} check-ins` : undefined}
        />
        <StatCard
          icon={Flame}
          label="Streak"
          value={metrics?.streak_dias != null ? `${metrics.streak_dias}d` : "-"}
          sub="dias consecutivos"
        />
        <StatCard
          icon={TrendingUp}
          label="Score medio"
          value={metrics?.score_medio != null ? metrics.score_medio.toFixed(1) : "-"}
          sub="ultimos 7 dias"
        />
      </div>

      {/* Quick Access + Today's Events */}
      <div className="grid gap-4 grid-cols-1 lg:grid-cols-2">
        {/* Quick nav */}
        <div className="space-y-3">
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Acesso rapido</h2>
          <div className="grid gap-3 grid-cols-2">
            <QuickCard icon={ListTodo} title="Tarefas" href="/tarefas" />
            <QuickCard icon={Target} title="Metas" href="/metas" />
            <QuickCard icon={Calendar} title="Agenda" href="/agenda" />
            <QuickCard icon={StickyNote} title="Notas" href="/notas" />
          </div>
        </div>

        {/* Today's events */}
        <div className="space-y-3">
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Eventos de hoje</h2>
          <div className="rounded-lg border border-border bg-card divide-y divide-border">
            {todayEvents.length === 0 ? (
              <p className="px-4 py-6 text-sm text-muted-foreground text-center">Nenhum evento hoje</p>
            ) : (
              todayEvents.map((ev: any) => (
                <div key={ev.id} className="px-4 py-3 flex items-center gap-3">
                  {ev.cor && (
                    <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: ev.cor }} />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-foreground truncate">{ev.titulo}</p>
                    <p className="text-xs text-muted-foreground">
                      {ev.dia_inteiro
                        ? "Dia inteiro"
                        : new Date(ev.data_inicio).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
                      {ev.local && ` — ${ev.local}`}
                    </p>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* AI weekly-review digest — gated by `daily_life.weekly_review` consent. */}
      <WeeklyReviewCard />

      {/* Org info */}
      {ssoCtx.org.name && (
        <p className="text-xs text-muted-foreground">
          Organizacao: <strong className="text-foreground">{ssoCtx.org.name}</strong>
        </p>
      )}
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-1">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon className="h-4 w-4" />
        <span className="text-xs font-medium">{label}</span>
      </div>
      <p className="text-2xl font-bold text-foreground">{value}</p>
      {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
    </div>
  );
}

function QuickCard({
  icon: Icon,
  title,
  href,
}: {
  icon: React.ElementType;
  title: string;
  href: string;
}) {
  return (
    <a
      href={href}
      className="group flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3 hover:border-primary/30 hover:shadow-sm transition-all"
    >
      <Icon className="h-4 w-4 text-primary group-hover:scale-110 transition-transform" />
      <span className="text-sm font-medium text-foreground">{title}</span>
    </a>
  );
}
