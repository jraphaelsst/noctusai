/**
 * Contatos — Platform (in-home) contact management.
 *
 * Shows contacts saved locally in social_wiring.contacts:
 *   - Manually created
 *   - Auto-saved from WhatsApp
 *   - Imported via CSV
 *
 * Features:
 *   - Source badge ("WhatsApp", "Manual", "Import")
 *   - Name as primary label; phone / email / company as secondary
 *   - Status filter (all / active / archived)
 *   - Search by name / email / company
 *   - Page-scoped CRUD: create / edit / archive
 *   - All states: loading / empty / error / success
 *
 * NO MailchimpGate — this page does NOT depend on Mailchimp.
 * Mailchimp audience members live at /email-marketing/membros (EmailMembros.tsx).
 */
import { useState } from "react";
import {
  UserRound,
  Plus,
  Archive,
  Pencil,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  Search,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  useContacts,
  useContactMutations,
  type Contact,
} from "@/hooks/useContacts";

const PAGE_SIZE = 20;

// ─── Source badges ────────────────────────────────────────────────────────────

const SOURCE_LABELS: Record<string, string> = {
  manual: "Manual",
  import: "Import",
  whatsapp: "WhatsApp",
};

const SOURCE_COLORS: Record<string, string> = {
  manual: "bg-blue-100 text-blue-800",
  import: "bg-purple-100 text-purple-800",
  whatsapp: "bg-green-100 text-green-800",
};

