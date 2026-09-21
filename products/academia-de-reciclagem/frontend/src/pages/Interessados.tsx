/**
 * Interessados — `/interessados` (internal, admin). Lists the public popup's
 * signups (`projects/interessados-CONTRACT.md`) with delete + confirm,
 * mirroring `Equipe.tsx`'s "confirm before delete" pattern but built on
 * TanStack Query like `Decisoes.tsx` / `Kb.tsx`.
 *
 * No-lying-loading-state: `showSkeleton = isPending && !data`, never
 * `isLoading`; `isRefreshing` is a text-only suffix, never an early return.
 */
import { useState } from "react";
import { Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge, Button, Dialog, DialogBody, DialogFooter, DialogHeader, PageSkeleton } from "@noctusai/lib/design-system";
import { Card, EmptyState, ErrorState } from "@/components/FormControls";
import { errorMessage } from "@/lib/errors";
import { useDeleteInteressado, useInteressadosList, type Interessado } from "@/hooks/useInteressados";

export default function Interessados() {
  const { data, isPending, isFetching, error } = useInteressadosList();
  const showSkeleton = isPending && !data;
  const isRefreshing = isFetching && !!data;
  const [confirmDelete, setConfirmDelete] = useState<Interessado | null>(null);
  const deleteInteressado = useDeleteInteressado();

  function handleConfirmDelete() {
    if (!confirmDelete) return;
    deleteInteressado.mutate(confirmDelete.id, {
      onSuccess: () => {
        toast.success("Interessado removido.");
        setConfirmDelete(null);
      },
      onError: (err) => toast.error(errorMessage(err)),
    });
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Interessados</h1>
        <p className="text-sm text-muted-foreground">
          Cadastros do popup público "Gostaria de receber futuras comunicações?".
          {/* lying-loading-ok: text-only suffix, never unmounts real content */}
          {isRefreshing ? " Atualizando…" : ""}
        </p>
      </div>

      {showSkeleton ? (
        <PageSkeleton />
      ) : error ? (
        <ErrorState message={errorMessage(error)} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState message="Nenhum interessado cadastrado ainda." />
      ) : (
        <div className="space-y-2">
          {data.items.map((item) => (
            <Card key={item.id} className="flex items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-foreground">{item.nome}</span>
                  {item.origem ? <Badge variant="outline">{item.origem}</Badge> : null}
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  {item.email} · {item.whatsapp}
                </p>
              </div>
              <Button
                variant="destructive"
                size="icon"
                onClick={() => setConfirmDelete(item)}
                aria-label={`Remover ${item.nome}`}
                data-testid={`button-delete-${item.id}`}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </Card>
          ))}
        </div>
      )}

      {confirmDelete ? (
        <Dialog open onClose={() => setConfirmDelete(null)} title="Remover interessado" className="max-w-md">
          <DialogHeader>
            <h2 className="text-lg font-semibold text-foreground">Remover interessado</h2>
          </DialogHeader>
          <DialogBody>
            <p className="text-sm text-muted-foreground">
              Tem certeza que deseja remover <strong className="text-foreground">{confirmDelete.nome}</strong>? Esta
              ação não pode ser desfeita.
            </p>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(null)} disabled={deleteInteressado.isPending}>
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleConfirmDelete}
              disabled={deleteInteressado.isPending}
              data-testid="button-confirm-delete"
            >
              {deleteInteressado.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Remover
            </Button>
          </DialogFooter>
        </Dialog>
      ) : null}
    </div>
  );
}
