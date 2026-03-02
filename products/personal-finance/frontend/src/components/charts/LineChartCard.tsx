import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { formatCurrency } from "@/lib/utils";

interface Props {
  title: string;
  data: any[];
  lines: { dataKey: string; color: string; name: string }[];
  xKey?: string;
  height?: number;
  valueFormatter?: (v: number) => string;
}

export function LineChartCard({ title, data, lines, xKey = "label", height = 300, valueFormatter }: Props) {
  const fmt = valueFormatter || formatCurrency;
  return (
    <div className="rounded-lg border bg-card p-4">
      <h3 className="font-semibold mb-4">{title}</h3>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
          <XAxis dataKey={xKey} tick={{ fontSize: 12 }} stroke="hsl(var(--muted-foreground))" />
          <YAxis tick={{ fontSize: 12 }} stroke="hsl(var(--muted-foreground))" tickFormatter={fmt} />
          <Tooltip formatter={(value: number) => fmt(value)} contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }} />
          <Legend />
          {lines.map((line) => (
            <Line key={line.dataKey} type="monotone" dataKey={line.dataKey} stroke={line.color} name={line.name} strokeWidth={2} dot={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
