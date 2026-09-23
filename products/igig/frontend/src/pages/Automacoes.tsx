/**
 * Automações — the rules the engine runs when a card enters a stage or sits
 * past its SLA (wave-2 contract, Slice E2/F; roadmap R11), and the
 * execuções log (what ran, on which card, and — for `erro` — why).
 *
 * Everyone reads; only org admins create / edit / toggle / delete (the
 * server refuses with 403 otherwise — this only hides what it would refuse).
 * Mobile-first (R0): rules are cards, the editor is a sheet <640px.
 */
import { useMemo, useState } from "react";
import { Badge, Button, Select, Skeleton, Switch } from "@noctusai/lib/design-system";
import type { BadgeVariant } from "@noctusai/lib/design-system";
import { cn } from "@noctusai/lib";
import { Pencil, Plus, Trash2, Workflow } from "lucide-react";
import { toast } from "sonner";

import { AutomacaoForm, PIPELINE_LABEL } from "@/components/automacoes/AutomacaoForm";
import { resumoAcao } from "@/components/automacoes/acaoParams";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import {
  EXECUCAO_STATUS_LABEL,
  GATILHO_LABEL,
  TIPO_ACAO_LABEL,
  useAutomacaoMutations,
  useAutomacoes,
  useExecucoes,
  type Automacao,
  type ExecucaoStatus,
  type PipelineAutomacao,
} from "@/hooks/useAutomacoes";
import { useProfissionais } from "@/hooks/useCustos";
import { esteiraPipeline } from "@/hooks/useEsteira";
import { describeError } from "@/lib/errors";
import { dataBR } from "@/lib/format";
import { comercialPipeline } from "@/lib/pipelines";
import { useIsOrgAdmin } from "@/lib/useIsOrgAdmin";

const EXEC_VARIANT: Record<ExecucaoStatus, BadgeVariant> = {
  executando: "outline",
  sucesso: "default",
  erro: "destructive",
  ignorada: "muted",
};

