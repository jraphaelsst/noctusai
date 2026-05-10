import { Card, CardContent, CardHeader, CardTitle } from "@noctusai/seed/components/ui/card";
import { Users, UserCircle, CalendarDays, DollarSign } from "lucide-react";

const metrics = [
  { label: "Terapeutas Ativos", value: "0", icon: Users, color: "text-blue-500" },
  { label: "Pacientes", value: "0", icon: UserCircle, color: "text-green-500" },
  { label: "Sessoes Agendadas", value: "0", icon: CalendarDays, color: "text-orange-500" },
  { label: "Receita do Mes", value: "R$ 0,00", icon: DollarSign, color: "text-primary" },
];

export default function ClinicDashboard() {
  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Dashboard da Clinica</h1>
        <p className="text-muted-foreground">Visao geral da sua clinica</p>
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
          <CardTitle className="text-lg">Proximas Sessoes</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">Nenhuma sessao agendada.</p>
        </CardContent>
      </Card>
    </div>
  );
}
