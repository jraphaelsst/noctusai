/**
 * Avaliações tab — Agent Studio CONTRACT.md §D4, §G "Avaliações".
 *
 * Cases list/editor (entrada, contexto, deve[]/nao_deve[] editable lists,
 * rubrica, tags) + runs list + "Rodar avaliação" on the draft + run detail
 * (per-case pass/fail, score, saída, veredito per criterion, judge notes),
 * polling while `executando` (`useEvalRun`, `KB §
 * PATTERNS/frontend/lying-loading-state.md`-compliant: `showSkeleton =
 * isPending && !data`, never a bare `isLoading`). Page-scoped CRUD: cases
 * are created/edited/run from this one tab.
 *
 * "The draft" version — §D4's "Rodar avaliação" runs against
 * `agent.versoes[status='rascunho'].id`, which lives on `AgentDetail`
 * (contract §D1, FE-DEF's `useStudioAgents`/`useVersions.ts`, not on this
 * branch — contract §J2.4). `useDraftVersion` below is FE-KE's own,
 * narrowly-scoped read of the SAME already-specified `GET
 * /api/studio/agents/{key}` endpoint — it exists only to find the draft's
 * `id`/`versao` for the "Rodar avaliação" button, not to re-implement
 * FE-DEF's Versões tab.
 */
import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, ClipboardList, Play, Plus, XCircle } from "lucide-react";
import { toast } from "sonner";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  FormError,
  Input,
  PageSkeleton,
  Textarea,
} from "@noctusai/lib/design-system";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import {
  useCreateEvalCase,
  useCreateEvalRun,
  useDeleteEvalCase,
  useEvalCases,
  useEvalRun,
  useEvalRuns,
} from "@/hooks/studio/useEvals";
import type { EvalCase, EvalRunStatus } from "@/api/studio/types-ke";

interface AgentVersionSummaryLite {
  id: string;
  versao: number;
  status: "rascunho" | "ativa" | "substituida";
}

interface AgentDetailLite {
  versoes: AgentVersionSummaryLite[];
}

/** Narrow read of `GET /api/studio/agents/{key}` — see file header. */
function useDraftVersion(agentKey: string) {
  const query = useQuery<AgentDetailLite>({
    queryKey: ["studio", agentKey, "agent-detail-lite"],
    queryFn: () => api.get<AgentDetailLite>(`/api/studio/agents/${agentKey}`),
    enabled: !!agentKey,
  });
  return query.data?.versoes.find((v) => v.status === "rascunho") ?? null;
}

const RUN_STATUS_VARIANT: Record<EvalRunStatus, "default" | "muted" | "destructive" | "outline"> = {
  pendente: "muted",
  executando: "muted",
  concluida: "default",
  falhou: "destructive",
  cancelada: "outline",
};

function CaseForm({ agentKey, onDone }: { agentKey: string; onDone: () => void }) {
  const [titulo, setTitulo] = useState("");
  const [slug, setSlug] = useState("");
  const [entrada, setEntrada] = useState("");
  const [contexto, setContexto] = useState("");
  const [deve, setDeve] = useState("");
  const [naoDeve, setNaoDeve] = useState("");
  const [rubrica, setRubrica] = useState("");
  const [error, setError] = useState<string | null>(null);
  const create = useCreateEvalCase(agentKey);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const deveList = deve.split("\n").map((s) => s.trim()).filter(Boolean);
    const naoDeveList = naoDeve.split("\n").map((s) => s.trim()).filter(Boolean);
    if (deveList.length === 0 && naoDeveList.length === 0) {
      setError("Informe ao menos um critério (deve ou não deve).");
      return;
    }
    try {
      await create.mutateAsync({
        slug,
        titulo,
        entrada,
        contexto: contexto || null,
        criterios: { deve: deveList, nao_deve: naoDeveList },
        rubrica: rubrica || null,
        tags: [],
        ativo: true,
      });
      toast.success("Caso criado.");
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 rounded-md border border-border p-3" data-testid="evals-new-case-form">
      <FormError message={error} />
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Slug" required>
          <Input value={slug} onChange={(e) => setSlug(e.target.value)} required />
        </Field>
        <Field label="Título" required>
          <Input value={titulo} onChange={(e) => setTitulo(e.target.value)} required />
        </Field>
      </div>
      <Field label="Entrada (mensagem enviada ao agente)" required>
        <Textarea rows={3} value={entrada} onChange={(e) => setEntrada(e.target.value)} required />
      </Field>
      <Field label="Contexto (opcional)">
        <Textarea rows={2} value={contexto} onChange={(e) => setContexto(e.target.value)} />
      </Field>
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Deve (uma por linha)">
          <Textarea rows={3} value={deve} onChange={(e) => setDeve(e.target.value)} />
        </Field>
        <Field label="Não deve (uma por linha)">
          <Textarea rows={3} value={naoDeve} onChange={(e) => setNaoDeve(e.target.value)} />
        </Field>
      </div>
      <Field label="Rubrica (opcional)">
        <Textarea rows={2} value={rubrica} onChange={(e) => setRubrica(e.target.value)} />
      </Field>
      <Button type="submit" variant="primary" size="sm" disabled={create.isPending}>
        Criar caso
      </Button>
    </form>
  );
}