function SourceBadge({ source }: { source: string }) {
  const label = SOURCE_LABELS[source] ?? source;
  const color = SOURCE_COLORS[source] ?? "bg-gray-100 text-gray-800";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${color}`}
      data-testid={`source-badge-${source}`}
    >
      {label}
    </span>
  );
}

// ─── Contact form ─────────────────────────────────────────────────────────────

interface ContactFormState {
  nome: string;
  email: string;
  telefone: string;
  empresa: string;
  tags: string;
}

const emptyForm = (): ContactFormState => ({
  nome: "",
  email: "",
  telefone: "",
  empresa: "",
  tags: "",
});

// ─── Main page ────────────────────────────────────────────────────────────────

export default function Contatos() {
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [archiveTarget, setArchiveTarget] = useState<Contact | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<ContactFormState>(emptyForm());

  const { data, isPending: listPending, isFetching, isError, error } = useContacts({
    page,
    pageSize: PAGE_SIZE,
    status: statusFilter || undefined,
    search: search || undefined,
  });

  const { create, update, archive } = useContactMutations();

  function openCreate() {
    setForm(emptyForm());
    setEditingId(null);
    setModalOpen(true);
  }

  function openEdit(contact: Contact) {
    setForm({
      nome: contact.nome ?? "",
      email: contact.email ?? "",
      telefone: contact.telefone ?? "",
      empresa: contact.empresa ?? "",
      tags: contact.tags?.join(", ") ?? "",
    });
    setEditingId(contact.id);
    setModalOpen(true);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const tagsArr = form.tags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);

    if (editingId) {
      update.mutate(
        {
          id: editingId,
          body: {
            nome: form.nome || undefined,
            email: form.email || undefined,
            telefone: form.telefone || undefined,
            empresa: form.empresa || undefined,
            tags: tagsArr.length ? tagsArr : undefined,
          },
        },
        {
          onSuccess: () => {
            toast.success("Contato atualizado.");
            setModalOpen(false);
          },
          onError: () => toast.error("Erro ao atualizar contato."),
        },
      );
    } else {
      create.mutate(
        {
          email: form.email,
          nome: form.nome || undefined,
          telefone: form.telefone || undefined,
          empresa: form.empresa || undefined,
          tags: tagsArr.length ? tagsArr : undefined,
          source: "manual",
        },
        {
          onSuccess: () => {
            toast.success("Contato criado.");
            setModalOpen(false);
          },
          onError: () => toast.error("Erro ao criar contato."),
        },
      );
    }
  }

  function handleArchive() {
    if (!archiveTarget) return;
    archive.mutate(archiveTarget.id, {
      onSuccess: () => {
        toast.success("Contato removido.");
        setArchiveTarget(null);
      },
      onError: () => toast.error("Erro ao remover contato."),
    });
  }

  const contacts = data?.data ?? [];

  // Skeleton ONLY when there is nothing to show — the seed idiom
  // (PipelineBoard / PipelineStagesManager). Bare `isLoading` is false
  // between retries and while a query is paused, which rendered a blank
  // page on a failed fetch (mailchimp templates 500, 2026-09-01).
  const showSkeleton = listPending || (isFetching && contacts.length === 0);
  const total = data?.pagination?.total ?? 0;
  const totalPages = data?.pagination?.total_pages ?? 1;
  const isPending = create.isPending || update.isPending;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <UserRound className="h-6 w-6 text-muted-foreground" />
          <div>
            <h1 className="text-2xl font-semibold">Contatos</h1>
            <p className="text-sm text-muted-foreground">
              Contatos da plataforma — WhatsApp, manual e importações
            </p>
          </div>
        </div>
        <Button onClick={openCreate} className="gap-2" data-testid="btn-novo-contato">
          <Plus className="h-4 w-4" />
          Novo contato
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          <Input
            className="pl-9"
            placeholder="Buscar por nome, email, empresa..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            data-testid="search-input"
          />
        </div>
        <div className="flex items-center gap-2">
          <Label className="shrink-0 text-sm">Status:</Label>
          <Select
            value={statusFilter || "all"}
            onValueChange={(v) => {
              setStatusFilter(v === "all" ? "" : v);
              setPage(1);
            }}
          >
            <SelectTrigger className="w-36" data-testid="status-filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos</SelectItem>
              <SelectItem value="active">Ativos</SelectItem>
              <SelectItem value="archived">Arquivados</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Loading */}
      {showSkeleton && (
        <div className="space-y-2" data-testid="contatos-loading">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      )}

      {/* Error */}
      {isError && (
        <Card className="border-destructive" data-testid="contatos-error">
          <CardContent className="flex items-center gap-3 pt-6">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <p className="text-sm text-destructive">
              Erro ao carregar contatos:{" "}
              {((error as Error)?.message ?? "").replace(/^\[\d+\]\s*/, "") ||
                "Tente novamente."}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Empty */}
      {!showSkeleton && !isError && contacts.length === 0 && (
        <Card data-testid="contatos-empty">
          <CardHeader>
            <CardTitle className="text-base">Nenhum contato encontrado</CardTitle>
            <CardDescription>
              {statusFilter || search
                ? "Nenhum contato com esses filtros. Tente outros critérios."
                : "Adicione seu primeiro contato ou conecte o WhatsApp para importar automaticamente."}
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {/* Table */}
      {!showSkeleton && !isError && contacts.length > 0 && (
        <Card data-testid="contatos-table">
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-4 py-3 text-left font-medium">Nome</th>
                    <th className="px-4 py-3 text-left font-medium">Contato</th>
                    <th className="px-4 py-3 text-left font-medium">Origem</th>
                    <th className="px-4 py-3 text-left font-medium">Tags</th>
                    <th className="px-4 py-3 text-right font-medium">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {contacts.map((contact) => (
                    <tr
                      key={contact.id}
                      className="border-b last:border-0 hover:bg-muted/30"
                      data-testid={`contato-row-${contact.id}`}
                    >
                      <td className="px-4 py-3">
                        <span className="font-medium">
                          {contact.nome || (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </span>
                        {contact.empresa && (
                          <p className="text-xs text-muted-foreground">
                            {contact.empresa}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        <div className="space-y-0.5">
                          {contact.telefone && (
                            <p className="text-xs">{contact.telefone}</p>
                          )}
                          {contact.whatsapp_phone && !contact.telefone && (
                            <p className="text-xs">{contact.whatsapp_phone}</p>
                          )}
                          {contact.email && (
                            <p className="text-xs">{contact.email}</p>
                          )}
                          {!contact.telefone && !contact.whatsapp_phone && !contact.email && (
                            <span className="text-xs">—</span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <SourceBadge source={contact.source} />
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
                          {contact.tags?.length > 0 ? (
                            contact.tags.map((tag) => (
                              <Badge key={tag} variant="outline" className="text-xs">
                                {tag}
                              </Badge>
                            ))
                          ) : (
                            <span className="text-muted-foreground text-xs">—</span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => openEdit(contact)}
                            data-testid={`edit-contato-${contact.id}`}
                          >
                            <Pencil className="h-4 w-4" />
                            <span className="sr-only">Editar</span>
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setArchiveTarget(contact)}
                            data-testid={`archive-contato-${contact.id}`}
                          >
                            <Archive className="h-4 w-4" />
                            <span className="sr-only">Remover</span>
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {total > PAGE_SIZE && (
              <div
                className="flex items-center justify-between px-4 py-3 border-t"
                data-testid="contatos-pagination"
              >
                <p className="text-sm text-muted-foreground">
                  Página {page} de {totalPages} ({total} contatos)
                </p>
                <div className="flex gap-1">
                  <Button
                    variant="outline"
                    size="icon"
                    disabled={page === 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Create / Edit Modal */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent data-testid="contato-modal">
          <DialogHeader>
            <DialogTitle>
              {editingId ? "Editar contato" : "Novo contato"}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4 pt-2">
            <div className="space-y-1.5">
              <Label htmlFor="contact-nome">Nome</Label>
              <Input
                id="contact-nome"
                data-testid="contact-nome-input"
                value={form.nome}
                onChange={(e) => setForm({ ...form, nome: e.target.value })}
                disabled={isPending}
                placeholder="João Silva"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="contact-email">
                Email {!editingId && <span className="text-destructive">*</span>}
              </Label>
              <Input
                id="contact-email"
                data-testid="contact-email-input"
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                disabled={isPending}
                required={!editingId}
                placeholder="joao@exemplo.com"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="contact-telefone">Telefone</Label>
                <Input
                  id="contact-telefone"
                  data-testid="contact-telefone-input"
                  value={form.telefone}
                  onChange={(e) =>
                    setForm({ ...form, telefone: e.target.value })
                  }
                  disabled={isPending}
                  placeholder="+55 11 99999-9999"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="contact-empresa">Empresa</Label>
                <Input
                  id="contact-empresa"
                  data-testid="contact-empresa-input"
                  value={form.empresa}
                  onChange={(e) =>
                    setForm({ ...form, empresa: e.target.value })
                  }
                  disabled={isPending}
                  placeholder="Acme Ltda."
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="contact-tags">Tags (separadas por vírgula)</Label>
              <Input
                id="contact-tags"
                data-testid="contact-tags-input"
                value={form.tags}
                onChange={(e) => setForm({ ...form, tags: e.target.value })}
                disabled={isPending}
                placeholder="vip, cliente, newsletter"
              />
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setModalOpen(false)}
              >
                Cancelar
              </Button>
              <Button
                type="submit"
                disabled={isPending || (!editingId && !form.email.trim())}
                data-testid="contact-modal-submit"
              >
                {isPending ? "Salvando..." : "Salvar"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Archive / Remove confirm */}
      <AlertDialog
        open={!!archiveTarget}
        onOpenChange={(open) => !open && setArchiveTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remover contato?</AlertDialogTitle>
            <AlertDialogDescription>
              O contato{" "}
              <strong>{archiveTarget?.nome || archiveTarget?.email || archiveTarget?.id}</strong>{" "}
              será removido permanentemente da plataforma.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleArchive}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="confirm-archive-contato"
            >
              {archive.isPending ? "Removendo..." : "Remover"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
