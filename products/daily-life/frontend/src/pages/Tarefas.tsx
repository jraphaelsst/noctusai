import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/store/authStore";
import { api } from "@/lib/api-client";
import { toast } from "sonner";
import {
  ListTodo,
  Plus,
  Pencil,
  Trash2,
  Loader2,
  X,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  CheckCircle2,
  Clock,
  Ban,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Tarefa {
  id: string;
  titulo: string;
  descricao?: string;
  prioridade: "alta" | "media" | "baixa";
  status: "pendente" | "em_progresso" | "concluida" | "cancelada";
  categoria?: string;
  data_vencimento?: string;
  created_at: string;
}

interface TarefaForm {
  titulo: string;
  descricao: string;
  prioridade: "alta" | "media" | "baixa";
  categoria: string;
  data_vencimento: string;
  status: "pendente" | "em_progresso" | "concluida" | "cancelada";
}

interface Stats {
  total: number;
  pendentes: number;
  em_progresso: number;
  concluidas: number;
  canceladas: number;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PRIORIDADE_CONFIG: Record<string, { label: string; className: string }> = {
  alta: { label: "Alta", className: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400" },
  media: { label: "Media", className: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400" },
  baixa: { label: "Baixa", className: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400" },
};

const STATUS_CONFIG: Record<string, { label: string; icon: React.ElementType; className: string }> = {
  pendente: { label: "Pendente", icon: Clock, className: "bg-muted text-muted-foreground" },
  em_progresso: { label: "Em progresso", icon: AlertCircle, className: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400" },
  concluida: { label: "Concluida", icon: CheckCircle2, className: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400" },
  cancelada: { label: "Cancelada", icon: Ban, className: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400" },
};

const EMPTY_FORM: TarefaForm = {
  titulo: "",
  descricao: "",
  prioridade: "media",
  categoria: "",
  data_vencimento: "",
  status: "pendente",
};

const PAGE_SIZE = 20;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Tarefas() {
  const { user } = useAuthStore();
  const qc = useQueryClient();

  // Filters
  const [statusFilter, setStatusFilter] = useState("");
  const [prioridadeFilter, setPrioridadeFilter] = useState("");
  const [categoriaFilter, setCategoriaFilter] = useState("");
  const [page, setPage] = useState(1);

  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState<Tarefa | null>(null);
  const [form, setForm] = useState<TarefaForm>(EMPTY_FORM);
  const [confirmDelete, setConfirmDelete] = useState<Tarefa | null>(null);

  // ---------------------------------------------------------------------------
  // Queries
  // ---------------------------------------------------------------------------

  const buildParams = () => {
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (statusFilter) params.set("status", statusFilter);
    if (prioridadeFilter) params.set("prioridade", prioridadeFilter);
    if (categoriaFilter) params.set("categoria", categoriaFilter);
    return params.toString();
  };

  const { data: tarefasRes, isLoading } = useQuery({
    queryKey: ["tarefas", page, statusFilter, prioridadeFilter, categoriaFilter],
    queryFn: () => api.get<{ data: Tarefa[]; total: number; page: number; page_size: number }>(`/api/tasks?${buildParams()}`),
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });

  const { data: statsRes } = useQuery({
    queryKey: ["tarefas-stats"],
    queryFn: () => api.get<{ data: Stats }>("/api/tasks/stats/resumo"),
    enabled: !!user,
    staleTime: 2 * 60 * 1000,
  });

  const tarefas = tarefasRes?.data ?? [];
  const total = tarefasRes?.total ?? 0;
  const stats = statsRes?.data ?? null;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // ---------------------------------------------------------------------------
  // Mutations
  // ---------------------------------------------------------------------------

  const createMutation = useMutation({
    mutationFn: (body: Partial<TarefaForm>) => api.post("/api/tasks", body),
    onSuccess: () => {
      toast.success("Tarefa criada com sucesso");
      qc.invalidateQueries({ queryKey: ["tarefas"] });
      qc.invalidateQueries({ queryKey: ["tarefas-stats"] });
      closeModal();
    },
    onError: (err: any) => toast.error("Erro ao criar tarefa", { description: err?.message }),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) => api.patch(`/api/tasks/${id}`, body),
    onSuccess: () => {
      toast.success("Tarefa atualizada");
      qc.invalidateQueries({ queryKey: ["tarefas"] });
      qc.invalidateQueries({ queryKey: ["tarefas-stats"] });
      closeModal();
    },
    onError: (err: any) => toast.error("Erro ao atualizar tarefa", { description: err?.message }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/api/tasks/${id}`),
    onSuccess: () => {
      toast.success("Tarefa removida");
      qc.invalidateQueries({ queryKey: ["tarefas"] });
      qc.invalidateQueries({ queryKey: ["tarefas-stats"] });
      setConfirmDelete(null);
    },
    onError: (err: any) => toast.error("Erro ao remover tarefa", { description: err?.message }),
  });

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setShowModal(true);
  }

  function openEdit(t: Tarefa) {
    setEditing(t);
    setForm({
      titulo: t.titulo,
      descricao: t.descricao ?? "",
      prioridade: t.prioridade,
      categoria: t.categoria ?? "",
      data_vencimento: t.data_vencimento ?? "",
      status: t.status,
    });
    setShowModal(true);
  }

  function closeModal() {
    setShowModal(false);
    setEditing(null);
    setForm(EMPTY_FORM);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload: Record<string, unknown> = { titulo: form.titulo };
    if (form.descricao) payload.descricao = form.descricao;
    if (form.prioridade) payload.prioridade = form.prioridade;
    if (form.categoria) payload.categoria = form.categoria;
    if (form.data_vencimento) payload.data_vencimento = form.data_vencimento;
    if (editing) {
      payload.status = form.status;
      updateMutation.mutate({ id: editing.id, body: payload });
    } else {
      createMutation.mutate(payload as Partial<TarefaForm>);
    }
  }

  const saving = createMutation.isPending || updateMutation.isPending;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <ListTodo className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Minhas Tarefas</h1>
            <p className="text-sm text-muted-foreground">Gerencie suas tarefas e acompanhe o progresso</p>
          </div>
        </div>
        <button
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          onClick={openCreate}
        >
          <Plus className="h-4 w-4" />
          Nova Tarefa
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: "Total", value: stats.total, color: "text-foreground" },
            { label: "Pendentes", value: stats.pendentes, color: "text-yellow-600 dark:text-yellow-400" },
            { label: "Em progresso", value: stats.em_progresso, color: "text-blue-600 dark:text-blue-400" },
            { label: "Concluidas", value: stats.concluidas, color: "text-green-600 dark:text-green-400" },
          ].map((s) => (
            <div key={s.label} className="rounded-lg border border-border bg-card p-4">
              <p className="text-xs text-muted-foreground">{s.label}</p>
              <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
          className="flex h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="">Todos os status</option>
          <option value="pendente">Pendente</option>
          <option value="em_progresso">Em progresso</option>
          <option value="concluida">Concluida</option>
          <option value="cancelada">Cancelada</option>
        </select>

        <select
          value={prioridadeFilter}
          onChange={(e) => { setPrioridadeFilter(e.target.value); setPage(1); }}
          className="flex h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="">Todas as prioridades</option>
          <option value="alta">Alta</option>
          <option value="media">Media</option>
          <option value="baixa">Baixa</option>
        </select>

        <input
          type="text"
          placeholder="Filtrar por categoria..."
          value={categoriaFilter}
          onChange={(e) => { setCategoriaFilter(e.target.value); setPage(1); }}
          className="flex h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:w-48"
        />
      </div>

      {/* Task List */}
      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Carregando tarefas...</p>
        </div>
      ) : tarefas.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center">
          <p className="text-muted-foreground">Nenhuma tarefa encontrada</p>
        </div>
      ) : (
        <div className="space-y-3">
          {tarefas.map((t) => {
            const prio = PRIORIDADE_CONFIG[t.prioridade] ?? PRIORIDADE_CONFIG.media;
            const st = STATUS_CONFIG[t.status] ?? STATUS_CONFIG.pendente;
            const StatusIcon = st.icon;
            const vencida = t.data_vencimento && t.status !== "concluida" && t.status !== "cancelada" && new Date(t.data_vencimento) < new Date();
            return (
              <div
                key={t.id}
                className="rounded-lg border border-border bg-card p-4 hover:border-primary/30 transition-colors cursor-pointer"
                onClick={() => openEdit(t)}
              >
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className={`font-medium text-foreground truncate ${t.status === "concluida" ? "line-through opacity-60" : ""}`}>
                        {t.titulo}
                      </h3>
                      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${prio.className}`}>
                        {prio.label}
                      </span>
                      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${st.className}`}>
                        <StatusIcon className="h-3 w-3" />
                        {st.label}
                      </span>
                    </div>
                    {t.descricao && (
                      <p className="mt-1 text-sm text-muted-foreground line-clamp-1">{t.descricao}</p>
                    )}
                    <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                      {t.categoria && <span className="rounded bg-muted px-1.5 py-0.5">{t.categoria}</span>}
                      {t.data_vencimento && (
                        <span className={vencida ? "text-red-600 dark:text-red-400 font-medium" : ""}>
                          Vence: {new Date(t.data_vencimento).toLocaleDateString("pt-BR")}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
                      onClick={(e) => { e.stopPropagation(); openEdit(t); }}
                      title="Editar"
                    >
                      <Pencil className="h-4 w-4" />
                    </button>
                    <button
                      className="rounded-md p-1.5 text-destructive hover:bg-destructive/10 transition-colors"
                      onClick={(e) => { e.stopPropagation(); setConfirmDelete(t); }}
                      title="Remover"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-4">
          <button
            className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors disabled:opacity-50"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            <ChevronLeft className="h-4 w-4" /> Anterior
          </button>
          <span className="text-sm text-muted-foreground">
            Pagina {page} de {totalPages}
          </span>
          <button
            className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors disabled:opacity-50"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            Proxima <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Create / Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={closeModal}>
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-foreground">
                {editing ? "Editar Tarefa" : "Nova Tarefa"}
              </h2>
              <button className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors" onClick={closeModal}>
                <X className="h-4 w-4" />
              </button>
            </div>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Titulo *</label>
                <input
                  type="text"
                  required
                  maxLength={300}
                  value={form.titulo}
                  onChange={(e) => setForm({ ...form, titulo: e.target.value })}
                  placeholder="Ex: Comprar mantimentos"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Descricao</label>
                <textarea
                  value={form.descricao}
                  onChange={(e) => setForm({ ...form, descricao: e.target.value })}
                  rows={3}
                  placeholder="Detalhes da tarefa..."
                  className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                />
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Prioridade</label>
                  <select
                    value={form.prioridade}
                    onChange={(e) => setForm({ ...form, prioridade: e.target.value as TarefaForm["prioridade"] })}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  >
                    <option value="alta">Alta</option>
                    <option value="media">Media</option>
                    <option value="baixa">Baixa</option>
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Categoria</label>
                  <input
                    type="text"
                    value={form.categoria}
                    onChange={(e) => setForm({ ...form, categoria: e.target.value })}
                    placeholder="Ex: Trabalho, Pessoal"
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Data de vencimento</label>
                  <input
                    type="date"
                    value={form.data_vencimento}
                    onChange={(e) => setForm({ ...form, data_vencimento: e.target.value })}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  />
                </div>
                {editing && (
                  <div>
                    <label className="mb-1 block text-sm font-medium text-foreground">Status</label>
                    <select
                      value={form.status}
                      onChange={(e) => setForm({ ...form, status: e.target.value as TarefaForm["status"] })}
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    >
                      <option value="pendente">Pendente</option>
                      <option value="em_progresso">Em progresso</option>
                      <option value="concluida">Concluida</option>
                      <option value="cancelada">Cancelada</option>
                    </select>
                  </div>
                )}
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
                  onClick={closeModal}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={saving || !form.titulo.trim()}
                  className="inline-flex items-center gap-2 rounded-md bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {saving ? (
                    <><Loader2 className="h-4 w-4 animate-spin" />Salvando...</>
                  ) : editing ? "Salvar alteracoes" : "Criar tarefa"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirm */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setConfirmDelete(null)}>
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-md rounded-lg border border-border bg-card p-6 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="mb-2 text-lg font-semibold text-foreground">Remover tarefa</h2>
            <p className="mb-6 text-sm text-muted-foreground">
              Tem certeza que deseja remover <strong className="text-foreground">{confirmDelete.titulo}</strong>?
            </p>
            <div className="flex justify-end gap-3">
              <button
                className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
                onClick={() => setConfirmDelete(null)}
              >
                Cancelar
              </button>
              <button
                className="inline-flex items-center gap-2 rounded-md bg-destructive px-6 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                disabled={deleteMutation.isPending}
                onClick={() => deleteMutation.mutate(confirmDelete.id)}
              >
                {deleteMutation.isPending ? (
                  <><Loader2 className="h-4 w-4 animate-spin" />Removendo...</>
                ) : "Confirmar remocao"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
