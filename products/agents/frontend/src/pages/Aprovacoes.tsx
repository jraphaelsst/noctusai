/**
 * Aprovações page — contract §E.2 (`GET /api/approvals?estado=pendente`,
 * `POST /api/approvals/{id}/decision`), `/aprovacoes`.
 *
 * Standalone approvals inbox — every pending `escrita` tool call across the
 * caller's own conversations (admins see every conversation in the org,
 * server-enforced). Shows `resumo` + the antes → depois diff + Aprovar/Negar,
 * independent of having the originating chat open.
 */
import { useState } from "react";
import { CheckCircle2, ChevronDown, ChevronUp, ShieldAlert, XCircle } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button } from "@noctusai/lib/design-system";
import { useApprovals, useDecideApproval, type Approval } from "@/hooks/useApprovals";
import { errorMessage } from "@/lib/errors";

function ApprovalRow({ approval }: { approval: Approval }) {
  const { decide, isPending } = useDecideApproval();
  const [diffOpen, setDiffOpen] = useState(false);

  async function handleDecide(aprovada: boolean) {
    try {
      await decide(approval.id, aprovada);
      toast.success(aprovada ? "Aprovação concedida." : "Aprovação negada.");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <div
      className="space-y-2 rounded-lg border border-border bg-card p-4"
      data-testid={`approval-row-${approval.id}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-foreground">{approval.tool_name}</p>
          <p className="text-sm text-muted-foreground">{approval.resumo}</p>
        </div>
        <Badge variant="muted">Pendente</Badge>
      </div>

      {approval.diff && (
        <div>
          <button
            type="button"
            onClick={() => setDiffOpen((v) => !v)}
            className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
            data-testid={`approval-diff-toggle-${approval.id}`}
          >
            {diffOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            {diffOpen ? "Ocultar diff" : "Ver diff"}
          </button>
          {diffOpen && (
            <div className="mt-1.5 space-y-1 rounded-md bg-muted p-2.5 font-mono text-xs">
              <p className="whitespace-pre-wrap text-destructive">
                <span className="font-semibold">- Antes: </span>
                {approval.diff.antes ?? "(vazio)"}
              </p>
              <p className="whitespace-pre-wrap text-primary">
                <span className="font-semibold">+ Depois: </span>
                {approval.diff.depois}
              </p>
            </div>
          )}
        </div>
      )}

      <div className="flex items-center gap-2 pt-1">
        <Button
          variant="primary"
          size="sm"
          onClick={() => handleDecide(true)}
          disabled={isPending}
          data-testid={`approval-aprovar-${approval.id}`}
        >
          <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
          Aprovar
        </Button>
        <Button
          variant="destructive"
          size="sm"
          onClick={() => handleDecide(false)}
          disabled={isPending}
          data-testid={`approval-negar-${approval.id}`}
        >
          <XCircle className="mr-1.5 h-3.5 w-3.5" />
          Negar
        </Button>
      </div>
    </div>
  );
}

export default function Aprovacoes() {
  const { data: approvals, showSkeleton, isError } = useApprovals();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Aprovações</h1>
        <p className="text-sm text-muted-foreground">
          Ações de escrita da Julia aguardando sua aprovação.
        </p>
      </div>

      {showSkeleton ? (
        <div className="space-y-3" data-testid="approvals-skeleton">
          {[1, 2].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-lg border border-border bg-muted/50" />
          ))}
        </div>
      ) : isError ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card p-8 text-muted-foreground">
          <ShieldAlert className="h-6 w-6" />
          <p className="text-sm">Erro ao carregar aprovações.</p>
        </div>
      ) : !approvals || approvals.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card p-8 text-muted-foreground">
          <CheckCircle2 className="h-6 w-6 opacity-30" />
          <p className="text-sm">Nenhuma aprovação pendente.</p>
        </div>
      ) : (
        <div className="space-y-3" data-testid="approvals-list">
          {approvals.map((approval) => (
            <ApprovalRow key={approval.id} approval={approval} />
          ))}
        </div>
      )}
    </div>
  );
}
