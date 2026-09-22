/**
 * Avaliações tab — Agent Studio CONTRACT.md §D4, §G "Avaliações".
 *
 * Cases list/editor (entrada, contexto, deve[]/nao_deve[] editable lists,
 * rubrica, tags, ativo) + runs list + "Rodar avaliação" on the draft + run
 * detail (per-case pass/fail, score, saída, veredito per criterion, judge
 * notes), polling while `executando` (`useEvalRun`, `KB §
 * PATTERNS/frontend/lying-loading-state.md`-compliant: `showSkeleton =
 * isPending && !data`, never a bare `isLoading`). Page-scoped CRUD: cases
 * are created/edited/(de)activated/run from this one tab.
 *
 * "The draft" version — §D4's "Rodar avaliação" runs against
 * `agent.versoes[status='rascunho'].id`, which lives on `AgentDetail`
 * (contract §D1). `useDraftVersion` below reads it off the SAME
 * `useStudioAgent`/`studioKeys.detail` query the rest of the shell uses
 * (`hooks/studio/useStudioAgents.ts`) — one cache entry per agent, never a
 * second `AgentDetail`-shaped query under its own key.
 *
 * Case delete conflict: a case with results attached is protected by the
 * backend (409 `case_in_use`, since deleting it would orphan
 * `eval_results` rows referenced by past runs). The UI never dead-ends the
 * admin there — it offers "Desativar" (`PATCH {ativo: false}`), which keeps
 * the case's history but excludes it from future runs.
 *
 * Partial-run labelling: `EvalRun` carries no explicit "ran a case subset"
 * flag (contract §D4), so a run is treated as partial when its `total` is
 * smaller than the agent's ACTIVE case count at render time — the same
 * population "Rodar avaliação" (no `case_ids`) would have used. A run
 * against every active case never gets the label, even if cases were
 * archived afterwards; that's an acceptable drift for a display-only badge.
 */
import { useState, type FormEvent } from "react";
import { CheckCircle2, ClipboardList, Pencil, Play, Plus, StopCircle, XCircle } from "lucide-react";
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
import { ApiError, errorMessage } from "@/lib/errors";
import { useStudioAgent } from "@/hooks/studio/useStudioAgents";
import {
  useCancelEvalRun,
  useCreateEvalCase,
  useCreateEvalRun,
  useDeleteEvalCase,
  useEvalCases,
  useEvalRun,
  useEvalRuns,
  useUpdateEvalCase,
} from "@/hooks/studio/useEvals";
import type { EvalCase, EvalCaseCreate, EvalRun, EvalRunStatus } from "@/api/studio/types-ke";

const IN_FLIGHT_RUN: EvalRunStatus[] = ["pendente", "executando"];

/** See file header. */
function useDraftVersion(agentKey: string) {
  const { data: agent } = useStudioAgent(agentKey);
  return agent?.versoes.find((v) => v.status === "rascunho") ?? null;
}

/** See file header ("Partial-run labelling"). */
function isPartialRun(run: EvalRun, activeCasesCount: number): boolean {
  return activeCasesCount > 0 && run.total > 0 && run.total < activeCasesCount;
}

const RUN_STATUS_VARIANT: Record<EvalRunStatus, "default" | "muted" | "destructive" | "outline"> = {
  pendente: "muted",
  executando: "muted",
  concluida: "default",
  falhou: "destructive",
  cancelada: "outline",
};

/** One `deve`/`não deve` criterion list — items are added and removed one at
 * a time, never edited as a single blob of text. */
