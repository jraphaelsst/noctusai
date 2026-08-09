/**
 * MarcaManagementModal — inline modal for marca CRUD.
 *
 * Allows creating, editing, and deleting clients. Opened from Conexoes via the
 * "Gerenciar marcas" affordance. No new nav route needed — everything lives
 * within /conexoes.
 *
 * Uses the useMarcas mutations; the list rerenders automatically via
 * TanStack Query cache invalidation.
 */
import { useState } from "react";
import { Pencil, Plus, Save, Trash2, X } from "lucide-react";
import { toast } from "sonner";

import type { Marca } from "@/hooks/useMarcas";
import {
  useCreateMarca,
  useDeleteMarca,
  useUpdateMarca,
} from "@/hooks/useMarcas";

interface MarcaManagementModalProps {
  marcas: Marca[];
  onClose: () => void;
}

interface MarcaFormState {
  name: string;
  slug: string;
  kind: string;
  notes: string;
}

const emptyForm = (): MarcaFormState => ({
  name: "",
  slug: "",
  kind: "",
  notes: "",
});

function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function MarcaManagementModal({
  marcas,
  onClose,
}: MarcaManagementModalProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<MarcaFormState>(emptyForm());
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const createMarca = useCreateMarca();
  const updateMarca = useUpdateMarca();
  const deleteMarca = useDeleteMarca();

  function startCreate() {
    setEditingId(null);
    setForm(emptyForm());
    setShowCreate(true);
  }

  function startEdit(client: Marca) {
    setShowCreate(false);
    setEditingId(client.id);
    setForm({
      name: client.name,
      slug: client.slug,
      kind: client.kind ?? "",
      notes: client.notes ?? "",
    });
  }

  function cancelForm() {
    setShowCreate(false);
    setEditingId(null);
    setForm(emptyForm());
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name.trim()) return;
    try {
      await createMarca.mutateAsync({
        name: form.name.trim(),
        slug: form.slug.trim() || slugify(form.name),
        kind: form.kind.trim() || undefined,
        notes: form.notes.trim() || undefined,
      });
      toast.success("Marca criada");
      cancelForm();
    } catch (err: any) {
      toast.error("Erro ao criar marca", { description: err?.message });
    }
  }

  async function handleUpdate(e: React.FormEvent) {
    e.preventDefault();
    if (!editingId || !form.name.trim()) return;
    try {
      await updateMarca.mutateAsync({
        id: editingId,
        name: form.name.trim(),
        slug: form.slug.trim() || undefined,
        kind: form.kind.trim() || null,
        notes: form.notes.trim() || null,
      });
      toast.success("Marca atualizada");
      cancelForm();
    } catch (err: any) {
      toast.error("Erro ao atualizar marca", { description: err?.message });
    }
  }

  async function handleDelete(id: string) {
    try {
      await deleteMarca.mutateAsync(id);
      toast.success("Marca removida");
      setConfirmDeleteId(null);
    } catch (err: any) {
      toast.error("Erro ao remover marca", { description: err?.message });
    }
  }

  const isBusy =
    createMarca.isPending ||
    updateMarca.isPending ||
    deleteMarca.isPending;

  const isFormVisible = showCreate || editingId !== null;

  return (
    /* Backdrop */
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Gerenciar marcas"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-lg rounded-xl border border-border bg-background shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-base font-semibold">Gerenciar marcas</h2>
          <button
            type="button"
            aria-label="Fechar"
            onClick={onClose}
            className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="max-h-[60vh] overflow-y-auto px-5 py-4 space-y-3">
          {/* Client list */}
          {marcas.length === 0 && !isFormVisible && (
            <p className="py-4 text-center text-sm text-muted-foreground">
              Nenhuma marca ainda. Crie a primeira abaixo.
            </p>
          )}

          {marcas.map((client) => (
            <div
              key={client.id}
              className="rounded-lg border border-border bg-card p-3"
            >
              {editingId === client.id ? (
                <form onSubmit={handleUpdate} className="space-y-2">
                  <ClientFormFields
                    form={form}
                    onChange={setForm}
                    busy={isBusy}
                  />
                  <div className="flex items-center gap-2 pt-1">
                    <button
                      type="submit"
                      disabled={isBusy}
                      className="inline-flex h-7 items-center gap-1 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground disabled:opacity-50"
                    >
                      <Save className="h-3 w-3" />
                      Salvar
                    </button>
                    <button
                      type="button"
                      onClick={cancelForm}
                      disabled={isBusy}
                      className="inline-flex h-7 items-center gap-1 rounded-md border border-input bg-background px-3 text-xs font-medium hover:bg-accent disabled:opacity-50"
                    >
                      <X className="h-3 w-3" />
                      Cancelar
                    </button>
                  </div>
                </form>
              ) : (
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{client.name}</p>
                    <p className="text-xs text-muted-foreground font-mono truncate">
                      {client.slug}
                      {client.kind && ` · ${client.kind}`}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      type="button"
                      aria-label={`Editar ${client.name}`}
                      onClick={() => startEdit(client)}
                      disabled={isBusy}
                      className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent disabled:opacity-50"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    {confirmDeleteId === client.id ? (
                      <div className="flex items-center gap-1">
                        <span className="text-xs text-destructive">Confirmar?</span>
                        <button
                          type="button"
                          onClick={() => handleDelete(client.id)}
                          disabled={isBusy}
                          className="inline-flex h-6 items-center rounded px-2 text-xs bg-destructive text-destructive-foreground disabled:opacity-50"
                        >
                          Sim
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmDeleteId(null)}
                          className="inline-flex h-6 items-center rounded border border-input bg-background px-2 text-xs"
                        >
                          Não
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        aria-label={`Remover ${client.name}`}
                        onClick={() => setConfirmDeleteId(client.id)}
                        disabled={isBusy}
                        className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}

          {/* Create form */}
          {showCreate && (
            <div className="rounded-lg border border-dashed border-border bg-muted/20 p-3">
              <p className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Nova marca
              </p>
              <form onSubmit={handleCreate} className="space-y-2">
                <ClientFormFields
                  form={form}
                  onChange={setForm}
                  busy={isBusy}
                />
                <div className="flex items-center gap-2 pt-1">
                  <button
                    type="submit"
                    disabled={isBusy || !form.name.trim()}
                    className="inline-flex h-7 items-center gap-1 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground disabled:opacity-50"
                  >
                    <Save className="h-3 w-3" />
                    Criar
                  </button>
                  <button
                    type="button"
                    onClick={cancelForm}
                    disabled={isBusy}
                    className="inline-flex h-7 items-center gap-1 rounded-md border border-input bg-background px-3 text-xs font-medium hover:bg-accent disabled:opacity-50"
                  >
                    <X className="h-3 w-3" />
                    Cancelar
                  </button>
                </div>
              </form>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-border px-5 py-3">
          {!showCreate && editingId === null && (
            <button
              type="button"
              onClick={startCreate}
              disabled={isBusy}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-input bg-background px-3 text-sm font-medium hover:bg-accent disabled:opacity-50"
            >
              <Plus className="h-3.5 w-3.5" />
              Nova marca
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className="ml-auto inline-flex h-8 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            Fechar
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Shared form fields ────────────────────────────────────────────────────

function ClientFormFields({
  form,
  onChange,
  busy,
}: {
  form: MarcaFormState;
  onChange: (f: MarcaFormState) => void;
  busy: boolean;
}) {
  return (
    <>
      <div className="grid grid-cols-2 gap-2">
        <div className="flex flex-col gap-0.5">
          <label className="text-xs font-medium text-muted-foreground" htmlFor="cf-name">
            Nome *
          </label>
          <input
            id="cf-name"
            type="text"
            required
            value={form.name}
            disabled={busy}
            onChange={(e) => onChange({ ...form, name: e.target.value })}
            className="h-8 w-full rounded-md border border-input bg-background px-2.5 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            placeholder="Ex: Acme Corp"
          />
        </div>
        <div className="flex flex-col gap-0.5">
          <label className="text-xs font-medium text-muted-foreground" htmlFor="cf-slug">
            Slug
          </label>
          <input
            id="cf-slug"
            type="text"
            value={form.slug}
            disabled={busy}
            onChange={(e) => onChange({ ...form, slug: e.target.value })}
            className="h-8 w-full rounded-md border border-input bg-background px-2.5 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            placeholder="acme-corp (auto)"
          />
        </div>
      </div>
      <div className="flex flex-col gap-0.5">
        <label className="text-xs font-medium text-muted-foreground" htmlFor="cf-kind">
          Tipo
        </label>
        <input
          id="cf-kind"
          type="text"
          value={form.kind}
          disabled={busy}
          onChange={(e) => onChange({ ...form, kind: e.target.value })}
          className="h-8 w-full rounded-md border border-input bg-background px-2.5 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          placeholder="Ex: parceiro, agência"
        />
      </div>
      <div className="flex flex-col gap-0.5">
        <label className="text-xs font-medium text-muted-foreground" htmlFor="cf-notes">
          Notas
        </label>
        <input
          id="cf-notes"
          type="text"
          value={form.notes}
          disabled={busy}
          onChange={(e) => onChange({ ...form, notes: e.target.value })}
          className="h-8 w-full rounded-md border border-input bg-background px-2.5 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          placeholder="Notas opcionais"
        />
      </div>
    </>
  );
}

export default MarcaManagementModal;
