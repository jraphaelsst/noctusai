/**
 * Contatos — Mailchimp audience member management.
 *
 * Shows a table of audience members with:
 *   - Status filter (all / subscribed / unsubscribed / cleaned / pending)
 *   - Count/offset pagination
 *   - Upsert modal (email read-only on edit)
 *   - Archive confirm
 *
 * All states: loading / empty / error / success.
 * Wrapped in <MailchimpGate> — redirects to config if disconnected.
 */
import { useState } from "react";
import {
  Users,
  Plus,
  Archive,
  Pencil,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
} from "lucide-react";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { toast } from "sonner";
import { MailchimpGate } from "@/components/mailchimp/MailchimpGate";
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
  useMailchimpContacts,
  useMailchimpContactMutations,
  type MemberOut,
} from "@/hooks/useMailchimpContacts";

const PAGE_SIZE = 25;

const STATUS_LABELS: Record<string, string> = {
  subscribed: "Inscrito",
  unsubscribed: "Desinscrito",
  cleaned: "Inválido",
  pending: "Pendente",
  transactional: "Transacional",
};

const STATUS_COLORS: Record<string, string> = {
  subscribed: "bg-green-100 text-green-800",
  unsubscribed: "bg-gray-100 text-gray-800",
  cleaned: "bg-red-100 text-red-800",
  pending: "bg-yellow-100 text-yellow-800",
  transactional: "bg-blue-100 text-blue-800",
};

interface ContactFormState {
  email: string;
  first_name: string;
  last_name: string;
  tags: string;
  status: string;
}

const emptyForm = (): ContactFormState => ({
  email: "",
  first_name: "",
  last_name: "",
  tags: "",
  status: "subscribed",
});

