/**
 * ArquivarAtendimentoConfirmDialog — confirm before archiving a funil card
 * (`atendimentos.arquivado=true`). Sibling of `ClienteCardDialog`'s own
 * Dialog (never nested inside it — a nested Dialog fights the outer one's
 * focus trap and scroll lock, the same reason `AdicionarCompradorDialog` /
 * `CriarRoteiroDialog` / `NovoContratoDialog` are siblings mounted by
 * `ClienteDetailModal`). Shape mirrors `components/n8n/DeleteWorkflowDialog
 * .tsx` — plain shadcn `AlertDialog`, no data-fetching of its own.
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

export interface ArquivarAtendimentoConfirmDialogProps {
  open: boolean;
  pending: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}

export function ArquivarAtendimentoConfirmDialog({
  open,
  pending,
  onOpenChange,
  onConfirm,
}: ArquivarAtendimentoConfirmDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Arquivar este card no funil?</AlertDialogTitle>
          <AlertDialogDescription>
            O card sai do quadro do Funil de Vendas. O cadastro do cliente
            continua ativo e pode ser localizado normalmente a qualquer
            momento.
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
            data-testid="arquivar-atendimento-confirm"
          >
            {pending ? "Arquivando…" : "Arquivar"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
