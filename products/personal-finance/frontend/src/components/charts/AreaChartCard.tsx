import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { formatCurrency } from "@/lib/utils";

interface Props {
  title: string;
  data: any[];
  dataKey: string;
  xKey?: string;
  color?: string;
  height?: number;
}

export function AreaChartCard({ title, data, dataKey, xKey = "label", color = "#10b981", height = 300 }: Props) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <h3 className="font-semibold mb-4">{title}</h3>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
          <XAxis dataKey={xKey} tick={{ fontSize: 12 }} stroke="hsl(var(--muted-foreground))" />
          <YAxis tick={{ fontSize: 12 }} stroke="hsl(var(--muted-foreground))" tickFormatter={(v) => formatCurrency(v)} />
          <Tooltip formatter={(value: number) => formatCurrency(value)} contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }} />
          <Area type="monotone" dataKey={dataKey} stroke={color} fill={color} fillOpacity={0.15} strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
