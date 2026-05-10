import { useState, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Calendar as CalendarIcon,
  ChevronLeft,
  ChevronRight,
  Video,
  X,
  Clock,
  Repeat,
} from 'lucide-react';
import { Button } from '@noctusai/seed/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@noctusai/seed/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@noctusai/seed/components/ui/dialog';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { cn } from '@/lib/utils';
import { WeekView } from '@/components/calendar/WeekView';
import { MonthView } from '@/components/calendar/MonthView';
import { AgendaView } from '@/components/calendar/AgendaView';
import { RecurringBadge } from '@/components/calendar/RecurringBadge';
import { useAppointments, useCancelAppointment } from '@/hooks/useAppointments';
import { APPOINTMENT_STATUS_CONFIG, type Appointment } from '@/types/scheduling';

type ViewMode = 'week' | 'month' | 'agenda';

function getWeekRange(date: Date): { start: string; end: string } {
  const d = new Date(date);
  const day = d.getDay();
  const monday = new Date(d);
  monday.setDate(d.getDate() - ((day + 6) % 7));
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  return {
    start: monday.toISOString().split('T')[0],
    end: sunday.toISOString().split('T')[0],
  };
}

function getMonthRange(date: Date): { start: string; end: string } {
  const start = new Date(date.getFullYear(), date.getMonth(), 1);
  const end = new Date(date.getFullYear(), date.getMonth() + 1, 0);
  return {
    start: start.toISOString().split('T')[0],
    end: end.toISOString().split('T')[0],
  };
}

