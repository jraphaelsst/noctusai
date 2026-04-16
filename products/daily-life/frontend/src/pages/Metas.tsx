import { useState } from "react";
import {
  useMetas,
  useCheckins,
  useCreateMeta,
  useUpdateMeta,
  useDeleteMeta,
  useCheckinMeta,
} from "@/hooks/useMetas";
import type { Meta, MetaForm, CheckInForm } from "@/hooks/useMetas";
import {
  Target,
  Plus,
  Pencil,
  Trash2,
  Loader2,
  X,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  CalendarCheck,
  Repeat,
  TrendingUp,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TIPO_CONFIG: Record<string, { label: string; className: string }> = {
  meta: { label: "Meta", className: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400" },
  habito: { label: "Habito", className: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400" },
};

const FREQ_CONFIG: Record<string, string> = {
  diario: "Diario",
  semanal: "Semanal",
  mensal: "Mensal",
};

const STATUS_CONFIG: Record<string, { label: string; className: string }> = {
  ativa: { label: "Ativa", className: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400" },
  concluida: { label: "Concluida", className: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400" },
  pausada: { label: "Pausada", className: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400" },
  cancelada: { label: "Cancelada", className: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400" },
};

const EMPTY_FORM: MetaForm = {
  titulo: "",
  descricao: "",
  tipo: "meta",
  categoria: "",
  meta_valor: "",
  unidade: "",
  frequencia: "",
  data_limite: "",
  status: "ativa",
};

const EMPTY_CHECKIN: CheckInForm = {
  data: new Date().toISOString().slice(0, 10),
  valor: "1",
  nota: "",
};

const PAGE_SIZE = 20;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Metas() {
  // Filters
  const [tipoFilter, setTipoFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);

  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState<Meta | null>(null);
  const [form, setForm] = useState<MetaForm>(EMPTY_FORM);
  const [confirmDelete, setConfirmDelete] = useState<Meta | null>(null);

  // Check-in state
  const [checkinGoalId, setCheckinGoalId] = useState<string | null>(null);
  const [checkinForm, setCheckinForm] = useState<CheckInForm>(EMPTY_CHECKIN);
  const [expandedCheckins, setExpandedCheckins] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Hooks
  // ---------------------------------------------------------------------------

  const { data: metasRes, isLoading } = useMetas(page, {
    tipo: tipoFilter,
    status: statusFilter,
  });

  const { data: checkinsRes } = useCheckins(expandedCheckins);

  const createMutation = useCreateMeta(() => closeModal());
  const updateMutation = useUpdateMeta(() => closeModal());
  const deleteMutation = useDeleteMeta(() => setConfirmDelete(null));
  const checkinMutation = useCheckinMeta(() => {
    setCheckinGoalId(null);
    setCheckinForm(EMPTY_CHECKIN);
  });

  const metas = metasRes?.data ?? [];
  const total = metasRes?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const checkins = checkinsRes?.data ?? [];

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setShowModal(true);
  }

  function openEdit(m: Meta) {
    setEditing(m);
    setForm({
      titulo: m.titulo,
      descricao: m.descricao ?? "",
      tipo: m.tipo,
      categoria: m.categoria ?? "",
      meta_valor: m.meta_valor != null ? String(m.meta_valor) : "",
      unidade: m.unidade ?? "",
      frequencia: m.frequencia ?? "",
      data_limite: m.data_limite ?? "",
      status: m.status,
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
    const payload: Record<string, unknown> = { titulo: form.titulo, tipo: form.tipo };
    if (form.descricao) payload.descricao = form.descricao;
    if (form.categoria) payload.categoria = form.categoria;
    if (form.meta_valor) payload.meta_valor = parseFloat(form.meta_valor);
    if (form.unidade) payload.unidade = form.unidade;
    if (form.frequencia) payload.frequencia = form.frequencia;
    if (form.data_limite) payload.data_limite = form.data_limite;
    if (editing) {
      payload.status = form.status;
      updateMutation.mutate({ id: editing.id, body: payload });
    } else {
      createMutation.mutate(payload);
    }
  }

  function handleCheckinSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!checkinGoalId) return;
    checkinMutation.mutate({
      goalId: checkinGoalId,
      body: {
        data: checkinForm.data,
        valor: parseFloat(checkinForm.valor) || 1,
        nota: checkinForm.nota || null,
      },
    });
  }

  function toggleCheckins(goalId: string) {
    setExpandedCheckins((prev) => (prev === goalId ? null : goalId));
  }

  function progressPercent(m: Meta): number {
    if (!m.meta_valor || m.meta_valor <= 0) return 0;
    return Math.min(100, Math.round((m.valor_atual / m.meta_valor) * 100));
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
          <Target className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Metas e Habitos</h1>
            <p className="text-sm text-muted-foreground">Defina objetivos e acompanhe habitos</p>
          </div>
        </div>
        <button
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          onClick={openCreate}
        >
          <Plus className="h-4 w-4" />
          Nova Meta
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <select
          value={tipoFilter}
          onChange={(e) => { setTipoFilter(e.target.value); setPage(1); }}
          className="flex h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="">Todos os tipos</option>
          <option value="meta">Metas</option>
          <option value="habito">Habitos</option>
        </select>
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
          className="flex h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="">Todos os status</option>
          <option value="ativa">Ativa</option>
          <option value="concluida">Concluida</option>
          <option value="pausada">Pausada</option>
          <option value="cancelada">Cancelada</option>
        </select>
      </div>

      {/* Goal Cards */}
      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Carregando metas...</p>
        </div>
      ) : metas.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center">
          <p className="text-muted-foreground">Nenhuma meta encontrada</p>
        </div>
      ) : (
        <div className="space-y-4">
          {metas.map((m) => {
            const tipo = TIPO_CONFIG[m.tipo] ?? TIPO_CONFIG.meta;
            const st = STATUS_CONFIG[m.status] ?? STATUS_CONFIG.ativa;
            const pct = progressPercent(m);
            const isExpanded = expandedCheckins === m.id;
            return (
              <div key={m.id} className="rounded-lg border border-border bg-card overflow-hidden">
                <div className="p-4">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="font-medium text-foreground truncate">{m.titulo}</h3>
                        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${tipo.className}`}>
                          {m.tipo === "habito" ? <Repeat className="h-3 w-3" /> : <TrendingUp className="h-3 w-3" />}
                          {tipo.label}
                        </span>
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${st.className}`}>
                          {st.label}
                        </span>
                      </div>
                      {m.descricao && (
                        <p className="mt-1 text-sm text-muted-foreground line-clamp-2">{m.descricao}</p>
                      )}
                      <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground flex-wrap">
                        {m.categoria && <span className="rounded bg-muted px-1.5 py-0.5">{m.categoria}</span>}
                        {m.frequencia && (
                          <span className="rounded bg-purple-100 px-1.5 py-0.5 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400">
                            {FREQ_CONFIG[m.frequencia] ?? m.frequencia}
                          </span>
                        )}
                        {m.data_limite && (
                          <span>Prazo: {new Date(m.data_limite).toLocaleDateString("pt-BR")}</span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {m.tipo === "habito" && m.status === "ativa" && (
                        <button
                          className="inline-flex items-center gap-1 rounded-md bg-purple-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-purple-700 transition-colors"
                          onClick={(e) => { e.stopPropagation(); setCheckinGoalId(m.id); setCheckinForm({ ...EMPTY_CHECKIN, data: new Date().toISOString().slice(0, 10) }); }}
                        >
                          <CalendarCheck className="h-3.5 w-3.5" />
                          Registrar
                        </button>
                      )}
                      <button
                        className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
                        onClick={() => openEdit(m)}
                        title="Editar"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        className="rounded-md p-1.5 text-destructive hover:bg-destructive/10 transition-colors"
                        onClick={() => setConfirmDelete(m)}
                        title="Remover"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>

                  {/* Progress bar */}
                  {m.meta_valor != null && m.meta_valor > 0 && (
                    <div className="mt-3">
                      <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                        <span>
                          {m.valor_atual}{m.unidade ? ` ${m.unidade}` : ""} / {m.meta_valor}{m.unidade ? ` ${m.unidade}` : ""}
                        </span>
                        <span>{pct}%</span>
                      </div>
                      <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${pct >= 100 ? "bg-green-500" : "bg-primary"}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {/* Check-in toggle */}
                  {m.tipo === "habito" && (
                    <button
                      className="mt-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                      onClick={() => toggleCheckins(m.id)}
                    >
                      {isExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                      {isExpanded ? "Ocultar" : "Ver"} historico
                    </button>
                  )}
                </div>

                {/* Check-in history */}
                {isExpanded && (
                  <div className="border-t border-border bg-muted/30 p-4">
                    <h4 className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">Historico de check-ins</h4>
                    {checkins.length === 0 ? (
                      <p className="text-sm text-muted-foreground">Nenhum check-in registrado</p>
                    ) : (
                      <div className="space-y-2">
                        {checkins.map((c) => (
                          <div key={c.id} className="flex items-center justify-between rounded-md bg-card px-3 py-2 text-sm">
                            <div className="flex items-center gap-3">
                              <span className="font-medium text-foreground">
                                {new Date(c.data).toLocaleDateString("pt-BR")}
                              </span>
                              <span className="text-muted-foreground">
                                Valor: {c.valor}
                              </span>
                            </div>
                            {c.nota && <span className="text-xs text-muted-foreground truncate max-w-[200px]">{c.nota}</span>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
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
                {editing ? "Editar Meta" : "Nova Meta"}
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
                  placeholder="Ex: Ler 12 livros este ano"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Descricao</label>
                <textarea
                  value={form.descricao}
                  onChange={(e) => setForm({ ...form, descricao: e.target.value })}
                  rows={3}
                  placeholder="Detalhes da meta..."
                  className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                />
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Tipo</label>
                  <select
                    value={form.tipo}
                    onChange={(e) => setForm({ ...form, tipo: e.target.value as MetaForm["tipo"] })}
                    disabled={!!editing}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-50"
                  >
                    <option value="meta">Meta</option>
                    <option value="habito">Habito</option>
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Categoria</label>
                  <input
                    type="text"
                    value={form.categoria}
                    onChange={(e) => setForm({ ...form, categoria: e.target.value })}
                    placeholder="Ex: Saude, Leitura"
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Valor alvo</label>
                  <input
                    type="number"
                    step="any"
                    min="0"
                    value={form.meta_valor}
                    onChange={(e) => setForm({ ...form, meta_valor: e.target.value })}
                    placeholder="Ex: 12"
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Unidade</label>
                  <input
                    type="text"
                    value={form.unidade}
                    onChange={(e) => setForm({ ...form, unidade: e.target.value })}
                    placeholder="Ex: livros, km"
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Data limite</label>
                  <input
                    type="date"
                    value={form.data_limite}
                    onChange={(e) => setForm({ ...form, data_limite: e.target.value })}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  />
                </div>
              </div>
              {(form.tipo === "habito" || (editing && editing.tipo === "habito")) && (
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Frequencia</label>
                  <select
                    value={form.frequencia}
                    onChange={(e) => setForm({ ...form, frequencia: e.target.value })}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  >
                    <option value="">Selecione...</option>
                    <option value="diario">Diario</option>
                    <option value="semanal">Semanal</option>
                    <option value="mensal">Mensal</option>
                  </select>
                </div>
              )}
              {editing && (
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Status</label>
                  <select
                    value={form.status}
                    onChange={(e) => setForm({ ...form, status: e.target.value as MetaForm["status"] })}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  >
                    <option value="ativa">Ativa</option>
                    <option value="concluida">Concluida</option>
                    <option value="pausada">Pausada</option>
                    <option value="cancelada">Cancelada</option>
                  </select>
                </div>
              )}
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
                  ) : editing ? "Salvar alteracoes" : "Criar meta"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Check-in Modal */}
      {checkinGoalId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setCheckinGoalId(null)}>
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-sm rounded-lg border border-border bg-card p-6 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-foreground">Registrar Check-in</h2>
              <button className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors" onClick={() => setCheckinGoalId(null)}>
                <X className="h-4 w-4" />
              </button>
            </div>
            <form onSubmit={handleCheckinSubmit} className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Data</label>
                <input
                  type="date"
                  required
                  value={checkinForm.data}
                  onChange={(e) => setCheckinForm({ ...checkinForm, data: e.target.value })}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Valor</label>
                <input
                  type="number"
                  step="any"
                  min="0"
                  value={checkinForm.valor}
                  onChange={(e) => setCheckinForm({ ...checkinForm, valor: e.target.value })}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Nota (opcional)</label>
                <input
                  type="text"
                  value={checkinForm.nota}
                  onChange={(e) => setCheckinForm({ ...checkinForm, nota: e.target.value })}
                  placeholder="Como foi?"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                />
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
                  onClick={() => setCheckinGoalId(null)}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={checkinMutation.isPending}
                  className="inline-flex items-center gap-2 rounded-md bg-purple-600 px-6 py-2 text-sm font-medium text-white hover:bg-purple-700 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {checkinMutation.isPending ? (
                    <><Loader2 className="h-4 w-4 animate-spin" />Registrando...</>
                  ) : "Registrar"}
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
            <h2 className="mb-2 text-lg font-semibold text-foreground">Remover meta</h2>
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
