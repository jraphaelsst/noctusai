/**
 * `CriacaoStatusLine` — the live status line + progress bar of a card in the criação pipeline
 * (criacao-pipeline-contract.md §3). It says what the agent is doing RIGHT NOW ("Sintetizando voz (2/3)"),
 * as part of the card, not as a toast or notification. The text and the bar are driven by the stream
 * (`useCriacaoProgresso`); with no live frame (reload, stream down) it falls back to the card's sub-state
 * sentence and an indeterminate bar, never an invented percentage.
 */
import { AlertTriangle, Loader2 } from "lucide-react";

import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { ESTADO_ROTULO, emAndamentoCriacao, useCriacaoProgresso } from "@/hooks/geracao/useCriacao";
import type { CriacaoEstado } from "@/types/esteira";

export interface CriacaoStatusLineProps {
  postId: string;
  estado: CriacaoEstado | null | undefined;
  /** Stable failure code of the step that failed (`falhou`), shown after the sentence. */
  falhaCodigo?: string | null;
  className?: string;
}

/** States worth a line on the card: the pipeline is working, waiting on the owner, or broken. */
const ESTADOS_VISIVEIS: ReadonlySet<CriacaoEstado> = new Set([
  "na_fila",
  "gerando",
  "refinando",
  "aguardando_edicao",
  "aguardando_aprovacao_midia",
  "midia_reprovada",
  "falhou",
]);

export function CriacaoStatusLine({ postId, estado, falhaCodigo, className }: CriacaoStatusLineProps) {
  const { progresso } = useCriacaoProgresso(postId, estado);
  if (!estado || !ESTADOS_VISIVEIS.has(estado)) return null;

  const falhou = estado === "falhou";
  const rodando = emAndamentoCriacao(estado);
  const texto = (rodando && progresso?.mensagem) || ESTADO_ROTULO[estado];
  const pct = rodando && progresso?.progresso != null ? Math.round(Math.min(Math.max(progresso.progresso, 0), 1) * 100) : null;

  return (
    <div
      data-testid={`criacao-status-${postId}`}
      data-estado={estado}
      className={cn("space-y-1 text-xs", falhou ? "text-destructive" : "text-muted-foreground", className)}
    >
      <p role="status" aria-live="polite" className="flex items-center gap-1">
        {falhou ? (
          <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden />
        ) : rodando ? (
          <Loader2 className="h-3 w-3 shrink-0 animate-spin motion-reduce:animate-none" aria-hidden />
        ) : null}
        <span>
          {texto}
          {falhou && falhaCodigo ? ` (${falhaCodigo})` : ""}
        </span>
      </p>
      {rodando && (
        <Progress
          className="h-1.5"
          value={pct ?? undefined}
          aria-label="Progresso da criação"
          aria-valuetext={pct == null ? "Em andamento" : `${pct}%`}
          data-indeterminate={pct == null ? "true" : undefined}
          indicatorClassName={pct == null ? "animate-pulse motion-reduce:animate-none w-1/3" : undefined}
        />
      )}
    </div>
  );
}
