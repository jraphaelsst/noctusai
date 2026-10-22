/**
 * AI first-draft progress panel (S3a) on the agent page: the latest run (polled while pendente|executando,
 * stops when terminal), per-area status/cost/lacunas with "Repetir", a run-level "Cancelar", and the
 * "Gerar com IA" form (the same BriefingForm the creation dialog uses) to start a run on an existing agent.
 * The result is always a DRAFT to review — publishing stays human.
 */
import { useState } from "react";
import { toast } from "sonner";
import { Badge, Button } from "@noctusai/lib/design-system";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { useCancelarGeracao, useCreateGeracao, useRepetirArea, useUltimaGeracao } from "@/hooks/studio/useGeracoes";
import {
  GERACAO_AREA_LABEL,
  LIMITE_USD_MAX,
  type GeracaoAreaOut,
  type GeracaoAreaStatus,
  type GeracaoOut,
  type GeracaoStatus,
} from "@/api/studio/types-geracao";
import { lifecycleError } from "@/lib/agentLifecycle";
import { BRIEFING_VAZIO, validarBriefing, type BriefingDraft, type BriefingErrors } from "@/lib/briefing";
import { BriefingForm } from "./BriefingForm";

export const STATUS_GERACAO_LABEL: Record<GeracaoStatus, string> = {
  pendente: "Na fila",
  executando: "Gerando…",
  concluida: "Concluída",
  parcial: "Parcial",
  falhou: "Falhou",
  cancelada: "Cancelada",
};
export const STATUS_AREA_LABEL: Record<GeracaoAreaStatus, string> = {
  pendente: "Pendente",
  executando: "Gerando…",
  concluida: "Concluída",
  falhou: "Falhou",
  pulado: "Pulada",
  cancelada: "Cancelada",
};

const usd = (v: number) => `US$ ${v.toFixed(2)}`;

function statusVariant(s: GeracaoStatus | GeracaoAreaStatus): "default" | "muted" | "destructive" | "outline" {
  if (s === "concluida") return "default";
  if (s === "falhou") return "destructive";
  if (s === "cancelada" || s === "pulado") return "muted";
  return "outline";
}

interface FalhaAcao {
  code: string | null;
  message: string;
  /** Retry that needs `forcar` (conteudo_editado / area_concluida). */
  retry?: () => void;
}

