/**
 * RestaurarClienteConfirmDialog — confirm before bringing a deleted cliente
 * back. The person is REBUILT from their lead sources; anything that lived
 * only on the deleted record is gone for good, and the dialog says so.
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

export interface RestaurarClienteConfirmDialogProps {
  open: boolean;
  pending: boolean;
  nome: string;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}

export function RestaurarClienteConfirmDialog({
  open,
  pending,
  nome,
  onOpenChange,
  onConfirm,
}: RestaurarClienteConfirmDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Restaurar cliente?</AlertDialogTitle>
          <AlertDialogDescription>
            <strong>{nome || "Esta pessoa"}</strong> será reconstruída a partir
            dos leads de origem. CPF, documentos, notas e tudo o mais que foi
            excluído junto com o cadastro <strong>não serão recuperados</strong>.
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
            data-testid="restaurar-cliente-confirm"
          >
            {pending ? "Restaurando…" : "Restaurar"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
