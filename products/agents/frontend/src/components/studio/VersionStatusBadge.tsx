import { Badge } from "@noctusai/lib/design-system";
import type { VersionStatus } from "@/api/studio/types";

const LABEL: Record<VersionStatus, string> = {
  rascunho: "Rascunho",
  ativa: "Ativa",
  substituida: "Substituída",
};

export function VersionStatusBadge({ status }: { status: VersionStatus }) {
  const variant = status === "ativa" ? "default" : status === "rascunho" ? "outline" : "muted";
  return (
    <Badge variant={variant} data-testid={`version-status-${status}`}>
      {LABEL[status]}
    </Badge>
  );
}
