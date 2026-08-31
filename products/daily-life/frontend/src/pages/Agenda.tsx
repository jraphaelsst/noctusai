import { useState, useMemo } from "react";
import {
  useAgenda,
  useCreateEvento,
  useUpdateEvento,
  useDeleteEvento,
} from "@/hooks/useAgenda";
import type { Evento, EventoForm } from "@/hooks/useAgenda";
import {
  Calendar,
  Plus,
  ChevronLeft,
  ChevronRight,
  MapPin,
  Clock,
  Bell,
  Loader2,
  Pencil,
  Trash2,
  X,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const COLOR_PRESETS = [
  { value: "#3b82f6", label: "Azul" },
  { value: "#22c55e", label: "Verde" },
  { value: "#ef4444", label: "Vermelho" },
  { value: "#eab308", label: "Amarelo" },
  { value: "#8b5cf6", label: "Roxo" },
  { value: "#ec4899", label: "Rosa" },
  { value: "#6b7280", label: "Cinza" },
];

const EMPTY_FORM: EventoForm = {
  titulo: "",
  descricao: "",
  data_inicio: "",
  data_fim: "",
  dia_inteiro: false,
  cor: "#3b82f6",
  local: "",
  lembrete_minutos: "",
  categoria: "",
};

function formatDateTimeBR(iso: string, diaInteiro: boolean): string {
  const d = new Date(iso);
  if (diaInteiro) {
    return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
  }
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" })
    + " " + d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function getMonthRange(year: number, month: number) {
  const inicio = new Date(year, month, 1);
  const fim = new Date(year, month + 1, 0, 23, 59, 59);
  return {
    inicio: inicio.toISOString(),
    fim: fim.toISOString(),
  };
}

function toLocalDatetime(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Agenda() {
  // Date navigation
  const [currentDate, setCurrentDate] = useState(() => new Date());
  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();
  const { inicio, fim } = useMemo(() => getMonthRange(year, month), [year, month]);

  // Pagination
  const [page, setPage] = useState(1);
  const pageSize = 50;

  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [editingEvent, setEditingEvent] = useState<Evento | null>(null);
  const [formData, setFormData] = useState<EventoForm>(EMPTY_FORM);
  const [confirmDelete, setConfirmDelete] = useState<Evento | null>(null);

  // ---------------------------------------------------------------------------
  // Hooks
  // ---------------------------------------------------------------------------

  const { data: response, isPending } = useAgenda(inicio, fim, page, pageSize);

  const createMutation = useCreateEvento(() => closeModal());
  const updateMutation = useUpdateEvento(() => closeModal());
  const deleteMutation = useDeleteEvento(() => setConfirmDelete(null));

  const eventos = response?.data ?? [];
  const pagination = response?.pagination;

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  function closeModal() {
    setShowModal(false);
    setEditingEvent(null);
    setFormData(EMPTY_FORM);
  }

  function openCreate() {
    setEditingEvent(null);
    setFormData(EMPTY_FORM);
    setShowModal(true);
  }

  function openEdit(ev: Evento) {
    setEditingEvent(ev);
    setFormData({
      titulo: ev.titulo,
      descricao: ev.descricao || "",
      data_inicio: toLocalDatetime(ev.data_inicio),
      data_fim: ev.data_fim ? toLocalDatetime(ev.data_fim) : "",
      dia_inteiro: ev.dia_inteiro,
      cor: ev.cor || "#3b82f6",
      local: ev.local || "",
      lembrete_minutos: ev.lembrete_minutos != null ? String(ev.lembrete_minutos) : "",
      categoria: ev.categoria || "",
    });
    setShowModal(true);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const body: Record<string, unknown> = {
      titulo: formData.titulo,
      descricao: formData.descricao || null,
      data_inicio: formData.data_inicio ? new Date(formData.data_inicio).toISOString() : null,
      data_fim: formData.data_fim ? new Date(formData.data_fim).toISOString() : null,
      dia_inteiro: formData.dia_inteiro,
      cor: formData.cor || null,
      local: formData.local || null,
      lembrete_minutos: formData.lembrete_minutos ? Number(formData.lembrete_minutos) : null,
      categoria: formData.categoria || null,
    };

    if (editingEvent) {
      updateMutation.mutate({ id: editingEvent.id, body });
    } else {
      createMutation.mutate(body);
    }
  }

  function prevMonth() {
    setCurrentDate(new Date(year, month - 1, 1));
    setPage(1);
  }

  function nextMonth() {
    setCurrentDate(new Date(year, month + 1, 1));
    setPage(1);
  }

  function goToday() {
    setCurrentDate(new Date());
    setPage(1);
  }

  const isSaving = createMutation.isPending || updateMutation.isPending;
  const monthLabel = currentDate.toLocaleDateString("pt-BR", { month: "long", year: "numeric" });

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Calendar className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Minha Agenda</h1>
            <p className="text-sm text-muted-foreground">
              Seus compromissos e eventos
            </p>
          </div>
        </div>
        <button
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          onClick={openCreate}
        >
          <Plus className="h-4 w-4" />
          Novo Evento
        </button>
      </div>

      {/* Date Navigation */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between rounded-lg border border-border bg-card px-4 py-3">
        <div className="flex items-center gap-2">
          <button
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
            onClick={prevMonth}
            aria-label="Mes anterior"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
          <span className="min-w-[160px] text-center text-sm font-semibold capitalize text-foreground">
            {monthLabel}
          </span>
          <button
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
            onClick={nextMonth}
            aria-label="Proximo mes"
          >
            <ChevronRight className="h-5 w-5" />
          </button>
        </div>
        <button
          className="rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors"
          onClick={goToday}
        >
          Hoje
        </button>
      </div>

      {/* Event List */}
      {isPending && !response ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Carregando eventos...</p>
        </div>
      ) : eventos.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center">
          <Calendar className="mx-auto h-10 w-10 text-muted-foreground/40 mb-3" />
          <p className="text-muted-foreground">Nenhum evento neste periodo</p>
          <button
            className="mt-3 text-sm text-primary hover:underline"
            onClick={openCreate}
          >
            Criar primeiro evento
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          {eventos.map((ev) => (
            <div
              key={ev.id}
              className="group flex items-start gap-3 rounded-lg border border-border bg-card p-4 hover:border-primary/20 transition-colors cursor-pointer"
              onClick={() => openEdit(ev)}
            >
              {/* Color indicator */}
              <div
                className="mt-1 h-3 w-3 shrink-0 rounded-full"
                style={{ backgroundColor: ev.cor || "#3b82f6" }}
              />

              {/* Content */}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-medium text-foreground truncate">{ev.titulo}</h3>
                  {ev.dia_inteiro && (
                    <span className="inline-flex rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                      Dia inteiro
                    </span>
                  )}
                  {ev.lembrete_minutos != null && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400">
                      <Bell className="h-3 w-3" />
                      {ev.lembrete_minutos}min
                    </span>
                  )}
                  {ev.status === "cancelado" && (
                    <span className="inline-flex rounded-full bg-destructive/10 px-2 py-0.5 text-xs font-medium text-destructive">
                      Cancelado
                    </span>
                  )}
                  {ev.status === "concluido" && (
                    <span className="inline-flex rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900/30 dark:text-green-400">
                      Concluido
                    </span>
                  )}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {formatDateTimeBR(ev.data_inicio, ev.dia_inteiro)}
                    {ev.data_fim && (
                      <> &mdash; {formatDateTimeBR(ev.data_fim, ev.dia_inteiro)}</>
                    )}
                  </span>
                  {ev.local && (
                    <span className="inline-flex items-center gap-1">
                      <MapPin className="h-3 w-3" />
                      {ev.local}
                    </span>
                  )}
                  {ev.categoria && (
                    <span className="inline-flex rounded bg-muted px-1.5 py-0.5 text-xs">
                      {ev.categoria}
                    </span>
                  )}
                </div>
                {ev.descricao && (
                  <p className="mt-1 text-xs text-muted-foreground line-clamp-1">
                    {ev.descricao}
                  </p>
                )}
              </div>

              {/* Actions */}
              <div className="flex shrink-0 items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
                  onClick={(e) => { e.stopPropagation(); openEdit(ev); }}
                  aria-label="Editar"
                >
                  <Pencil className="h-4 w-4" />
                </button>
                <button
                  className="rounded-md p-1.5 text-destructive hover:bg-destructive/10 transition-colors"
                  onClick={(e) => { e.stopPropagation(); setConfirmDelete(ev); }}
                  aria-label="Excluir"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {pagination && pagination.total_pages > 1 && (
        <div className="flex items-center justify-between rounded-lg border border-border bg-card px-4 py-3">
          <span className="text-xs text-muted-foreground">
            {pagination.total} evento{pagination.total !== 1 ? "s" : ""}
          </span>
          <div className="flex items-center gap-2">
            <button
              className="rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
            >
              Anterior
            </button>
            <span className="text-xs text-muted-foreground">
              {page} / {pagination.total_pages}
            </span>
            <button
              className="rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={page >= pagination.total_pages}
              onClick={() => setPage(page + 1)}
            >
              Proximo
            </button>
          </div>
        </div>
      )}

      {/* Create/Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={closeModal}>
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-lg max-h-[90vh] overflow-y-auto rounded-lg border border-border bg-card p-6 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-foreground">
                {editingEvent ? "Editar Evento" : "Novo Evento"}
              </h2>
              <button
                className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
                onClick={closeModal}
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Titulo */}
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Titulo *</label>
                <input
                  type="text"
                  required
                  maxLength={300}
                  value={formData.titulo}
                  onChange={(e) => setFormData({ ...formData, titulo: e.target.value })}
                  placeholder="Nome do evento"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                />
              </div>

              {/* Descricao */}
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Descricao</label>
                <textarea
                  rows={3}
                  value={formData.descricao}
                  onChange={(e) => setFormData({ ...formData, descricao: e.target.value })}
                  placeholder="Detalhes do evento"
                  className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                />
              </div>

              {/* Date fields */}
              <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Inicio *</label>
                  <input
                    type={formData.dia_inteiro ? "date" : "datetime-local"}
                    required
                    value={formData.dia_inteiro ? formData.data_inicio.slice(0, 10) : formData.data_inicio}
                    onChange={(e) => setFormData({ ...formData, data_inicio: e.target.value })}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Fim</label>
                  <input
                    type={formData.dia_inteiro ? "date" : "datetime-local"}
                    value={formData.dia_inteiro ? formData.data_fim.slice(0, 10) : formData.data_fim}
                    onChange={(e) => setFormData({ ...formData, data_fim: e.target.value })}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  />
                </div>
              </div>

              {/* Dia inteiro toggle */}
              <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.dia_inteiro}
                  onChange={(e) => setFormData({ ...formData, dia_inteiro: e.target.checked })}
                  className="h-4 w-4 rounded border-input text-primary focus:ring-ring"
                />
                Dia inteiro
              </label>

              {/* Cor */}
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Cor</label>
                <div className="flex flex-wrap gap-2">
                  {COLOR_PRESETS.map((c) => (
                    <button
                      key={c.value}
                      type="button"
                      title={c.label}
                      onClick={() => setFormData({ ...formData, cor: c.value })}
                      className={`h-8 w-8 rounded-full border-2 transition-all ${
                        formData.cor === c.value
                          ? "border-foreground scale-110"
                          : "border-transparent hover:border-muted-foreground/30"
                      }`}
                      style={{ backgroundColor: c.value }}
                    />
                  ))}
                </div>
              </div>

              {/* Local + Categoria */}
              <div className="grid gap-4 grid-cols-1 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Local</label>
                  <input
                    type="text"
                    value={formData.local}
                    onChange={(e) => setFormData({ ...formData, local: e.target.value })}
                    placeholder="Onde sera o evento"
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Categoria</label>
                  <input
                    type="text"
                    value={formData.categoria}
                    onChange={(e) => setFormData({ ...formData, categoria: e.target.value })}
                    placeholder="Ex: trabalho, pessoal"
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  />
                </div>
              </div>

              {/* Lembrete */}
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Lembrete (minutos antes)</label>
                <input
                  type="number"
                  min={0}
                  value={formData.lembrete_minutos}
                  onChange={(e) => setFormData({ ...formData, lembrete_minutos: e.target.value })}
                  placeholder="Ex: 15"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                />
              </div>

              {/* Actions */}
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
                  className="inline-flex items-center gap-2 rounded-md bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={isSaving || !formData.titulo || !formData.data_inicio}
                >
                  {isSaving ? (
                    <><Loader2 className="h-4 w-4 animate-spin" />Salvando...</>
                  ) : editingEvent ? "Salvar" : "Criar"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setConfirmDelete(null)}>
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-md rounded-lg border border-border bg-card p-6 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="mb-2 text-lg font-semibold text-foreground">Excluir evento</h2>
            <p className="mb-6 text-sm text-muted-foreground">
              Tem certeza que deseja excluir <strong className="text-foreground">{confirmDelete.titulo}</strong>?
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
                onClick={() => deleteMutation.mutate(confirmDelete.id)}
                disabled={deleteMutation.isPending}
              >
                {deleteMutation.isPending ? (
                  <><Loader2 className="h-4 w-4 animate-spin" />Excluindo...</>
                ) : "Confirmar exclusao"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
