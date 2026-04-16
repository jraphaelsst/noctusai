import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useContact, useUpdateContact, useDeleteContact, Contact } from "@/hooks/useContacts";
import { toast } from "sonner";
import { Loader2, ArrowLeft, Trash2, Save, AlertCircle } from "lucide-react";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATUS_CONFIG: Record<string, { label: string; className: string }> = {
  active: { label: "Ativo", className: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400" },
  unsubscribed: { label: "Descadastrado", className: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400" },
  bounced: { label: "Bounced", className: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400" },
  complained: { label: "Reclamou", className: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400" },
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ContactDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: contactRes, isLoading, isError } = useContact(id!);
  const updateMutation = useUpdateContact();
  const deleteMutation = useDeleteContact();

  const contact: Contact | null = contactRes?.data ?? null;

  // Edit form state
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ nome: "", telefone: "", empresa: "", tags: "" });
  const [confirmDelete, setConfirmDelete] = useState(false);

  function startEditing() {
    if (!contact) return;
    setForm({
      nome: contact.nome ?? "",
      telefone: contact.telefone ?? "",
      empresa: contact.empresa ?? "",
      tags: (contact.tags ?? []).join(", "),
    });
    setEditing(true);
  }

  function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!contact) return;
    const payload: Partial<Contact> & { id: string } = { id: contact.id };
    payload.nome = form.nome.trim() || undefined;
    payload.telefone = form.telefone.trim() || undefined;
    payload.empresa = form.empresa.trim() || undefined;
    payload.tags = form.tags.split(",").map((t) => t.trim()).filter(Boolean);

    updateMutation.mutate(payload, {
      onSuccess: () => {
        toast.success("Contato atualizado");
        setEditing(false);
      },
      onError: (err: any) => toast.error("Erro ao atualizar", { description: err?.message }),
    });
  }

  function handleDelete() {
    if (!contact) return;
    deleteMutation.mutate(contact.id, {
      onSuccess: () => {
        toast.success("Contato removido");
        navigate("/contacts");
      },
      onError: (err: any) => toast.error("Erro ao remover", { description: err?.message }),
    });
  }

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Carregando contato...</p>
      </div>
    );
  }

  if (isError || !contact) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <AlertCircle className="h-8 w-8 text-destructive" />
        <p className="text-sm text-muted-foreground">Contato nao encontrado.</p>
        <button
          onClick={() => navigate("/contacts")}
          className="text-sm text-primary hover:underline"
        >
          Voltar para contatos
        </button>
      </div>
    );
  }

  const st = STATUS_CONFIG[contact.status] ?? STATUS_CONFIG.active;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate("/contacts")}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-foreground">
              {contact.nome || contact.email}
            </h1>
            <p className="text-sm text-muted-foreground">{contact.email}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {!editing && (
            <button
              onClick={startEditing}
              className="inline-flex items-center gap-2 rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:bg-muted transition-colors"
            >
              Editar
            </button>
          )}
          <button
            onClick={() => setConfirmDelete(true)}
            className="inline-flex items-center gap-2 rounded-md bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors"
          >
            <Trash2 className="h-4 w-4" />
            Remover
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Contact Info / Edit Form */}
        <div className="lg:col-span-1">
          <div className="rounded-lg border border-border bg-card p-5 space-y-4">
            <h2 className="text-lg font-semibold text-foreground">Informacoes</h2>

            {editing ? (
              <form onSubmit={handleSave} className="space-y-4">
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Nome</label>
                  <input
                    type="text"
                    value={form.nome}
                    onChange={(e) => setForm({ ...form, nome: e.target.value })}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Telefone</label>
                  <input
                    type="text"
                    value={form.telefone}
                    onChange={(e) => setForm({ ...form, telefone: e.target.value })}
                    placeholder="(00) 00000-0000"
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Empresa</label>
                  <input
                    type="text"
                    value={form.empresa}
                    onChange={(e) => setForm({ ...form, empresa: e.target.value })}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Tags</label>
                  <input
                    type="text"
                    value={form.tags}
                    onChange={(e) => setForm({ ...form, tags: e.target.value })}
                    placeholder="Separadas por virgula"
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                </div>
                <div className="flex gap-3 pt-2">
                  <button
                    type="submit"
                    disabled={updateMutation.isPending}
                    className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
                  >
                    {updateMutation.isPending ? (
                      <><Loader2 className="h-4 w-4 animate-spin" />Salvando...</>
                    ) : (
                      <><Save className="h-4 w-4" />Salvar</>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditing(false)}
                    className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
                  >
                    Cancelar
                  </button>
                </div>
              </form>
            ) : (
              <div className="space-y-3">
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Nome</p>
                  <p className="text-sm text-foreground">{contact.nome || "--"}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">E-mail</p>
                  <p className="text-sm text-foreground">{contact.email}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Telefone</p>
                  <p className="text-sm text-foreground">{contact.telefone || "--"}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Empresa</p>
                  <p className="text-sm text-foreground">{contact.empresa || "--"}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Tags</p>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {(contact.tags ?? []).length > 0 ? contact.tags.map((tag) => (
                      <span key={tag} className="inline-flex rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                        {tag}
                      </span>
                    )) : <span className="text-sm text-muted-foreground">--</span>}
                  </div>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Status</p>
                  <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${st.className}`}>
                    {st.label}
                  </span>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Origem</p>
                  <p className="text-sm text-foreground">{contact.source || "--"}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Criado em</p>
                  <p className="text-sm text-foreground">
                    {new Date(contact.created_at).toLocaleDateString("pt-BR")}
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Custom Fields & History placeholder */}
        <div className="lg:col-span-2 space-y-6">
          {/* Custom Fields */}
          {contact.custom_fields && Object.keys(contact.custom_fields).length > 0 && (
            <div className="rounded-lg border border-border bg-card p-5 space-y-4">
              <h2 className="text-lg font-semibold text-foreground">Campos Personalizados</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {Object.entries(contact.custom_fields).map(([key, value]) => (
                  <div key={key}>
                    <p className="text-xs font-medium text-muted-foreground">{key}</p>
                    <p className="text-sm text-foreground">{String(value)}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* History placeholder */}
          <div className="rounded-lg border border-border bg-card p-5 space-y-4">
            <h2 className="text-lg font-semibold text-foreground">Historico de Envios</h2>
            <div className="text-center py-8 text-muted-foreground">
              <p className="text-sm">Historico de envios sera exibido aqui quando disponivel.</p>
            </div>
          </div>
        </div>
      </div>

      {/* Delete Confirm */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setConfirmDelete(false)}>
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-md rounded-lg border border-border bg-card p-6 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="mb-2 text-lg font-semibold text-foreground">Remover contato</h2>
            <p className="mb-6 text-sm text-muted-foreground">
              Tem certeza que deseja remover <strong className="text-foreground">{contact.nome || contact.email}</strong>? Esta acao nao pode ser desfeita.
            </p>
            <div className="flex justify-end gap-3">
              <button
                className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
                onClick={() => setConfirmDelete(false)}
              >
                Cancelar
              </button>
              <button
                className="inline-flex items-center gap-2 rounded-md bg-destructive px-6 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                disabled={deleteMutation.isPending}
                onClick={handleDelete}
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
