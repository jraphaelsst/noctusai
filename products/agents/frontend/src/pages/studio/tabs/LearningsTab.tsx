/**
 * Aprendizados tab — Agent Packages CONTRACT §D3 / §H2 (dev-advisors only).
 *
 * Learnings pushed from consumer repos: list with project + status filters,
 * a row detail, and admin-only Aceitar / Descartar with a REQUIRED note
 * (the server also enforces admin on PATCH). The review is optimistic with
 * rollback; a failure is shown inline, never swallowed.
 */
import { useState, type FormEvent } from "react";
import { Check, X } from "lucide-react";
import { Badge, Button, Field, FormError, Textarea } from "@noctusai/lib/design-system";
import type { Learning, LearningReviewStatus, LearningStatus } from "@/api/studio/types-packages";
import { StudioEmpty, StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { useLearnings, usePackageProjects, useReviewLearning } from "@/hooks/studio/usePackages";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { errorMessage } from "@/lib/errors";
import { formatDate } from "@/lib/utils";

const SELECT_CLASS =
  "h-9 rounded-md border border-input bg-background px-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50";

const STATUS_OPTIONS: { value: "" | LearningStatus; label: string }[] = [
  { value: "", label: "Todos os status" },
  { value: "novo", label: "Novo" },
  { value: "aceito", label: "Aceito" },
  { value: "descartado", label: "Descartado" },
  { value: "promovido", label: "Promovido" },
];

const STATUS_LABEL: Record<LearningStatus, string> = {
  novo: "Novo",
  aceito: "Aceito",
  descartado: "Descartado",
  promovido: "Promovido",
};

function StatusBadge({ status }: { status: LearningStatus }) {
  const variant = status === "aceito" || status === "promovido" ? "default" : status === "descartado" ? "muted" : "outline";
  return <Badge variant={variant}>{STATUS_LABEL[status] ?? status}</Badge>;
}

function ReviewForm({ learning, agentKey }: { learning: Learning; agentKey: string }) {
  const [nota, setNota] = useState("");
  const [error, setError] = useState<string | null>(null);
  const review = useReviewLearning(agentKey);

  async function submit(status: LearningReviewStatus, e?: FormEvent) {
    e?.preventDefault();
    if (!nota.trim()) {
      setError("Informe uma nota para registrar a decisão.");
      return;
    }
    setError(null);
    try {
      await review.mutateAsync({
        id: learning.id,
        review: { status, nota: nota.trim() },
      });
      setNota("");
    } catch (err) {
      setError(`Não foi possível salvar a revisão: ${errorMessage(err)}`);
    }
  }

  return (
    <form className="space-y-2 border-t border-border pt-3" data-testid="learning-review-form" onSubmit={(e) => e.preventDefault()}>
      <Field label="Nota da revisão (obrigatória)">
        <Textarea rows={2} value={nota} onChange={(e) => setNota(e.target.value)} data-testid="learning-review-nota" maxLength={2000} />
      </Field>
      {error && <FormError message={error} />}
      <div className="flex gap-2">
        <Button type="button" size="sm" disabled={review.isPending} onClick={() => void submit("aceito")} data-testid="learning-accept">
          <Check className="mr-1 h-3.5 w-3.5" /> Aceitar
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={review.isPending}
          onClick={() => void submit("descartado")}
          data-testid="learning-discard"
        >
          <X className="mr-1 h-3.5 w-3.5" /> Descartar
        </Button>
      </div>
    </form>
  );
}

function LearningDetail({ learning, agentKey, isAdmin }: { learning: Learning; agentKey: string; isAdmin: boolean }) {
  return (
    <section className="space-y-3 rounded-lg border border-border bg-card p-4" data-testid="learning-detail">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{learning.tipo}</Badge>
        <StatusBadge status={learning.status} />
        <span className="text-xs text-muted-foreground">
          Projeto: <span className="font-mono">{learning.project_slug}</span> · {learning.data}
        </span>
      </div>
      <p className="whitespace-pre-wrap text-sm text-foreground">{learning.texto}</p>
      <div>
        <p className="text-xs font-medium text-muted-foreground">Evidência</p>
        <p className="whitespace-pre-wrap text-sm" data-testid="learning-evidencia">
          {learning.evidencia || "—"}
        </p>
      </div>
      {learning.nota && (
        <div>
          <p className="text-xs font-medium text-muted-foreground">Nota da revisão</p>
          <p className="whitespace-pre-wrap text-sm">{learning.nota}</p>
          {learning.reviewed_at && <p className="text-xs text-muted-foreground">Revisado em {formatDate(learning.reviewed_at, true)}</p>}
        </div>
      )}
      {isAdmin && learning.status !== "promovido" && <ReviewForm key={learning.id} learning={learning} agentKey={agentKey} />}
    </section>
  );
}

export default function LearningsTab({ agentKey }: { agentKey: string }) {
  const isAdmin = useIsAdmin();
  const [project, setProject] = useState("");
  const [status, setStatus] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data: projects } = usePackageProjects(agentKey);
  const { data: items, showSkeleton, isRefreshing, isError, error, refetch } = useLearnings(agentKey, project, status);

  const selected = items?.find((l) => l.id === selectedId) ?? null;

  return (
    <div className="space-y-4" data-testid="learnings-tab">
      <div className="flex flex-wrap items-center gap-2">
        <select aria-label="Filtrar por projeto" className={SELECT_CLASS} value={project} onChange={(e) => setProject(e.target.value)}>
          <option value="">Todos os projetos</option>
          {(projects ?? []).map((p) => (
            <option key={p.slug} value={p.slug}>
              {p.slug}
            </option>
          ))}
        </select>
        <select aria-label="Filtrar por status" className={SELECT_CLASS} value={status} onChange={(e) => setStatus(e.target.value)}>
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        {isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
      </div>

      {showSkeleton ? (
        <StudioLoading rows={3} testId="learnings-skeleton" />
      ) : isError ? (
        <StudioError error={error} onRetry={refetch} />
      ) : !items || items.length === 0 ? (
        <StudioEmpty titulo="Nenhum aprendizado encontrado">
          <p className="text-xs">Os aprendizados chegam quando um repositório consumidor faz push com LEARNINGS.md atualizado.</p>
        </StudioEmpty>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
          <ul className="space-y-1" data-testid="learnings-list">
            {items.map((l) => (
              <li key={l.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(l.id)}
                  data-testid={`learning-row-${l.id}`}
                  className={`w-full rounded-md border px-3 py-2 text-left text-sm hover:bg-accent ${
                    selectedId === l.id ? "border-primary bg-accent" : "border-border"
                  }`}
                >
                  <span className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">{l.tipo}</Badge>
                    <StatusBadge status={l.status} />
                    <span className="font-mono text-xs text-muted-foreground">{l.project_slug}</span>
                    <span className="text-xs text-muted-foreground">{l.data}</span>
                  </span>
                  <span className="mt-1 line-clamp-2 block text-foreground">{l.texto}</span>
                </button>
              </li>
            ))}
          </ul>
          {selected ? (
            <LearningDetail learning={selected} agentKey={agentKey} isAdmin={isAdmin} />
          ) : (
            <p className="text-sm text-muted-foreground">Selecione um aprendizado para ver os detalhes.</p>
          )}
        </div>
      )}
    </div>
  );
}
