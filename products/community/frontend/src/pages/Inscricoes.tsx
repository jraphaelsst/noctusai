/**
 * Inscrições — `/inscricoes` (community-m1-contract.md §Frontend).
 *
 * Two sections on one page, per contract:
 *  1. The pending-first applications queue (status tabs + `resumo`, an
 *     expandable answers view resolved against `usePerguntas()` labels —
 *     the backend never inlines question text into `respostas`), an
 *     approve dialog (optional plan select) and a reject dialog (motivo
 *     required).
 *  2. The manager-defined questions editor — a flat CRUD entity
 *     (pergunta/tipo/opções/obrigatória/ordem), so it CONSUMES
 *     `<ResourceManager/>` (`@noctusai/lib/components`) exactly like
 *     Planos does, rather than hand-rolling another list+modal shell.
 *     "Reorder" is the contract's own "drag-free `ordem` field" — an
 *     editable number, not drag-and-drop. `DELETE` soft-deactivates
 *     (`ativa=false`); a row action reactivates via `PATCH {ativa:true}`,
 *     mirroring the Planos page's reactivate seam.
 */
import { useState, type FormEvent } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button, Input, Dialog, DialogHeader, DialogBody, DialogFooter } from "@noctusai/lib/design-system";
import { ResourceManager } from "@noctusai/lib/components";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { Card, EmptyState, ErrorState, Field, FormError, Select, Textarea } from "@/components/FormControls";
import {
  useAplicacoes,
  useAprovarAplicacao,
  useRejeitarAplicacao,
  usePerguntas,
  type Aplicacao,
  type AplicacaoStatus,
  type Pergunta,
} from "@/hooks/useAplicacoes";
import { usePlanos } from "@/hooks/usePlanos";

const STATUS_LABELS: Record<AplicacaoStatus, string> = {
  pendente: "Pendente",
  aprovada: "Aprovada",
  rejeitada: "Rejeitada",
};

const TIPO_LABELS: Record<Pergunta["tipo"], string> = {
  texto: "Texto curto",
  texto_longo: "Texto longo",
  escolha_unica: "Escolha única",
  escolha_multipla: "Escolha múltipla",
  booleano: "Sim/Não",
};

const TABS: Array<{ key: "todas" | AplicacaoStatus; label: string }> = [
  { key: "pendente", label: "Pendentes" },
  { key: "aprovada", label: "Aprovadas" },
  { key: "rejeitada", label: "Rejeitadas" },
  { key: "todas", label: "Todas" },
];

function formatDateBR(value: string): string {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("pt-BR");
}

