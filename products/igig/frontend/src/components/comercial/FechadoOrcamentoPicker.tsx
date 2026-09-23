/**
 * "Qual orçamento foi aceito?" — the gate on dragging a negócio into the
 * `fechado`-role stage (roadmap R4: no close without an orçamento).
 *
 * `useFechadoGate()` is the `PipelineBoard.onBeforeMove` handler: a move into
 * the fechado role PARKS a promise and opens this picker; choosing an
 * orçamento resolves it with `{extra: {orcamento_id}}` (spread into the
 * `mover-etapa` body, which accepts it, marks the deal ganho and creates the
 * Cliente); cancelling resolves `false` (the card snaps back — nothing was
 * mutated). With no eligible orçamento the picker offers "Gerar orçamento"
 * instead, which cancels the move and opens the orçamento modal.
 */
import { useCallback, useRef, useState } from "react";
import { FilePlus2 } from "lucide-react";
import type { MoveDecision, MoveIntentContext } from "@noctusai/lib/components";
import { Badge, Button, Skeleton } from "@noctusai/lib/design-system";
import { cn } from "@noctusai/lib";

import { SheetDialog } from "@/components/common/SheetDialog";
import { useOrcamentos } from "@/hooks/useOrcamentos";
import { describeError } from "@/lib/errors";
import { brl } from "@/lib/format";
import { PAPEL_FECHADO } from "@/lib/pipelines";
import { ORCAMENTO_STATUS_LABEL, type Negocio, type Orcamento } from "@/types/crm";

/** Statuses that can no longer be the accepted one. */
const ENCERRADOS = new Set(["recusado", "expirado", "substituido"]);

export function orcamentosElegiveis(orcamentos: Orcamento[]): Orcamento[] {
  return orcamentos.filter((o) => !ENCERRADOS.has(o.status));
}

interface Pendente {
  negocio: Negocio;
  resolve: (d: MoveDecision) => void;
}

export function useFechadoGate() {
  const [pendente, setPendente] = useState<Pendente | null>(null);
  const ref = useRef<Pendente | null>(null);

  const onBeforeMove = useCallback((ctx: MoveIntentContext<Negocio>): Promise<MoveDecision> | MoveDecision => {
    if (ctx.toStage.papel !== PAPEL_FECHADO || ctx.fromStage.id === ctx.toStage.id) return true;
    return new Promise<MoveDecision>((resolve) => {
      const p = { negocio: ctx.card, resolve };
      ref.current = p;
      setPendente(p);
    });
  }, []);

  const decidir = useCallback((d: MoveDecision) => {
    ref.current?.resolve(d);
    ref.current = null;
    setPendente(null);
  }, []);

  return { onBeforeMove, pendente: pendente?.negocio ?? null, decidir };
}

export interface FechadoOrcamentoPickerProps {
  negocio: Negocio | null;
  onEscolher: (orcamentoId: string) => void;
  onCancelar: () => void;
  onGerarOrcamento: (negocio: Negocio) => void;
}

export function FechadoOrcamentoPicker({ negocio, onEscolher, onCancelar, onGerarOrcamento }: FechadoOrcamentoPickerProps) {
  const { orcamentos, showSkeleton, isError, error } = useOrcamentos(
    { negocio_id: negocio?.id },
    { enabled: !!negocio },
  );
  const elegiveis = orcamentosElegiveis(orcamentos);
  const [escolhido, setEscolhido] = useState<string | null>(null);
  const nome = negocio?.lead?.empresa || negocio?.lead?.nome || negocio?.titulo || "";

  return (
    <SheetDialog
      open={!!negocio}
      onClose={() => {
        setEscolhido(null);
        onCancelar();
      }}
      title="Qual orçamento foi aceito?"
      description={`Fechar ${nome} exige o orçamento aceito — ele vira o contrato e o cliente é criado.`}
      widthClassName="sm:max-w-md"
      testId="fechado-picker"
      footer={
        <div className="flex flex-wrap justify-end gap-2">
          <Button
            variant="ghost"
            onClick={() => {
              setEscolhido(null);
              onCancelar();
            }}
          >
            Cancelar
          </Button>
          {elegiveis.length > 0 ? (
            <Button
              disabled={!escolhido}
              onClick={() => {
                if (!escolhido) return;
                const id = escolhido;
                setEscolhido(null);
                onEscolher(id);
              }}
            >
              Fechar negócio
            </Button>
          ) : null}
        </div>
      }
    >
      {showSkeleton ? (
        <div className="space-y-2">
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      ) : isError ? (
        <p role="alert" className="text-sm text-destructive">
          {describeError(error, "Não foi possível carregar os orçamentos.")}
        </p>
      ) : elegiveis.length === 0 ? (
        <div className="space-y-3 text-center">
          <p className="text-sm text-muted-foreground">Este negócio ainda não tem orçamento em aberto.</p>
          <Button
            onClick={() => {
              if (negocio) onGerarOrcamento(negocio);
            }}
          >
            <FilePlus2 className="mr-1 h-4 w-4" /> Gerar orçamento
          </Button>
        </div>
      ) : (
        <ul role="radiogroup" aria-label="Orçamentos" className="space-y-2">
          {elegiveis.map((o) => (
            <li key={o.id}>
              <button
                type="button"
                role="radio"
                aria-checked={escolhido === o.id}
                onClick={() => setEscolhido(o.id)}
                className={cn(
                  "flex w-full items-center gap-3 rounded-lg border p-3 text-left text-sm transition-colors",
                  escolhido === o.id ? "border-primary bg-primary/5" : "border-border hover:bg-muted",
                )}
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium text-foreground">
                    {o.titulo} · v{o.versao}
                  </span>
                  <span className="text-xs text-muted-foreground">{brl(o.total_mensal)}/mês</span>
                </span>
                <Badge variant={o.status === "aceito" ? "default" : "outline"}>{ORCAMENTO_STATUS_LABEL[o.status]}</Badge>
              </button>
            </li>
          ))}
        </ul>
      )}
    </SheetDialog>
  );
}
