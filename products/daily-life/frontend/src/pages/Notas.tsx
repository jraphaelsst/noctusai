import { useState, useCallback } from "react";
import {
  useNotas,
  useCreateNota,
  useUpdateNota,
  useDeleteNota,
  usePinNota,
} from "@/hooks/useNotas";
import type { Nota, NotaForm } from "@/hooks/useNotas";
import {
  StickyNote,
  Plus,
  Search,
  Pin,
  Pencil,
  Trash2,
  Loader2,
  X,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const EMPTY_FORM: NotaForm = {
  titulo: "",
  conteudo: "",
  tags: "",
  fixada: false,
  categoria: "",
};

const TAG_COLORS = [
  "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400",
  "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  "bg-pink-100 text-pink-800 dark:bg-pink-900/30 dark:text-pink-400",
  "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400",
];

function getTagColor(tag: string): string {
  let hash = 0;
  for (let i = 0; i < tag.length; i++) {
    hash = tag.charCodeAt(i) + ((hash << 5) - hash);
  }
  return TAG_COLORS[Math.abs(hash) % TAG_COLORS.length];
}

// ---------------------------------------------------------------------------
// Debounce hook
// ---------------------------------------------------------------------------

function useDebounce(delay: number) {
  const [timer, setTimer] = useState<ReturnType<typeof setTimeout> | null>(null);

  const debounce = useCallback(
    (fn: () => void) => {
      if (timer) clearTimeout(timer);
      setTimer(setTimeout(fn, delay));
    },
    [delay, timer],
  );

  return debounce;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Notas() {
  // Search
  const [searchInput, setSearchInput] = useState("");
  const [busca, setBusca] = useState("");
  const debounce = useDebounce(400);

  // Pagination
  const [page, setPage] = useState(1);
  const pageSize = 20;

  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [editingNote, setEditingNote] = useState<Nota | null>(null);
  const [formData, setFormData] = useState<NotaForm>(EMPTY_FORM);
  const [confirmDelete, setConfirmDelete] = useState<Nota | null>(null);

  // ---------------------------------------------------------------------------
  // Hooks
  // ---------------------------------------------------------------------------

  const { data: response, isPending } = useNotas(busca, page, pageSize);

  const createMutation = useCreateNota(() => closeModal());
  const updateMutation = useUpdateNota(() => closeModal());
  const deleteMutation = useDeleteNota(() => setConfirmDelete(null));
  const pinMutation = usePinNota();

  const notas = response?.data ?? [];
  const pagination = response?.pagination;

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  function closeModal() {
    setShowModal(false);
    setEditingNote(null);
    setFormData(EMPTY_FORM);
  }

  function openCreate() {
    setEditingNote(null);
    setFormData(EMPTY_FORM);
    setShowModal(true);
  }

  function openEdit(nota: Nota) {
    setEditingNote(nota);
    setFormData({
      titulo: nota.titulo,
      conteudo: nota.conteudo || "",
      tags: (nota.tags || []).join(", "),
      fixada: nota.fixada,
      categoria: nota.categoria || "",
    });
    setShowModal(true);
  }

  function handleSearchChange(value: string) {
    setSearchInput(value);
    debounce(() => {
      setBusca(value);
      setPage(1);
    });
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const tags = formData.tags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);

    const body: Record<string, unknown> = {
      titulo: formData.titulo,
      conteudo: formData.conteudo || null,
      tags: tags.length > 0 ? tags : null,
      fixada: formData.fixada,
      categoria: formData.categoria || null,
    };

    if (editingNote) {
      updateMutation.mutate({ id: editingNote.id, body });
    } else {
      createMutation.mutate(body);
    }
  }

  const isSaving = createMutation.isPending || updateMutation.isPending;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <StickyNote className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Minhas Notas</h1>
            <p className="text-sm text-muted-foreground">
              Anotacoes rapidas e diario pessoal
            </p>
          </div>
        </div>
        <button
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          onClick={openCreate}
        >
          <Plus className="h-4 w-4" />
          Nova Nota
        </button>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          value={searchInput}
          onChange={(e) => handleSearchChange(e.target.value)}
          placeholder="Buscar por titulo ou conteudo..."
          className="flex h-10 w-full rounded-md border border-input bg-background pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        />
      </div>

      {/* Notes Grid */}
      {isPending && !response ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Carregando notas...</p>
        </div>
      ) : notas.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center">
          <StickyNote className="mx-auto h-10 w-10 text-muted-foreground/40 mb-3" />
          <p className="text-muted-foreground">
            {busca ? "Nenhuma nota encontrada para essa busca" : "Nenhuma nota criada ainda"}
          </p>
          {!busca && (
            <button
              className="mt-3 text-sm text-primary hover:underline"
              onClick={openCreate}
            >
              Criar primeira nota
            </button>
          )}
        </div>
      ) : (
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          {notas.map((nota) => (
            <div
              key={nota.id}
              className={`group relative flex flex-col rounded-lg border bg-card p-4 hover:shadow-sm transition-all cursor-pointer ${
                nota.fixada
                  ? "border-primary/30 bg-primary/5"
                  : "border-border hover:border-primary/20"
              }`}
              onClick={() => openEdit(nota)}
            >
              {/* Pin indicator */}
              {nota.fixada && (
                <div className="absolute -top-2 -right-2 rounded-full bg-primary p-1">
                  <Pin className="h-3 w-3 text-primary-foreground" />
                </div>
              )}

              {/* Title */}
              <h3 className="font-medium text-foreground truncate pr-6">{nota.titulo}</h3>

              {/* Content preview */}
              {nota.conteudo && (
                <p className="mt-1.5 text-xs text-muted-foreground line-clamp-3 whitespace-pre-line">
                  {nota.conteudo}
                </p>
              )}

              {/* Tags */}
              {nota.tags && nota.tags.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {nota.tags.map((tag) => (
                    <span
                      key={tag}
                      className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ${getTagColor(tag)}`}
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}

              {/* Footer */}
              <div className="mt-auto pt-3 flex items-center justify-between">
                <span className="text-[10px] text-muted-foreground">
                  {new Date(nota.updated_at).toLocaleDateString("pt-BR", {
                    day: "2-digit",
                    month: "short",
                    year: "numeric",
                  })}
                </span>

                {/* Actions */}
                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    className="rounded-md p-1 text-muted-foreground hover:bg-muted transition-colors"
                    onClick={(e) => {
                      e.stopPropagation();
                      pinMutation.mutate({ id: nota.id, fixada: !nota.fixada });
                    }}
                    title={nota.fixada ? "Desafixar" : "Fixar"}
                    aria-label={nota.fixada ? "Desafixar" : "Fixar"}
                  >
                    <Pin className={`h-3.5 w-3.5 ${nota.fixada ? "text-primary" : ""}`} />
                  </button>
                  <button
                    className="rounded-md p-1 text-muted-foreground hover:bg-muted transition-colors"
                    onClick={(e) => { e.stopPropagation(); openEdit(nota); }}
                    aria-label="Editar"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                  <button
                    className="rounded-md p-1 text-destructive hover:bg-destructive/10 transition-colors"
                    onClick={(e) => { e.stopPropagation(); setConfirmDelete(nota); }}
                    aria-label="Excluir"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {pagination && pagination.total_pages > 1 && (
        <div className="flex items-center justify-between rounded-lg border border-border bg-card px-4 py-3">
          <span className="text-xs text-muted-foreground">
            {pagination.total} nota{pagination.total !== 1 ? "s" : ""}
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
                {editingNote ? "Editar Nota" : "Nova Nota"}
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
                  placeholder="Titulo da nota"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                />
              </div>

              {/* Conteudo */}
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Conteudo</label>
                <textarea
                  rows={8}
                  value={formData.conteudo}
                  onChange={(e) => setFormData({ ...formData, conteudo: e.target.value })}
                  placeholder="Escreva sua nota aqui..."
                  className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                />
              </div>

              {/* Tags */}
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Tags</label>
                <input
                  type="text"
                  value={formData.tags}
                  onChange={(e) => setFormData({ ...formData, tags: e.target.value })}
                  placeholder="Ex: trabalho, ideia, importante (separadas por virgula)"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                />
                {formData.tags && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {formData.tags
                      .split(",")
                      .map((t) => t.trim())
                      .filter(Boolean)
                      .map((tag) => (
                        <span
                          key={tag}
                          className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ${getTagColor(tag)}`}
                        >
                          {tag}
                        </span>
                      ))}
                  </div>
                )}
              </div>

              {/* Categoria */}
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Categoria</label>
                <input
                  type="text"
                  value={formData.categoria}
                  onChange={(e) => setFormData({ ...formData, categoria: e.target.value })}
                  placeholder="Ex: pessoal, projeto"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                />
              </div>

              {/* Fixada toggle */}
              <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.fixada}
                  onChange={(e) => setFormData({ ...formData, fixada: e.target.checked })}
                  className="h-4 w-4 rounded border-input text-primary focus:ring-ring"
                />
                Fixar nota no topo
              </label>

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
                  disabled={isSaving || !formData.titulo}
                >
                  {isSaving ? (
                    <><Loader2 className="h-4 w-4 animate-spin" />Salvando...</>
                  ) : editingNote ? "Salvar" : "Criar"}
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
            <h2 className="mb-2 text-lg font-semibold text-foreground">Excluir nota</h2>
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
