/**
 * Heatmap — ano×mês grid (the Leads "heatmap ano×mês" view — see
 * leads-module-PROJECT.md §6/§5.3 `HeatmapOut`). Plain HTML/CSS grid, not
 * recharts (recharts has no first-class calendar/matrix heatmap primitive;
 * a table-shaped grid is both simpler and more accessible here — every cell
 * is a real DOM node with a title/tooltip, not an SVG path).
 *
 * `null` cell ≠ `0` cell: null renders BLANK (no data collected for that
 * month at all), zero renders as the lowest filled step (data collected,
 * value is genuinely zero) — collapsing the two would silently misrepresent
 * "no data" as "confirmed zero leads," which the source spreadsheet cannot
 * support for months outside its 28-month history.
 *
 *   <Heatmap anos={out.anos} cells={out.cells} max={out.max} />
 */
import { cn } from "../../utils";
import { useChartTheme } from "./useChartTheme";
import { heatmapStep } from "./palette";
import { formatCompactNumber, PT_BR_MONTH_LABELS_SHORT } from "./formatters";
import type { HeatmapProps } from "./types";

const STEPS = 5;

export function Heatmap({
  anos,
  cells,
  max,
  monthLabels = [...PT_BR_MONTH_LABELS_SHORT],
  valueFormatter = formatCompactNumber,
  onCellClick,
  className,
}: HeatmapProps) {
  const theme = useChartTheme();
  const scale = theme.sequentialScale(STEPS);

  return (
    <div className={cn("w-full overflow-x-auto", className)}>
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr>
            <th className="w-12 pb-2 pr-2 text-left font-medium text-muted-foreground">Ano</th>
            {monthLabels.map((m) => (
              <th key={m} className="px-1 pb-2 text-center font-medium text-muted-foreground">
                {m}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {anos.map((ano) => {
            const row = cells[String(ano)] ?? [];
            return (
              <tr key={ano}>
                <th className="pr-2 text-left font-medium text-muted-foreground">{ano}</th>
                {monthLabels.map((_, mesIdx) => {
                  const value = row[mesIdx] ?? null;
                  const isNull = value === null || value === undefined;
                  const step = isNull ? null : heatmapStep(value, max, STEPS);
                  const bg = isNull ? undefined : scale[step ?? 0];
                  return (
                    <td key={mesIdx} className="p-0.5">
                      <button
                        type="button"
                        disabled={!onCellClick}
                        onClick={() => onCellClick?.(ano, mesIdx + 1, value)}
                        title={
                          isNull
                            ? "Sem dados"
                            : `${monthLabels[mesIdx]}/${ano}: ${valueFormatter(value as number)}`
                        }
                        className={cn(
                          "flex h-6 w-full min-w-[1.75rem] items-center justify-center rounded-sm text-[10px] font-medium",
                          isNull ? "bg-muted/40 text-transparent" : "text-foreground",
                          onCellClick && !isNull && "cursor-pointer hover:opacity-80",
                          !onCellClick && "cursor-default",
                        )}
                        style={bg ? { backgroundColor: bg } : undefined}
                      >
                        {isNull ? "" : (step ?? 0) >= Math.floor(STEPS / 2) ? valueFormatter(value as number) : ""}
                      </button>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
