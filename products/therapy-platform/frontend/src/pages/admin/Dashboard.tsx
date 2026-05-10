import { Card, CardContent, CardHeader, CardTitle } from "@noctusai/seed/components/ui/card";
import { Users, Building2, CalendarDays, DollarSign } from "lucide-react";

const metrics = [
  { label: "Terapeutas Pendentes", value: "0", icon: Users, color: "text-orange-500" },
  { label: "Clinicas Pendentes", value: "0", icon: Building2, color: "text-blue-500" },
  { label: "Sessoes Hoje", value: "0", icon: CalendarDays, color: "text-green-500" },
  { label: "Receita Total", value: "R$ 0,00", icon: DollarSign, color: "text-primary" },
];

export default function AdminDashboard() {
  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Painel Administrativo</h1>
        <p className="text-muted-foreground">Visao geral da plataforma</p>
      </div>

      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        {metrics.map((m) => (
          <Card key={m.label}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">{m.label}</CardTitle>
              <m.icon className={`h-5 w-5 ${m.color}`} />
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{m.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Atividade Recente</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">Nenhuma atividade registrada ainda.</p>
        </CardContent>
      </Card>
    </div>
  );
}