function ContactsContent() {
  const [statusFilter, setStatusFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const [modalOpen, setModalOpen] = useState(false);
  const [archiveTarget, setArchiveTarget] = useState<string | null>(null);
  const [form, setForm] = useState<ContactFormState>(emptyForm());
  const [editingEmail, setEditingEmail] = useState<string | null>(null);

  const { data, isLoading, isError, error } = useMailchimpContacts({
    status: statusFilter || undefined,
    count: PAGE_SIZE,
    offset,
  });

  const { upsert, archive } = useMailchimpContactMutations();

  function openCreate() {
    setForm(emptyForm());
    setEditingEmail(null);
    setModalOpen(true);
  }

  function openEdit(member: MemberOut) {
    setForm({
      email: member.email,
      first_name: member.first_name ?? "",
      last_name: member.last_name ?? "",
      tags: member.tags.join(", "),
      status: member.status,
    });
    setEditingEmail(member.email);
    setModalOpen(true);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const email = editingEmail ?? form.email.trim();
    const tagsArr = form.tags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);

    upsert.mutate(
      {
        email,
        body: {
          status: form.status,
          first_name: form.first_name || undefined,
          last_name: form.last_name || undefined,
          tags: tagsArr.length ? tagsArr : undefined,
        },
      },
      {
        onSuccess: () => {
          toast.success(editingEmail ? "Contato atualizado." : "Contato criado.");
          setModalOpen(false);
        },
        onError: () => toast.error("Erro ao salvar contato."),
      },
    );
  }

  function handleArchive() {
    if (!archiveTarget) return;
    archive.mutate(archiveTarget, {
      onSuccess: () => {
        toast.success("Contato arquivado.");
        setArchiveTarget(null);
      },
      onError: () => toast.error("Erro ao arquivar contato."),
    });
  }

  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Users className="h-6 w-6 text-muted-foreground" />
          <div>
            <h1 className="text-2xl font-semibold">Contatos</h1>
            <p className="text-sm text-muted-foreground">
              Membros da sua audiência Mailchimp
            </p>
          </div>
        </div>
        <Button onClick={openCreate} className="gap-2" data-testid="btn-novo-contato">
          <Plus className="h-4 w-4" />
          Novo contato
        </Button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <Label className="shrink-0 text-sm">Status:</Label>
        <Select
          value={statusFilter || "all"}
          onValueChange={(v) => {
            setStatusFilter(v === "all" ? "" : v);
            setOffset(0);
          }}
        >
          <SelectTrigger className="w-44" data-testid="status-filter">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos</SelectItem>
            <SelectItem value="subscribed">Inscritos</SelectItem>
            <SelectItem value="unsubscribed">Desinscritos</SelectItem>
            <SelectItem value="cleaned">Inválidos</SelectItem>
            <SelectItem value="pending">Pendentes</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="space-y-2" data-testid="contatos-loading">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
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
              {((error as Error)?.message ?? "").replace(/^\[\d+\]\s*/, "") || "Tente novamente."}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Empty */}
      {!isLoading && !isError && data?.items.length === 0 && (
        <Card data-testid="contatos-empty">
          <CardHeader>
            <CardTitle className="text-base">Nenhum contato encontrado</CardTitle>
            <CardDescription>
              {statusFilter
                ? "Nenhum contato com esse status. Tente outro filtro."
                : "Adicione seu primeiro contato clicando em Novo contato."}
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {/* Table */}
      {!isLoading && !isError && (data?.items.length ?? 0) > 0 && (
        <Card data-testid="contatos-table">
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-4 py-3 text-left font-medium">Email</th>
                    <th className="px-4 py-3 text-left font-medium">Nome</th>
                    <th className="px-4 py-3 text-left font-medium">Status</th>
                    <th className="px-4 py-3 text-left font-medium">Tags</th>
                    <th className="px-4 py-3 text-left font-medium">
                      Última alteração
                    </th>
                    <th className="px-4 py-3 text-right font-medium">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {data!.items.map((member) => (
                    <tr
                      key={member.email}
                      className="border-b last:border-0 hover:bg-muted/30"
                      data-testid={`contato-row-${member.email}`}
                    >
                      <td className="px-4 py-3 font-medium">{member.email}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {[member.first_name, member.last_name]
                          .filter(Boolean)
                          .join(" ") || "—"}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                            STATUS_COLORS[member.status] ??
                            "bg-gray-100 text-gray-800"
                          }`}
                        >
                          {STATUS_LABELS[member.status] ?? member.status}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
                          {member.tags.length > 0
                            ? member.tags.map((tag) => (
                                <Badge key={tag} variant="outline" className="text-xs">
                                  {tag}
                                </Badge>
                              ))
                            : <span className="text-muted-foreground">—</span>}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {format(
                          new Date(member.last_changed),
                          "dd/MM/yyyy",
                          { locale: ptBR },
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => openEdit(member)}
                            data-testid={`edit-contato-${member.email}`}
                          >
                            <Pencil className="h-4 w-4" />
                            <span className="sr-only">Editar</span>
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setArchiveTarget(member.email)}
                            data-testid={`archive-contato-${member.email}`}
                          >
                            <Archive className="h-4 w-4" />
                            <span className="sr-only">Arquivar</span>
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
                  {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} de {total}
                </p>
                <div className="flex gap-1">
                  <Button
                    variant="outline"
                    size="icon"
                    disabled={currentPage === 1}
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    disabled={currentPage >= totalPages}
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Upsert Modal */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent data-testid="contato-modal">
          <DialogHeader>
            <DialogTitle>
              {editingEmail ? "Editar contato" : "Novo contato"}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4 pt-2">
            <div className="space-y-1.5">
              <Label htmlFor="contact-email">Email *</Label>
              <Input
                id="contact-email"
                data-testid="contact-email-input"
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                disabled={!!editingEmail || upsert.isPending}
                required={!editingEmail}
                placeholder="contato@exemplo.com"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="contact-first-name">Nome</Label>
                <Input
                  id="contact-first-name"
                  data-testid="contact-first-name-input"
                  value={form.first_name}
                  onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                  disabled={upsert.isPending}
                  placeholder="João"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="contact-last-name">Sobrenome</Label>
                <Input
                  id="contact-last-name"
                  data-testid="contact-last-name-input"
                  value={form.last_name}
                  onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                  disabled={upsert.isPending}
                  placeholder="Silva"
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="contact-status">Status</Label>
              <Select
                value={form.status}
                onValueChange={(v) => setForm({ ...form, status: v })}
                disabled={upsert.isPending}
              >
                <SelectTrigger id="contact-status" data-testid="contact-status-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="subscribed">Inscrito</SelectItem>
                  <SelectItem value="unsubscribed">Desinscrito</SelectItem>
                  <SelectItem value="pending">Pendente</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="contact-tags">Tags (separadas por vírgula)</Label>
              <Input
                id="contact-tags"
                data-testid="contact-tags-input"
                value={form.tags}
                onChange={(e) => setForm({ ...form, tags: e.target.value })}
                disabled={upsert.isPending}
                placeholder="vip, newsletter, cliente"
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
                disabled={upsert.isPending || (!editingEmail && !form.email.trim())}
                data-testid="contact-modal-submit"
              >
                {upsert.isPending ? "Salvando..." : "Salvar"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Archive confirm */}
      <AlertDialog
        open={!!archiveTarget}
        onOpenChange={(open) => !open && setArchiveTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Arquivar contato?</AlertDialogTitle>
            <AlertDialogDescription>
              O contato <strong>{archiveTarget}</strong> será arquivado na
              audiência Mailchimp. Esta ação pode ser revertida pelo Mailchimp.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleArchive}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="confirm-archive-contato"
            >
              {archive.isPending ? "Arquivando..." : "Arquivar"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export default function Contatos() {
  return (
    <MailchimpGate>
      <ContactsContent />
    </MailchimpGate>
  );
}
