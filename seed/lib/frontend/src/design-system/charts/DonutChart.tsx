/**
 * DonutChart — thin, typed recharts wrapper over `PieChart`/`Pie`. Unlike
 * Line/Area/Bar, a donut plots ROWS as slices (one value per row) rather
 * than columns-as-series — see `types.ts` for why it deliberately does NOT
 * share the `xKey`/`series` shape.
 *
 *   <DonutChart data={buckets} nameKey="label" valueKey="total" colorKey="cor" />
 */
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { cn } from "../../utils";
import { useChartTheme } from "./useChartTheme";
import { DEFAULT_VALUE_FORMATTER } from "./_cartesian-shared";
import type { ChartDatum, DonutChartProps as DonutChartComponentProps } from "./types";

export function DonutChart<T extends ChartDatum = ChartDatum>({
  data,
  nameKey,
  valueKey,
  colorKey,
  height = 280,
  valueFormatter = DEFAULT_VALUE_FORMATTER,
  innerRadiusRatio = 0.6,
  className,
}: DonutChartComponentProps<T>) {
  const theme = useChartTheme();
  const outerRadius = 100;
  const innerRadius = Math.max(0, Math.min(0.95, innerRadiusRatio)) * outerRadius;

  return (
    <div className={cn("w-full", className)} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey={valueKey}
            nameKey={nameKey}
            cx="50%"
            cy="50%"
            innerRadius={innerRadius}
            outerRadius={outerRadius}
            paddingAngle={2}
          >
            {data.map((row, i) => {
              const override = colorKey ? (row[colorKey] as string | undefined) : undefined;
              return <Cell key={`${String(row[nameKey])}-${i}`} fill={theme.getSeriesColor(i, override)} />;
            })}
          </Pie>
          <Tooltip
            formatter={(value: number, name: string) => [valueFormatter(value), name]}
            contentStyle={{
              background: theme.tooltipBackground,
              border: `1px solid ${theme.tooltipBorder}`,
              borderRadius: 6,
              fontSize: 12,
            }}
            labelStyle={{ color: theme.tooltipForeground }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
