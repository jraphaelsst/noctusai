/**
 * Live progress of one eval run (owner 2026-11-17: "I need to see progress ... numbers updating"): cases done out of total
 * with a progress bar, passed / failed / errored so far, the running score, the cost so far against the limit, elapsed time and
 * the ETA. Every number is the server's (`useRunProgresso`, polled every 1.5 s while the run is active, stopping by itself).
 *
 * States (`KB § PATTERNS/frontend/lying-loading-state.md`): skeleton only while there is no data at all; an error to load is
 * shown in red with the reason, never a silent blank; a run that ERRORED says so in red with the code and text (an errored case
 * is no behaviour failure); the mechanism suite stores its executions when it ends, so while it executes the panel says
 * "medindo" (indeterminate) instead of inventing a percentage.
 */
import { Loader2 } from "lucide-react";
import { Badge } from "@noctusai/lib/design-system";
import { errorMessage } from "@/lib/errors";
import { formatUsdCost } from "@/lib/utils";
import { useRunProgresso } from "@/hooks/studio/useEvals";
import type { EvalLoopSuite, RunProgresso } from "@/api/studio/types-ke";
import { StudioLoading } from "./StudioStates";

const pct = (v: number | null | undefined): string => (v == null ? "—" : `${Math.round(v * 100)}%`);

/** `75` -> "1 min 15 s"; `null` -> "—". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  if (m < 60) return r ? `${m} min ${r} s` : `${m} min`;
  return `${Math.floor(m / 60)} h ${m % 60} min`;
}

const STATUS_LABEL: Record<string, string> = {
  pendente: "na fila",
  executando: "em execução",
  concluida: "concluída",
  falhou: "falhou",
  cancelada: "cancelada",
  erro: "erro",
  parcial_com_erros: "concluída com erros",
};

export const statusLabel = (s: string): string => STATUS_LABEL[s] ?? s;

function ErroBanner({ p }: { p: RunProgresso }) {
  const comErro = p.status === "erro" || p.status === "parcial_com_erros" || p.status === "falhou";
  if (!comErro && !p.erro) return null;
  return (
    <div
      role="alert"
      className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive"
      data-testid="run-progress-erro"
    >
      <p className="font-semibold">
        {p.status === "parcial_com_erros"
          ? `${p.erros ?? "Alguns"} caso(s) terminaram em erro — a nota é só dos casos medidos.`
          : p.status === "erro"
            ? "A avaliação não conseguiu medir nenhum caso (sem nota)."
            : "A avaliação falhou."}
      </p>
      {p.erro && <p>{p.erro}</p>}
      {p.erro_codigo && <p className="text-[11px] opacity-80">código: {p.erro_codigo}</p>}
    </div>
  );
}

export function RunProgressView({ p }: { p: RunProgresso }) {
  const total = p.total ?? 0;
  const feitos = p.concluidos ?? 0;
  const ratio = total > 0 ? Math.min(1, feitos / total) : 0;
  const barra = p.indeterminado ? null : Math.round(ratio * 100);
  const overLimit = p.limite_usd != null && p.custo_usd != null && p.custo_usd >= p.limite_usd;
  return (
    <div className="space-y-2" data-testid="run-progress" aria-busy={p.ativo || undefined}>
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="flex items-center gap-1.5 font-semibold text-foreground" data-testid="run-progress-contagem">
          {p.ativo && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" aria-hidden />}
          {p.indeterminado ? "Medindo a suíte…" : `${feitos} de ${total} casos`}
        </span>
        <Badge variant={p.status === "erro" || p.status === "falhou" ? "destructive" : "muted"} data-testid="run-progress-status">
          {statusLabel(p.status)}
        </Badge>
      </div>
      <div
        role="progressbar"
        aria-label="Progresso da avaliação"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={barra ?? undefined}
        aria-valuetext={p.indeterminado ? "em andamento, total desconhecido" : `${feitos} de ${total} casos`}
        className="h-2 w-full overflow-hidden rounded bg-muted"
      >
        <div
          className={`h-full ${p.indeterminado ? "w-1/3 animate-pulse bg-primary/60" : p.erros && p.erros > 0 && p.aprovados === 0 && p.reprovados === 0 ? "bg-destructive" : "bg-primary"}`}
          style={p.indeterminado ? undefined : { width: `${(barra ?? 0).toString()}%` }}
          data-testid="run-progress-barra"
        />
      </div>
      {p.indeterminado ? (
        <p className="text-xs text-muted-foreground" data-testid="run-progress-indeterminado">
          A suíte de mecanismo só grava os resultados quando termina: aqui aparecem o tempo e o custo, e os números fechados
          chegam ao final.
        </p>
      ) : (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4" data-testid="run-progress-numeros">
          <div>
            <dt className="text-muted-foreground">Aprovados</dt>
            <dd className="font-medium text-foreground" data-testid="run-progress-aprovados">
              {p.aprovados ?? "—"}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Reprovados</dt>
            <dd className="font-medium text-foreground" data-testid="run-progress-reprovados">
              {p.reprovados ?? "—"}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Com erro</dt>
            <dd className={`font-medium ${p.erros ? "text-destructive" : "text-foreground"}`} data-testid="run-progress-erros">
              {p.erros ?? "—"}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Nota parcial</dt>
            <dd className="font-medium text-foreground" data-testid="run-progress-score">
              {pct(p.score_parcial)}
            </dd>
          </div>
        </dl>
      )}
      <p className="text-xs text-muted-foreground" data-testid="run-progress-tempo">
        Custo {formatUsdCost(p.custo_usd)}
        {p.limite_usd != null ? ` de ${formatUsdCost(p.limite_usd)}` : ""}
        {overLimit ? " (limite atingido)" : ""} · decorrido {formatDuration(p.decorrido_s)}
        {p.ativo && !p.indeterminado ? ` · faltam ~${formatDuration(p.eta_s)}` : ""}
      </p>
      <ErroBanner p={p} />
    </div>
  );
}

export function RunProgressPanel({ agentKey, suite, runId }: { agentKey: string; suite: EvalLoopSuite; runId: string | null }) {
  const progresso = useRunProgresso(agentKey, suite, runId);
  if (!runId) return null;
  if (progresso.showSkeleton) return <StudioLoading rows={2} testId="run-progress-loading" />;
  if (progresso.isError && !progresso.data) {
    return (
      <p role="alert" className="text-xs text-destructive" data-testid="run-progress-load-error">
        Não foi possível carregar o progresso: {errorMessage(progresso.error)}
      </p>
    );
  }
  if (!progresso.data) return null;
  return <RunProgressView p={progresso.data} />;
}
