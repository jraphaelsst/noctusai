import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { formatCurrency } from "@/lib/utils";
import { CHART_COLORS } from "@/lib/constants";

interface DataItem {
  nome: string;
  total: number;
  cor?: string;
}

interface Props {
  title: string;
  data: DataItem[];
  height?: number;
}

export function DonutChartCard({ title, data, height = 300 }: Props) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <h3 className="font-semibold mb-4">{title}</h3>
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie data={data} cx="50%" cy="50%" innerRadius={60} outerRadius={100} dataKey="total" nameKey="nome" paddingAngle={2}>
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.cor || CHART_COLORS[index % CHART_COLORS.length]} />
            ))}
          </Pie>
          <Tooltip formatter={(value: number) => formatCurrency(value)} contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }} />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