export default function Inscricoes() {
  const [tab, setTab] = useState<"todas" | AplicacaoStatus>("pendente");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [approving, setApproving] = useState<Aplicacao | null>(null);
  const [rejecting, setRejecting] = useState<Aplicacao | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);

  const { data, isPending, isFetching, error } = useAplicacoes(
    tab === "todas" ? undefined : { status: tab },
  );
  const { data: perguntasData } = usePerguntas();
  const perguntasById = new Map((perguntasData?.items ?? []).map((p) => [p.id, p]));

  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Inscrições</h1>
        <p className="text-sm text-muted-foreground">
          Fila de inscrições e o formulário público de aplicação.
          {/* lying-loading-ok: text-only suffix, never unmounts real content */}
          {isRefreshing ? " Atualizando…" : ""}
        </p>
      </div>

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Status da inscrição">
        {TABS.map((t) => (
          <Button
            key={t.key}
            variant={tab === t.key ? "primary" : "outline"}
            size="sm"
            onClick={() => setTab(t.key)}
          >
            {t.label}
            {t.key !== "todas" ? ` (${data?.resumo?.[t.key] ?? 0})` : ""}
          </Button>
        ))}
      </div>

      {showSkeleton ? (
        <div className="space-y-3" data-testid="aplicacoes-skeleton">
          {[1, 2].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-lg border border-border bg-muted/50" />
          ))}
        </div>
      ) : error ? (
        <ErrorState message={errorMessage(error)} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState message="Nenhuma inscrição encontrada." />
      ) : (
        <div className="space-y-3" data-testid="aplicacoes-list">
          {data.items.map((a) => (
            <Card key={a.id} data-testid={`aplicacao-row-${a.id}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate font-medium text-foreground">{a.nome}</p>
                  <p className="text-sm text-muted-foreground">
                    {a.email}
                    {a.telefone ? ` · ${a.telefone}` : ""}
                  </p>
                  <p className="text-xs text-muted-foreground">Enviado em {formatDateBR(a.created_at)}</p>
                  {a.status === "rejeitada" && a.motivo ? (
                    <p className="mt-1 text-xs text-destructive">Motivo: {a.motivo}</p>
                  ) : null}
                </div>
                <Badge variant={a.status === "aprovada" ? "default" : a.status === "rejeitada" ? "destructive" : "outline"}>
                  {STATUS_LABELS[a.status]}
                </Badge>
              </div>

              <button
                type="button"
                className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                onClick={() => setExpanded(expanded === a.id ? null : a.id)}
              >
                {expanded === a.id ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                {expanded === a.id ? "Ocultar respostas" : "Ver respostas"}
              </button>
              {expanded === a.id && (
                <div className="mt-2 space-y-1.5 rounded-md bg-muted/50 p-2.5 text-sm">
                  {Object.entries(a.respostas).map(([perguntaId, valor]) => (
                    <p key={perguntaId}>
                      <span className="font-medium text-foreground">
                        {perguntasById.get(perguntaId)?.pergunta ?? perguntaId}:
                      </span>{" "}
                      <span className="text-muted-foreground">{String(valor)}</span>
                    </p>
                  ))}
                </div>
              )}

              {a.status === "pendente" ? (
                <div className="mt-3 flex gap-2">
                  <Button variant="primary" size="sm" onClick={() => setApproving(a)} data-testid={`aprovar-${a.id}`}>
                    Aprovar
                  </Button>
                  <Button variant="destructive" size="sm" onClick={() => setRejecting(a)} data-testid={`rejeitar-${a.id}`}>
                    Rejeitar
                  </Button>
                </div>
              ) : null}
            </Card>
          ))}
        </div>
      )}

      <div className="border-t border-border pt-6">
        <button
          type="button"
          className="inline-flex items-center gap-1 text-sm font-medium text-foreground hover:underline"
          onClick={() => setEditorOpen((v) => !v)}
          data-testid="toggle-perguntas-editor"
        >
          {editorOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          Perguntas do formulário
        </button>
        {editorOpen && <PerguntasEditor />}
      </div>

      {approving && <AprovarDialog aplicacao={approving} onClose={() => setApproving(null)} />}
      {rejecting && <RejeitarDialog aplicacao={rejecting} onClose={() => setRejecting(null)} />}
    </div>
  );
}

function AprovarDialog({ aplicacao, onClose }: { aplicacao: Aplicacao; onClose: () => void }) {
  const [planoId, setPlanoId] = useState("");
  const [ativar, setAtivar] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const { data: planosData } = usePlanos({ ativo: true, page_size: 100 });
  const aprovar = useAprovarAplicacao();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    aprovar.mutate(
      { id: aplicacao.id, plano_id: planoId || null, ativar: planoId ? ativar : false },
      {
        onSuccess: () => {
          toast.success("Inscrição aprovada.");
          onClose();
        },
        onError: (err) => setFormError(errorMessage(err)),
      },
    );
  }

  return (
    <Dialog open onClose={onClose} title="Aprovar inscrição" className="max-w-md">
      <form onSubmit={handleSubmit}>
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">Aprovar inscrição de {aplicacao.nome}</h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <FormError message={formError} />
          <Field label="Plano (opcional)">
            <Select value={planoId} onChange={(e) => setPlanoId(e.target.value)}>
              <option value="">Sem plano — membro fica pendente</option>
              {(planosData?.items ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nome}
                </option>
              ))}
            </Select>
          </Field>
          {planoId ? (
            <label className="flex items-center gap-2 text-sm text-foreground">
              <input type="checkbox" checked={ativar} onChange={(e) => setAtivar(e.target.checked)} />
              Ativar o membro imediatamente
            </label>
          ) : null}
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={aprovar.isPending}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" disabled={aprovar.isPending}>
            {aprovar.isPending ? "Aprovando..." : "Aprovar"}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}

function RejeitarDialog({ aplicacao, onClose }: { aplicacao: Aplicacao; onClose: () => void }) {
  const [motivo, setMotivo] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const rejeitar = useRejeitarAplicacao();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    rejeitar.mutate(
      { id: aplicacao.id, motivo },
      {
        onSuccess: () => {
          toast.success("Inscrição rejeitada.");
          onClose();
        },
        onError: (err) => setFormError(errorMessage(err)),
      },
    );
  }

  return (
    <Dialog open onClose={onClose} title="Rejeitar inscrição" className="max-w-md">
      <form onSubmit={handleSubmit}>
        <DialogHeader>
          <h2 className="text-lg font-semibold text-foreground">Rejeitar inscrição de {aplicacao.nome}</h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <FormError message={formError} />
          <Field label="Motivo" required>
            <Textarea value={motivo} onChange={(e) => setMotivo(e.target.value)} required rows={3} />
          </Field>
        </DialogBody>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose} disabled={rejeitar.isPending}>
            Cancelar
          </Button>
          <Button type="submit" variant="destructive" disabled={rejeitar.isPending}>
            {rejeitar.isPending ? "Rejeitando..." : "Rejeitar"}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}

const OPCOES_TIPOS = new Set<Pergunta["tipo"]>(["escolha_unica", "escolha_multipla"]);

function PerguntasEditor() {
  const [reloadTick, setReloadTick] = useState(0);

  async function handleReativar(row: Pergunta) {
    try {
      await api.patch(`/api/aplicacoes/perguntas/${row.id}`, { ativa: true });
      toast.success("Pergunta reativada");
      setReloadTick((n) => n + 1);
    } catch (err) {
      toast.error("Erro ao reativar pergunta", { description: errorMessage(err) });
    }
  }

  return (
    <div className="mt-4">
      <ResourceManager<Pergunta>
        key={reloadTick}
        title="Perguntas do formulário"
        description="O que os candidatos respondem ao se inscrever."
        api={api}
        apiPath="/api/aplicacoes/perguntas"
        singularName="Pergunta"
        deleteLabel="Desativar"
        emptyMessage="Nenhuma pergunta cadastrada. Crie a primeira!"
        toForm={(row) => ({
          pergunta: row.pergunta,
          tipo: row.tipo,
          opcoes_csv: (row.opcoes ?? []).join(", "),
          obrigatoria: row.obrigatoria,
          ordem: row.ordem,
        })}
        toPayload={(form) => ({
          pergunta: form.pergunta,
          tipo: form.tipo,
          opcoes: OPCOES_TIPOS.has(form.tipo)
            ? String(form.opcoes_csv ?? "")
                .split(",")
                .map((o: string) => o.trim())
                .filter(Boolean)
            : [],
          obrigatoria: !!form.obrigatoria,
          ordem: Number(form.ordem) || 0,
        })}
        columns={[
          { key: "pergunta", header: "Pergunta" },
          { key: "tipo", header: "Tipo", render: (row) => TIPO_LABELS[row.tipo] },
          { key: "obrigatoria", header: "Obrigatória", render: (row) => (row.obrigatoria ? "Sim" : "Não") },
          { key: "ordem", header: "Ordem" },
          {
            key: "ativa",
            header: "Status",
            render: (row) => <Badge variant={row.ativa ? "default" : "muted"}>{row.ativa ? "Ativa" : "Inativa"}</Badge>,
          },
        ]}
        fields={[
          { name: "pergunta", label: "Pergunta", type: "textarea", required: true },
          {
            name: "tipo",
            label: "Tipo",
            type: "select",
            required: true,
            options: [
              { value: "texto", label: "Texto curto" },
              { value: "texto_longo", label: "Texto longo" },
              { value: "escolha_unica", label: "Escolha única" },
              { value: "escolha_multipla", label: "Escolha múltipla" },
              { value: "booleano", label: "Sim/Não" },
            ],
          },
          {
            name: "opcoes_csv",
            label: "Opções",
            help: "Separe por vírgula. Obrigatório para os tipos de escolha.",
          },
          { name: "obrigatoria", label: "Obrigatória", type: "checkbox", defaultValue: true },
          { name: "ordem", label: "Ordem", type: "number", defaultValue: 0 },
        ]}
        rowActions={(row) =>
          !row.ativa ? (
            <button
              type="button"
              className="text-sm border border-border bg-card text-foreground rounded-md px-3 py-1.5 hover:bg-accent transition-colors"
              onClick={() => void handleReativar(row)}
            >
              Reativar
            </button>
          ) : null
        }
      />
    </div>
  );
}
