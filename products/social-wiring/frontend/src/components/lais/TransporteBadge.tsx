/** Page-header badge shown while the connection is not on the Meta Cloud API (contract §14). */
import { Badge } from "@/components/ui/badge";
import { TRANSPORTE_BADGE, TRANSPORTE_EXPLICACAO, envioLiberado, type Transporte } from "@/hooks/useLaisTransporte";

export function TransporteBadge({ transporte }: { transporte: Transporte | undefined }) {
  if (envioLiberado(transporte)) return null;
  return (
    <Badge variant="outline" title={TRANSPORTE_EXPLICACAO} data-testid="transporte-badge">
      {TRANSPORTE_BADGE}
    </Badge>
  );
}
