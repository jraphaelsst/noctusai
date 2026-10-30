/** Crédito status chip — shared by the Crédito list and Conversas › Interações. */
import type { CreditoStatus } from "@/hooks/useJuliaCredito";

const META: Record<CreditoStatus, { label: string; cls: string }> = {
  pendente: { label: "Pendente", cls: "bg-warning-light text-warning-foreground" },
  aprovado: { label: "Aprovado", cls: "bg-success-light text-success" },
  reprovado: { label: "Reprovado", cls: "bg-danger-light text-destructive" },
  erro: { label: "Erro", cls: "bg-muted text-foreground" },
};

export function CreditoStatusChip({ status }: { status: string }) {
  const m = META[status as CreditoStatus] ?? { label: status, cls: "bg-muted" };
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${m.cls}`} data-testid="credito-chip">{m.label}</span>;
}
