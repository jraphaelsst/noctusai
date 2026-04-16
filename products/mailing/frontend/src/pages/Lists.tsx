import { useState } from "react";
import { useLists, useCreateList, useDeleteList, ContactList } from "@/hooks/useLists";
import { toast } from "sonner";
import { Plus, Trash2, Loader2, X, List, AlertCircle } from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ListForm {
  nome: string;
  descricao: string;
  tipo: "static" | "dynamic";
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TIPO_CONFIG: Record<string, { label: string; className: string }> = {
  static: { label: "Estatica", className: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400" },
  dynamic: { label: "Dinamica", className: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400" },
};

const EMPTY_FORM: ListForm = { nome: "", descricao: "", tipo: "static" };

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Lists() {
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<ListForm>(EMPTY_FORM);
  const [confirmDelete, setConfirmDelete] = useState<ContactList | null>(null);

  const { data: listsRes, isLoading, isError } = useLists();
  const createMutation = useCreateList();
  const deleteMutation = useDeleteList();

  const lists: ContactList[] = listsRes?.data ?? [];

  function closeModal() {
    setShowModal(false);
    setForm(EMPTY_FORM);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.nome.trim()) return;
    const payload: Partial<ContactList> = {
      nome: form.nome.trim(),
      tipo: form.tipo,
    };
    if (form.descricao.trim()) payload.descricao = form.descricao.trim();

    createMutation.mutate(payload, {
      onSuccess: () => {
        toast.success("Lista criada com sucesso");
        closeModal();
      },
      onError: (err: any) => toast.error("Erro ao criar lista", { description: err?.message }),
    });
  }

  function handleDelete(list: ContactList) {
    deleteMutation.mutate(list.id, {
      onSuccess: () => {
        toast.success("Lista removida");
        setConfirmDelete(null);
      },
      onError: (err: any) => toast.error("Erro ao remover lista", { description: err?.message }),
    });
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <AlertCircle className="h-8 w-8 text-destructive" />
        <p className="text-sm text-muted-foreground">Erro ao carregar listas.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <List className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Listas</h1>
            <p className="text-sm text-muted-foreground">
              Organize seus contatos em listas segmentadas para campanhas direcionadas.
            </p>
          </div>
        </div>
        <button
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          onClick={() => setShowModal(true)}
        >
          <Plus className="h-4 w-4" />
          Nova Lista
        </button>
      </div>

      {/* Lists Table */}
      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Carregando listas...</p>
        </div>
      ) : lists.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center">
          <p className="text-sm text-muted-foreground">Nenhuma lista criada.</p>
          <p className="text-xs text-muted-foreground mt-1">Crie listas para organizar seus contatos e enviar campanhas segmentadas.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">Nome</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Tipo</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Contatos</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Criada em</th>
                <th className="px-4 py-3 font-medium text-muted-foreground w-16">Acoes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {lists.map((l) => {
                const tipo = TIPO_CONFIG[l.tipo] ?? TIPO_CONFIG.static;
                return (
                  <tr key={l.id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3">
                      <div>
                        <p className="font-medium text-foreground">{l.nome}</p>
                        {l.descricao && (
                          <p className="text-xs text-muted-foreground line-clamp-1">{l.descricao}</p>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${tipo.className}`}>
                        {tipo.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-foreground">{l.contact_count}</td>
                    <td className="px-4 py-3 text-muted-foreground hidden md:table-cell">
                      {new Date(l.created_at).toLocaleDateString("pt-BR")}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        className="rounded-md p-1.5 text-destructive hover:bg-destructive/10 transition-colors"
                        onClick={() => setConfirmDelete(l)}
                        title="Remover"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Create Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={closeModal}>
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-foreground">Nova Lista</h2>
              <button className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors" onClick={closeModal}>
                <X className="h-4 w-4" />
              </button>
            </div>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Nome *</label>
                <input
                  type="text"
                  required
                  value={form.nome}
                  onChange={(e) => setForm({ ...form, nome: e.target.value })}
                  placeholder="Ex: Clientes VIP"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Descricao</label>
                <textarea
                  value={form.descricao}
                  onChange={(e) => setForm({ ...form, descricao: e.target.value })}
                  rows={3}
                  placeholder="Descricao da lista..."
                  className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Tipo</label>
                <select
                  value={form.tipo}
                  onChange={(e) => setForm({ ...form, tipo: e.target.value as "static" | "dynamic" })}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <option value="static">Estatica</option>
                  <option value="dynamic">Dinamica</option>
                </select>
                <p className="mt-1 text-xs text-muted-foreground">
                  Listas estaticas tem membros fixos. Listas dinamicas atualizam automaticamente com base em filtros.
                </p>
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
                  disabled={createMutation.isPending || !form.nome.trim()}
                  className="inline-flex items-center gap-2 rounded-md bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {createMutation.isPending ? (
                    <><Loader2 className="h-4 w-4 animate-spin" />Criando...</>
                  ) : "Criar lista"}
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
            <h2 className="mb-2 text-lg font-semibold text-foreground">Remover lista</h2>
            <p className="mb-6 text-sm text-muted-foreground">
              Tem certeza que deseja remover a lista <strong className="text-foreground">{confirmDelete.nome}</strong>?
              Isso nao remove os contatos da base.
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
                onClick={() => handleDelete(confirmDelete)}
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
