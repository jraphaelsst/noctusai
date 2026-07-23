/**
 * ExecutionsDialog — GET /api/n8n/workflows/{id}/executions, on-demand
 * (the query only fires while this dialog is open, via
 * `useWorkflowExecutions`'s own `enabled` gate on a non-null workflowId).
 */
import { AlertCircle, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useWorkflowExecutions } from "@/hooks/useN8nWorkflows";

export interface ExecutionsDialogProps {
  workflowId: string | null;
  workflowName: string | null;
  onOpenChange: (open: boolean) => void;
}

function statusVariant(status: string | null): "default" | "secondary" | "destructive" | "outline" {
  if (!status) return "outline";
  const s = status.toLowerCase();
  if (s === "success") return "default";
  if (s === "error" || s === "failed" || s === "crashed") return "destructive";
  if (s === "running" || s === "waiting" || s === "new") return "secondary";
  return "outline";
}

export function ExecutionsDialog({ workflowId, workflowName, onOpenChange }: ExecutionsDialogProps) {
  const { data, isLoading, isError } = useWorkflowExecutions(workflowId);

  return (
    <Dialog open={!!workflowId} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Execuções — {workflowName}</DialogTitle>
        </DialogHeader>

        {isLoading && (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Carregando execuções…
          </div>
        )}

        {!isLoading && isError && (
          <div className="flex flex-col items-center gap-2 py-8 text-sm text-destructive">
            <AlertCircle className="h-6 w-6" />
            Falha ao carregar execuções.
          </div>
        )}

        {!isLoading && !isError && (data?.executions.length ?? 0) === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            Nenhuma execução registrada para este fluxo.
          </p>
        )}

        {!isLoading && !isError && (data?.executions.length ?? 0) > 0 && (
          <div className="max-h-96 space-y-2 overflow-y-auto">
            {data!.executions.map((exec) => (
              <div
                key={exec.id}
                className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
              >
                <div>
                  <p className="font-medium">#{exec.id}</p>
                  <p className="text-xs text-muted-foreground">
                    {exec.started_at ? new Date(exec.started_at).toLocaleString("pt-BR") : "—"}
                    {exec.mode ? ` · ${exec.mode}` : ""}
                  </p>
                </div>
                <Badge variant={statusVariant(exec.status)}>{exec.status ?? "desconhecido"}</Badge>
              </div>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
