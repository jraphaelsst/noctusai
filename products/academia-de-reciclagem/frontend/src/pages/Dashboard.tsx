/**
 * Dashboard — real counts, no hard-coded numbers.
 *
 * Open questions (usePerguntasList('aberta').total), tasks grouped by
 * `estado` (useTasks()), and the most recently updated KB entries
 * (useKbList, sorted client-side by `updated_at` — the backend's default
 * order without `consulta` is not contract-guaranteed).
 */
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { BookOpen, HelpCircle, ListTodo, Scale } from "lucide-react";

import { Badge, PageSkeleton } from "@noctusai/lib/design-system";
import { Card, ErrorState } from "@/components/FormControls";
import { errorMessage } from "@/lib/errors";
import { useKbList } from "@/hooks/useKb";
import { usePerguntasList } from "@/hooks/usePerguntas";
import { useDecisoesList } from "@/hooks/useDecisoes";
import { FASE_ESTADOS, useTasks } from "@/hooks/useRoadmap";

export default function Dashboard() {
  const perguntas = usePerguntasList("aberta");
  const decisoes = useDecisoesList("vigente");
  const tasks = useTasks();
  const recentKb = useKbList({ limite: 5, offset: 0 });

  const showSkeleton =
    (perguntas.isPending && !perguntas.data) ||
    (tasks.isPending && !tasks.data) ||
    (recentKb.isPending && !recentKb.data);

  const tasksByEstado = useMemo(() => {
    const counts: Record<string, number> = Object.fromEntries(FASE_ESTADOS.map((e) => [e, 0]));
    for (const t of tasks.data?.items ?? []) counts[t.estado] = (counts[t.estado] ?? 0) + 1;
    return counts;
  }, [tasks.data]);

  const recentEntries = useMemo(
    () =>
      (recentKb.data?.items ?? [])
        .slice()
        .sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1)),
    [recentKb.data],
  );

  if (showSkeleton) return <PageSkeleton />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Visão geral do conhecimento e do trabalho em andamento.
        </p>
      </div>

      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        <Link to="/perguntas">
          <StatCard
            icon={HelpCircle}
            label="Perguntas abertas"
            value={perguntas.error ? "—" : perguntas.data?.total ?? 0}
            error={perguntas.error ? errorMessage(perguntas.error) : null}
          />
        </Link>
        <Link to="/decisoes">
          <StatCard
            icon={Scale}
            label="Decisões vigentes"
            value={decisoes.error ? "—" : decisoes.data?.total ?? 0}
            error={decisoes.error ? errorMessage(decisoes.error) : null}
          />
        </Link>
        <Link to="/roadmap">
          <StatCard
            icon={ListTodo}
            label="Tarefas em andamento"
            value={tasks.error ? "—" : tasksByEstado["em-andamento"] ?? 0}
            error={tasks.error ? errorMessage(tasks.error) : null}
          />
        </Link>
        <Link to="/kb">
          <StatCard
            icon={BookOpen}
            label="Entradas na base"
            value={recentKb.error ? "—" : recentKb.data?.total ?? 0}
            error={recentKb.error ? errorMessage(recentKb.error) : null}
          />
        </Link>
      </div>

      <Card>
        <h2 className="mb-3 text-lg font-semibold text-foreground">Tarefas por estado</h2>
        {tasks.error ? (
          <ErrorState message={errorMessage(tasks.error)} />
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {FASE_ESTADOS.map((estado) => (
              <div key={estado} className="rounded-md border border-border bg-muted/50 px-4 py-3">
                <p className="text-xs font-medium text-muted-foreground">{estado}</p>
                <p className="text-lg font-semibold text-foreground">{tasksByEstado[estado] ?? 0}</p>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <h2 className="mb-3 text-lg font-semibold text-foreground">Atualizações recentes na base</h2>
        {recentKb.error ? (
          <ErrorState message={errorMessage(recentKb.error)} />
        ) : recentEntries.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhuma entrada ainda.</p>
        ) : (
          <ul className="space-y-2">
            {recentEntries.map((entry) => (
              <li key={entry.slug}>
                <Link
                  to={`/kb/${entry.slug}`}
                  className="flex items-center justify-between gap-2 rounded-md px-2 py-1 hover:bg-accent"
                >
                  <span className="text-sm text-foreground">{entry.titulo}</span>
                  <Badge variant="muted">{entry.categoria}</Badge>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  error,
}: {
  icon: typeof BookOpen;
  label: string;
  value: number | string;
  error: string | null;
}) {
  return (
    <Card className="h-full transition-colors hover:border-primary">
      <div className="flex items-center gap-3">
        <Icon className="h-5 w-5 text-primary" />
        <div>
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          <p className="text-xl font-semibold text-foreground">{value}</p>
        </div>
      </div>
      {error ? <p className="mt-1 text-xs text-destructive">{error}</p> : null}
    </Card>
  );
}