export default function PatientCalendar() {
  const navigate = useNavigate();
  const [view, setView] = useState<ViewMode>('week');
  const [currentDate, setCurrentDate] = useState(new Date());
  const [selectedAppointment, setSelectedAppointment] = useState<Appointment | null>(null);

  const cancelAppointment = useCancelAppointment();

  const dateRange = useMemo(
    () => (view === 'month' ? getMonthRange(currentDate) : getWeekRange(currentDate)),
    [view, currentDate]
  );

  const { data: appointmentsData } = useAppointments({
    date_start: dateRange.start,
    date_end: dateRange.end,
    page_size: 200,
  });

  const appointments = useMemo(() => appointmentsData?.data ?? [], [appointmentsData]);

  function navigateDate(direction: -1 | 0 | 1) {
    if (direction === 0) {
      setCurrentDate(new Date());
      return;
    }
    setCurrentDate((prev) => {
      const d = new Date(prev);
      if (view === 'month') {
        d.setMonth(d.getMonth() + direction);
      } else {
        d.setDate(d.getDate() + direction * 7);
      }
      return d;
    });
  }

  const handleDayClick = useCallback(
    (day: Date) => {
      setCurrentDate(day);
      setView('week');
    },
    []
  );

  function handleCancel(id: string) {
    cancelAppointment.mutate({ id }, { onSuccess: () => setSelectedAppointment(null) });
  }

  function handleJoinSession(link: string) {
    window.open(link, '_blank', 'noopener');
  }

  // Date label
  const dateLabel = useMemo(() => {
    if (view === 'month') {
      return currentDate.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });
    }
    const d = new Date(currentDate);
    const day = d.getDay();
    const monday = new Date(d);
    monday.setDate(d.getDate() - ((day + 6) % 7));
    const sunday = new Date(monday);
    sunday.setDate(monday.getDate() + 6);
    const mStr = monday.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' });
    const sStr = sunday.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' });
    return `${mStr} - ${sStr}`;
  }, [view, currentDate]);

  return (
    <div className="container mx-auto p-4 sm:p-6 space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <CalendarIcon className="h-6 w-6" />
            Minha Agenda
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Visualize e gerencie suas sessoes
          </p>
        </div>
        <Button variant="outline" onClick={() => navigate('/patient/recorrentes')}>
          <Repeat className="h-4 w-4 mr-1" />
          Agendamentos Recorrentes
        </Button>
      </div>

      {/* Navigation */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b pb-3">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => navigateDate(-1)}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="sm" onClick={() => navigateDate(0)}>
            Hoje
          </Button>
          <Button variant="outline" size="sm" onClick={() => navigateDate(1)}>
            <ChevronRight className="h-4 w-4" />
          </Button>
          <span className="text-sm font-medium ml-2 capitalize">{dateLabel}</span>
        </div>

        <Tabs value={view} onValueChange={(v) => setView(v as ViewMode)}>
          <TabsList>
            <TabsTrigger value="week">Semana</TabsTrigger>
            <TabsTrigger value="month">Mes</TabsTrigger>
            <TabsTrigger value="agenda">Lista</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* Calendar views */}
      {view === 'week' && (
        <WeekView
          appointments={appointments}
          currentDate={currentDate}
          onDateChange={setCurrentDate}
          onAppointmentClick={setSelectedAppointment}
          participantField="therapist_name"
        />
      )}

      {view === 'month' && (
        <MonthView
          appointments={appointments}
          currentDate={currentDate}
          onDayClick={handleDayClick}
        />
      )}

      {view === 'agenda' && (
        <AgendaView
          appointments={appointments}
          viewerRole="paciente"
          onCancel={handleCancel}
          onViewDetail={setSelectedAppointment}
          onJoinSession={handleJoinSession}
        />
      )}

      {/* Appointment detail dialog */}
      <Dialog open={!!selectedAppointment} onOpenChange={(open) => !open && setSelectedAppointment(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Detalhes da Sessao</DialogTitle>
          </DialogHeader>
          {selectedAppointment && (
            <PatientAppointmentDetail
              appointment={selectedAppointment}
              onCancel={handleCancel}
              onJoinSession={handleJoinSession}
              isCancelling={cancelAppointment.isPending}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ── Patient appointment detail ─────────────────────────────────

function PatientAppointmentDetail({
  appointment,
  onCancel,
  onJoinSession,
  isCancelling,
}: {
  appointment: Appointment;
  onCancel: (id: string) => void;
  onJoinSession: (link: string) => void;
  isCancelling: boolean;
}) {
  const start = new Date(appointment.scheduled_start);
  const end = new Date(appointment.scheduled_end);
  const statusConfig = APPOINTMENT_STATUS_CONFIG[appointment.status];
  const isCancellable = ['waiting', 'payment_pending'].includes(appointment.status);
  const isJoinable = ['waiting', 'in_progress'].includes(appointment.status) && !!appointment.meeting_link;
  const hoursUntil = (start.getTime() - Date.now()) / 3600000;
  const isLateCancellation = hoursUntil < 24 && hoursUntil > 0;

  return (
    <div className="space-y-4">
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Terapeuta</span>
          <span className="font-medium">{appointment.therapist_name ?? 'Terapeuta'}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Data</span>
          <span className="font-medium">
            {start.toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long' })}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Horario</span>
          <span className="font-medium flex items-center gap-1">
            <Clock className="h-3.5 w-3.5" />
            {start.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })} -{' '}
            {end.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Status</span>
          <Badge variant="secondary" className={cn(statusConfig.color)}>
            {statusConfig.label}
          </Badge>
        </div>
        {appointment.session_price_applied != null && (
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Valor</span>
            <span className="font-medium">R$ {appointment.session_price_applied.toFixed(2)}</span>
          </div>
        )}
        {appointment.recurring_schedule_id && (
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Tipo</span>
            <RecurringBadge />
          </div>
        )}
      </div>

      <div className="flex gap-2 pt-2">
        {isJoinable && (
          <Button className="flex-1" onClick={() => onJoinSession(appointment.meeting_link!)}>
            <Video className="h-4 w-4 mr-1" />
            Entrar na sessao
          </Button>
        )}
        {isCancellable && (
          <Button
            variant="destructive"
            className="flex-1"
            onClick={() => onCancel(appointment.id)}
            disabled={isCancelling}
          >
            <X className="h-4 w-4 mr-1" />
            {isCancelling ? 'Cancelando...' : 'Cancelar'}
          </Button>
        )}
      </div>

      {isCancellable && isLateCancellation && (
        <p className="text-xs text-red-600">
          Atencao: cancelamento com menos de 24h de antecedencia. O valor da sessao podera ser cobrado integralmente.
        </p>
      )}
    </div>
  );
}
