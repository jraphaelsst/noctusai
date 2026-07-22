/**
 * StatTileRow — the responsive KPI grid every dashboard subtab re-derives by
 * hand today (`grid-cols-1 sm:grid-cols-2 lg:grid-cols-4` is the established
 * layout across social-wiring/personal-finance/erp-imobiliario). Purely a
 * layout wrapper — `children` are typically `<StatTile/>`s, but this imposes
 * no such requirement.
 *
 *   <StatTileRow>
 *     <StatTile label="Total" value={summary.total} />
 *     <StatTile label="Novos" value={summary.novos} />
 *   </StatTileRow>
 */
import { cn } from "../../utils";
import type { StatTileRowProps } from "./types";

export function StatTileRow({ children, className }: StatTileRowProps) {
  return <div className={cn("grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4", className)}>{children}</div>;
}
