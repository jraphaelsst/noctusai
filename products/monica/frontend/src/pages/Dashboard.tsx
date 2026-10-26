/**
 * Home: where the funnel stands today -- leads per stage (real counts from the leads organ), each linking to the
 * funnel. Loading is a skeleton on the first load only; a failed load says so with a retry, never "0 leads".
 */
import { Link } from "react-router-dom";
import { Users } from "lucide-react";

import { leadsHooks } from "@/lib/crm";

export default function Dashboard() {
  const board = leadsHooks.useLeadsBoard({});
  const columns = board.data ?? [];
  const total = columns.reduce((sum, c) => sum + c.total, 0);

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      <div className="flex items-center gap-3">
        <Users className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Início</h1>
          <p className="text-sm text-muted-foreground">Como está o seu funil hoje.</p>
        </div>
      </div>

      {board.showSkeleton ? (
        <div className="grid gap-3 grid-cols-2 lg:grid-cols-4" data-testid="dashboard-loading">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-lg border border-border bg-muted/40" />
          ))}
        </div>
      ) : board.isError && !board.data ? (
        <div className="rounded-lg border border-destructive/40 p-4 text-sm" role="alert">
          Não foi possível carregar o funil.{" "}
          <button type="button" className="underline" onClick={() => void board.refetch()}>Tentar de novo</button>
        </div>
      ) : (
        <>
          <p className="text-sm text-muted-foreground" data-testid="dashboard-total">
            {total === 0 ? "Nenhum lead ainda." : `${total} ${total === 1 ? "lead" : "leads"} no total.`}
          </p>
          <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
            {columns.map((c) => (
              <Link
                key={c.etapa}
                to="/leads"
                className="rounded-lg border border-border bg-card p-4 transition-colors hover:bg-accent"
                data-testid={`dashboard-stage-${c.etapa}`}
              >
                <p className="text-sm text-muted-foreground">{c.stage.label}</p>
                <p className="text-3xl font-semibold text-foreground">{c.total}</p>
              </Link>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
