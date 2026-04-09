import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Users, CalendarDays, DollarSign, MessageSquare } from "lucide-react";

const metrics = [
  { label: "Pacientes Ativos", value: "0", icon: Users, color: "text-blue-500" },
  { label: "Proxima Sessao", value: "Nenhuma", icon: CalendarDays, color: "text-green-500" },
  { label: "Receita do Mes", value: "R$ 0,00", icon: DollarSign, color: "text-primary" },
  { label: "Mensagens", value: "0", icon: MessageSquare, color: "text-orange-500" },
];

export default function TherapistDashboard() {
  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Meu Consultorio</h1>
        <p className="text-muted-foreground">Visao geral do seu consultorio</p>
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
          <CardTitle className="text-lg">Agenda de Hoje</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">Nenhuma sessao agendada para hoje.</p>
        </CardContent>
      </Card>
    </div>
  );
}