function AreaLinha({
  area,
  bloqueada,
  pendente,
  onRepetir,
}: {
  area: GeracaoAreaOut;
  bloqueada: boolean;
  pendente: boolean;
  onRepetir: (forcar: boolean) => void;
}) {
  const [confirmando, setConfirmando] = useState(false);
  const concluida = area.status === "concluida";
  const podeRepetir = ["falhou", "pulado", "cancelada", "concluida"].includes(area.status);
  return (
    <li className="space-y-1 px-3 py-2 text-sm" data-testid={`geracao-area-${area.area}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{GERACAO_AREA_LABEL[area.area]}</span>
        <Badge variant={statusVariant(area.status)} data-testid={`geracao-area-status-${area.area}`}>
          {STATUS_AREA_LABEL[area.status]}
        </Badge>
        <span className="text-xs tabular-nums text-muted-foreground">
          {usd(area.custo_usd)}
          {area.itens_escritos > 0 ? ` · ${area.itens_escritos} item(ns)` : ""}
        </span>
        <span className="ml-auto flex items-center gap-2">
          {podeRepetir && !confirmando && (
            <Button
              size="sm"
              variant="ghost"
              disabled={bloqueada || pendente}
              onClick={() => (concluida ? setConfirmando(true) : onRepetir(false))}
              data-testid={`geracao-repetir-${area.area}`}
            >
              Repetir
            </Button>
          )}
          {confirmando && (
            <span className="flex items-center gap-2 text-xs" data-testid={`geracao-repetir-confirma-${area.area}`}>
              Gerar de novo substitui o conteúdo desta área.
              <Button
                size="sm"
                variant="primary"
                disabled={pendente}
                onClick={() => {
                  setConfirmando(false);
                  onRepetir(true);
                }}
                data-testid={`geracao-repetir-confirmar-${area.area}`}
              >
                Confirmar
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirmando(false)}>
                Voltar
              </Button>
            </span>
          )}
        </span>
      </div>
      {area.erro && <p className="text-xs text-destructive">{area.erro}</p>}
      {area.lacunas.length > 0 && (
        <ul className="list-disc pl-5 text-xs text-muted-foreground" data-testid={`geracao-lacunas-${area.area}`}>
          {area.lacunas.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      )}
    </li>
  );
}

function RunView({ agentKey, g }: { agentKey: string; g: GeracaoOut }) {
  const repetir = useRepetirArea(agentKey);
  const cancelar = useCancelarGeracao(agentKey);
  const [falha, setFalha] = useState<FalhaAcao | null>(null);
  const ativa = g.status === "pendente" || g.status === "executando";

  async function doRepetir(area: GeracaoAreaOut["area"], forcar: boolean) {
    setFalha(null);
    try {
      await repetir.mutateAsync({ id: g.id, area, forcar });
    } catch (err) {
      const e = lifecycleError(err);
      setFalha({ ...e, retry: e.code === "conteudo_editado" ? () => void doRepetir(area, true) : undefined });
    }
  }
  async function doCancelar() {
    setFalha(null);
    try {
      await cancelar.mutateAsync({ id: g.id });
      toast.success("Geração cancelada.");
    } catch (err) {
      setFalha(lifecycleError(err));
    }
  }

  return (
    <div className="space-y-3" data-testid="geracao-run">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={statusVariant(g.status)} data-testid="geracao-status">
          {STATUS_GERACAO_LABEL[g.status]}
        </Badge>
        <span className="text-sm tabular-nums" data-testid="geracao-custo">
          {usd(g.custo_usd)} de {usd(g.limite_usd)}
        </span>
        <span className="text-xs text-muted-foreground" data-testid="geracao-gerador">
          {g.modelo}
          {g.versao_gerador !== null ? ` · gerador v${g.versao_gerador}` : ""}
        </span>
        {ativa && (
          <Button size="sm" variant="ghost" className="ml-auto" disabled={cancelar.isPending} onClick={() => void doCancelar()} data-testid="geracao-cancelar">
            {cancelar.isPending ? "Cancelando…" : "Cancelar"}
          </Button>
        )}
      </div>
      {g.erro && <p className="text-sm text-destructive">{g.erro}</p>}
      <ul className="divide-y divide-border rounded-lg border border-border">
        {g.areas.map((a) => (
          <AreaLinha
            key={a.area}
            area={a}
            bloqueada={ativa}
            pendente={repetir.isPending}
            onRepetir={(forcar) => void doRepetir(a.area, forcar)}
          />
        ))}
      </ul>
      {falha && (
        <div className="space-y-1 text-sm text-destructive" role="alert" data-testid="geracao-falha">
          <p>{falha.message}</p>
          {falha.retry && (
            <Button size="sm" variant="ghost" onClick={falha.retry} data-testid="geracao-falha-forcar">
              Repetir mesmo assim (sobrescreve edições)
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

function NovaGeracao({ agentKey, onDone }: { agentKey: string; onDone: () => void }) {
  const create = useCreateGeracao(agentKey);
  const [draft, setDraft] = useState<BriefingDraft>(BRIEFING_VAZIO);
  const [errors, setErrors] = useState<BriefingErrors>({});
  const [falha, setFalha] = useState<FalhaAcao | null>(null);

  async function enviar(forcar: boolean) {
    setFalha(null);
    const v = validarBriefing(draft);
    setErrors(v.errors);
    if (!v.briefing) return;
    try {
      await create.mutateAsync({ briefing: v.briefing, ...(forcar ? { forcar: true } : {}) });
      toast.success("Geração iniciada. O resultado é um rascunho para revisar.");
      onDone();
    } catch (err) {
      const e = lifecycleError(err);
      setFalha({ ...e, retry: e.code === "conteudo_editado" ? () => void enviar(true) : undefined });
    }
  }

  return (
    <form
      className="space-y-3 rounded-lg border border-border p-3"
      onSubmit={(e) => {
        e.preventDefault();
        void enviar(false);
      }}
      data-testid="geracao-form"
    >
      <BriefingForm value={draft} onChange={setDraft} errors={errors} idPrefix="geracao-briefing" />
      <p className="text-xs text-muted-foreground">
        Custo máximo de {usd(LIMITE_USD_MAX)} por geração. O resultado é um rascunho: revise antes de publicar.
      </p>
      {falha && (
        <div className="space-y-1 text-sm text-destructive" role="alert" data-testid="geracao-form-erro">
          <p>{falha.message}</p>
          {falha.retry && (
            <Button type="button" size="sm" variant="ghost" onClick={falha.retry} data-testid="geracao-form-forcar">
              Gerar mesmo assim (sobrescreve edições)
            </Button>
          )}
        </div>
      )}
      <div className="flex gap-2">
        <Button type="submit" variant="primary" disabled={create.isPending} data-testid="geracao-form-submit">
          {create.isPending ? "Enviando…" : "Gerar rascunho"}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Fechar
        </Button>
      </div>
    </form>
  );
}

export function GeracaoPanel({ agentKey }: { agentKey: string }) {
  const { geracao, showSkeleton, isError, error, refetch, ativa } = useUltimaGeracao(agentKey);
  const [formAberto, setFormAberto] = useState(false);

  return (
    <section className="space-y-3 rounded-lg border border-border bg-card p-4" data-testid="geracao-panel">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold">Geração com IA</h2>
        <Badge variant="outline">rascunho — revise antes de publicar</Badge>
        {!ativa && !formAberto && !showSkeleton && (
          <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setFormAberto(true)} data-testid="geracao-abrir-form">
            Gerar com IA
          </Button>
        )}
      </div>
      {showSkeleton ? (
        <StudioLoading rows={2} testId="geracao-skeleton" />
      ) : isError ? (
        <StudioError error={error} onRetry={refetch} />
      ) : (
        <>
          {formAberto && <NovaGeracao agentKey={agentKey} onDone={() => setFormAberto(false)} />}
          {geracao ? (
            <RunView agentKey={agentKey} g={geracao} />
          ) : (
            !formAberto && (
              <p className="text-sm text-muted-foreground" data-testid="geracao-vazio">
                Nenhuma geração ainda. Descreva o agente num briefing e a IA escreve o primeiro rascunho (até {usd(LIMITE_USD_MAX)}).
              </p>
            )
          )}
        </>
      )}
    </section>
  );
}
