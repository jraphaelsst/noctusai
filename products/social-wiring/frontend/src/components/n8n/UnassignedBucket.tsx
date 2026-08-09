/**
 * UnassignedBucket — the "Sem marca" droppable list of `scope=unassigned`
 * workflows. Dragging one of these into the client's tree (root or any
 * folder) is the ONLY way a workflow enters a client (the assign mutation
 * applies the client's n8n tag) — the live n8n instance carries zero tags
 * today, so this bucket is where every workflow starts out.
 */
import { useDroppable } from "@dnd-kit/core";
import { Inbox } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { WorkflowCard } from "@/components/n8n/WorkflowCard";
import type { N8nWorkflowOut } from "@/hooks/useN8nWorkflows";

export interface UnassignedBucketProps {
  workflows: N8nWorkflowOut[];
  loading: boolean;
  error: string | null;
  onToggleActive: (workflow: N8nWorkflowOut, active: boolean) => void;
  onRun: (workflow: N8nWorkflowOut) => void;
  onOpenExecutions: (workflow: N8nWorkflowOut) => void;
  onRename: (workflow: N8nWorkflowOut) => void;
  onDelete: (workflow: N8nWorkflowOut) => void;
  runPendingId?: string | null;
  togglePendingId?: string | null;
}

export function UnassignedBucket({
  workflows,
  loading,
  error,
  onToggleActive,
  onRun,
  onOpenExecutions,
  onRename,
  onDelete,
  runPendingId,
  togglePendingId,
}: UnassignedBucketProps) {
  const { setNodeRef, isOver } = useDroppable({ id: "unassigned" });

  return (
    <Card className={isOver ? "border-primary bg-primary/5" : undefined}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <Inbox className="h-4 w-4" />
          Sem marca
        </CardTitle>
      </CardHeader>
      <CardContent ref={setNodeRef} className="min-h-[6rem] space-y-2" data-testid="n8n-unassigned-bucket">
        {loading && <p className="text-xs text-muted-foreground">Carregando…</p>}
        {!loading && error && <p className="text-xs text-destructive">{error}</p>}
        {!loading && !error && workflows.length === 0 && (
          <p className="text-xs text-muted-foreground">
            Nenhum fluxo sem marca. Arraste um fluxo daqui da marca para desatribuí-lo.
          </p>
        )}
        {!loading &&
          !error &&
          workflows.map((workflow) => (
            <WorkflowCard
              key={workflow.id}
              workflow={workflow}
              onToggleActive={onToggleActive}
              onRun={onRun}
              onOpenExecutions={onOpenExecutions}
              onRename={onRename}
              onDelete={onDelete}
              runPending={runPendingId === workflow.id}
              togglePending={togglePendingId === workflow.id}
            />
          ))}
      </CardContent>
    </Card>
  );
}
