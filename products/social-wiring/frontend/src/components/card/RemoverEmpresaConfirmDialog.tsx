/**
 * RemoverEmpresaConfirmDialog — confirm before unlinking (and, when this
 * was the last participação, hard-deleting) an empresa from this card
 * (slice D — admin/owner only, enforced server-side by `card_hub.router
 * .delete_empresa_route`). Sibling of `ExcluirClienteConfirmDialog` — same
 * destructive-red `AlertDialogAction` styling, same "name what you're
 * deleting" posture.
 */
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

export interface RemoverEmpresaConfirmDialogProps {
  open: boolean;
  pending: boolean;
  /** The empresa's display name — the confirmation must name which one. */
  nome: string;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}

export function RemoverEmpresaConfirmDialog({
  open,
  pending,
  nome,
  onOpenChange,
  onConfirm,
}: RemoverEmpresaConfirmDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Remover empresa?</AlertDialogTitle>
          <AlertDialogDescription>
            O vínculo com <strong>{nome || "esta empresa"}</strong> será removido
            deste atendimento. Se nenhum outro cliente estiver vinculado a ela, o
            cadastro da empresa, seus documentos (Cartão CNPJ), seus dados e suas
            certidões serão excluídos permanentemente. Esta ação não pode ser
            desfeita. Se outro atendimento ainda usar esta empresa, apenas o
            vínculo com este cliente é removido — a empresa e suas certidões
            continuam disponíveis para o outro atendimento.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>Cancelar</AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault();
              onConfirm();
            }}
            disabled={pending}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            data-testid="remover-empresa-confirm"
          >
            {pending ? "Removendo…" : "Remover"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
