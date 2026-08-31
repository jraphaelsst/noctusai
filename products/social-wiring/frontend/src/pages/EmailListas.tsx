/**
 * EmailListas — Mailchimp static segment management ("Listas").
 *
 * Per the plan: "Listas" = static segments inside one Mailchimp audience.
 *
 * Features:
 *   - Table: Nome, Membros, Atualizada em
 *   - Create / rename / delete segment
 *   - "Membros" drawer: paginated member list, add-by-email (400 shows
 *     "crie em Contatos primeiro"), remove per row
 *
 * All states: loading / empty / error / success.
 * Wrapped in <MailchimpGate>.
 */
import { useState } from "react";
import {
  List,
  Plus,
  Pencil,
  Trash2,
  Users,
  UserPlus,
  UserMinus,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  X,
} from "lucide-react";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { toast } from "sonner";
import { MailchimpGate } from "@/components/mailchimp/MailchimpGate";
import { Button } from "@/components/ui/button";
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
  useMailchimpSegments,
  useMailchimpSegmentMembers,
  useMailchimpSegmentMutations,
  type SegmentOut,
} from "@/hooks/useMailchimpSegments";

const PAGE_SIZE = 25;

// ─── Member drawer ────────────────────────────────────────────────────────────

interface MembrosDrawerProps {
  segment: SegmentOut | null;
  onClose: () => void;
}