function RunDetailPanel({ agentKey, runId }: { agentKey: string; runId: string }) {
  const { data: run, showSkeleton, isError } = useEvalRun(agentKey, runId);

  if (showSkeleton) return <PageSkeleton />;
  if (isError || !run) return <ErrorState message="Erro ao carregar a execução." />;

  return (
    <Card className="space-y-3" data-testid="evals-run-detail">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-foreground">
            Execução {run.id.slice(0, 8)} — {run.aprovados}/{run.total} aprovados
          </p>
          <p className="text-xs text-muted-foreground">
            score {run.score != null ? run.score.toFixed(3) : "—"} · limiar {run.limiar.toFixed(3)}
          </p>
        </div>
        <Badge variant={RUN_STATUS_VARIANT[run.status]}>{run.status}</Badge>
      </div>
      {run.erro && <FormError message={run.erro} />}
      <div className="space-y-2">
        {run.resultados.map((r) => (
          <div key={r.case_id} className="rounded-md border border-border p-2 text-xs" data-testid={`evals-result-${r.case_id}`}>
            <div className="flex items-center gap-2">
              {r.status === "aprovado" ? (
                <CheckCircle2 className="h-3.5 w-3.5 text-primary" />
              ) : r.status === "reprovado" || r.status === "erro" ? (
                <XCircle className="h-3.5 w-3.5 text-destructive" />
              ) : (
                <span className="h-3.5 w-3.5 rounded-full border border-muted-foreground/40" />
              )}
              <span className="font-medium text-foreground">{r.case_titulo}</span>
              <span className="text-muted-foreground">{r.status}</span>
              {r.score != null && <span className="text-muted-foreground">score {r.score.toFixed(2)}</span>}
            </div>
            {r.saida && <p className="mt-1 whitespace-pre-wrap text-muted-foreground">{r.saida}</p>}
            {r.veredito && r.veredito.length > 0 && (
              <ul className="mt-1 space-y-0.5">
                {r.veredito.map((v, i) => (
                  <li key={i} className={v.ok ? "text-primary" : "text-destructive"}>
                    [{v.tipo}] {v.criterio} — {v.ok ? "ok" : "falhou"}
                    {v.motivo ? ` — ${v.motivo}` : ""}
                  </li>
                ))}
              </ul>
            )}
            {r.notas_juiz && <p className="mt-1 italic text-muted-foreground">{r.notas_juiz}</p>}
          </div>
        ))}
      </div>
    </Card>
  );
}

export default function EvalsTab({ agentKey }: { agentKey: string }) {
  const isAdmin = useIsAdmin();
  const { data: cases, showSkeleton, isError, error } = useEvalCases(agentKey);
  const { data: runs } = useEvalRuns(agentKey);
  const draft = useDraftVersion(agentKey);
  const createRun = useCreateEvalRun(agentKey);
  const deleteCase = useDeleteEvalCase(agentKey);
  const [showNewCase, setShowNewCase] = useState(false);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);

  async function handleRun() {
    if (!draft) return;
    try {
      const run = await createRun.mutateAsync({ version_id: draft.id });
      setSelectedRun(run.id);
      toast.success("Avaliação iniciada.");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  if (showSkeleton) return <PageSkeleton />;
  if (isError) return <ErrorState message={errorMessage(error)} />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
          <ClipboardList className="h-4 w-4" /> Casos de avaliação
        </p>
        {isAdmin && (
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="sm"
              onClick={handleRun}
              disabled={!draft || createRun.isPending || !cases || cases.length === 0}
              data-testid="evals-run-button"
              title={!draft ? "Crie um rascunho para rodar avaliações." : undefined}
            >
              <Play className="mr-1.5 h-3.5 w-3.5" />
              Rodar avaliação
            </Button>
            <Button variant="outline" size="sm" onClick={() => setShowNewCase((v) => !v)}>
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              Novo caso
            </Button>
          </div>
        )}
      </div>

      {isAdmin && showNewCase && <CaseForm agentKey={agentKey} onDone={() => setShowNewCase(false)} />}

      {!cases || cases.length === 0 ? (
        <EmptyState message="Nenhum caso de avaliação ainda." />
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {cases.map((c: EvalCase) => (
            <Card key={c.id} className="space-y-1" data-testid={`evals-case-${c.slug}`}>
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium text-foreground">{c.titulo}</p>
                {isAdmin && (
                  <button
                    type="button"
                    className="text-xs text-destructive hover:underline"
                    onClick={() => deleteCase.mutate(c.id)}
                  >
                    Excluir
                  </button>
                )}
              </div>
              <p className="line-clamp-2 text-xs text-muted-foreground">{c.entrada}</p>
              <div className="flex flex-wrap gap-1 text-[10px] text-muted-foreground">
                {c.criterios.deve.length > 0 && <span>{c.criterios.deve.length} deve</span>}
                {c.criterios.nao_deve.length > 0 && <span>{c.criterios.nao_deve.length} não deve</span>}
              </div>
            </Card>
          ))}
        </div>
      )}

      <div className="space-y-2">
        <p className="text-sm font-semibold text-foreground">Execuções</p>
        {!runs || runs.length === 0 ? (
          <EmptyState message="Nenhuma execução ainda." />
        ) : (
          <div className="divide-y divide-border rounded-md border border-border">
            {runs.map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() => setSelectedRun(r.id)}
                data-testid={`evals-run-row-${r.id}`}
                className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs hover:bg-accent/50 ${
                  selectedRun === r.id ? "bg-accent/40" : ""
                }`}
              >
                <span>{new Date(r.started_at ?? r.finished_at ?? "").toLocaleString("pt-BR")}</span>
                <span className="text-muted-foreground">
                  {r.aprovados}/{r.total}
                </span>
                <Badge variant={RUN_STATUS_VARIANT[r.status]}>{r.status}</Badge>
              </button>
            ))}
          </div>
        )}
      </div>

      {selectedRun && <RunDetailPanel agentKey={agentKey} runId={selectedRun} />}
    </div>
  );
}
