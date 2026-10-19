/** Crédito status chip — shared by the Crédito list and Conversas › Interações. */
import type { CreditoStatus } from "@/hooks/useJuliaCredito";

const META: Record<CreditoStatus, { label: string; cls: string }> = {
  pendente: { label: "Pendente", cls: "bg-amber-100 text-amber-800" },
  aprovado: { label: "Aprovado", cls: "bg-emerald-100 text-emerald-800" },
  reprovado: { label: "Reprovado", cls: "bg-red-100 text-red-800" },
  erro: { label: "Erro", cls: "bg-zinc-200 text-zinc-800" },
};

export function CreditoStatusChip({ status }: { status: string }) {
  const m = META[status as CreditoStatus] ?? { label: status, cls: "bg-muted" };
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${m.cls}`} data-testid="credito-chip">{m.label}</span>;
}
