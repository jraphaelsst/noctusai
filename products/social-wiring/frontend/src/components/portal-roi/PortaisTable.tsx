/**
 * PortaisTable — the 24-portal ROI table, PROJECT.md §3.5's non-negotiable
 * rendering rules made concrete:
 *   · `investimento`/`cpl`/`roi`/`taxa_conversao` render "—" (tooltip "Não
 *     informado") for `null`, NEVER a currency/percent zero.
 *   · A portal with leads and no recorded spend gets a VISIBLE "Registrar
 *     investimento" primary affordance on its own row — the page's main
 *     call to action on day one (23 of 24 rows).
 * "Empty" (no `lead_sources` at all) is handled one level up by the page —
 * this component always renders a full table for whatever rows it's given.
 */
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import {
  formatCount,
  formatMoneyOrNaoInformado,
  formatMultipleOrNaoInformado,
  formatPercentOrNaoInformado,
  type PortalRoiCategoria,
  type PortalRoiPortal,
} from "@/hooks/usePortalRoi";

const CATEGORIA_LABEL: Record<PortalRoiCategoria, string> = {
  portal: "Portal",
  social: "Social",
  direto: "Direto",
  outro: "Outro",
};

/** Renders a formatted value, or a muted "—" with a "Não informado" native
 * tooltip (`title`) when the underlying value is `null` (never recorded).
 * A native `title` — not the Radix `Tooltip` organ — deliberately: this
 * table can render standalone (tests, future non-shell contexts) without
 * an ancestor `TooltipProvider`, and §3.5 only requires "a tooltip", not a
 * specific implementation. */
function InformedOrDash({
  value,
  formatted,
}: {
  value: number | null;
  formatted: string;
}) {
  if (value !== null) return <span>{formatted}</span>;
  return (
    <span
      className="cursor-default text-muted-foreground"
      title="Não informado"
      data-testid="nao-informado"
    >
      {formatted}
    </span>
  );
}

export interface PortaisTableProps {
  portais: PortalRoiPortal[];
  onManage: (origemId: string, origemLabel: string) => void;
}

export function PortaisTable({ portais, onManage }: PortaisTableProps) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th className="px-4 py-2 font-medium">Portal</th>
            <th className="px-4 py-2 font-medium">Categoria</th>
            <th className="px-4 py-2 font-medium">Leads</th>
            <th className="px-4 py-2 font-medium">Vendas</th>
            <th className="px-4 py-2 font-medium">Valor vendas</th>
            <th className="px-4 py-2 font-medium">Investimento</th>
            <th className="px-4 py-2 font-medium">CPL</th>
            <th className="px-4 py-2 font-medium">ROI</th>
            <th className="px-4 py-2 font-medium">Conversão</th>
            <th className="px-4 py-2 font-medium" />
          </tr>
        </thead>
        <tbody>
          {portais.map((p) => {
            const semInvestimento = p.investimento === null;
            return (
              <tr key={p.origem_id} className="border-b last:border-0" data-testid="portal-row">
                <td className="px-4 py-3 font-medium">{p.label}</td>
                <td className="px-4 py-3">
                  <Badge variant="secondary">{CATEGORIA_LABEL[p.categoria] ?? p.categoria}</Badge>
                </td>
                <td className="px-4 py-3 tabular-nums">{formatCount(p.total_leads)}</td>
                <td className="px-4 py-3 tabular-nums">{formatCount(p.total_vendas)}</td>
                <td className="px-4 py-3 tabular-nums">
                  {formatMoneyOrNaoInformado(p.valor_vendas)}
                </td>
                <td className="px-4 py-3 tabular-nums">
                  <InformedOrDash
                    value={p.investimento}
                    formatted={formatMoneyOrNaoInformado(p.investimento)}
                  />
                </td>
                <td className="px-4 py-3 tabular-nums">
                  <InformedOrDash value={p.cpl} formatted={formatMoneyOrNaoInformado(p.cpl)} />
                </td>
                <td className="px-4 py-3 tabular-nums">
                  <InformedOrDash
                    value={p.roi}
                    formatted={formatMultipleOrNaoInformado(p.roi)}
                  />
                </td>
                <td className="px-4 py-3 tabular-nums">
                  <InformedOrDash
                    value={p.taxa_conversao}
                    formatted={formatPercentOrNaoInformado(p.taxa_conversao)}
                  />
                </td>
                <td className="px-4 py-3 text-right">
                  {semInvestimento ? (
                    <Button
                      size="sm"
                      onClick={() => onManage(p.origem_id, p.label)}
                      data-testid="registrar-investimento-btn"
                    >
                      Registrar investimento
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => onManage(p.origem_id, p.label)}
                      data-testid="ver-lancamentos-btn"
                    >
                      Ver lançamentos
                    </Button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
