import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useContacts, useCreateContact, useDeleteContact, Contact } from "@/hooks/useContacts";
import { toast } from "sonner";
import {
  Plus,
  Trash2,
  Loader2,
  X,
  ChevronLeft,
  ChevronRight,
  Search,
  Users,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ContactForm {
  email: string;
  nome: string;
  empresa: string;
  tags: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATUS_CONFIG: Record<string, { label: string; className: string }> = {
  active: { label: "Ativo", className: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400" },
  unsubscribed: { label: "Descadastrado", className: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400" },
  bounced: { label: "Bounced", className: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400" },
  complained: { label: "Reclamou", className: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400" },
};

const EMPTY_FORM: ContactForm = { email: "", nome: "", empresa: "", tags: "" };
const PAGE_SIZE = 20;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Contacts() {
  const navigate = useNavigate();

  // Filters
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [debouncedSearch, setDebouncedSearch] = useState("");

  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<ContactForm>(EMPTY_FORM);
  const [confirmDelete, setConfirmDelete] = useState<Contact | null>(null);

  // Debounce search
  const [timer, setTimer] = useState<ReturnType<typeof setTimeout> | null>(null);
  function handleSearchChange(value: string) {
    setSearch(value);
    if (timer) clearTimeout(timer);
    const t = setTimeout(() => {
      setDebouncedSearch(value);
      setPage(1);
    }, 400);
    setTimer(t);
  }

  // Queries
  const { data: contactsRes, isLoading } = useContacts(page, PAGE_SIZE, {
    status: statusFilter || undefined,
    search: debouncedSearch || undefined,
  });
  const createMutation = useCreateContact();
  const deleteMutation = useDeleteContact();

  const contacts: Contact[] = contactsRes?.data ?? [];
  const total = contactsRes?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // Handlers
  function closeModal() {
    setShowModal(false);
    setForm(EMPTY_FORM);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.email.trim()) return;
    const payload: Partial<Contact> = {
      email: form.email.trim(),
    };
    if (form.nome.trim()) payload.nome = form.nome.trim();
    if (form.empresa.trim()) payload.empresa = form.empresa.trim();
    if (form.tags.trim()) {
      payload.tags = form.tags.split(",").map((t) => t.trim()).filter(Boolean);
    }
    createMutation.mutate(payload, {
      onSuccess: () => {
        toast.success("Contato criado com sucesso");
        closeModal();
      },
      onError: (err: any) => toast.error("Erro ao criar contato", { description: err?.message }),
    });
  }

  function handleDelete(contact: Contact) {
    deleteMutation.mutate(contact.id, {
      onSuccess: () => {
        toast.success("Contato removido");
        setConfirmDelete(null);
      },
      onError: (err: any) => toast.error("Erro ao remover contato", { description: err?.message }),
    });
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Users className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Contatos</h1>
            <p className="text-sm text-muted-foreground">
              Gerencie sua base de contatos, segmente por tags e acompanhe o status de cada um.
            </p>
          </div>
        </div>
        <button
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          onClick={() => setShowModal(true)}
        >
          <Plus className="h-4 w-4" />
          Novo Contato
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Buscar por nome, e-mail ou empresa..."
            value={search}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="flex h-10 w-full rounded-md border border-input bg-background pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
          className="flex h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="">Todos os status</option>
          <option value="active">Ativo</option>
          <option value="unsubscribed">Descadastrado</option>
          <option value="bounced">Bounced</option>
          <option value="complained">Reclamou</option>
        </select>
      </div>

      {/* Contacts Table */}
      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Carregando contatos...</p>
        </div>
      ) : contacts.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center">
          <p className="text-sm text-muted-foreground">Nenhum contato encontrado.</p>
          <p className="text-xs text-muted-foreground mt-1">Importe contatos ou adicione manualmente para comecar.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">Nome</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">E-mail</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Empresa</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Tags</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3 font-medium text-muted-foreground w-16">Acoes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {contacts.map((c) => {
                const st = STATUS_CONFIG[c.status] ?? STATUS_CONFIG.active;
                return (
                  <tr
                    key={c.id}
                    className="hover:bg-muted/30 transition-colors cursor-pointer"
                    onClick={() => navigate(`/contacts/${c.id}`)}
                  >
                    <td className="px-4 py-3 font-medium text-foreground">{c.nome || "--"}</td>
                    <td className="px-4 py-3 text-foreground">{c.email}</td>
                    <td className="px-4 py-3 text-muted-foreground hidden md:table-cell">{c.empresa || "--"}</td>
                    <td className="px-4 py-3 hidden lg:table-cell">
                      <div className="flex flex-wrap gap-1">
                        {(c.tags ?? []).map((tag) => (
                          <span key={tag} className="inline-flex rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                            {tag}
                          </span>
                        ))}
                        {(!c.tags || c.tags.length === 0) && <span className="text-xs text-muted-foreground">--</span>}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${st.className}`}>
                        {st.label}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        className="rounded-md p-1.5 text-destructive hover:bg-destructive/10 transition-colors"
                        onClick={(e) => { e.stopPropagation(); setConfirmDelete(c); }}
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

      {/* Create Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={closeModal}>
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-foreground">Novo Contato</h2>
              <button className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors" onClick={closeModal}>
                <X className="h-4 w-4" />
              </button>
            </div>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">E-mail *</label>
                <input
                  type="email"
                  required
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  placeholder="contato@exemplo.com"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Nome</label>
                <input
                  type="text"
                  value={form.nome}
                  onChange={(e) => setForm({ ...form, nome: e.target.value })}
                  placeholder="Nome do contato"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Empresa</label>
                <input
                  type="text"
                  value={form.empresa}
                  onChange={(e) => setForm({ ...form, empresa: e.target.value })}
                  placeholder="Empresa do contato"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Tags</label>
                <input
                  type="text"
                  value={form.tags}
                  onChange={(e) => setForm({ ...form, tags: e.target.value })}
                  placeholder="cliente, vip, newsletter (separadas por virgula)"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
                <p className="mt-1 text-xs text-muted-foreground">Separe as tags por virgula</p>
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
                  disabled={createMutation.isPending || !form.email.trim()}
                  className="inline-flex items-center gap-2 rounded-md bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {createMutation.isPending ? (
                    <><Loader2 className="h-4 w-4 animate-spin" />Criando...</>
                  ) : "Criar contato"}
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
            <h2 className="mb-2 text-lg font-semibold text-foreground">Remover contato</h2>
            <p className="mb-6 text-sm text-muted-foreground">
              Tem certeza que deseja remover <strong className="text-foreground">{confirmDelete.nome || confirmDelete.email}</strong>?
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
