/**
 * EmailTemplates — Mailchimp template management.
 *
 * Shows a card grid with:
 *   - preview_image thumbnail
 *   - name, edited date, drag-and-drop badge
 *   - "Editar no Mailchimp" external link (edit_url, target="_blank")
 *   - Rename / Delete actions
 *   - "Novo template" modal: { name, html }
 *
 * All states: loading / empty / error / success.
 * Wrapped in <MailchimpGate>.
 */
import { useState } from "react";
import {
  FileText,
  Plus,
  ExternalLink,
  Pencil,
  Trash2,
  AlertCircle,
  ChevronLeft,
  ChevronRight,
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
import { Textarea } from "@/components/ui/textarea";
import {
  useMailchimpTemplates,
  useMailchimpTemplateMutations,
  type TemplateOut,
} from "@/hooks/useMailchimpTemplates";

const PAGE_SIZE = 24; // 3-col grid × 8 rows

function TemplatesContent() {
  const [offset, setOffset] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<TemplateOut | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<TemplateOut | null>(null);
  const [createForm, setCreateForm] = useState({ name: "", html: "" });
  const [renameValue, setRenameValue] = useState("");

  const { data, isPending, isFetching, isError, error } = useMailchimpTemplates({
    count: PAGE_SIZE,
    offset,
  });
  const { create, update, remove } = useMailchimpTemplateMutations();
  // Skeleton ONLY when there is nothing to show — the seed idiom
  // (PipelineBoard / PipelineStagesManager). Bare `isLoading` is false
  // between retries and while a query is paused, which rendered a blank
  // page on a failed fetch (mailchimp templates 500, 2026-09-01).
  const showSkeleton = isPending || (isFetching && (data?.items.length ?? 0) === 0);
  function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    create.mutate(
      { name: createForm.name.trim(), html: createForm.html },
      {
        onSuccess: () => {
          toast.success("Template criado.");
          setCreateOpen(false);
          setCreateForm({ name: "", html: "" });
        },
        onError: (err: unknown) => {
          const msg =
            (err as any)?.body?.detail?.message ??
            "Erro ao criar template.";
          toast.error(msg);
        },
      },
    );
  }

  function handleRename(e: React.FormEvent) {
    e.preventDefault();
    if (!renameTarget) return;
    update.mutate(
      { id: renameTarget.id, body: { name: renameValue.trim() } },
      {
        onSuccess: () => {
          toast.success("Template renomeado.");
          setRenameTarget(null);
        },
        onError: () => toast.error("Erro ao renomear template."),
      },
    );
  }

  function handleDelete() {
    if (!deleteTarget) return;
    remove.mutate(deleteTarget.id, {
      onSuccess: () => {
        toast.success("Template removido.");
        setDeleteTarget(null);
      },
      onError: () => toast.error("Erro ao remover template."),
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
          <FileText className="h-6 w-6 text-muted-foreground" />
          <div>
            <h1 className="text-2xl font-semibold">Templates</h1>
            <p className="text-sm text-muted-foreground">
              Templates de email da sua conta Mailchimp
            </p>
          </div>
        </div>
        <Button
          onClick={() => setCreateOpen(true)}
          className="gap-2"
          data-testid="btn-novo-template"
        >
          <Plus className="h-4 w-4" />
          Novo template
        </Button>
      </div>

      {/* Loading */}
      {showSkeleton && (
        <div
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
          data-testid="templates-loading"
        >
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-48 w-full" />
          ))}
        </div>
      )}

      {/* Error */}
      {isError && (
        <Card className="border-destructive" data-testid="templates-error">
          <CardContent className="flex items-center gap-3 pt-6">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <p className="text-sm text-destructive">
              Erro ao carregar templates:{" "}
              {(error as any)?.body?.detail?.message ?? "Tente novamente."}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Empty */}
      {!showSkeleton && !isError && (data?.items.length ?? 0) === 0 && (
        <Card data-testid="templates-empty">
          <CardHeader>
            <CardTitle className="text-base">Nenhum template encontrado</CardTitle>
            <CardDescription>
              Crie seu primeiro template HTML ou acesse o editor visual do
              Mailchimp.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {/* Card grid */}
      {!showSkeleton && !isError && (data?.items.length ?? 0) > 0 && (
        <>
          <div
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
            data-testid="templates-grid"
          >
            {data!.items.map((tmpl) => (
              <Card
                key={tmpl.id}
                className="overflow-hidden"
                data-testid={`template-card-${tmpl.id}`}
              >
                {/* Thumbnail */}
                <div className="h-36 bg-muted flex items-center justify-center overflow-hidden">
                  {tmpl.preview_image ? (
                    <img
                      src={tmpl.preview_image}
                      alt={`Preview de ${tmpl.name}`}
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <FileText className="h-10 w-10 text-muted-foreground/50" />
                  )}
                </div>

                <CardContent className="p-3 space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium leading-tight line-clamp-2">
                      {tmpl.name}
                    </p>
                    {tmpl.drag_and_drop && (
                      <Badge variant="outline" className="shrink-0 text-xs">
                        Drag & Drop
                      </Badge>
                    )}
                  </div>

                  <p className="text-xs text-muted-foreground">
                    Editado em{" "}
                    {format(new Date(tmpl.date_edited), "dd/MM/yyyy", {
                      locale: ptBR,
                    })}
                  </p>

                  <div className="flex items-center gap-1 pt-1">
                    {tmpl.edit_url && (
                      <Button
                        asChild
                        variant="outline"
                        size="sm"
                        className="flex-1 gap-1.5 text-xs"
                        data-testid={`edit-mailchimp-${tmpl.id}`}
                      >
                        <a
                          href={tmpl.edit_url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                          Editar no Mailchimp
                        </a>
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => {
                        setRenameValue(tmpl.name);
                        setRenameTarget(tmpl);
                      }}
                      data-testid={`rename-template-${tmpl.id}`}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                      <span className="sr-only">Renomear</span>
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setDeleteTarget(tmpl)}
                      data-testid={`delete-template-${tmpl.id}`}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      <span className="sr-only">Excluir</span>
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Pagination */}
          {total > PAGE_SIZE && (
            <div className="flex items-center justify-between">
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
        </>
      )}

      {/* Create modal */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-lg" data-testid="create-template-modal">
          <DialogHeader>
            <DialogTitle>Novo template HTML</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreate} className="space-y-4 pt-2">
            <div className="space-y-1.5">
              <Label htmlFor="template-name">Nome do template</Label>
              <Input
                id="template-name"
                data-testid="template-name-input"
                value={createForm.name}
                onChange={(e) =>
                  setCreateForm({ ...createForm, name: e.target.value })
                }
                disabled={create.isPending}
                placeholder="Newsletter Junho"
                autoFocus
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="template-html">HTML</Label>
              <Textarea
                id="template-html"
                data-testid="template-html-input"
                value={createForm.html}
                onChange={(e) =>
                  setCreateForm({ ...createForm, html: e.target.value })
                }
                disabled={create.isPending}
                placeholder="<!DOCTYPE html>..."
                rows={8}
                className="font-mono text-xs"
              />
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setCreateOpen(false)}
              >
                Cancelar
              </Button>
              <Button
                type="submit"
                disabled={
                  !createForm.name.trim() ||
                  !createForm.html.trim() ||
                  create.isPending
                }
                data-testid="create-template-submit"
              >
                {create.isPending ? "Criando..." : "Criar"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Rename modal */}
      <Dialog
        open={!!renameTarget}
        onOpenChange={(open) => !open && setRenameTarget(null)}
      >
        <DialogContent data-testid="rename-template-modal">
          <DialogHeader>
            <DialogTitle>Renomear template</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleRename} className="space-y-4 pt-2">
            <div className="space-y-1.5">
              <Label htmlFor="rename-template-name">Nome</Label>
              <Input
                id="rename-template-name"
                data-testid="rename-template-input"
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                disabled={update.isPending}
                autoFocus
              />
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setRenameTarget(null)}
              >
                Cancelar
              </Button>
              <Button
                type="submit"
                disabled={!renameValue.trim() || update.isPending}
                data-testid="rename-template-submit"
              >
                {update.isPending ? "Salvando..." : "Salvar"}
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
            <AlertDialogTitle>Excluir template?</AlertDialogTitle>
            <AlertDialogDescription>
              O template <strong>{deleteTarget?.name}</strong> será removido
              permanentemente da sua conta Mailchimp.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="confirm-delete-template"
            >
              {remove.isPending ? "Excluindo..." : "Excluir"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export default function EmailTemplates() {
  return (
    <MailchimpGate>
      <TemplatesContent />
    </MailchimpGate>
  );
}
