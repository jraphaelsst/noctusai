import { Card, CardContent, CardHeader, CardTitle } from "@noctusai/seed/components/ui/card";
import { Users, Building2, CalendarDays, DollarSign } from "lucide-react";
import { useAdminDashboard } from "@/hooks/useAdmin";

interface AdminDashboardMetrics {
  pending_therapists?: number;
  pending_clinics?: number;
  sessions_today?: number;
  total_revenue?: number;
  platform_fees?: number;
}

const currencyBRL = (value: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);

export default function AdminDashboard() {
  const { data, isPending } = useAdminDashboard();
  const metrics = (data ?? {}) as AdminDashboardMetrics;
  const showSkeleton = isPending && !data;

  const cards = [
    {
      label: "Terapeutas Pendentes",
      value: showSkeleton ? "…" : String(metrics.pending_therapists ?? 0),
      icon: Users,
      color: "text-orange-500",
    },
    {
      label: "Clinicas Pendentes",
      value: showSkeleton ? "…" : String(metrics.pending_clinics ?? 0),
      icon: Building2,
      color: "text-blue-500",
    },
    {
      label: "Sessoes Hoje",
      value: showSkeleton ? "…" : String(metrics.sessions_today ?? 0),
      icon: CalendarDays,
      color: "text-green-500",
    },
    {
      label: "Receita Total",
      value: showSkeleton ? "…" : currencyBRL(metrics.total_revenue ?? 0),
      icon: DollarSign,
      color: "text-primary",
    },
  ];

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Painel Administrativo</h1>
        <p className="text-muted-foreground">Visao geral da plataforma</p>
      </div>

      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((m) => (
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
