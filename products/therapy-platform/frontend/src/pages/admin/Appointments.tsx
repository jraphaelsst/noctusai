import { useState, useMemo } from 'react';
import { CalendarDays, Search } from 'lucide-react';
import { Card, CardContent } from '@noctusai/seed/components/ui/card';
import { Input } from '@noctusai/seed/components/ui/input';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Tabs, TabsList, TabsTrigger } from '@noctusai/seed/components/ui/tabs';
import { useAdminAppointments } from '@/hooks/useAdmin';

type StatusFilter = 'todos' | 'waiting' | 'in_progress' | 'completed' | 'cancelled' | 'no_show';

const STATUS_BADGE: Record<string, { label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive'; className?: string }> = {
  waiting: { label: 'Aguardando', variant: 'outline', className: 'border-blue-500 text-blue-600' },
  confirmed: { label: 'Confirmado', variant: 'outline', className: 'border-blue-500 text-blue-600' },
  in_progress: { label: 'Em andamento', variant: 'default' },
  completed: { label: 'Concluido', variant: 'secondary' },
  cancelled: { label: 'Cancelado', variant: 'destructive' },
  no_show: { label: 'Falta', variant: 'destructive', className: 'bg-red-900' },
  agendada: { label: 'Agendada', variant: 'outline', className: 'border-blue-500 text-blue-600' },
  confirmada: { label: 'Confirmada', variant: 'outline', className: 'border-blue-500 text-blue-600' },
  em_andamento: { label: 'Em andamento', variant: 'default' },
  concluida: { label: 'Concluida', variant: 'secondary' },
  cancelada: { label: 'Cancelada', variant: 'destructive' },
  falta: { label: 'Falta', variant: 'destructive', className: 'bg-red-900' },
};

interface AdminAppointment {
  id: string;
  patient_name?: string;
  therapist_name?: string;
  clinic_name?: string;
  scheduled_start: string;
  scheduled_end?: string;
  status: string;
}

export default function AdminAppointments() {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('todos');
  const [busca, setBusca] = useState('');
  const [dateStart, setDateStart] = useState('');
  const [dateEnd, setDateEnd] = useState('');

  const filters: Record<string, string> = {};
  if (statusFilter !== 'todos') filters.status = statusFilter;
  if (dateStart) filters.date_start = dateStart;
  if (dateEnd) filters.date_end = dateEnd;

  const { data, isPending } = useAdminAppointments(
    Object.keys(filters).length > 0 ? filters : undefined
  );

  const showSkeleton = isPending && !data;
  const appointments = (data?.data ?? []) as AdminAppointment[];

  const filtered = useMemo(() => {
    if (!busca.trim()) return appointments;
    const q = busca.toLowerCase();
    return appointments.filter(a =>
      (a.patient_name?.toLowerCase().includes(q)) ||
      (a.therapist_name?.toLowerCase().includes(q)) ||
      (a.clinic_name?.toLowerCase().includes(q))
    );
  }, [appointments, busca]);

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Agendamentos</h1>
        <p className="text-muted-foreground">Visao geral de todos os agendamentos da plataforma</p>
      </div>

      <div className="flex flex-col gap-4">
        <div className="flex flex-col sm:flex-row gap-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              value={busca}
              onChange={e => setBusca(e.target.value)}
              placeholder="Buscar por paciente, terapeuta ou clinica..."
              className="pl-9"
            />
          </div>
          <div className="flex gap-2">
            <Input
              type="date"
              value={dateStart}
              onChange={e => setDateStart(e.target.value)}
              className="w-40"
            />
            <Input
              type="date"
              value={dateEnd}
              onChange={e => setDateEnd(e.target.value)}
              className="w-40"
            />
          </div>
        </div>

        <Tabs value={statusFilter} onValueChange={v => setStatusFilter(v as StatusFilter)}>
          <TabsList className="flex-wrap h-auto">
            <TabsTrigger value="todos">Todos</TabsTrigger>
            <TabsTrigger value="waiting">Aguardando</TabsTrigger>
            <TabsTrigger value="in_progress">Em andamento</TabsTrigger>
            <TabsTrigger value="completed">Concluidos</TabsTrigger>
            <TabsTrigger value="cancelled">Cancelados</TabsTrigger>
            <TabsTrigger value="no_show">Faltas</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {showSkeleton ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Card key={i} className="animate-pulse">
              <CardContent className="p-4 h-16" />
            </Card>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center">
            <CalendarDays className="h-12 w-12 text-muted-foreground/30 mx-auto mb-4" />
            <p className="text-lg font-medium text-muted-foreground">Nenhum agendamento encontrado</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {/* Table header */}
          <div className="hidden md:grid grid-cols-[1fr_1fr_1fr_auto_auto] gap-4 px-4 py-2 text-sm font-medium text-muted-foreground">
            <span>Paciente</span>
            <span>Terapeuta</span>
            <span>Data/Hora</span>
            <span>Clinica</span>
            <span>Status</span>
          </div>

          {filtered.map(a => {
            const badge = STATUS_BADGE[a.status] ?? { label: a.status, variant: 'outline' as const };
            return (
              <Card key={a.id} className="hover:shadow-sm transition-shadow">
                <CardContent className="p-4">
                  <div className="grid grid-cols-1 md:grid-cols-[1fr_1fr_1fr_auto_auto] gap-3 items-center">
                    <div>
                      <p className="font-medium text-sm">{a.patient_name ?? '-'}</p>
                      <p className="text-xs text-muted-foreground md:hidden">
                        {a.therapist_name ?? '-'}
                      </p>
                    </div>
                    <p className="text-sm hidden md:block">{a.therapist_name ?? '-'}</p>
                    <div className="text-sm">
                      {new Date(a.scheduled_start).toLocaleString('pt-BR', {
                        day: '2-digit',
                        month: '2-digit',
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </div>
                    <p className="text-sm">{a.clinic_name ?? '-'}</p>
                    <Badge variant={badge.variant} className={badge.className}>
                      {badge.label}
                    </Badge>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
