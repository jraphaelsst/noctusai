/**
 * DeleteWorkflowDialog — irreversible-delete confirm
 * (DELETE /api/n8n/workflows/{id}), per the brief's "confirm first —
 * irreversible" requirement.
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
import type { N8nWorkflowOut } from "@/hooks/useN8nWorkflows";

export interface DeleteWorkflowDialogProps {
  workflow: N8nWorkflowOut | null;
  pending: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}

export function DeleteWorkflowDialog({
  workflow,
  pending,
  onOpenChange,
  onConfirm,
}: DeleteWorkflowDialogProps) {
  return (
    <AlertDialog open={!!workflow} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Excluir fluxo?</AlertDialogTitle>
          <AlertDialogDescription>
            "{workflow?.name}" será excluído permanentemente do n8n. Esta ação não pode ser
            desfeita.
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
          >
            {pending ? "Excluindo…" : "Excluir"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
