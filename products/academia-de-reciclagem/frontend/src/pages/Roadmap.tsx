/**
 * Roadmap e tarefas — `/roadmap` (contract §A.4, §A.5, §B.4).
 *
 * Phases ordered by `ordem` + tasks as a `KanbanBoard` (`@noctusai/lib/
 * components`) by `estado` — moving a card calls `PATCH /api/tasks/{codigo}`
 * (contract). "Nova tarefa" form + "Preparar sessão" panel (`GET
 * /api/session-prep`).
 */
import { useMemo, useState, type FormEvent } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import {
  Badge,
  Button,
  Card,
  Dialog,
  DialogBody,
  DialogFooter,
  DialogHeader,
  EmptyState,
  ErrorState,
  Field,
  FormError,
  Input,
  PageSkeleton,
  Select,
  Textarea,
} from "@noctusai/lib/design-system";
import { KanbanBoard } from "@noctusai/lib/components";
import { errorMessage } from "@/lib/errors";
import {
  FASE_ESTADOS,
  useCreateTask,
  usePhases,
  useSessionPrep,
  useTasks,
  useUpdateTask,
  type FaseEstado,
  type Task,
} from "@/hooks/useRoadmap";

const ESTADO_LABEL: Record<FaseEstado, string> = {
  pendente: "Pendente",
  "em-andamento": "Em andamento",
  concluida: "Concluída",
  cancelada: "Cancelada",
};

function phaseEstadoBadge(estado: FaseEstado) {
  const variant = estado === "concluida" ? "default" : estado === "cancelada" ? "muted" : "outline";
  return <Badge variant={variant}>{ESTADO_LABEL[estado]}</Badge>;
}

export default function Roadmap() {
  const phases = usePhases();
  const tasks = useTasks();
  const sessionPrep = useSessionPrep();
  const updateTask = useUpdateTask();
  const [createOpen, setCreateOpen] = useState(false);
  const [prepOpen, setPrepOpen] = useState(false);

  const showSkeleton = (phases.isPending && !phases.data) || (tasks.isPending && !tasks.data);
  const isRefreshing = (phases.isFetching && !!phases.data) || (tasks.isFetching && !!tasks.data);

  const orderedPhases = useMemo(
    () => (phases.data?.items ?? []).slice().sort((a, b) => a.ordem - b.ordem),
    [phases.data],
  );

  const columns = useMemo(
    () =>
      FASE_ESTADOS.map((estado) => ({
        stage: { id: estado, label: ESTADO_LABEL[estado] },
        cards: (tasks.data?.items ?? []).filter((t) => t.estado === estado),
      })),
    [tasks.data],
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Roadmap e tarefas</h1>
          <p className="text-sm text-muted-foreground">
            Fases do projeto e o quadro de tarefas.
            {/* lying-loading-ok: text-only suffix, never unmounts real content */}
            {isRefreshing ? " Atualizando…" : ""}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setPrepOpen(true)}>
            Preparar sessão
          </Button>
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            Nova tarefa
          </Button>
        </div>
      </div>

      {showSkeleton ? (
        <PageSkeleton />
      ) : phases.error ? (
        <ErrorState message={errorMessage(phases.error)} />
      ) : (
        <>
          {orderedPhases.length === 0 ? (
            <EmptyState message="Nenhuma fase cadastrada." />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {orderedPhases.map((phase) => (
                <Card key={phase.codigo} className="space-y-1">
                  <div className="flex items-center justify-between gap-2">
                    <Badge variant="outline">{phase.codigo}</Badge>
                    {phaseEstadoBadge(phase.estado)}
                  </div>
                  <p className="font-semibold text-foreground">{phase.titulo}</p>
                  <p className="text-xs text-muted-foreground">{phase.objetivo}</p>
                </Card>
              ))}
            </div>
          )}

          <div>
            <h2 className="mb-3 text-lg font-semibold text-foreground">Tarefas</h2>
            {tasks.error ? (
              <ErrorState message={errorMessage(tasks.error)} />
            ) : (
              <KanbanBoard<Task, FaseEstado>
                columns={columns}
                getCardId={(t) => t.codigo}
                getCardStage={(t) => t.estado}
                onMove={(codigo, fromStage, toStage) => {
                  if (fromStage === toStage) return;
                  updateTask.mutate(
                    { codigo, changes: { estado: toStage } },
                    {
                      onError: (err) => toast.error(errorMessage(err)),
                    },
                  );
                }}
                renderCard={(task) => (
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">{task.codigo}</Badge>
                      <span className="text-xs text-muted-foreground">{task.fase}</span>
                    </div>
                    <p className="text-sm font-medium text-foreground">{task.titulo}</p>
                    {task.detalhe ? (
                      <p className="line-clamp-2 text-xs text-muted-foreground">{task.detalhe}</p>
                    ) : null}
                    {task.bloqueada_por ? (
                      <p className="text-xs text-destructive">Bloqueada por: {task.bloqueada_por}</p>
                    ) : null}
                  </div>
                )}
              />
            )}
          </div>
        </>
      )}

      {createOpen ? (
        <CreateTaskDialog phases={orderedPhases.map((p) => p.codigo)} onClose={() => setCreateOpen(false)} />
      ) : null}
      {prepOpen ? <SessionPrepDialog onClose={() => setPrepOpen(false)} /> : null}
    </div>
  );
}

