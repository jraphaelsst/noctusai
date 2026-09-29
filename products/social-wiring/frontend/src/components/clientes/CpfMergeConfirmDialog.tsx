/**
 * CpfMergeConfirmDialog — confirm before unifying a CPF group
 * (`pessoa-mesma-cpf-multideal-CONTRACT.md` §1, brief 2026-09-28: "Use the
 * product's in-app confirm dialog (never window.confirm) and say plainly
 * what merge does").
 *
 * Sibling of `ExcluirClienteConfirmDialog`/`ArquivarAtendimentoConfirmDialog`
 * for the same focus-trap reason (rendered beside the card/queue, never
 * nested in another Dialog's content). Unlike those two, this one is not
 * itself destructive-styled (`bg-destructive`) — a merge here folds records
 * into one, it does not delete data outright (§0: `_repoint_cliente_scoped_
 * tables` moves every scoped row to the survivor; only the absorbed
 * `clientes` row itself goes away) — but it is still IRREVERSIBLE on this
 * axis (no `/merges/{id}/desfazer` sibling in the CPF contract, unlike the
 * identity axis's D3 undo), which is exactly why the copy below names the
 * survivor and spells out what happens to everyone else in the group.
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

export interface CpfMergeConfirmDialogProps {
  open: boolean;
  pending: boolean;
  /** The candidate that will survive — named explicitly so the operator
   *  confirms the RIGHT record keeps the history. */
  sobreviventeNome: string;
  /** How many OTHER candidates in the group will be absorbed and removed. */
  quantidadeAbsorvidos: number;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}

export function CpfMergeConfirmDialog({
  open,
  pending,
  sobreviventeNome,
  quantidadeAbsorvidos,
  onOpenChange,
  onConfirm,
}: CpfMergeConfirmDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Unificar como a mesma pessoa?</AlertDialogTitle>
          <AlertDialogDescription>
            <strong>{sobreviventeNome || "Este cadastro"}</strong> vai manter todas
            as negociações, documentos e dados de contato de{" "}
            {quantidadeAbsorvidos === 1
              ? "1 outro cadastro"
              : `${quantidadeAbsorvidos} outros cadastros`}{" "}
            com o mesmo CPF. Os demais cadastros do grupo serão excluídos
            permanentemente — esta ação não pode ser desfeita.
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
            data-testid="cpf-merge-confirm"
          >
            {pending ? "Unificando…" : "Unificar"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
