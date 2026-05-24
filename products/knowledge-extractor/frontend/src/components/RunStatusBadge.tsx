/**
 * RunStatusBadge — maps a run's status to a colored badge.
 *
 * Shared by the Dashboard "recent runs" list and the Runs page table so
 * the status vocabulary (running / done / error) renders identically.
 */
import { Badge } from "@/components/ui/badge";
import type { RunStatus } from "@/lib/api";

const STATUS_META: Record<
  RunStatus,
  { label: string; variant: "default" | "secondary" | "destructive" | "outline" }
> = {
  running: { label: "Em execução", variant: "secondary" },
  done: { label: "Concluído", variant: "default" },
  error: { label: "Erro", variant: "destructive" },
};

export function RunStatusBadge({ status }: { status: RunStatus }) {
  const meta = STATUS_META[status] ?? { label: status, variant: "outline" as const };
  return <Badge variant={meta.variant}>{meta.label}</Badge>;
}