function CreateTaskDialog({ phases, onClose }: { phases: string[]; onClose: () => void }) {
  const [titulo, setTitulo] = useState("");
  const [fase, setFase] = useState(phases[0] ?? "");
  const [detalhe, setDetalhe] = useState("");
  const [bloqueadaPor, setBloqueadaPor] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const createTask = useCreateTask();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    createTask.mutate(
      { titulo, fase, detalhe: detalhe || undefined, bloqueada_por: bloqueadaPor || undefined },
      {
        onSuccess: () => {
          toast.success("Tarefa criada.");
          onClose();
        },
        onError: (err) => setFormError(errorMessage(err)),
      },
    );
  }

  return (
    <Dialog open onClose={onClose} title="Nova tarefa" className="max-w-lg">
      <form onSubmit={handleSubmit}>
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">Nova tarefa</h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <FormError message={formError} />
          <Field label="Título" required>
            <Input value={titulo} onChange={(e) => setTitulo(e.target.value)} required />
          </Field>
          <Field label="Fase" required>
            <Select value={fase} onChange={(e) => setFase(e.target.value)} required>
              {phases.length === 0 ? <option value="">Nenhuma fase disponível</option> : null}
              {phases.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Detalhe">
            <Textarea rows={2} value={detalhe} onChange={(e) => setDetalhe(e.target.value)} />
          </Field>
          <Field label="Bloqueada por (código ou descrição)">
            <Input value={bloqueadaPor} onChange={(e) => setBloqueadaPor(e.target.value)} />
          </Field>
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={createTask.isPending}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" disabled={createTask.isPending || !fase}>
            {createTask.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Criar
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}

function SessionPrepDialog({ onClose }: { onClose: () => void }) {
  const { data, isPending, error } = useSessionPrep();

  return (
    <Dialog open onClose={onClose} title="Preparar sessão" className="max-w-lg">
      <DialogHeader>
        <h2 className="text-lg font-semibold text-foreground">Preparar sessão</h2>
      </DialogHeader>
      <DialogBody className="space-y-4">
        {isPending && !data ? (
          <p className="text-sm text-muted-foreground">Carregando…</p>
        ) : error ? (
          <ErrorState message={errorMessage(error)} />
        ) : !data ? null : (
          <>
            <div>
              <p className="text-xs font-medium text-muted-foreground">Fase atual</p>
              {data.fase_atual ? (
                <p className="text-sm text-foreground">
                  {data.fase_atual.codigo} — {data.fase_atual.titulo}
                </p>
              ) : (
                <p className="text-sm text-muted-foreground">Nenhuma fase em andamento.</p>
              )}
            </div>
            <div>
              <p className="text-xs font-medium text-muted-foreground">Próximas tarefas</p>
              {data.proximas.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nenhuma.</p>
              ) : (
                <ul className="space-y-1">
                  {data.proximas.map((t) => (
                    <li key={t.codigo} className="text-sm text-foreground">
                      {t.codigo} — {t.titulo}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <p className="text-xs font-medium text-muted-foreground">Tarefas bloqueadas</p>
              {data.bloqueadas.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nenhuma.</p>
              ) : (
                <ul className="space-y-1">
                  {data.bloqueadas.map((t) => (
                    <li key={t.codigo} className="text-sm text-destructive">
                      {t.codigo} — {t.titulo} ({t.bloqueada_por})
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <p className="text-xs font-medium text-muted-foreground">
                Perguntas abertas: {data.perguntas_abertas}
              </p>
              {data.perguntas_bloqueantes.length > 0 ? (
                <ul className="mt-1 space-y-1">
                  {data.perguntas_bloqueantes.map((q) => (
                    <li key={q.codigo} className="text-sm text-destructive">
                      {q.codigo} — {q.pergunta}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          </>
        )}
      </DialogBody>
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          Fechar
        </Button>
      </DialogFooter>
    </Dialog>
  );
}