function CriteriaListField({
  label,
  items,
  onChange,
  testId,
}: {
  label: string;
  items: string[];
  onChange: (items: string[]) => void;
  testId: string;
}) {
  const [draft, setDraft] = useState("");
  function add() {
    const v = draft.trim();
    if (!v) return;
    onChange([...items, v]);
    setDraft("");
  }
  return (
    <Field label={label}>
      <div className="space-y-1.5" data-testid={testId}>
        {items.length > 0 && (
          <ul className="space-y-1">
            {items.map((item, i) => (
              <li
                key={`${i}-${item}`}
                className="flex items-center justify-between gap-2 rounded-md border border-border px-2 py-1 text-xs"
              >
                <span className="break-words">{item}</span>
                <button
                  type="button"
                  className="flex-shrink-0 text-muted-foreground hover:text-destructive hover:underline"
                  onClick={() => onChange(items.filter((_, idx) => idx !== i))}
                  data-testid={`${testId}-remove-${i}`}
                >
                  Remover
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="flex gap-2">
          <Input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Adicionar critério"
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
            data-testid={`${testId}-draft`}
          />
          <Button type="button" size="sm" variant="outline" onClick={add} data-testid={`${testId}-add`}>
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </Field>
  );
}

interface CaseFormValue {
  slug: string;
  titulo: string;
  entrada: string;
  contexto: string;
  deve: string[];
  naoDeve: string[];
  rubrica: string;
  tags: string;
  ativo: boolean;
}

function emptyCaseForm(): CaseFormValue {
  return { slug: "", titulo: "", entrada: "", contexto: "", deve: [], naoDeve: [], rubrica: "", tags: "", ativo: true };
}

function caseToForm(c: EvalCase): CaseFormValue {
  return {
    slug: c.slug,
    titulo: c.titulo,
    entrada: c.entrada,
    contexto: c.contexto ?? "",
    deve: c.criterios.deve,
    naoDeve: c.criterios.nao_deve,
    rubrica: c.rubrica ?? "",
    tags: c.tags.join(", "),
    ativo: c.ativo,
  };
}

function formToPayload(f: CaseFormValue): EvalCaseCreate {
  return {
    slug: f.slug,
    titulo: f.titulo,
    entrada: f.entrada,
    contexto: f.contexto || null,
    criterios: { deve: f.deve, nao_deve: f.naoDeve },
    rubrica: f.rubrica || null,
    tags: f.tags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean),
    ativo: f.ativo,
  };
}

/** Shared fields for both "Novo caso" (create) and "Editar caso" (patch). */
function CaseFormFields({
  value,
  onChange,
  slugEditable,
  showAtivo,
}: {
  value: CaseFormValue;
  onChange: (v: CaseFormValue) => void;
  slugEditable: boolean;
  showAtivo: boolean;
}) {
  return (
    <>
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Slug" required>
          <Input
            value={value.slug}
            onChange={(e) => onChange({ ...value, slug: e.target.value })}
            required
            disabled={!slugEditable}
          />
        </Field>
        <Field label="Título" required>
          <Input value={value.titulo} onChange={(e) => onChange({ ...value, titulo: e.target.value })} required />
        </Field>
      </div>
      <Field label="Entrada (mensagem enviada ao agente)" required>
        <Textarea rows={3} value={value.entrada} onChange={(e) => onChange({ ...value, entrada: e.target.value })} required />
      </Field>
      <Field label="Contexto (opcional)">
        <Textarea rows={2} value={value.contexto} onChange={(e) => onChange({ ...value, contexto: e.target.value })} />
      </Field>
      <div className="grid gap-2 sm:grid-cols-2">
        <CriteriaListField
          label="Deve"
          items={value.deve}
          onChange={(deve) => onChange({ ...value, deve })}
          testId="evals-criteria-deve"
        />
        <CriteriaListField
          label="Não deve"
          items={value.naoDeve}
          onChange={(naoDeve) => onChange({ ...value, naoDeve })}
          testId="evals-criteria-nao-deve"
        />
      </div>
      <Field label="Rubrica (opcional)">
        <Textarea rows={2} value={value.rubrica} onChange={(e) => onChange({ ...value, rubrica: e.target.value })} />
      </Field>
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Tags (separadas por vírgula)">
          <Input value={value.tags} onChange={(e) => onChange({ ...value, tags: e.target.value })} />
        </Field>
        {showAtivo && (
          <label className="flex items-end gap-1.5 pb-2 text-xs">
            <input
              type="checkbox"
              checked={value.ativo}
              onChange={(e) => onChange({ ...value, ativo: e.target.checked })}
              data-testid="evals-case-ativo"
            />
            ativo (entra nas próximas execuções)
          </label>
        )}
      </div>
    </>
  );
}

function CaseForm({ agentKey, onDone }: { agentKey: string; onDone: () => void }) {
  const [value, setValue] = useState<CaseFormValue>(emptyCaseForm());
  const [error, setError] = useState<string | null>(null);
  const create = useCreateEvalCase(agentKey);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (value.deve.length === 0 && value.naoDeve.length === 0) {
      setError("Informe ao menos um critério (deve ou não deve).");
      return;
    }
    try {
      await create.mutateAsync(formToPayload(value));
      toast.success("Caso criado.");
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 rounded-md border border-border p-3" data-testid="evals-new-case-form">
      <FormError message={error} />
      <CaseFormFields value={value} onChange={setValue} slugEditable showAtivo={false} />
      <Button type="submit" variant="primary" size="sm" disabled={create.isPending}>
        Criar caso
      </Button>
    </form>
  );
}

/** The case editor (§G): entrada, contexto, deve[]/nao_deve[], rubrica,
 * tags, ativo — full patch via `useUpdateEvalCase`. Slug is immutable once
 * created (it identifies the case; `EvalCasePatch` never carries it). */
function CaseEditForm({ agentKey, caseData, onDone }: { agentKey: string; caseData: EvalCase; onDone: () => void }) {
  const [value, setValue] = useState<CaseFormValue>(() => caseToForm(caseData));
  const [error, setError] = useState<string | null>(null);
  const update = useUpdateEvalCase(agentKey);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (value.deve.length === 0 && value.naoDeve.length === 0) {
      setError("Informe ao menos um critério (deve ou não deve).");
      return;
    }
    const { slug: _slug, ...patch } = formToPayload(value);
    void _slug;
    try {
      await update.mutateAsync({ caseId: caseData.id, patch });
      toast.success("Caso salvo.");
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-2 rounded-md border border-border p-3"
      data-testid={`evals-edit-case-form-${caseData.slug}`}
    >
      <FormError message={error} />
      <CaseFormFields value={value} onChange={setValue} slugEditable={false} showAtivo />
      <div className="flex gap-2">
        <Button type="submit" variant="primary" size="sm" disabled={update.isPending}>
          Salvar
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onDone}>
          Cancelar edição
        </Button>
      </div>
    </form>
  );
}

function RunDetailPanel({
  agentKey,
  runId,
  isAdmin,
  activeCasesCount,
}: {
  agentKey: string;
  runId: string;
  isAdmin: boolean;
  activeCasesCount: number;
}) {
  const { data: run, showSkeleton, isError } = useEvalRun(agentKey, runId);
  const cancelRun = useCancelEvalRun(agentKey);

  if (showSkeleton) return <PageSkeleton />;
  if (isError || !run) return <ErrorState message="Erro ao carregar a execução." />;

  async function handleCancel() {
    try {
      await cancelRun.mutateAsync(run!.id);
      toast.success("Avaliação cancelada.");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <Card className="space-y-3" data-testid="evals-run-detail">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-foreground">
            Execução {run.id.slice(0, 8)} — {run.aprovados}/{run.total} aprovados
          </p>
          <p className="text-xs text-muted-foreground">
            score {run.score != null ? run.score.toFixed(3) : "—"} · limiar {run.limiar.toFixed(3)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isPartialRun(run, activeCasesCount) && (
            <Badge variant="outline" data-testid="evals-run-partial">
              parcial (não vale para publicar)
            </Badge>
          )}
          <Badge variant={RUN_STATUS_VARIANT[run.status]}>{run.status}</Badge>
          {isAdmin && IN_FLIGHT_RUN.includes(run.status) && (
            <Button
              size="sm"
              variant="outline"
              onClick={handleCancel}
              disabled={cancelRun.isPending}
              data-testid="evals-run-cancel"
            >
              <StopCircle className="mr-1.5 h-3.5 w-3.5" />
              Cancelar
            </Button>
          )}
        </div>
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
  const updateCase = useUpdateEvalCase(agentKey);
  const [showNewCase, setShowNewCase] = useState(false);
  const [editingCase, setEditingCase] = useState<string | null>(null);
  const [inUseCase, setInUseCase] = useState<EvalCase | null>(null);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);

  const activeCasesCount = cases?.filter((c) => c.ativo).length ?? 0;

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

  async function handleDelete(c: EvalCase) {
    setInUseCase(null);
    try {
      await deleteCase.mutateAsync(c.id);
      toast.success("Caso excluído.");
    } catch (err) {
      // §G: a case with attached results can't be deleted (409 case_in_use)
      // — offer deactivation instead of dead-ending the admin on an error.
      if (err instanceof ApiError && err.code === "case_in_use") {
        setInUseCase(c);
      } else {
        toast.error(errorMessage(err));
      }
    }
  }

  async function handleDeactivate(c: EvalCase) {
    try {
      await updateCase.mutateAsync({ caseId: c.id, patch: { ativo: false } });
      toast.success("Caso desativado.");
      setInUseCase(null);
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
          {cases.map((c: EvalCase) =>
            editingCase === c.id ? (
              <CaseEditForm key={c.id} agentKey={agentKey} caseData={c} onDone={() => setEditingCase(null)} />
            ) : (
              <Card key={c.id} className="space-y-1" data-testid={`evals-case-${c.slug}`}>
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-medium text-foreground">{c.titulo}</p>
                  {isAdmin && (
                    <div className="flex flex-shrink-0 items-center gap-2">
                      {!c.ativo && <Badge variant="muted">inativo</Badge>}
                      <button
                        type="button"
                        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:underline"
                        onClick={() => setEditingCase(c.id)}
                        data-testid={`evals-case-edit-${c.slug}`}
                      >
                        <Pencil className="h-3 w-3" /> Editar
                      </button>
                      <button
                        type="button"
                        className="text-xs text-destructive hover:underline"
                        onClick={() => handleDelete(c)}
                        data-testid={`evals-case-delete-${c.slug}`}
                      >
                        Excluir
                      </button>
                    </div>
                  )}
                </div>
                <p className="line-clamp-2 text-xs text-muted-foreground">{c.entrada}</p>
                <div className="flex flex-wrap gap-1 text-[10px] text-muted-foreground">
                  {c.criterios.deve.length > 0 && <span>{c.criterios.deve.length} deve</span>}
                  {c.criterios.nao_deve.length > 0 && <span>{c.criterios.nao_deve.length} não deve</span>}
                  {c.tags.map((t) => (
                    <span key={t} className="rounded-full bg-accent px-1.5">
                      {t}
                    </span>
                  ))}
                </div>
                {inUseCase?.id === c.id && (
                  <div
                    className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-700"
                    role="alert"
                    data-testid={`evals-case-in-use-${c.slug}`}
                  >
                    <p>
                      Este caso já tem resultados de avaliações anteriores e não pode ser excluído. Você pode
                      desativá-lo para tirá-lo das próximas execuções sem perder o histórico.
                    </p>
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-1.5"
                      onClick={() => handleDeactivate(c)}
                      disabled={updateCase.isPending}
                      data-testid={`evals-case-deactivate-${c.slug}`}
                    >
                      Desativar
                    </Button>
                  </div>
                )}
              </Card>
            ),
          )}
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
                <div className="flex items-center gap-2">
                  {isPartialRun(r, activeCasesCount) && (
                    <Badge variant="outline" data-testid={`evals-run-partial-${r.id}`}>
                      parcial
                    </Badge>
                  )}
                  <Badge variant={RUN_STATUS_VARIANT[r.status]}>{r.status}</Badge>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {selectedRun && (
        <RunDetailPanel agentKey={agentKey} runId={selectedRun} isAdmin={isAdmin} activeCasesCount={activeCasesCount} />
      )}
    </div>
  );
}
