/**
 * ExcluirClienteConfirmDialog — confirm before the IRREVERSIBLE hard delete
 * of a cliente (owner directive, 2026-09-24 — admin/owner only, enforced
 * server-side by `clientes_router.excluir_cliente_route`). Names the
 * client and states the action is permanent, per the brief. Sibling of
 * `ClienteCardDialog`'s own Dialog for the same focus-trap reason
 * `ArquivarAtendimentoConfirmDialog` is; the destructive-red
 * `AlertDialogAction` styling matches this product's other hard-delete
 * confirm (`pages/leads/BaseDeLeads.tsx`).
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

export interface ExcluirClienteConfirmDialogProps {
  open: boolean;
  pending: boolean;
  /** The client's name — the confirmation must name who is being deleted. */
  nome: string;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}

export function ExcluirClienteConfirmDialog({
  open,
  pending,
  nome,
  onOpenChange,
  onConfirm,
}: ExcluirClienteConfirmDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Excluir cliente?</AlertDialogTitle>
          <AlertDialogDescription>
            O cadastro de <strong>{nome || "este cliente"}</strong> e todos os
            seus dados — documentos, notas, checklists e cards no funil —
            serão excluídos permanentemente. Esta ação não pode ser desfeita.
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
            data-testid="excluir-cliente-confirm"
          >
            {pending ? "Excluindo…" : "Excluir"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
