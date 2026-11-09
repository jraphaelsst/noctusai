/**
 * ReabrirRoteiroDialog — the confirmation before "Reabrir como rascunho"
 * (roteiro-ciclo CONTRACT §5; mockup state "Confirmar Reabrir").
 *
 * An alert dialog (Radix: focus moves in, is trapped, and returns to the
 * trigger). It warns that a PDF already downloaded is out of date — the PDF
 * disappears from the roteiro until it is generated again.
 *
 * Presentational: the caller owns the mutation and the error toast.
 */
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";

export interface ReabrirRoteiroDialogProps {
  open: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  /** `Roteiro.gerado_por_nome` — named in the warning; null ⇒ the generic sentence. */
  geradoPorNome?: string | null;
}

export function ReabrirRoteiroDialog({ open, onCancel, onConfirm, geradoPorNome }: ReabrirRoteiroDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={(aberto) => !aberto && onCancel()}>
      <AlertDialogContent data-testid="roteiro-confirmar-reabrir">
        <AlertDialogHeader>
          <AlertDialogTitle>Reabrir este roteiro como rascunho?</AlertDialogTitle>
          <AlertDialogDescription>
            A lista volta a aceitar imóveis novos e remoções. {geradoPorNome
              ? `${geradoPorNome}, que gerou o roteiro, será avisado(a).`
              : "Quem gerou o roteiro será avisado."}{" "}
            O PDF já baixado fica desatualizado.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <Button variant="outline" onClick={onCancel} data-testid="roteiro-reabrir-manter">
            Manter gerado
          </Button>
          <Button onClick={onConfirm} data-testid="roteiro-confirmar-reabrir-ok">
            Reabrir como rascunho
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
