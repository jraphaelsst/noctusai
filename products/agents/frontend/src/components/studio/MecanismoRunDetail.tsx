/**
 * Detail of one mechanism-suite run, opened from the Execuções list (`GET .../mecanismo-runs/{id}`): the same verdict + per-case
 * failure reasons the readiness action draws (`MecanismoResultado`, shared, not forked). Every state is drawn: loading skeleton,
 * read error with retry, a run still executing, failed (fixed server text), cancelled, finished.
 */
import { Card } from "@noctusai/lib/design-system";
import { useMecanismoRun } from "@/hooks/studio/useMecanismo";
import { MecanismoResultado } from "@/components/studio/ProntidaoAcao";
import { formatUsdCost } from "@/lib/utils";

export function MecanismoRunDetail({ agentKey, runId }: { agentKey: string; runId: string }) {
  const run = useMecanismoRun(agentKey, runId);
  const r = run.data;
  return (
    <Card className="space-y-1 p-3" data-testid="mecanismo-run-detail">
      <p className="text-sm font-semibold text-foreground">Execução da suíte de mecanismo</p>
      {run.showSkeleton && <p role="status" className="text-xs text-muted-foreground">Carregando a execução...</p>}
      {run.isError && !r && (
        <p role="alert" className="text-xs text-destructive" data-testid="mecanismo-run-detail-erro">
          Não foi possível carregar a execução.{" "}
          <button type="button" className="underline" onClick={run.refetch}>Tentar de novo</button>
        </p>
      )}
      {r?.status === "executando" && (
        <p role="status" className="text-xs text-muted-foreground" data-testid="mecanismo-run-detail-andamento">
          A suíte ainda está rodando. O resultado aparece aqui quando terminar.
        </p>
      )}
      {r?.status === "falhou" && (
        <p role="alert" className="text-xs text-destructive" data-testid="mecanismo-run-detail-falhou">
          A execução falhou{r.erro ? `: ${r.erro}` : "."}
        </p>
      )}
      {r?.status === "cancelada" && <p className="text-xs text-muted-foreground">A execução foi cancelada.</p>}
      {r?.status === "concluida" && <MecanismoResultado run={r} testId="mecanismo-run-detail" />}
      {r && (
        <p className="text-xs text-muted-foreground">
          Custo: {formatUsdCost(r.custo_usd)} · Driver: {r.driver}
        </p>
      )}
    </Card>
  );
}