function MembrosDrawer({ segment, onClose }: MembrosDrawerProps) {
  const [memberOffset, setMemberOffset] = useState(0);
  const [addEmail, setAddEmail] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const { addMember, removeMember } = useMailchimpSegmentMutations();

  // `isPending`, not `isLoading` — v5's `isLoading` goes FALSE mid-refetch
  // and would unmount this member list on every background refresh.
  // → KB § PATTERNS/frontend/lying-loading-state.md
  const { data, isPending } = useMailchimpSegmentMembers(
    segment?.id ?? null,
    { count: PAGE_SIZE, offset: memberOffset },
  );

  function handleAddMember(e: React.FormEvent) {
    e.preventDefault();
    setAddError(null);
    addMember.mutate(
      { segmentId: segment!.id, email: addEmail.trim() },
      {
        onSuccess: () => {
          toast.success("Membro adicionado.");
          setAddEmail("");
        },
        onError: (err: unknown) => {
          // api client throws Error("[400] <message>") for non-2xx responses.
          // A 400 from Mailchimp means the contact doesn't exist in the audience.
          const msg = (err as Error)?.message ?? "";
          if (msg.startsWith("[400]") || msg.startsWith("[422]")) {
            setAddError(
              "Este email não está na audiência. Crie o contato em Contatos primeiro.",
            );
          } else {
            setAddError("Erro ao adicionar membro.");
          }
        },
      },
    );
  }

  function handleRemoveMember(email: string) {
    removeMember.mutate(
      { segmentId: segment!.id, email },
      {
        onSuccess: () => toast.success("Membro removido."),
        onError: () => toast.error("Erro ao remover membro."),
      },
    );
  }

  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(memberOffset / PAGE_SIZE) + 1;

  if (!segment) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      data-testid="membros-drawer"
    >
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
        aria-hidden
      />
      <div className="relative w-full max-w-md bg-background shadow-xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <div>
            <h2 className="text-lg font-semibold">Membros: {segment.name}</h2>
            <p className="text-sm text-muted-foreground">
              {segment.member_count} membro(s)
            </p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-5 w-5" />
            <span className="sr-only">Fechar</span>
          </Button>
        </div>

        {/* Add member form */}
        <div className="px-5 py-4 border-b bg-muted/30">
          <form onSubmit={handleAddMember} className="space-y-2">
            <Label htmlFor="add-member-email">Adicionar por email</Label>
            <div className="flex gap-2">
              <Input
                id="add-member-email"
                data-testid="add-member-email-input"
                type="email"
                placeholder="membro@exemplo.com"
                value={addEmail}
                onChange={(e) => {
                  setAddEmail(e.target.value);
                  setAddError(null);
                }}
                disabled={addMember.isPending}
              />
              <Button
                type="submit"
                size="icon"
                disabled={!addEmail.trim() || addMember.isPending}
                data-testid="add-member-submit"
              >
                <UserPlus className="h-4 w-4" />
              </Button>
            </div>
            {addError && (
              <p
                className="text-sm text-destructive flex items-center gap-1"
                data-testid="add-member-error"
              >
                <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                {addError}
              </p>
            )}
          </form>
        </div>

        {/* Member list */}
        <div className="flex-1 overflow-y-auto">
          {isPending ? (
            <div className="p-4 space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : data?.items.length === 0 ? (
            <div className="p-6 text-center text-sm text-muted-foreground">
              Nenhum membro nesta lista.
            </div>
          ) : (
            <ul className="divide-y">
              {data!.items.map((m) => (
                <li
                  key={m.email}
                  className="flex items-center justify-between px-5 py-3"
                  data-testid={`member-row-${m.email}`}
                >
                  <div>
                    <p className="text-sm font-medium">{m.email}</p>
                    <p className="text-xs text-muted-foreground">
                      {[m.first_name, m.last_name].filter(Boolean).join(" ") || "—"}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleRemoveMember(m.email)}
                    data-testid={`remove-member-${m.email}`}
                  >
                    <UserMinus className="h-4 w-4" />
                    <span className="sr-only">Remover</span>
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Pagination */}
        {total > PAGE_SIZE && (
          <div className="flex items-center justify-between px-5 py-3 border-t">
            <p className="text-sm text-muted-foreground">
              {memberOffset + 1}–{Math.min(memberOffset + PAGE_SIZE, total)} de {total}
            </p>
            <div className="flex gap-1">
              <Button
                variant="outline"
                size="icon"
                disabled={currentPage === 1}
                onClick={() =>
                  setMemberOffset(Math.max(0, memberOffset - PAGE_SIZE))
                }
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                disabled={currentPage >= totalPages}
                onClick={() => setMemberOffset(memberOffset + PAGE_SIZE)}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

function ListasContent() {
  const [offset, setOffset] = useState(0);
  const [modalOpen, setModalOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<SegmentOut | null>(null);
  const [membrosSegment, setMembrosSegment] = useState<SegmentOut | null>(null);
  const [formName, setFormName] = useState("");
  const [editingSegment, setEditingSegment] = useState<SegmentOut | null>(null);

  // `isPending`, not `isLoading` — the list is `placeholderData`-backed
  // (keepPreviousData) for pagination, so `isPending` only fires once,
  // on the very first load; paging never re-triggers this skeleton.
  // → KB § PATTERNS/frontend/lying-loading-state.md
  const { data, isPending, isError, error } = useMailchimpSegments({
    count: PAGE_SIZE,
    offset,
  });
  const { create, update, remove } = useMailchimpSegmentMutations();

  function openCreate() {
    setFormName("");
    setEditingSegment(null);
    setModalOpen(true);
  }

  function openEdit(seg: SegmentOut) {
    setFormName(seg.name);
    setEditingSegment(seg);
    setModalOpen(true);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (editingSegment) {
      update.mutate(
        { id: editingSegment.id, body: { name: formName.trim() } },
        {
          onSuccess: () => {
            toast.success("Lista renomeada.");
            setModalOpen(false);
          },
          onError: () => toast.error("Erro ao renomear lista."),
        },
      );
    } else {
      create.mutate(
        { name: formName.trim() },
        {
          onSuccess: () => {
            toast.success("Lista criada.");
            setModalOpen(false);
          },
          onError: () => toast.error("Erro ao criar lista."),
        },
      );
    }
  }

  function handleDelete() {
    if (!deleteTarget) return;
    remove.mutate(deleteTarget.id, {
      onSuccess: () => {
        toast.success("Lista removida.");
        setDeleteTarget(null);
      },
      onError: () => toast.error("Erro ao remover lista."),
    });
  }

  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <List className="h-6 w-6 text-muted-foreground" />
            <div>
              <h1 className="text-2xl font-semibold">Listas</h1>
              <p className="text-sm text-muted-foreground">
                Segmentos estáticos na sua audiência Mailchimp
              </p>
            </div>
          </div>
          <Button onClick={openCreate} className="gap-2" data-testid="btn-nova-lista">
            <Plus className="h-4 w-4" />
            Nova lista
          </Button>
        </div>

        {/* Loading */}
        {isPending && (
          <div className="space-y-2" data-testid="listas-loading">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        )}

        {/* Error */}
        {isError && (
          <Card className="border-destructive" data-testid="listas-error">
            <CardContent className="flex items-center gap-3 pt-6">
              <AlertCircle className="h-5 w-5 text-destructive" />
              <p className="text-sm text-destructive">
                Erro ao carregar listas:{" "}
                {(error as any)?.body?.detail?.message ?? "Tente novamente."}
              </p>
            </CardContent>
          </Card>
        )}

        {/* Empty */}
        {!isPending && !isError && data?.items.length === 0 && (
          <Card data-testid="listas-empty">
            <CardHeader>
              <CardTitle className="text-base">Nenhuma lista encontrada</CardTitle>
              <CardDescription>
                Crie sua primeira lista de segmentação clicando em Nova lista.
              </CardDescription>
            </CardHeader>
          </Card>
        )}

        {/* Table */}
        {!isPending && !isError && (data?.items.length ?? 0) > 0 && (
          <Card data-testid="listas-table">
            <CardContent className="p-0">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-4 py-3 text-left font-medium">Nome</th>
                    <th className="px-4 py-3 text-left font-medium">Membros</th>
                    <th className="px-4 py-3 text-left font-medium">Atualizada em</th>
                    <th className="px-4 py-3 text-right font-medium">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {data!.items.map((seg) => (
                    <tr
                      key={seg.id}
                      className="border-b last:border-0 hover:bg-muted/30"
                      data-testid={`lista-row-${seg.id}`}
                    >
                      <td className="px-4 py-3 font-medium">{seg.name}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {seg.member_count}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {format(new Date(seg.updated_at), "dd/MM/yyyy", {
                          locale: ptBR,
                        })}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="gap-1.5"
                            onClick={() => setMembrosSegment(seg)}
                            data-testid={`membros-btn-${seg.id}`}
                          >
                            <Users className="h-3.5 w-3.5" />
                            Membros
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => openEdit(seg)}
                            data-testid={`edit-lista-${seg.id}`}
                          >
                            <Pencil className="h-4 w-4" />
                            <span className="sr-only">Renomear</span>
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setDeleteTarget(seg)}
                            data-testid={`delete-lista-${seg.id}`}
                          >
                            <Trash2 className="h-4 w-4" />
                            <span className="sr-only">Excluir</span>
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {total > PAGE_SIZE && (
                <div className="flex items-center justify-between px-4 py-3 border-t">
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
      </div>

      {/* Create/rename modal */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent data-testid="lista-modal">
          <DialogHeader>
            <DialogTitle>
              {editingSegment ? "Renomear lista" : "Nova lista"}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4 pt-2">
            <div className="space-y-1.5">
              <Label htmlFor="lista-name">Nome da lista</Label>
              <Input
                id="lista-name"
                data-testid="lista-name-input"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                disabled={create.isPending || update.isPending}
                placeholder="ex: Clientes VIP"
                autoFocus
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setModalOpen(false)}>
                Cancelar
              </Button>
              <Button
                type="submit"
                disabled={
                  !formName.trim() || create.isPending || update.isPending
                }
                data-testid="lista-modal-submit"
              >
                {create.isPending || update.isPending ? "Salvando..." : "Salvar"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir lista?</AlertDialogTitle>
            <AlertDialogDescription>
              A lista <strong>{deleteTarget?.name}</strong> será removida. Os
              contatos permanecem na audiência.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="confirm-delete-lista"
            >
              {remove.isPending ? "Excluindo..." : "Excluir"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Members drawer */}
      {membrosSegment && (
        <MembrosDrawer
          segment={membrosSegment}
          onClose={() => setMembrosSegment(null)}
        />
      )}
    </>
  );
}

export default function EmailListas() {
  return (
    <MailchimpGate>
      <ListasContent />
    </MailchimpGate>
  );
}
