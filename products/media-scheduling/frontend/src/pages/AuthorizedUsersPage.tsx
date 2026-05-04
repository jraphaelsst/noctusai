/**
 * AuthorizedUsersPage — CRUD on media_scheduling.authorized_users.
 *
 * These are the WhatsApp-authorized phone numbers + names (NOT platform SSO users —
 * separate concept per PROJECT.md §5).
 */
import { useState } from "react";
import {
  AuthorizedUser,
  useAuthorizedUsers,
  useCreateAuthorizedUser,
  useDeleteAuthorizedUser,
  useUpdateAuthorizedUser,
} from "@/hooks/useAuthorizedUsers";
import { toast } from "sonner";
import { Loader2, Plus, Trash2, UserCheck, X, Pencil } from "lucide-react";

interface FormState {
  phone_number: string;
  name: string;
  is_active: boolean;
  notes: string;
}

const EMPTY_FORM: FormState = {
  phone_number: "",
  name: "",
  is_active: true,
  notes: "",
};

export default function AuthorizedUsersPage() {
  const { data, isLoading, error } = useAuthorizedUsers();
  const createMutation = useCreateAuthorizedUser();
  const updateMutation = useUpdateAuthorizedUser();
  const deleteMutation = useDeleteAuthorizedUser();

  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState<AuthorizedUser | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [confirmDelete, setConfirmDelete] = useState<AuthorizedUser | null>(null);

  const users: AuthorizedUser[] = data?.data ?? [];

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setShowModal(true);
  }

  function openEdit(u: AuthorizedUser) {
    setEditing(u);
    setForm({
      phone_number: u.phone_number,
      name: u.name,
      is_active: u.is_active,
      notes: u.notes ?? "",
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
    const trimmed = {
      phone_number: form.phone_number.trim(),
      name: form.name.trim(),
      is_active: form.is_active,
      notes: form.notes.trim() || null,
    };
    if (!trimmed.phone_number || !trimmed.name) return;

    if (editing) {
      updateMutation.mutate(
        { id: editing.id, ...trimmed },
        {
          onSuccess: () => {
            toast.success("Usuário autorizado atualizado");
            closeModal();
          },
          onError: (err: any) =>
            toast.error("Erro ao atualizar usuário", { description: err?.message }),
        },
      );
    } else {
      createMutation.mutate(trimmed, {
        onSuccess: () => {
          toast.success("Usuário autorizado criado");
          closeModal();
        },
        onError: (err: any) =>
          toast.error("Erro ao criar usuário", { description: err?.message }),
      });
    }
  }

  function handleDelete(u: AuthorizedUser) {
    deleteMutation.mutate(u.id, {
      onSuccess: () => {
        toast.success("Usuário removido");
        setConfirmDelete(null);
      },
      onError: (err: any) =>
        toast.error("Erro ao remover usuário", { description: err?.message }),
    });
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <UserCheck className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Usuários Autorizados</h1>
            <p className="text-sm text-muted-foreground">
              Números de WhatsApp autorizados a iniciar conversas com o agendador.
              Não confundir com usuários SSO da plataforma.
            </p>
          </div>
        </div>
        <button
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          onClick={openCreate}
        >
          <Plus className="h-4 w-4" />
          Novo usuário
        </button>
      </div>

      {/* Body */}
      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Carregando usuários...</p>
        </div>
      ) : error ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          Erro ao carregar usuários autorizados.
        </div>
      ) : users.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center">
          <p className="text-sm text-muted-foreground">Nenhum usuário autorizado ainda.</p>
          <p className="text-xs text-muted-foreground mt-1">
            Adicione um número de WhatsApp para liberar o agendamento conversacional.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">Nome</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Telefone</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Notas</th>
                <th className="px-4 py-3 font-medium text-muted-foreground w-24">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3 font-medium text-foreground">{u.name || "--"}</td>
                  <td className="px-4 py-3 text-foreground">{u.phone_number}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        u.is_active
                          ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      {u.is_active ? "Ativo" : "Inativo"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground hidden md:table-cell">
                    {u.notes || "--"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <button
                        className="rounded-md p-1.5 text-foreground hover:bg-muted transition-colors"
                        onClick={() => openEdit(u)}
                        title="Editar"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        className="rounded-md p-1.5 text-destructive hover:bg-destructive/10 transition-colors"
                        onClick={() => setConfirmDelete(u)}
                        title="Remover"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create / Edit Modal */}
      {showModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={closeModal}
        >
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-foreground">
                {editing ? "Editar usuário autorizado" : "Novo usuário autorizado"}
              </h2>
              <button
                className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
                onClick={closeModal}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">
                  Telefone WhatsApp *
                </label>
                <input
                  type="text"
                  required
                  value={form.phone_number}
                  onChange={(e) => setForm({ ...form, phone_number: e.target.value })}
                  placeholder="+55 11 99999-0000"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Nome *</label>
                <input
                  type="text"
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Nome do usuário"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Notas</label>
                <textarea
                  rows={3}
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                  placeholder="Observações internas (opcional)"
                  className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </div>
              <label className="flex items-center gap-2 text-sm text-foreground">
                <input
                  type="checkbox"
                  checked={form.is_active}
                  onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                  className="rounded border-input"
                />
                Usuário ativo
              </label>
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
                  disabled={
                    createMutation.isPending ||
                    updateMutation.isPending ||
                    !form.phone_number.trim() ||
                    !form.name.trim()
                  }
                  className="inline-flex items-center gap-2 rounded-md bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {createMutation.isPending || updateMutation.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Salvando...
                    </>
                  ) : (
                    "Salvar"
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirm */}
      {confirmDelete && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setConfirmDelete(null)}
        >
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-md rounded-lg border border-border bg-card p-6 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="mb-2 text-lg font-semibold text-foreground">Remover usuário</h2>
            <p className="mb-6 text-sm text-muted-foreground">
              Tem certeza que deseja remover{" "}
              <strong className="text-foreground">
                {confirmDelete.name || confirmDelete.phone_number}
              </strong>
              ? O número não poderá mais iniciar conversas com o agendador.
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
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Removendo...
                  </>
                ) : (
                  "Confirmar remoção"
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
