import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { formatCurrency } from "@/lib/utils";

interface Props {
  title: string;
  data: any[];
  bars: { dataKey: string; color: string; name: string }[];
  xKey?: string;
  height?: number;
}

export function BarChartCard({ title, data, bars, xKey = "label", height = 300 }: Props) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <h3 className="font-semibold mb-4">{title}</h3>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
          <XAxis dataKey={xKey} tick={{ fontSize: 12 }} stroke="hsl(var(--muted-foreground))" />
          <YAxis tick={{ fontSize: 12 }} stroke="hsl(var(--muted-foreground))" tickFormatter={(v) => formatCurrency(v)} />
          <Tooltip formatter={(value: number) => formatCurrency(value)} contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }} />
          <Legend />
          {bars.map((bar) => (
            <Bar key={bar.dataKey} dataKey={bar.dataKey} fill={bar.color} name={bar.name} radius={[4, 4, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