function horaBR(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${dataBR(iso)} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export default function Automacoes() {
  const admin = useIsOrgAdmin();
  const [filtro, setFiltro] = useState<PipelineAutomacao | "">("");
  const { automacoes, showSkeleton, isError, error, isRefreshing } = useAutomacoes(filtro ? { pipeline: filtro } : {});
  const { atualizar, remover } = useAutomacaoMutations();
  const [editando, setEditando] = useState<Automacao | null>(null);
  const [formAberto, setFormAberto] = useState(false);
  const [aRemover, setARemover] = useState<Automacao | null>(null);

  const comercialStages = comercialPipeline.useStages();
  const esteiraStages = esteiraPipeline.useStages();
  const { profissionais } = useProfissionais();
  const etapaLabel = useMemo(() => {
    const mapa = new Map<string, string>();
    for (const s of comercialStages.data ?? []) mapa.set(s.id, s.label);
    for (const s of esteiraStages.data ?? []) mapa.set(s.id, s.label);
    return (id: string) => mapa.get(id) ?? "etapa removida";
  }, [comercialStages.data, esteiraStages.data]);
  const nomeProfissional = (id: string) => profissionais.find((p) => p.id === id)?.nome;

  function abrirNova() {
    setEditando(null);
    setFormAberto(true);
  }

  return (
    <div className="mx-auto w-full min-w-0 max-w-full space-y-6 overflow-x-hidden p-4 sm:p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-foreground sm:text-2xl">Automações</h1>
          <p className="text-sm text-muted-foreground">
            Regras que rodam quando um card entra numa etapa ou fica parado além do SLA.
          </p>
        </div>
        {admin ? (
          <Button variant="primary" className="max-sm:h-10" onClick={abrirNova} data-testid="automacao-nova">
            <Plus className="mr-1 h-4 w-4" /> Nova automação
          </Button>
        ) : null}
      </header>

      {!admin ? (
        <p className="rounded-lg border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
          Somente administradores da agência podem criar ou alterar automações.
        </p>
      ) : null}

      <section className="space-y-3" aria-label="Regras">
        <div className="flex items-center gap-2">
          <Select
            aria-label="Filtrar por quadro"
            className="h-10 sm:w-60"
            value={filtro}
            onChange={(e) => setFiltro(e.target.value as PipelineAutomacao | "")}
          >
            <option value="">Todos os quadros</option>
            <option value="comercial">{PIPELINE_LABEL.comercial}</option>
            <option value="esteira">{PIPELINE_LABEL.esteira}</option>
          </Select>
        </div>

        {showSkeleton ? (
          <div className="space-y-2">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : isError ? (
          <p role="alert" className="rounded-lg border border-border bg-card p-4 text-sm text-destructive">
            {describeError(error, "Não foi possível carregar as automações.")}
          </p>
        ) : automacoes.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border bg-card p-6 text-center text-sm text-muted-foreground">
            <Workflow className="mx-auto mb-2 h-6 w-6" />
            {filtro ? "Nenhuma automação neste quadro." : "Nenhuma automação ainda."}
            {admin ? (
              <div className="mt-3">
                <Button className="max-sm:h-10" onClick={abrirNova}>
                  <Plus className="mr-1 h-4 w-4" /> Criar a primeira
                </Button>
              </div>
            ) : null}
          </div>
        ) : (
          <ul className={cn("space-y-2 transition-opacity", isRefreshing && "opacity-70")} data-testid="automacoes-lista">
            {automacoes.map((a) => (
              <li key={a.id} className="rounded-lg border border-border bg-card p-3" data-testid={`automacao-${a.id}`}>
                <div className="flex items-start gap-3">
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">{a.pipeline === "comercial" ? "Comercial" : "Esteira"}</Badge>
                      <span className="text-sm font-medium text-foreground">{etapaLabel(a.stage_id)}</span>
                      {!a.ativo ? <Badge variant="muted">pausada</Badge> : null}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {a.gatilho === "sla" ? `${GATILHO_LABEL.sla} · ${a.sla_horas}h` : GATILHO_LABEL.entrada_etapa} →{" "}
                      {TIPO_ACAO_LABEL[a.acao.tipo]}
                    </p>
                    <p className="truncate text-sm text-foreground">{resumoAcao(a.acao, { profissional: nomeProfissional })}</p>
                  </div>
                  {admin ? (
                    <Switch
                      checked={a.ativo}
                      aria-label={a.ativo ? "Pausar automação" : "Ativar automação"}
                      disabled={atualizar.isPending}
                      onCheckedChange={(ativo) =>
                        atualizar.mutate(
                          { id: a.id, patch: { ativo } },
                          {
                            onSuccess: () => toast.success(ativo ? "Automação ativada." : "Automação pausada."),
                            onError: (e) => toast.error(describeError(e, "Não foi possível alterar a automação.")),
                          },
                        )
                      }
                    />
                  ) : null}
                </div>
                {admin ? (
                  <div className="mt-2 flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="max-sm:h-10"
                      aria-label="Editar automação"
                      onClick={() => {
                        setEditando(a);
                        setFormAberto(true);
                      }}
                    >
                      <Pencil className="mr-1 h-3 w-3" /> Editar
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive max-sm:h-10"
                      aria-label="Excluir automação"
                      onClick={() => setARemover(a)}
                    >
                      <Trash2 className="mr-1 h-3 w-3" /> Excluir
                    </Button>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <ExecucoesLog etapaLabel={etapaLabel} />

      <AutomacaoForm open={formAberto} automacao={editando} onClose={() => setFormAberto(false)} />

      <ConfirmDialog
        open={!!aRemover}
        title="Excluir automação"
        description={
          <p>
            Excluir esta automação e todo o histórico de execuções dela? Para só parar de rodar mantendo o histórico, pause
            em vez de excluir.
          </p>
        }
        confirmLabel={remover.isPending ? "Excluindo…" : "Excluir"}
        busy={remover.isPending}
        onCancel={() => setARemover(null)}
        onConfirm={() =>
          aRemover &&
          remover.mutate(aRemover.id, {
            onSuccess: () => {
              setARemover(null);
              toast.success("Automação excluída.");
            },
            onError: (e) => toast.error(describeError(e, "Não foi possível excluir a automação.")),
          })
        }
      />
    </div>
  );
}

function ExecucoesLog({ etapaLabel }: { etapaLabel: (id: string) => string }) {
  const { execucoes, showSkeleton, isError, error, isRefreshing, refetch } = useExecucoes(50);
  return (
    <section className="space-y-3" aria-label="Execuções">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-foreground">Execuções recentes</h2>
        <Button variant="ghost" size="sm" className="max-sm:h-10" onClick={() => void refetch()} disabled={isRefreshing}>
          {isRefreshing ? "Atualizando…" : "Atualizar"}
        </Button>
      </div>
      {showSkeleton ? (
        <Skeleton className="h-24 w-full" />
      ) : isError ? (
        <p role="alert" className="text-sm text-destructive">
          {describeError(error, "Não foi possível carregar as execuções.")}
        </p>
      ) : execucoes.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border p-4 text-center text-sm text-muted-foreground">
          Nenhuma execução ainda.
        </p>
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border bg-card" data-testid="execucoes-lista">
          {execucoes.map((e) => (
            <li key={e.id} className="space-y-1 p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={EXEC_VARIANT[e.status] ?? "outline"}>{EXECUCAO_STATUS_LABEL[e.status] ?? e.status}</Badge>
                <span className="min-w-0 flex-1 truncate text-foreground">
                  {e.automacao
                    ? `${TIPO_ACAO_LABEL[e.automacao.tipo] ?? e.automacao.tipo} · ${etapaLabel(e.automacao.stage_id)}`
                    : "Automação excluída"}
                </span>
                <span className="text-xs text-muted-foreground">{horaBR(e.executado_em)}</span>
              </div>
              {e.detalhe ? (
                <p className={cn("break-words text-xs", e.status === "erro" ? "text-destructive" : "text-muted-foreground")}>
                  {e.detalhe}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
